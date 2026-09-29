import pytest

from remote_eval.overnight.run_overnight import count_recordings, scrub, report_counts, read_secrets


def test_overnight_count_requires_real_audio_and_ignores_answer_metadata(tmp_path):
    folder = tmp_path / "ecommerce_01_65e8cf8f4c7424fa062e54a3"
    folder.mkdir()
    (folder / "input.wav").write_bytes(b"RIFF")
    (folder / "metadata.json").write_text('{"expected_tool_calls":"not read"}')
    assert count_recordings(tmp_path) == 1
    with pytest.raises(ValueError, match="input.wav"):
        count_recordings(tmp_path / "empty")


def test_overnight_report_marks_partial_coverage_and_local_scoring():
    report = report_counts(expected=100, completed=64, failed=4)
    assert report == {"expected": 100, "completed": 64, "failed": 4,
                      "missing": 32, "full_coverage": False,
                      "official_score": False, "judge": "none"}


def test_kaggle_worker_logs_redact_all_credentials():
    assert scrub("key1 secret2 google3", ("key1", "secret2", "google3")) == (
        "[redacted] [redacted] [redacted]"
    )


def test_missing_kaggle_secret_grant_gives_actionable_failure_without_values():
    class Unavailable:
        def get_secret(self, label):
            raise ConnectionError("private backend details")

    with pytest.raises(RuntimeError, match="Kaggle Secrets") as error:
        read_secrets(Unavailable())
    assert "private backend details" not in str(error.value)
