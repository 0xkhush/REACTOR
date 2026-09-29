"""Create an exact-match tool-only summary for a curated list of recorded smoke rooms."""

import argparse
import json
from pathlib import Path

if __package__:
    from .evaluate_smoke import actual_calls_for_room, evaluate_calls, example_id_from_input
    from .smoke_fdb import UPSTREAM, verify_upstream
else:
    from evaluate_smoke import actual_calls_for_room, evaluate_calls, example_id_from_input
    from smoke_fdb import UPSTREAM, verify_upstream


def summarize(cases: list[dict], *, tool_log: Path = Path("/tmp/agent_tool_calls.log"), upstream=UPSTREAM):
    source = verify_upstream(upstream)
    data = json.loads((source / "benchmark_data_v2.json").read_text())
    scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}
    results = []
    for case in cases:
        input_path = Path(case["input"])
        example_id = example_id_from_input(input_path)
        if example_id not in scenarios:
            raise ValueError(f"No FDB-v3 scoring scenario for {example_id}")
        calls = actual_calls_for_room(tool_log, case["room"])
        if not calls:
            result = {"passed": False, "failure_reason": "No actual tool calls found for room",
                      "checks": {"tool_selection": {"passed": False}, "argument_accuracy": {"passed": False}}}
        else:
            result = evaluate_calls(scenarios[example_id], calls, upstream=upstream)
        checks = result["checks"]
        results.append({
            "name": case.get("name", example_id), "example_id": example_id, "room": case["room"],
            "actual_calls": calls, "passed": result["passed"],
            "failure_reason": result["failure_reason"],
            "tool_selection_passed": checks["tool_selection"]["passed"],
            "exact_argument_passed": checks.get("argument_accuracy", {}).get("passed", False),
        })
    total = len(results)
    return {
        "benchmark_revision": "3e799c45a045256f47d5f1c9cda90157e2d2ec9e",
        "mode": "exact_match_tool_only",
        "official_score": False,
        "judge": "none",
        "summary": {
            "examples": total,
            "tool_selection_passed": sum(row["tool_selection_passed"] for row in results),
            "exact_argument_passed": sum(row["exact_argument_passed"] for row in results),
            "strict_tool_passed": sum(row["passed"] for row in results),
        },
        "examples": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", action="append", required=True, help="Smoke room; repeat with each --input")
    parser.add_argument("--input", action="append", required=True, type=Path, help="Corresponding input.wav; repeat")
    parser.add_argument("--log", type=Path, default=Path("/tmp/agent_tool_calls.log"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    args = parser.parse_args()
    if len(args.room) != len(args.input):
        parser.error("provide one --input for each --room")
    report = summarize([{"room": room, "input": str(path)} for room, path in zip(args.room, args.input)],
                       tool_log=args.log, upstream=args.upstream)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
