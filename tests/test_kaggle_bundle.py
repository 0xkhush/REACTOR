import json
from pathlib import Path

import pytest

from scripts.package_kaggle_dataset import package_audio_dataset


def test_package_contains_only_audio_and_non_answer_manifest(tmp_path):
    source = tmp_path / "source"
    example = source / "travel_01_65e8cf8f4c7424fa062e54a3"
    example.mkdir(parents=True)
    (example / "input.wav").write_bytes(b"RIFF-audio")
    (example / "metadata.json").write_text('{"expected_tool_calls":[{"secret":"answer"}]}')
    destination = tmp_path / "bundle"

    manifest = package_audio_dataset(source, destination, dataset_id="zxkhush/reactor-fdb-v3-audio")

    assert (destination / example.name / "input.wav").read_bytes() == b"RIFF-audio"
    assert not (destination / example.name / "metadata.json").exists()
    assert not list(destination.rglob("*.json")) or set(p.name for p in destination.rglob("*.json")) == {"dataset-metadata.json", "manifest.json"}
    assert manifest[0]["example_id"] == "travel_01"
    metadata = json.loads((destination / "dataset-metadata.json").read_text())
    assert metadata["id"] == "zxkhush/reactor-fdb-v3-audio"
    assert metadata["licenses"] == [{"name": "CC-BY-NC-4.0"}]
    assert "NonCommercial" in metadata["description"]


def test_package_rejects_missing_input_audio_and_keeps_destination_empty(tmp_path):
    source = tmp_path / "source"
    (source / "ecommerce_01_x").mkdir(parents=True)
    destination = tmp_path / "bundle"
    with pytest.raises(ValueError, match="input.wav"):
        package_audio_dataset(source, destination, dataset_id="zxkhush/reactor-fdb-v3-audio")
    assert not destination.exists()


def test_package_refuses_destination_inside_source(tmp_path):
    source = tmp_path / "source"
    (source / "example").mkdir(parents=True)
    (source / "example" / "input.wav").write_bytes(b"RIFF")
    with pytest.raises(ValueError, match="outside"):
        package_audio_dataset(source, source / "bundle", dataset_id="zxkhush/reactor-fdb-v3-audio")
