import pytest
import subprocess
import sys

from scripts.evaluate_smoke import example_id_from_input, evaluate_calls


def test_example_id_comes_from_folder_name_without_reading_answer_metadata(tmp_path):
    audio = tmp_path / "ecommerce_01_65e8cf8f4c7424fa062e54a3" / "input.wav"
    assert example_id_from_input(audio) == "ecommerce_01"


def test_unrecognized_folder_does_not_guess_an_example_id(tmp_path):
    with pytest.raises(ValueError, match="example folder"):
        example_id_from_input(tmp_path / "wrong" / "input.wav")


def test_upstream_exact_evaluator_separates_correct_and_extra_tool_calls():
    scenario = {
        "expected_tool_calls": [{"function": "track_order", "args": {"order_id": "ABC123"}}],
    }
    assert evaluate_calls(scenario, [{"function": "track_order", "args": {"order_id": "ABC123"}}])["passed"]
    assert not evaluate_calls(scenario, [
        {"function": "track_order", "args": {"order_id": "ABC123"}},
        {"function": "track_order", "args": {"order_id": "ABC123"}},
    ])["passed"]


def test_evaluation_script_runs_directly_as_a_cli():
    completed = subprocess.run([sys.executable, "scripts/evaluate_smoke.py", "--help"],
                               capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert "--room" in completed.stdout
