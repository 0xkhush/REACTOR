"""Create a private Kaggle-ready bundle containing FDB input audio only."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


FOLDER = re.compile(r"^(.+)_([0-9a-f]{24})$")
SOURCE_URL = "https://github.com/DanielLin94144/Full-Duplex-Bench/tree/main/v3"


def package_audio_dataset(source: Path, destination: Path, *, dataset_id: str) -> list[dict]:
    source = source.resolve()
    destination = destination.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("destination must be outside the source data directory")
    if not source.is_dir():
        raise FileNotFoundError(f"FDB audio directory not found: {source}")
    recordings = sorted(source.glob("*/input.wav"))
    if not recordings:
        raise ValueError(f"No input.wav files found under {source}")
    for file in recordings:
        if not FOLDER.fullmatch(file.parent.name):
            raise ValueError(f"Unrecognized FDB example folder: {file.parent.name}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Kaggle bundle destination must be empty; refusing to overwrite files")
    destination.mkdir(parents=True, exist_ok=True)

    manifest = []
    for audio in recordings:
        folder_name = audio.parent.name
        example_id, speaker_id = FOLDER.fullmatch(folder_name).groups()
        target_dir = destination / folder_name
        target_dir.mkdir()
        target = target_dir / "input.wav"
        shutil.copy2(audio, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest.append({
            "example_id": example_id,
            "speaker_id": speaker_id,
            "path": f"{folder_name}/input.wav",
            "bytes": target.stat().st_size,
            "sha256": digest,
        })

    (destination / "manifest.json").write_text(json.dumps({
        "source": SOURCE_URL,
        "notice": "Input audio only. Scenario metadata and expected answers are intentionally excluded.",
        "examples": manifest,
    }, indent=2) + "\n")
    description = (
        "Private hackathon evaluation input bundle. FDB-v3 audio developed by National Taiwan University. "
        f"Source and attribution: {SOURCE_URL}. Licensed CC BY-NC 4.0; NonCommercial use only. "
        "This upload contains input WAV files and a file-integrity manifest only; it excludes scenario metadata and expected tool calls."
    )
    metadata = {
        "title": "REACTOR FDB-v3 Audio Inputs",
        "id": dataset_id,
        "subtitle": "Private audio-only evaluation inputs for REACTOR",
        "description": description,
        "licenses": [{"name": "CC-BY-NC-4.0"}],
    }
    (destination / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("fdb_v3_data_released"))
    parser.add_argument("--destination", type=Path, default=Path("artifacts/kaggle-fdb-v3-audio"))
    parser.add_argument("--dataset-id", default="zxkhush/reactor-fdb-v3-audio")
    args = parser.parse_args()
    manifest = package_audio_dataset(args.source, args.destination, dataset_id=args.dataset_id)
    print(json.dumps({"output": str(args.destination), "examples": len(manifest),
                      "contains_answers": False}, indent=2))


if __name__ == "__main__":
    main()
