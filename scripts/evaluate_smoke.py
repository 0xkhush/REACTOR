"""Score recorded calls with the pinned FDB evaluator; exact matching is the default."""

import argparse
from collections import Counter, defaultdict, deque
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


def judge_preflight(judge_provider="openai", judge_model=None):
    if judge_provider == "google":
        if __package__:
            from .google_argument_judge import google_judge_preflight
        else:
            from google_argument_judge import google_judge_preflight
        return google_judge_preflight(judge_model)
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

    def __init__(self, *, upstream=UPSTREAM, use_llm=False, judge_provider="openai", judge_model=None):
        if judge_provider not in {"openai", "google"}:
            raise ValueError("Unsupported judge provider")
        self.use_llm = use_llm
        self.judge_provider = judge_provider
        self._google_judge = None
        self._attempts = 0
        self._fallbacks = 0
        self._client = None
        self._closed = False
        self._module = load_evaluator(upstream)
        if use_llm:
            original_judge = self._module.llm_judge_argument
            original_exact = self._module.exact_match_args
            self._original_judge = original_judge
            self._original_exact = original_exact
            if judge_provider == "google":
                if __package__:
                    from .google_argument_judge import GoogleArgumentJudge
                else:
                    from google_argument_judge import GoogleArgumentJudge
                self._google_judge = GoogleArgumentJudge(judge_model)
                self._client = self._google_judge
                active_judge = self._google_judge.judge
            else:
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
                active_judge = original_judge
            self._active_judge = active_judge

            def tracked_judge(expected_args, actual_args, function_name):
                self._attempts += 1
                try:
                    verdict = self._active_judge(expected_args, actual_args, function_name)
                except Exception:
                    if self.judge_provider != "google":
                        raise
                    return tracked_fallback(expected_args, actual_args)
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
        if self._google_judge is not None:
            return {**self._google_judge.stats, "attempts": self._attempts, "exact_fallbacks": self._fallbacks}
        return {"model": "gpt-4o" if self.use_llm else None,
                "attempts": self._attempts, "exact_fallbacks": self._fallbacks}

    def evaluate(self, scenario, actual_calls):
        if self._closed:
            raise RuntimeError("Call evaluator is closed")
        expected = scenario["expected_tool_calls"]
        if (self.use_llm and self.judge_provider == "google" and len(expected) > 1
                and Counter(row["function"] for row in expected) == Counter(row["function"] for row in actual_calls)):
            # One standard API request per recording, not the paid Batch API.
            # The pinned classifier still consumes one verdict per expected
            # tool using its original FIFO duplicate-function pairing.
            actual_by_function = defaultdict(deque)
            for row in actual_calls:
                actual_by_function[row["function"]].append(row)
            items = []
            for index, row in enumerate(expected):
                actual = actual_by_function[row["function"]].popleft()
                items.append({"case_id": str(index), "function_name": row["function"],
                              "expected_args": row.get("args", {}), "actual_args": actual.get("args", {})})
            try:
                verdicts = self._google_judge.calibrate(items)
            except Exception:
                verdicts = None
            pending = deque(items)

            def recording_judge(expected_args, actual_args, function_name):
                item = pending.popleft()
                if (item["function_name"] != function_name or item["expected_args"] != expected_args
                        or item["actual_args"] != actual_args or verdicts is None):
                    raise RuntimeError("Grouped argument verdict is unavailable or does not match this comparison")
                result = verdicts[item["case_id"]]
                return result["correct"], result["explanation"]

            previous = self._active_judge
            self._active_judge = recording_judge
            try:
                return self._module.evaluate_scenario_pass(scenario, actual_calls, use_llm=True)
            finally:
                self._active_judge = previous  # no verdict state survives a recording
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
                   use_llm=False, judge_provider="openai", judge_model=None) -> dict:
    with CallEvaluator(upstream=upstream, use_llm=use_llm, judge_provider=judge_provider, judge_model=judge_model) as scorer:
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
    mode_flags = parser.add_mutually_exclusive_group()
    mode_flags.add_argument("--use-llm", action="store_true", help="Use the pinned GPT-4o argument judge; requires confirmed judge access")
    mode_flags.add_argument("--google-judge", action="store_true", help="Use the Google-only alternative argument judge")
    parser.add_argument("--judge-model", help="Verified free-tier Google judge model; valid only with --google-judge")
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
    if args.judge_model and not args.google_judge:
        parser.error("--judge-model requires --google-judge")
    use_llm = args.use_llm or args.google_judge
    provider = "google" if args.google_judge else "openai"
    with CallEvaluator(upstream=args.upstream, use_llm=use_llm, judge_provider=provider, judge_model=args.judge_model) as scorer:
        result = scorer.evaluate(scenarios[scenario_id], calls)
    mode = "exact_match_tool_only"
    if use_llm:
        mode = "semantic_arguments_tool_only" if not scorer.judge_stats["exact_fallbacks"] else "mixed_semantic_exact_arguments_tool_only"
        if args.google_judge:
            mode = "google_" + mode
    report = {"mode": mode, "example_id": scenario_id,
                       "passed": result["passed"], "failure_reason": result["failure_reason"],
                       "checks": result["checks"]}
    if use_llm:
        report.update(judge=scorer.judge_stats, official_score=False, response_quality_evaluated=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
