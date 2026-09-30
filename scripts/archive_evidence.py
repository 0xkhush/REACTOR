"""Archive explicit Kaggle evaluation reports for the submitted repository."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


REPORTS = ("run_manifest.json", "strict_pass_exact.json", "tool_accuracy_exact.json")


def archive_evaluation(source: Path, destination: Path) -> dict:
    documents = {name: json.loads((source / name).read_text()) for name in REPORTS}
    manifest = documents["run_manifest.json"]
    strict = documents["strict_pass_exact.json"]
    total = manifest["expected_recordings"]
    if (strict["total_scenarios"] != total or strict["passed"] + strict["failed"] != total
            or documents["tool_accuracy_exact.json"]["total_scenarios"] != total):
        raise ValueError("Evaluation denominator mismatch; do not archive a partial report as a full run")
    if manifest.get("judge") != "none" or manifest.get("official_score", False):
        raise ValueError("This archiver labels only local exact-match, no-judge evidence")
    summary = {
        "mode": "local_FDB_v3_exact_no_semantic_judge", "official_score": False,
        "denominator": total, "strict_passed": strict["passed"], "strict_failed": strict["failed"],
        "strict_pass_rate": strict["passed"] / total if total else 0,
        "capture_completed_with_calls": manifest.get("completed"),
        "capture_without_calls": manifest.get("no_tool_call"),
        "capture_failed": manifest.get("inference_failed"),
        "full_capture_coverage": manifest.get("full_coverage"),
        "judge": "none", "benchmark_revision": manifest.get("benchmark_revision"),
        "asr_model": manifest.get("asr_model"),
        "capture_code_provenance": "Pre-release mixed revisions; no per-recording code SHA was captured.",
        "latest_candidate_full_run": False,
        "latency_status": "Diagnostic timestamps only; official audio-timeline equivalence not verified.",
        "sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in REPORTS},
    }
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination / "FDB_v3_exact_reports.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in REPORTS:
            archive.write(source / name, name)
        captured = source / "captured_results.jsonl"
        if captured.is_file():
            archive.write(captured, "captured_results.jsonl")
    (destination / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("docs/results"))
    arguments = parser.parse_args()
    print(json.dumps(archive_evaluation(arguments.source, arguments.destination), indent=2))
