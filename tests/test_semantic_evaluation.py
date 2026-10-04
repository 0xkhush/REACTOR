import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import evaluate_batch_calls as batch
from scripts import evaluate_smoke as smoke

openai = pytest.importorskip("openai")


SCENARIO = {"expected_tool_calls": [{"function": "search_products",
                                      "args": {"query": "mechanical keyboards", "max_price": 200}}]}
ACTUAL = [{"function": "search_products", "args": {"query": "mechanical keyboard", "max_price": 200}}]


def sdk_client(create, close=lambda: None):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=close)


@pytest.fixture
def judge(monkeypatch):
    """Only substitute the external API; use the real pinned FDB classifier."""
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key-not-for-network")
    monkeypatch.setenv("REACTOR_JUDGE_QUOTA_CONFIRMED", "yes")
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "correct": True, "explanation": "The singular and plural queries describe the same product category.",
        })))])

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(create))
    return requests


def test_semantic_mode_uses_upstream_judge_verdict_without_changing_exact_result(judge):
    assert smoke.evaluate_calls(SCENARIO, ACTUAL)["passed"] is False
    scorer = smoke.CallEvaluator(use_llm=True)
    result = scorer.evaluate(SCENARIO, ACTUAL)
    assert result["passed"] is True
    assert result["checks"]["tool_selection"]["passed"] is True
    assert len(judge) == 1
    assert judge[0]["model"] == "gpt-4o"
    assert scorer.judge_stats == {"model": "gpt-4o", "attempts": 1, "exact_fallbacks": 0}
    assert smoke.evaluate_calls(SCENARIO, ACTUAL)["passed"] is False


def test_semantic_mode_cannot_turn_missing_tools_into_a_pass(judge):
    scorer = smoke.CallEvaluator(use_llm=True)
    result = scorer.evaluate(SCENARIO, [])
    assert result["passed"] is False
    assert judge == []
    assert scorer.judge_stats["attempts"] == 0


def test_upstream_exact_fallback_is_counted_when_judge_request_fails(judge, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("private-test-key-not-for-network")

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(fail))
    scorer = smoke.CallEvaluator(use_llm=True)
    result = scorer.evaluate(SCENARIO, ACTUAL)
    assert result["passed"] is False
    assert scorer.judge_stats == {"model": "gpt-4o", "attempts": 1, "exact_fallbacks": 1}
    assert "private-test-key" not in json.dumps(result)


def test_judge_access_must_be_confirmed_before_constructing_api_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key-not-for-network")
    monkeypatch.setenv("REACTOR_JUDGE_QUOTA_CONFIRMED", "no")

    def forbidden(**kwargs):
        pytest.fail("API client constructed without confirmed judge access")

    monkeypatch.setattr(openai, "OpenAI", forbidden)
    with pytest.raises(RuntimeError, match="REACTOR_JUDGE_QUOTA_CONFIRMED"):
        smoke.CallEvaluator(use_llm=True)


@pytest.mark.parametrize("invalid_verdict", ["false", "true"])
def test_nonboolean_judge_verdict_cannot_be_counted_as_a_semantic_pass(judge, monkeypatch, invalid_verdict):
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"correct": invalid_verdict,
                                                                             "explanation": "invalid type"})))])))
    scorer = smoke.CallEvaluator(use_llm=True)
    assert scorer.evaluate(SCENARIO, ACTUAL)["passed"] is False
    assert scorer.judge_stats["exact_fallbacks"] == 1


def capture(tmp_path):
    name = "ecommerce_08_61517db6a7589569521b2356"
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    (inputs / name).mkdir(parents=True)
    (inputs / name / "input.wav").write_bytes(b"RIFF")
    (outputs / name).mkdir(parents=True)
    (outputs / name / "result.json").write_text(json.dumps({"status": "completed", "actual_tool_calls": ACTUAL}))
    return inputs, outputs


def test_semantic_batch_report_has_distinct_labels_and_same_denominator(tmp_path, judge):
    inputs, outputs = capture(tmp_path)
    exact = batch.evaluate_batch_calls(inputs, outputs)
    semantic = batch.evaluate_batch_calls(inputs, outputs, use_llm=True)
    assert exact["strict_tool_passed"] == 0
    assert semantic["strict_tool_passed"] == 1
    assert semantic["semantic_arguments_passed"] == 1
    assert "exact_arguments_passed" not in semantic
    assert semantic["expected"] == exact["expected"] == 1
    assert semantic["official_score"] is False
    assert semantic["mode"] == "captured_calls_semantic_arguments_no_asr"
    assert semantic["judge"]["exact_fallbacks"] == 0


def test_fallback_batch_is_not_labelled_as_fully_semantic(tmp_path, judge, monkeypatch):
    inputs, outputs = capture(tmp_path)
    def fail(**kwargs):
        raise RuntimeError()

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(fail))
    result = batch.evaluate_batch_calls(inputs, outputs, use_llm=True)
    assert result["mode"] == "captured_calls_mixed_semantic_exact_arguments_no_asr"
    assert result["judge"]["exact_fallbacks"] == 1
    assert result["strict_tool_passed"] == 0


def test_successful_exact_fallback_is_not_counted_as_semantically_judged(tmp_path, judge, monkeypatch):
    inputs, outputs = capture(tmp_path)
    result_file = next(outputs.glob("*/result.json"))
    result_file.write_text(json.dumps({"status": "completed", "actual_tool_calls": [{
        "function": "search_products", "args": {"query": "mechanical keyboards", "max_price": 200},
    }]}))

    def fail(**kwargs):
        raise RuntimeError()

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(fail))
    result = batch.evaluate_batch_calls(inputs, outputs, use_llm=True)
    assert result["strict_tool_passed"] == 1
    assert result["arguments_passed"] == 1
    assert result["semantic_arguments_passed"] == 0
    assert result["judge"]["exact_fallbacks"] == 1
    assert result["mode"] == "captured_calls_mixed_semantic_exact_arguments_no_asr"


def test_semantic_cli_default_report_does_not_overwrite_existing_exact_report(tmp_path, judge, monkeypatch):
    inputs, outputs = capture(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    exact = tmp_path / "artifacts/batch-call-eval-exact.json"
    exact.write_text("preserve exact report")
    monkeypatch.setattr(sys, "argv", ["evaluate_batch_calls.py", "--use-llm", "--inputs", str(inputs),
                                      "--outputs", str(outputs)])
    batch.main()
    assert exact.read_text() == "preserve exact report"
    report = json.loads((tmp_path / "artifacts/batch-call-eval-semantic.json").read_text())
    assert report["semantic_arguments_passed"] == 1
    assert report["official_score"] is False


def test_semantic_preflight_makes_no_requests_or_report_changes(tmp_path):
    inputs, outputs = capture(tmp_path)
    report = tmp_path / "existing-exact.json"
    report.write_text("preserve existing report")
    env = {key: value for key, value in os.environ.items()
           if key not in {"OPENAI_API_KEY", "REACTOR_JUDGE_QUOTA_CONFIRMED"}}
    completed = subprocess.run([sys.executable, "scripts/evaluate_batch_calls.py", "--use-llm", "--check",
                                "--inputs", str(inputs), "--outputs", str(outputs), "--output", str(report)],
                               capture_output=True, text=True, env=env, timeout=15)
    assert completed.returncode == 0, completed.stderr
    diagnostic = json.loads(completed.stdout)
    assert diagnostic["hosted_requests"] == 0
    assert diagnostic["judge_key_present"] is False
    assert diagnostic["recordings"] == 1
    assert diagnostic["result_files_present"] == 1
    assert diagnostic["missing_result_files"] == 0
    assert report.read_text() == "preserve existing report"


def test_semantic_batch_closes_its_owned_client_after_evaluation(tmp_path, judge, monkeypatch):
    inputs, outputs = capture(tmp_path)
    closed = []
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: sdk_client(
        lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"correct":true,"explanation":"matching meaning"}'))]),
        close=lambda: closed.append(True)))
    assert batch.evaluate_batch_calls(inputs, outputs, use_llm=True)["strict_tool_passed"] == 1
    assert closed == [True]
