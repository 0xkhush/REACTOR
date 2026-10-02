"""Score captured calls with exact or opt-in pinned FDB semantic argument judging."""

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .evaluate_smoke import CallEvaluator, judge_preflight
    from .smoke_fdb import UPSTREAM, verify_upstream
else:
    from evaluate_smoke import CallEvaluator, judge_preflight
    from smoke_fdb import UPSTREAM, verify_upstream


def evaluate_batch_calls(inputs: Path, outputs: Path, *, upstream: Path = UPSTREAM, use_llm=False,
                         judge_provider="openai", judge_model=None, failed_from=None) -> dict:
    source = verify_upstream(upstream)
    recordings = sorted(inputs.glob("*/input.wav"))
    if not recordings:
        raise ValueError(f"No FDB recordings under {inputs}")
    recordings, selection = failed_selection(recordings, failed_from)
    benchmark = json.loads((source / "benchmark_data_v2.json").read_text())
    scenarios = {scenario["id"]: scenario for scenario in benchmark["scenarios"]}
    with CallEvaluator(upstream=upstream, use_llm=use_llm, judge_provider=judge_provider, judge_model=judge_model) as scorer:
        report = score_captures(recordings, outputs, scenarios, scorer)
    if selection:
        report["selection"] = selection
        report["mixed_population_diagnostic"] = {
            "mode": "baseline_exact_plus_failed_subset_rejudged", "expected": selection["population_size"],
            "passed": selection["baseline_exact_passes_unrejudged"] + report["strict_tool_passed"],
            "fully_semantic": False, "official_score": False,
        }
    return report


def failed_selection(recordings, baseline_path):
    if baseline_path is None:
        return recordings, None
    content = Path(baseline_path).read_bytes()
    baseline = json.loads(content)
    rows = baseline.get("examples", [])
    if (baseline.get("mode") != "captured_calls_exact_match_no_asr_no_judge"
            or type(baseline.get("expected")) is not int or baseline["expected"] != len(rows)
            or any(not isinstance(row.get("folder"), str) or type(row.get("passed")) is not bool for row in rows)):
        raise ValueError("Failed selection requires a complete, well-formed exact baseline report")
    names = {row["folder"] for row in rows}
    if len(names) != len(rows) or baseline.get("strict_tool_passed") != sum(row["passed"] for row in rows):
        raise ValueError("Baseline denominator or pass count is inconsistent")
    lookup = {path.parent.name: path for path in recordings}
    failed = {row["folder"] for row in rows if not row["passed"]}
    if not failed or not failed.issubset(lookup) or not set(lookup).issubset(names):
        raise ValueError("Inputs must contain every failed baseline recording and no unrelated recordings")
    selected = [lookup[name] for name in sorted(failed)]
    return selected, {"scope": "previous_exact_failures_only", "population_size": len(rows),
                      "selected_recordings": len(selected),
                      "baseline_exact_passes_unrejudged": baseline["strict_tool_passed"],
                      "baseline_report": str(baseline_path),
                      "baseline_sha256": hashlib.sha256(content).hexdigest()}


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
        if scorer.judge_provider == "google":
            report["mode"] = "captured_calls_google_" + report["mode"].removeprefix("captured_calls_")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("fdb_v3_data_released"))
    parser.add_argument("--outputs", type=Path, default=Path("artifacts/batch_inference"))
    parser.add_argument("--output", type=Path, help="Report path; exact and semantic modes have separate defaults")
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    mode_flags = parser.add_mutually_exclusive_group()
    mode_flags.add_argument("--use-llm", action="store_true", help="Use the official pinned GPT-4o argument judge, with confirmed access")
    mode_flags.add_argument("--google-judge", action="store_true", help="Use the Google-only alternative argument judge")
    parser.add_argument("--judge-model", help="Verified free-tier Google judge model; valid only with --google-judge")
    parser.add_argument("--failed-from", type=Path, help="Evaluate only failures in this complete exact baseline report")
    parser.add_argument("--check", action="store_true", help="Offline capture/judge preflight; no requests or report writes")
    args = parser.parse_args()
    if args.judge_model and not args.google_judge:
        parser.error("--judge-model requires --google-judge")
    use_llm = args.use_llm or args.google_judge
    provider = "google" if args.google_judge else "openai"
    if args.check:
        verify_upstream(args.upstream)
        recordings = list(args.inputs.glob("*/input.wav"))
        if not recordings:
            raise ValueError(f"No FDB recordings under {args.inputs}")
        recordings, selection = failed_selection(recordings, args.failed_from)
        present = sum((args.outputs / path.parent.name / "result.json").is_file() for path in recordings)
        preflight = {"mode": "google_judge_preflight" if args.google_judge else "semantic_judge_preflight" if args.use_llm else "exact_preflight",
                     "recordings": len(recordings), "result_files_present": present,
                     "missing_result_files": len(recordings) - present, "hosted_requests": 0}
        if use_llm:
            preflight.update(judge_preflight(provider, args.judge_model))
        if selection:
            preflight["selection"] = selection
        print(json.dumps(preflight, indent=2))
        return
    if args.output is None:
        args.output = Path("artifacts/batch-call-eval-google-semantic.json" if args.google_judge else "artifacts/batch-call-eval-semantic.json" if args.use_llm
                           else "artifacts/batch-call-eval-exact.json")
    report = evaluate_batch_calls(args.inputs, args.outputs, upstream=args.upstream, use_llm=use_llm,
                                  judge_provider=provider, judge_model=args.judge_model, failed_from=args.failed_from)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "mode", "expected", "captured_results", "missing_results", "full_capture_coverage",
        "tool_selection_passed", "semantic_arguments_passed" if use_llm else "exact_arguments_passed", "strict_tool_passed",
        "capture_status_counts", "official_score",
    )} | ({"judge": report["judge"]} if use_llm else {}), indent=2))


if __name__ == "__main__":
    main()
