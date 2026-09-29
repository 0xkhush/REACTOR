import json
from pathlib import Path

import pytest

from scripts.smoke_fdb import check_dataset, matching_calls, count_completed


def test_dataset_check_uses_audio_paths_not_answer_metadata(tmp_path):
    folder = tmp_path / "travel_01_speaker"
    folder.mkdir()
    (folder / "input.wav").write_bytes(b"RIFF")
    (folder / "metadata.json").write_text("this is not parsed")
    assert check_dataset(tmp_path) == [folder / "input.wav"]


def test_empty_dataset_is_a_failure(tmp_path):
    with pytest.raises(ValueError, match="no input.wav"):
        check_dataset(tmp_path)


def test_only_requested_room_tool_calls_are_counted(tmp_path):
    log = tmp_path / "tools.jsonl"
    log.write_text("\n".join(json.dumps({"room": room, "call": {"function": name}})
                             for room, name in [("a", "search_flights"), ("b", "book_flight"),
                                                ("a", "book_flight")]))
    assert matching_calls(log, "a") == ["search_flights", "book_flight"]


def test_full_coverage_does_not_count_failed_result_as_completed(tmp_path):
    for index, status in enumerate(["completed", "inference_failed"]):
        folder = tmp_path / f"sample_{index}"
        folder.mkdir()
        (folder / "result_gemini2_5.json").write_text(json.dumps({"status": status}))
    assert count_completed(tmp_path, "gemini2_5") == (1, 1)
