import json
import subprocess
import sys

from scripts.summarize_smokes import summarize


def test_summary_separates_tool_selection_from_exact_argument_results(tmp_path):
    log = tmp_path / "calls.jsonl"
    log.write_text("\n".join(json.dumps({"room": room, "call": call}) for room, call in [
        ("ecommerce", {"function": "track_order", "args": {"order_id": "ABC123"}}),
        ("travel", {"function": "search_flights", "args": {"destination": "Tokyo", "date": "2026-07-15"}}),
        ("finance", {"function": "get_exchange_rate", "args": {"amount": 500, "from_currency": "USD", "to_currency": "EUR"}}),
    ]))
    cases = [
        {"name": "ecommerce_01", "room": "ecommerce", "input": "fdb_v3_data_released/ecommerce_01_65e8cf8f4c7424fa062e54a3/input.wav"},
        {"name": "travel_01", "room": "travel", "input": "fdb_v3_data_released/travel_01_62a885d5b6af18b3d4579e1b/input.wav"},
        {"name": "finance_01", "room": "finance", "input": "fdb_v3_data_released/finance_01_65e8cf8f4c7424fa062e54a3/input.wav"},
    ]
    report = summarize(cases, tool_log=log)
    assert report["mode"] == "exact_match_tool_only"
    assert report["official_score"] is False
    assert report["summary"] == {
        "examples": 3, "tool_selection_passed": 3,
        "exact_argument_passed": 2, "strict_tool_passed": 2,
    }
    assert [row["example_id"] for row in report["examples"]] == ["ecommerce_01", "travel_01", "finance_01"]
    assert report["examples"][1]["failure_reason"] == "Wrong arguments for: ['search_flights']"


def test_summary_cli_emits_json_for_curated_rooms(tmp_path):
    log = tmp_path / "calls.jsonl"
    log.write_text(json.dumps({"room": "finance", "call": {
        "function": "get_exchange_rate",
        "args": {"amount": 500, "from_currency": "USD", "to_currency": "EUR"},
    }}))
    completed = subprocess.run([
        sys.executable, "scripts/summarize_smokes.py", "--room", "finance",
        "--input", "fdb_v3_data_released/finance_01_65e8cf8f4c7424fa062e54a3/input.wav",
        "--log", str(log),
    ], text=True, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["summary"]["strict_tool_passed"] == 1
