"""Score recorded calls with the pinned FDB evaluator; exact matching is the default."""

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values

if __package__:
    from .smoke_fdb import ROOT, UPSTREAM, verify_upstream
else:
    from smoke_fdb import ROOT, UPSTREAM, verify_upstream


def example_id_from_input(input_path: Path) -> str:
    if input_path.name != "input.wav":
        raise ValueError("Expected an input.wav recording")
    match = re.fullmatch(r"(.+)_([0-9a-f]{24})", input_path.parent.name)
    if not match:
        raise ValueError("Input must be inside a released FDB-v3 example folder")
    return match.group(1)


def judge_settings():
    values = dotenv_values(ROOT / ".env.local")
    return {name: os.environ.get(name, values.get(name) or "")
            for name in ("OPENAI_API_KEY", "REACTOR_JUDGE_QUOTA_CONFIRMED")}


def judge_preflight():
    settings = judge_settings()
    return {"judge_key_present": bool(settings["OPENAI_API_KEY"].strip()),
            "judge_access_confirmed": settings["REACTOR_JUDGE_QUOTA_CONFIRMED"] == "yes",
            "judge_package_present": importlib.util.find_spec("openai") is not None,
            "judge_model": "gpt-4o", "hosted_requests": 0}


def load_evaluator(upstream):
    source = verify_upstream(upstream)
    spec = importlib.util.spec_from_file_location("reactor_fdb_pass_rate", source / "evaluate_pass_rate.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load pinned FDB-v3 exact-match evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CallEvaluator:
    """Reuse the original judge policy and record its silent exact fallbacks.

    Instrumentation is limited to this privately loaded scorer module; the
    vendor files, agent logic, and original scoring policy stay unchanged.
    """

    def __init__(self, *, upstream=UPSTREAM, use_llm=False):
        self.use_llm = use_llm
        self._attempts = 0
        self._fallbacks = 0
        self._client = None
        self._closed = False
        self._module = load_evaluator(upstream)
        if use_llm:
            settings = judge_settings()
            if not settings["OPENAI_API_KEY"].strip():
                raise RuntimeError("--use-llm requires OPENAI_API_KEY in the environment or ignored .env.local")
            if settings["REACTOR_JUDGE_QUOTA_CONFIRMED"] != "yes":
                raise RuntimeError("Confirm judge access/budget and set REACTOR_JUDGE_QUOTA_CONFIRMED=yes")
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError("Install the optional judge dependencies with pip install -e '.[judge]'") from None
            self._client = OpenAI(api_key=settings["OPENAI_API_KEY"], max_retries=0, timeout=30)
            self._module._openai_client = self._client
            original_judge = self._module.llm_judge_argument
            original_exact = self._module.exact_match_args
            self._original_judge = original_judge
            self._original_exact = original_exact

            def tracked_judge(expected_args, actual_args, function_name):
                self._attempts += 1
                verdict = original_judge(expected_args, actual_args, function_name)
                if type(verdict[0]) is not bool:
                    # The judge contract requires a JSON boolean. In Python,
                    # the string "false" is truthy and would otherwise inflate
                    # passes. Treat an invalid verdict as an explicit fallback.
                    return tracked_fallback(expected_args, actual_args)
                return verdict

            def tracked_fallback(*args, **kwargs):
                self._fallbacks += 1
                return original_exact(*args, **kwargs)

            self._module.llm_judge_argument = tracked_judge
            self._module.exact_match_args = tracked_fallback

    @property
    def judge_stats(self):
        return {"model": "gpt-4o" if self.use_llm else None,
                "attempts": self._attempts, "exact_fallbacks": self._fallbacks}

    def evaluate(self, scenario, actual_calls):
        if self._closed:
            raise RuntimeError("Call evaluator is closed")
        return self._module.evaluate_scenario_pass(scenario, actual_calls, use_llm=self.use_llm)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._client is not None:
            client, self._client = self._client, None
            self._module._openai_client = None
            self._module.llm_judge_argument = self._original_judge
            self._module.exact_match_args = self._original_exact
            client.close()

    def __enter__(self):
        if self._closed:
            raise RuntimeError("Call evaluator is closed")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def evaluate_calls(scenario: dict, actual_calls: list[dict], *, upstream: Path = UPSTREAM,
                   use_llm=False) -> dict:
    with CallEvaluator(upstream=upstream, use_llm=use_llm) as scorer:
        return scorer.evaluate(scenario, actual_calls)


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
    parser.add_argument("--use-llm", action="store_true", help="Use the pinned FDB semantic argument judge; requires confirmed judge access")
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
    with CallEvaluator(upstream=args.upstream, use_llm=args.use_llm) as scorer:
        result = scorer.evaluate(scenarios[scenario_id], calls)
    mode = "exact_match_tool_only"
    if args.use_llm:
        mode = "semantic_arguments_tool_only" if not scorer.judge_stats["exact_fallbacks"] else "mixed_semantic_exact_arguments_tool_only"
    report = {"mode": mode, "example_id": scenario_id,
                       "passed": result["passed"], "failure_reason": result["failure_reason"],
                       "checks": result["checks"]}
    if args.use_llm:
        report.update(judge=scorer.judge_stats, official_score=False, response_quality_evaluated=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
