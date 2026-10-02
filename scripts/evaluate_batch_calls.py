"""Score captured calls with exact or opt-in pinned FDB semantic argument judging."""

import argparse
import json
from pathlib import Path

if __package__:
    from .evaluate_smoke import CallEvaluator, judge_preflight
    from .smoke_fdb import UPSTREAM, verify_upstream
else:
    from evaluate_smoke import CallEvaluator, judge_preflight
    from smoke_fdb import UPSTREAM, verify_upstream


def evaluate_batch_calls(inputs: Path, outputs: Path, *, upstream: Path = UPSTREAM, use_llm=False) -> dict:
    source = verify_upstream(upstream)
    recordings = sorted(inputs.glob("*/input.wav"))
    if not recordings:
        raise ValueError(f"No FDB recordings under {inputs}")
    benchmark = json.loads((source / "benchmark_data_v2.json").read_text())
    scenarios = {scenario["id"]: scenario for scenario in benchmark["scenarios"]}
    with CallEvaluator(upstream=upstream, use_llm=use_llm) as scorer:
        return score_captures(recordings, outputs, scenarios, scorer)


def score_captures(recordings, outputs, scenarios, scorer):
    use_llm = scorer.use_llm
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
        before = scorer.judge_stats
        scored = scorer.evaluate(scenarios[example_id], calls)
        after = scorer.judge_stats
        arguments_passed = scored["checks"].get("argument_accuracy", {}).get("passed", False)
        row = {"example_id": example_id, "folder": example_folder,
                        "capture_status": captured.get("status", "unknown"),
                        "num_actual_calls": len(calls), "passed": scored["passed"],
                        "failure_reason": scored["failure_reason"],
                        "tool_selection_passed": scored["checks"]["tool_selection"]["passed"],
                        "exact_arguments_passed": arguments_passed}
        if use_llm:
            attempts = after["attempts"] - before["attempts"]
            fallbacks = after["exact_fallbacks"] - before["exact_fallbacks"]
            del row["exact_arguments_passed"]
            row.update(arguments_passed=arguments_passed,
                       semantic_arguments_passed=arguments_passed and attempts > 0 and fallbacks == 0,
                       judge_attempts=attempts, judge_exact_fallbacks=fallbacks)
        results.append(row)
    report = {
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
    if use_llm:
        del report["exact_arguments_passed"]
        report.update(mode="captured_calls_semantic_arguments_no_asr" if not scorer.judge_stats["exact_fallbacks"]
                           else "captured_calls_mixed_semantic_exact_arguments_no_asr",
                      judge=scorer.judge_stats,
                      arguments_passed=sum(row.get("arguments_passed", False) for row in results),
                      semantic_arguments_passed=sum(row.get("semantic_arguments_passed", False) for row in results),
                      response_quality_evaluated=False,
                      asr_used=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("fdb_v3_data_released"))
    parser.add_argument("--outputs", type=Path, default=Path("artifacts/batch_inference"))
    parser.add_argument("--output", type=Path, help="Report path; exact and semantic modes have separate defaults")
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    parser.add_argument("--use-llm", action="store_true", help="Use the official pinned FDB argument-judge policy, with confirmed judge access")
    parser.add_argument("--check", action="store_true", help="Offline capture/judge preflight; no requests or report writes")
    args = parser.parse_args()
    if args.check:
        verify_upstream(args.upstream)
        recordings = list(args.inputs.glob("*/input.wav"))
        if not recordings:
            raise ValueError(f"No FDB recordings under {args.inputs}")
        present = sum((args.outputs / path.parent.name / "result.json").is_file() for path in recordings)
        preflight = {"mode": "semantic_judge_preflight" if args.use_llm else "exact_preflight",
                     "recordings": len(recordings), "result_files_present": present,
                     "missing_result_files": len(recordings) - present, "hosted_requests": 0}
        if args.use_llm:
            preflight.update(judge_preflight())
        print(json.dumps(preflight, indent=2))
        return
    if args.output is None:
        args.output = Path("artifacts/batch-call-eval-semantic.json" if args.use_llm
                           else "artifacts/batch-call-eval-exact.json")
    report = evaluate_batch_calls(args.inputs, args.outputs, upstream=args.upstream, use_llm=args.use_llm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "mode", "expected", "captured_results", "missing_results", "full_capture_coverage",
        "tool_selection_passed", "semantic_arguments_passed" if args.use_llm else "exact_arguments_passed", "strict_tool_passed",
        "capture_status_counts", "official_score",
    )} | ({"judge": report["judge"]} if args.use_llm else {}), indent=2))


if __name__ == "__main__":
    main()
