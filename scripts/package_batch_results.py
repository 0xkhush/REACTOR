"""Bundle only generated agent audio and sanitized tool-call results for Kaggle ASR."""

import argparse
import io
import json
import re
import zipfile
from pathlib import Path


ALLOWED_FIELDS = ("example_id", "room", "model", "provider", "status",
                  "actual_tool_calls", "stream_start_time", "elapsed_seconds")
EXAMPLE_FOLDER = re.compile(r"^(.+)_([0-9a-f]{24})$")


def package_results(source: Path, destination: Path, *, dataset_id: str) -> dict:
    if not source.is_dir():
        raise FileNotFoundError(f"Batch result folder does not exist: {source}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Result upload destination must be empty")
    cases = sorted(source.glob("*/result.json"))
    if not cases:
        raise ValueError("No per-example result.json files to package")
    for result in cases:
        if not EXAMPLE_FOLDER.fullmatch(result.parent.name):
            raise ValueError("Unexpected result folder: " + result.parent.name)
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(destination / "results.zip", "w", zipfile.ZIP_DEFLATED,
                         compresslevel=3, allowZip64=True) as archive:
        for result in cases:
            original = json.loads(result.read_text())
            safe = {key: original[key] for key in ALLOWED_FIELDS if key in original}
            archive.writestr(result.parent.name + "/result.json", json.dumps(safe, indent=2))
            audio = result.parent / "output.wav"
            if audio.is_file():
                archive.write(audio, arcname=result.parent.name + "/output.wav")
            records.append({"folder": result.parent.name, "status": safe.get("status"),
                            "has_output_audio": audio.is_file()})
    progress_path = source / "batch-manifest.json"
    progress = json.loads(progress_path.read_text()) if progress_path.is_file() else {}
    report = {"expected": progress.get("expected", len(records)),
              "remaining": progress.get("remaining", 0),
              "examples": len(records), "cases": records,
              "official_score": False,
              "note": "Recorded agent audio and actual calls only; no benchmark answers or credentials"}
    (destination / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    (destination / "dataset-metadata.json").write_text(json.dumps({
        "id": dataset_id,
        "title": "REACTOR FDB-v3 Agent Audio Outputs",
        "subtitle": "Private REACTOR recordings and actual-call traces",
        "description": ("Private non-commercial derivative outputs for FDB-v3, developed by National Taiwan "
                        "University. Source: https://github.com/DanielLin94144/Full-Duplex-Bench. "
                        "CC BY-NC 4.0. Contains no expected answers or API keys."),
        "licenses": [{"name": "CC-BY-NC-4.0"}],
    }, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("artifacts/batch_inference"))
    parser.add_argument("--destination", type=Path, default=Path("artifacts/kaggle-batch-results"))
    parser.add_argument("--dataset-id", default="zxkhush/reactor-fdb-v3-results")
    args = parser.parse_args()
    report = package_results(args.source, args.destination, dataset_id=args.dataset_id)
    print(json.dumps({"examples": report["examples"], "remaining": report["remaining"],
                      "output": str(args.destination)}, indent=2))
