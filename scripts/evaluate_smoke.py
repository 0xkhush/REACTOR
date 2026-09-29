"""Score recorded tool calls with FDB-v3's exact-match evaluator (no LLM judge)."""

import argparse
import importlib.util
import json
import re
from pathlib import Path

if __package__:
    from .smoke_fdb import UPSTREAM, verify_upstream
else:
    from smoke_fdb import UPSTREAM, verify_upstream


def example_id_from_input(input_path: Path) -> str:
    if input_path.name != "input.wav":
        raise ValueError("Expected an input.wav recording")
    match = re.fullmatch(r"(.+)_([0-9a-f]{24})", input_path.parent.name)
    if not match:
        raise ValueError("Input must be inside a released FDB-v3 example folder")
    return match.group(1)


def evaluate_calls(scenario: dict, actual_calls: list[dict], *, upstream: Path = UPSTREAM) -> dict:
    source = verify_upstream(upstream)
    spec = importlib.util.spec_from_file_location("reactor_fdb_pass_rate", source / "evaluate_pass_rate.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load pinned FDB-v3 exact-match evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate_scenario_pass(scenario, actual_calls, use_llm=False)


def actual_calls_for_room(path: Path, room: str) -> list[dict]:
    if not path.is_file():
        return []
    return [row["call"] for line in path.read_text().splitlines()
            if (row := json.loads(line)).get("room") == room]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    parser.add_argument("--log", type=Path, default=Path("/tmp/agent_tool_calls.log"))
    args = parser.parse_args()
    source = verify_upstream(args.upstream)
    scenario_id = example_id_from_input(args.input)
    data = json.loads((source / "benchmark_data_v2.json").read_text())
    scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}
    if scenario_id not in scenarios:
        raise ValueError("No FDB-v3 evaluation definition for this example ID")
    calls = actual_calls_for_room(args.log, args.room)
    if not calls:
        raise ValueError("No executed tool calls for this room")
    result = evaluate_calls(scenarios[scenario_id], calls, upstream=args.upstream)
    print(json.dumps({"mode": "exact_match_tool_only", "example_id": scenario_id,
                      "passed": result["passed"], "failure_reason": result["failure_reason"],
                      "checks": result["checks"]}, indent=2))


if __name__ == "__main__":
    main()
