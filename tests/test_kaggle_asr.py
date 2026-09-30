from types import SimpleNamespace
from pathlib import Path

import pytest

from remote_eval.asr_eval.run_asr_eval import (
    normalize_words, speech_end, strict_coverage, result_coverage, relative_call_times,
    prepare_workspace, locate_results_source, checkout_pinned,
)


def test_word_timestamps_match_upstream_result_contract():
    result = SimpleNamespace(timestamp={"word": [
        {"word": " Hello", "start": 0.1, "end": 0.4},
        {"word": " world", "start": 0.5, "end": 0.8},
    ]})
    text, chunks = normalize_words(result)
    assert text == "Hello world"
    assert chunks == [{"text": "Hello", "timestamp": [0.1, 0.4]},
                      {"text": "world", "timestamp": [0.5, 0.8]}]


def test_user_speech_end_uses_first_long_pause():
    words = [{"timestamp": [0, 0.3]}, {"timestamp": [0.4, 0.8]}, {"timestamp": [3.1, 3.5]}]
    assert speech_end(words) == 0.8
    assert speech_end(words[:2]) == 0.8
    assert speech_end([]) == 0


def test_partial_coverage_is_explicit():
    assert strict_coverage(expected=100, results=11) == {
        "expected": 100, "results": 11, "missing": 89,
        "full_coverage": False, "official_score": False,
    }


def test_result_coverage_does_not_treat_no_tool_or_missing_output_as_pass():
    results = [
        {"status": "completed", "actual_tool_calls": [{"function": "x"}]},
        {"status": "no_tool_call", "actual_tool_calls": []},
        {"status": "inference_failed", "actual_tool_calls": []},
    ]
    assert result_coverage(5, results) == {
        "expected_recordings": 5, "captured_results": 3, "remaining": 2,
        "completed": 1, "no_tool_call": 1, "inference_failed": 1,
        "full_coverage": False, "official_score": False,
    }


def test_call_times_are_made_relative_for_upstream_latency_evaluator():
    calls = [{"function": "search_flights", "args": {},
              "timestamp_start": 120.5, "timestamp_end": 121.0}]
    assert relative_call_times(calls, 100.0)[0]["timestamp_start"] == 20.5
    assert calls[0]["timestamp_start"] == 120.5


def test_workspace_parent_is_created_before_git_clone(tmp_path):
    work = tmp_path / "new" / "work"
    assert prepare_workspace(work) == work
    assert work.is_dir()


def test_locate_results_accepts_kaggle_auto_extracted_zip_or_archive(tmp_path):
    root = tmp_path / "dataset"
    extracted = root / "results"
    extracted.mkdir(parents=True)
    assert locate_results_source(root) == extracted
    extracted.rmdir()
    root.mkdir(exist_ok=True)
    archive = root / "results.zip"
    archive.write_bytes(b"zip")
    assert locate_results_source(root) == archive


def test_locate_results_errors_when_kaggle_dataset_has_no_payload(tmp_path):
    root = tmp_path / "empty-results"
    root.mkdir()
    with pytest.raises(FileNotFoundError, match="results"):
        locate_results_source(root)


def test_existing_non_git_checkout_is_rejected_without_overwrite(tmp_path):
    repo = tmp_path / "REACTOR"
    repo.mkdir()
    marker = repo / "user-output.txt"
    marker.write_text("keep")
    with pytest.raises(RuntimeError, match="not a pinned Git checkout"):
        checkout_pinned("https://example.invalid/repo.git", repo, "abcdef0")
    assert marker.read_text() == "keep"
