from pathlib import Path

import pytest

from remote_eval.gpu_check.gpu_probe import choose_audio_sample


def test_gpu_probe_chooses_smallest_audio_without_reading_answers(tmp_path):
    root = tmp_path / "reactor-fdb-v3-audio"
    large = root / "recordings" / "travel_01_65e8cf8f4c7424fa062e54a3"
    small = root / "recordings" / "finance_01_65e8cf8f4c7424fa062e54a3"
    large.mkdir(parents=True)
    small.mkdir(parents=True)
    (large / "input.wav").write_bytes(b"RIFF" + b"x" * 100)
    (small / "input.wav").write_bytes(b"RIFF")
    (small / "metadata.json").write_text('{"expected_tool_calls":"never read"}')
    assert choose_audio_sample(root) == small / "input.wav"


def test_gpu_probe_reports_missing_dataset(tmp_path):
    with pytest.raises(FileNotFoundError, match="recordings"):
        choose_audio_sample(tmp_path)
