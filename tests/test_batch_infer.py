import json
from pathlib import Path

from scripts.batch_infer import pending_inputs, relative_calls, report_progress


def test_pending_inputs_skip_recordings_with_existing_terminal_results(tmp_path):
    source = tmp_path / "audio"
    for name in ("a", "b", "c"):
        folder = source / name
        folder.mkdir(parents=True)
        (folder / "input.wav").write_bytes(b"RIFF")
    output = tmp_path / "outputs"
    (output / "b").mkdir(parents=True)
    (output / "b" / "result.json").write_text('{"status":"no_tool_call"}')
    pending = pending_inputs(source, output)
    assert [path.parent.name for path in pending] == ["a", "c"]


def test_retry_mode_retries_connection_failure_only_when_output_is_absent(tmp_path):
    source, output = tmp_path / "audio", tmp_path / "outputs"
    folders = [source / name for name in ("a", "b", "c")]
    for folder in folders:
        folder.mkdir(parents=True)
        (folder / "input.wav").write_bytes(b"RIFF")
    for name, status in [("a", "completed"), ("b", "inference_failed")]:
        result_dir = output / name
        result_dir.mkdir(parents=True)
        (result_dir / "result.json").write_text(json.dumps({"status": status}))
    (output / "a" / "output.wav").write_bytes(b"audio")
    retry = pending_inputs(source, output, retry_failed=True)
    assert [path.parent.name for path in retry] == ["b", "c"]
    # A partially produced audio artifact means inference may have reached the service;
    # do not silently replay it as a presumed pre-connect failure.
    (output / "b" / "output.wav").write_bytes(b"partial")
    retry = pending_inputs(source, output, retry_failed=True)
    assert [path.parent.name for path in retry] == ["c"]


def test_progress_includes_failed_or_unrun_examples_in_denominator():
    progress = report_progress(expected=100, terminal={"a": "completed", "b": "no_tool_call", "c": "inference_failed"})
    assert progress == {
        "expected": 100, "completed": 1, "no_tool_call": 1,
        "inference_failed": 1, "remaining": 97,
        "official_score": False, "mode": "audio_capture_no_asr",
    }


def test_receiver_failure_after_audio_started_is_not_retried_even_without_wav(tmp_path):
    source, output = tmp_path / "audio", tmp_path / "results"
    (source / "a").mkdir(parents=True)
    (source / "a" / "input.wav").write_bytes(b"RIFF")
    (output / "a").mkdir(parents=True)
    (output / "a" / "result.json").write_text(json.dumps({
        "status": "inference_failed", "stream_start_time": 123.0,
    }))
    assert pending_inputs(source, output, retry_failed=True) == []


def test_batch_call_timestamps_are_relative_to_audio_stream_start():
    actual = [{"function": "track_order", "args": {"order_id": "ABC"},
               "timestamp_start": 110.5, "timestamp_end": 111.0}]
    adjusted = relative_calls(actual, 100.0)
    assert adjusted[0]["timestamp_start"] == 10.5
    assert adjusted[0]["timestamp_end"] == 11.0
    assert actual[0]["timestamp_start"] == 110.5
