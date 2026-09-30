import json
from pathlib import Path

from scripts.batch_infer import pending_inputs, report_progress


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


def test_progress_includes_failed_or_unrun_examples_in_denominator():
    progress = report_progress(expected=100, terminal={"a": "completed", "b": "no_tool_call", "c": "inference_failed"})
    assert progress == {
        "expected": 100, "completed": 1, "no_tool_call": 1,
        "inference_failed": 1, "remaining": 97,
        "official_score": False, "mode": "audio_capture_no_asr",
    }
