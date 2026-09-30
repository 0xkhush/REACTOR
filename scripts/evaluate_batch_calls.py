"""Score the captured tool logs over the full attempted denominator, without ASR or judge."""

import argparse
import json
from pathlib import Path

if __package__:
    from .evaluate_smoke import evaluate_calls
    from .smoke_fdb import UPSTREAM, verify_upstream
else:
    from evaluate_smoke import evaluate_calls
    from smoke_fdb import UPSTREAM, verify_upstream


def evaluate_batch_calls(inputs: Path, outputs: Path, *, upstream: Path = UPSTREAM) -> dict:
    source = verify_upstream(upstream)
    recordings = sorted(inputs.glob("*/input.wav"))
    if not recordings:
        raise ValueError(f"No FDB recordings under {inputs}")
    benchmark = json.loads((source / "benchmark_data_v2.json").read_text())
    scenarios = {scenario["id"]: scenario for scenario in benchmark["scenarios"]}
    results = []
    for recording in recordings:
        example_folder = recording.parent.name
        example_id = example_folder.rsplit("_", 1)[0]
        if example_id not in scenarios:
            raise ValueError(f"No scoring scenario for {example_id}")
        result_file = outputs / example_folder / "result.json"
        if not result_file.is_file():
            results.append({"example_id": example_id, "folder": example_folder,
                            "capture_status": "missing_result", "passed": False,
                            "failure_reason": "No captured result file"})
            continue
        captured = json.loads(result_file.read_text())
        calls = captured.get("actual_tool_calls", [])
        scored = evaluate_calls(scenarios[example_id], calls, upstream=upstream)
        results.append({"example_id": example_id, "folder": example_folder,
                        "capture_status": captured.get("status", "unknown"),
                        "num_actual_calls": len(calls), "passed": scored["passed"],
                        "failure_reason": scored["failure_reason"],
                        "tool_selection_passed": scored["checks"]["tool_selection"]["passed"],
                        "exact_arguments_passed": scored["checks"].get("argument_accuracy", {}).get("passed", False)})
    return {
        "benchmark_revision": "3e799c45a045256f47d5f1c9cda90157e2d2ec9e",
        "mode": "captured_calls_exact_match_no_asr_no_judge",
        "official_score": False,
        "expected": len(recordings),
        "captured_results": sum(row["capture_status"] != "missing_result" for row in results),
        "missing_results": sum(row["capture_status"] == "missing_result" for row in results),
        "full_capture_coverage": all(row["capture_status"] != "missing_result" for row in results),
        "tool_selection_passed": sum(row.get("tool_selection_passed", False) for row in results),
        "exact_arguments_passed": sum(row.get("exact_arguments_passed", False) for row in results),
        "strict_tool_passed": sum(row["passed"] for row in results),
        "capture_status_counts": {
            status: sum(row["capture_status"] == status for row in results)
            for status in sorted({row["capture_status"] for row in results})
        },
        "examples": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("fdb_v3_data_released"))
    parser.add_argument("--outputs", type=Path, default=Path("artifacts/batch_inference"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/batch-call-eval-exact.json"))
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    args = parser.parse_args()
    report = evaluate_batch_calls(args.inputs, args.outputs, upstream=args.upstream)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "mode", "expected", "captured_results", "missing_results", "full_capture_coverage",
        "tool_selection_passed", "exact_arguments_passed", "strict_tool_passed",
        "capture_status_counts", "official_score",
    )}, indent=2))


if __name__ == "__main__":
    main()
