import json
import re
import sys
from types import SimpleNamespace

import pytest
from google import genai

from scripts.evaluate_smoke import CallEvaluator
from scripts.evaluate_batch_calls import evaluate_batch_calls


SCENARIO = {"expected_tool_calls": [{"function": "search_products", "args": {"query": "running shoes"}}]}
CALLS = [{"function": "search_products", "args": {"query": "running shoe"}}]


@pytest.fixture
def google_judge(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key-not-for-network")
    monkeypatch.setenv("REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED", "yes")
    monkeypatch.setattr("scripts.google_argument_judge.time.sleep", lambda seconds: None)
    state = {"requests": [], "closed": [], "text": '{"correct":true,"explanation":"same product category"}'}

    def generate(**kwargs):
        state["requests"].append(kwargs)
        if state.get("error"):
            raise state["error"]
        text = state["responses"].pop(0) if state.get("responses") else state["text"]
        return SimpleNamespace(text=text, model_version="test-model-version", usage_metadata=None)

    monkeypatch.setattr(genai, "Client", lambda **kwargs: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate), close=lambda: state["closed"].append(True)))

    def forbidden(**kwargs):
        pytest.fail("Google evaluation must not initialize an OpenAI client")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=forbidden))
    return state


def test_google_judge_uses_only_selected_google_model_and_pinned_classifier(google_judge):
    with CallEvaluator(use_llm=True, judge_provider="google", judge_model="gemma-4-31b-it") as scorer:
        result = scorer.evaluate(SCENARIO, CALLS)
        assert result["passed"] is True
        assert scorer.judge_stats["provider"] == "google"
        assert scorer.judge_stats["model"] == "gemma-4-31b-it"
        assert scorer.judge_stats["exact_fallbacks"] == 0
    assert google_judge["requests"][0]["model"] == "gemma-4-31b-it"
    assert google_judge["closed"] == [True]


def test_missing_tools_are_not_sent_to_google_judge(google_judge):
    with CallEvaluator(use_llm=True, judge_provider="google") as scorer:
        assert scorer.evaluate(SCENARIO, [])["passed"] is False
    assert google_judge["requests"] == []


@pytest.mark.parametrize("reply", ['{"correct":"true","explanation":"wrong type"}', "not JSON"])
def test_invalid_google_verdict_is_visible_exact_fallback_not_semantic_pass(google_judge, reply):
    google_judge["text"] = reply
    with CallEvaluator(use_llm=True, judge_provider="google") as scorer:
        assert scorer.evaluate(SCENARIO, CALLS)["passed"] is False
        assert scorer.judge_stats["exact_fallbacks"] == 1


def test_unverified_models_cannot_be_selected_as_paid_fallback(google_judge):
    with pytest.raises(ValueError, match="free-tier"):
        CallEvaluator(use_llm=True, judge_provider="google", judge_model="gemini-3.1-pro-preview")
    assert google_judge["requests"] == []


def test_google_judge_requires_its_own_free_access_confirmation(google_judge, monkeypatch):
    monkeypatch.setenv("REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED", "no")
    monkeypatch.setenv("REACTOR_JUDGE_QUOTA_CONFIRMED", "yes")
    with pytest.raises(RuntimeError, match="REACTOR_GOOGLE_JUDGE_FREE_CONFIRMED"):
        CallEvaluator(use_llm=True, judge_provider="google")
    assert google_judge["requests"] == []


def test_google_batch_report_is_not_labelled_as_gpt4o_or_official(tmp_path, google_judge):
    name = "ecommerce_08_61517db6a7589569521b2356"
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    (inputs / name).mkdir(parents=True)
    (inputs / name / "input.wav").write_bytes(b"RIFF")
    (outputs / name).mkdir(parents=True)
    (outputs / name / "result.json").write_text(json.dumps({"status": "completed", "actual_tool_calls": [{
        "function": "search_products", "args": {"query": "mechanical keyboard", "max_price": 200},
    }]}))
    report = evaluate_batch_calls(inputs, outputs, use_llm=True, judge_provider="google")
    assert report["mode"] == "captured_calls_google_semantic_arguments_no_asr"
    assert report["judge"]["provider"] == "google"
    assert report["strict_tool_passed"] == 1
    assert report["official_score"] is False


def test_calibration_requires_one_valid_verdict_for_every_control(google_judge):
    from scripts.google_argument_judge import GoogleArgumentJudge

    items = [{"case_id": "a", "function_name": "search_products", "expected_args": {"query": "bikes"},
              "actual_args": {"query": "bike"}},
             {"case_id": "b", "function_name": "add_to_cart", "expected_args": {"quantity": 1},
              "actual_args": {"quantity": 10}}]
    google_judge["text"] = '{"verdicts":[{"case_id":"a","correct":true,"explanation":"same"}]}'
    with GoogleArgumentJudge() as judge:
        with pytest.raises(ValueError, match="every control"):
            judge.calibrate(items)


def test_calibration_preserves_negative_verdicts_and_does_not_choose_by_benchmark_passes(google_judge):
    from scripts.google_argument_judge import GoogleArgumentJudge

    items = [{"case_id": "a", "function_name": "search_products", "expected_args": {"query": "bikes"},
              "actual_args": {"query": "bike"}},
             {"case_id": "b", "function_name": "add_to_cart", "expected_args": {"quantity": 1},
              "actual_args": {"quantity": 10}}]
    google_judge["text"] = '{"verdicts":[{"case_id":"b","correct":false,"explanation":"quantity changed"},' \
                           '{"case_id":"a","correct":true,"explanation":"same category"}]}'
    with GoogleArgumentJudge() as judge:
        result = judge.calibrate(items)
    assert result["a"]["correct"] is True
    assert result["b"]["correct"] is False


def test_quota_error_stops_further_requests_and_never_switches_provider(google_judge):
    class QuotaError(RuntimeError):
        code = 429

    google_judge["error"] = QuotaError("private provider detail")
    with CallEvaluator(use_llm=True, judge_provider="google") as scorer:
        assert scorer.evaluate(SCENARIO, CALLS)["passed"] is False
        assert scorer.evaluate(SCENARIO, CALLS)["passed"] is False
        assert scorer.judge_stats["quota_blocked"] is True
        assert scorer.judge_stats["exact_fallbacks"] == 2
    assert len(google_judge["requests"]) == 1


def test_calibration_selection_rejects_false_positive_judges():
    from scripts.calibrate_google_judge import select_model

    candidates = [
        {"model": "gemma-4-31b-it", "valid_response": True, "correct_controls": 15,
         "total_controls": 16, "false_positives": 0},
        {"model": "gemini-3.8-flash", "valid_response": True, "correct_controls": 15,
         "total_controls": 16, "false_positives": 1},
    ]
    for candidate in candidates:
        candidate["context_checks_passed"] = True
    assert select_model(candidates) == "gemma-4-31b-it"


def test_equal_calibration_quality_prefers_the_free_only_gemma_model():
    from scripts.calibrate_google_judge import select_model

    candidates = [{"model": model, "valid_response": True, "correct_controls": 16,
                   "total_controls": 16, "false_positives": 0, "context_checks_passed": True}
                  for model in ("gemini-3.8-flash", "gemma-4-31b-it")]
    assert select_model(candidates) == "gemma-4-31b-it"


def test_calibration_does_not_send_control_answer_labels(google_judge):
    from scripts.calibrate_google_judge import calibration_inputs, CONTROLS
    from scripts.google_argument_judge import GoogleArgumentJudge

    items = calibration_inputs(CONTROLS)
    google_judge["text"] = json.dumps({"verdicts": [
        {"case_id": item["case_id"], "correct": True, "explanation": "test output"} for item in items]})
    with GoogleArgumentJudge() as judge:
        judge.calibrate(items)
    assert "expected_correct" not in google_judge["requests"][0]["contents"]


def test_blind_calibration_payload_has_opaque_ids_and_no_descriptive_metadata():
    from scripts.calibrate_google_judge import calibration_inputs, CONTROLS

    items = calibration_inputs(CONTROLS)
    assert len({row["case_id"] for row in items}) == len(items)
    assert all(re.fullmatch(r"[0-9a-f]{12}", row["case_id"]) for row in items)
    assert all(set(row) == {"case_id", "function_name", "expected_args", "actual_args"} for row in items)
    labels = [row["expected_correct"] for row in CONTROLS]
    assert any(not first and second for first, second in zip(labels, labels[1:]))


def test_stable_pro_is_explicitly_supported_without_provider_fallback(google_judge):
    with CallEvaluator(use_llm=True, judge_provider="google", judge_model="gemini-2.5-pro") as scorer:
        assert scorer.evaluate(SCENARIO, CALLS)["passed"] is True
        assert scorer.judge_stats["returned_model_versions"] == ["test-model-version"]
        assert scorer.judge_stats["policy_version"] == "google-semantic-v2-category-query"
    assert google_judge["requests"][0]["model"] == "gemini-2.5-pro"
    assert len(google_judge["requests"]) == 1


def test_calibration_rejects_a_model_that_passes_grouped_controls_but_fails_single_context(google_judge, monkeypatch):
    from scripts import calibrate_google_judge as calibration

    positive = {"case_id": "43ae16b05c91", "case_name": "category", "function_name": "search_products",
                "expected_args": {"query": "office chairs"}, "actual_args": {"query": "office chair"},
                "expected_correct": True}
    negative = {"case_id": "83db24936a70", "case_name": "quantity", "function_name": "search_products",
                "expected_args": {"query": "two office chairs"}, "actual_args": {"query": "one office chair"},
                "expected_correct": False}
    monkeypatch.setattr(calibration, "CONTROLS", [positive, negative])
    monkeypatch.setattr(calibration, "SINGLE_CONTROLS", [positive], raising=False)
    google_judge["responses"] = [json.dumps({"verdicts": [
        {"case_id": "43ae16b05c91", "correct": True, "explanation": "same category"},
        {"case_id": "83db24936a70", "correct": False, "explanation": "changed quantity"},
    ]}), '{"correct":false,"explanation":"plural differs"}']
    report = calibration.compare(["gemini-2.5-flash"])
    assert report["selected_model"] is None
    candidate = report["candidates"][0]
    assert candidate["correct_controls"] == 2
    assert candidate["context_checks_passed"] is False
    assert candidate["context_correct_controls"] == 0
    assert len(google_judge["requests"]) == 2


def test_equal_blind_calibration_quality_prefers_pro_to_stable_flash():
    from scripts.calibrate_google_judge import select_model

    candidates = [{"model": model, "valid_response": True, "correct_controls": 24,
                   "total_controls": 24, "false_positives": 0, "context_checks_passed": True}
                  for model in ("gemini-2.5-flash", "gemini-2.5-pro")]
    assert select_model(candidates) == "gemini-2.5-pro"


def test_calibration_refuses_existing_report_before_hosted_requests(tmp_path, monkeypatch):
    from scripts import calibrate_google_judge as calibration

    output = tmp_path / "preserved.json"
    output.write_text("original evidence\n")
    monkeypatch.setattr(sys, "argv", ["calibrate_google_judge.py", "--output", str(output)])
    monkeypatch.setattr(calibration, "compare", lambda models: pytest.fail("Must reject overwrites before inference"))
    with pytest.raises(SystemExit) as error:
        calibration.main()
    assert error.value.code == 2
    assert output.read_text() == "original evidence\n"


def test_calibration_default_writes_a_new_protocol_report(tmp_path, monkeypatch):
    from scripts import calibrate_google_judge as calibration

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["calibrate_google_judge.py", "--model", "gemini-2.5-pro"])
    monkeypatch.setattr(calibration, "compare", lambda models: {"selected_model": "gemini-2.5-pro"})
    calibration.main()
    assert json.loads((tmp_path / "artifacts/google-blind-v2-calibration.json").read_text())["selected_model"] == "gemini-2.5-pro"
    assert not (tmp_path / "artifacts/google-judge-calibration.json").exists()


def test_late_scalar_failure_retains_completed_control_evidence(google_judge, monkeypatch):
    from scripts import calibrate_google_judge as calibration

    positive = {"case_id": "43ae16b05c91", "function_name": "search_products",
                "expected_args": {"query": "office chairs"}, "actual_args": {"query": "office chair"},
                "expected_correct": True}
    negative = {"case_id": "83db24936a70", "function_name": "search_products",
                "expected_args": {"query": "two office chairs"}, "actual_args": {"query": "one office chair"},
                "expected_correct": False}
    monkeypatch.setattr(calibration, "CONTROLS", [positive, negative])
    monkeypatch.setattr(calibration, "SINGLE_CONTROLS", [positive, negative])
    google_judge["responses"] = [json.dumps({"verdicts": [
        {"case_id": "43ae16b05c91", "correct": True, "explanation": "same category"},
        {"case_id": "83db24936a70", "correct": False, "explanation": "changed quantity"},
    ]}), '{"correct":true,"explanation":"same category"}', "not JSON"]
    report = calibration.compare(["gemini-2.5-flash"])
    candidate = report["candidates"][0]
    assert report["selected_model"] is None
    assert candidate["valid_response"] is False
    assert candidate["correct_controls"] == 2
    assert len(candidate["controls"]) == 2
    assert len(candidate["context_controls"]) == 1
    assert candidate["context_correct_controls"] == 1
    assert candidate["context_checks_passed"] is False
    assert candidate["judge"]["api_requests"] == 3


def test_failed_selection_never_rejudges_passes_and_labels_population_as_mixed(tmp_path, google_judge):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    names = ["ecommerce_08_61517db6a7589569521b2356", "ecommerce_08_5ff07b5ee7a1d23e719e421e"]
    for index, name in enumerate(names):
        (inputs / name).mkdir(parents=True)
        (inputs / name / "input.wav").write_bytes(b"RIFF")
        (outputs / name).mkdir(parents=True)
        query = "mechanical keyboard" if index == 0 else "mechanical keyboards"
        (outputs / name / "result.json").write_text(json.dumps({"status": "completed", "actual_tool_calls": [{
            "function": "search_products", "args": {"query": query, "max_price": 200},
        }]}))
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"mode": "captured_calls_exact_match_no_asr_no_judge", "expected": 2,
                                   "strict_tool_passed": 1, "examples": [
                                       {"folder": names[0], "passed": False}, {"folder": names[1], "passed": True}]}))
    report = evaluate_batch_calls(inputs, outputs, use_llm=True, judge_provider="google", failed_from=baseline)
    assert len(google_judge["requests"]) == 1
    assert report["expected"] == 1
    assert report["examples"][0]["folder"] == names[0]
    assert report["selection"]["population_size"] == 2
    assert report["selection"]["baseline_exact_passes_unrejudged"] == 1
    assert report["mixed_population_diagnostic"]["passed"] == 2
    assert report["mixed_population_diagnostic"]["fully_semantic"] is False
    assert report["official_score"] is False


def test_stable_flash_candidate_is_allowed_and_has_no_automatic_function_calling(google_judge):
    with CallEvaluator(use_llm=True, judge_provider="google", judge_model="gemini-2.5-flash") as scorer:
        assert scorer.evaluate(SCENARIO, CALLS)["passed"] is True
    request = google_judge["requests"][0]
    assert request["model"] == "gemini-2.5-flash"
    assert request["config"].automatic_function_calling.disable is True


def test_multi_step_argument_comparisons_use_one_google_request_per_recording(google_judge):
    scenario = {"expected_tool_calls": [
        {"function": "track_order", "args": {"order_id": "RQ61"}},
        {"function": "search_products", "args": {"query": "running shoes"}},
    ]}
    actual = [{"function": "track_order", "args": {"order_id": "RQ61"}},
              {"function": "search_products", "args": {"query": "running shoe"}}]
    google_judge["text"] = '{"verdicts":[{"case_id":"0","correct":true,"explanation":"same ID"},' \
                           '{"case_id":"1","correct":true,"explanation":"same category"}]}'
    with CallEvaluator(use_llm=True, judge_provider="google") as scorer:
        assert scorer.evaluate(scenario, actual)["passed"] is True
        assert scorer.judge_stats["attempts"] == 2
        assert scorer.judge_stats["api_requests"] == 1
    assert len(google_judge["requests"]) == 1


def test_grouped_request_failure_records_each_fallback_and_does_not_cache_across_cases(google_judge):
    scenario = {"expected_tool_calls": [{"function": "track_order", "args": {"order_id": "RQ61"}},
                                         {"function": "search_products", "args": {"query": "running shoes"}}]}
    actual = [{"function": "track_order", "args": {"order_id": "RQ61"}},
              {"function": "search_products", "args": {"query": "running shoe"}}]
    with CallEvaluator(use_llm=True, judge_provider="google") as scorer:
        assert scorer.evaluate(scenario, actual)["passed"] is False  # scalar verdict is invalid for a pair set
        assert scorer.judge_stats["exact_fallbacks"] == 2
        google_judge["text"] = '{"verdicts":[{"case_id":"0","correct":true,"explanation":"same ID"},' \
                               '{"case_id":"1","correct":true,"explanation":"same category"}]}'
        assert scorer.evaluate(scenario, actual)["passed"] is True
    assert len(google_judge["requests"]) == 2
