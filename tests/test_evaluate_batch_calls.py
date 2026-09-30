import json

from scripts.evaluate_batch_calls import evaluate_batch_calls


def test_full_capture_call_report_scores_all_records_including_no_call_failures(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    ecommerce = "ecommerce_01_65e8cf8f4c7424fa062e54a3"
    travel = "travel_01_62a885d5b6af18b3d4579e1b"
    finance = "finance_01_65e8cf8f4c7424fa062e54a3"
    for folder_name in (ecommerce, travel, finance):
        folder = inputs / folder_name
        folder.mkdir()
        (folder / "input.wav").write_bytes(b"RIFF")
    outputs = tmp_path / "outputs"
    fixtures = {
        ecommerce: {"example_id": "ecommerce_01", "status": "completed",
                    "actual_tool_calls": [{"function": "track_order", "args": {"order_id": "ABC123"}}]},
        travel: {"example_id": "travel_01", "status": "completed",
                 "actual_tool_calls": [{"function": "search_flights",
                                        "args": {"destination": "Tokyo", "date": "2026-07-15"}}]},
        finance: {"example_id": "finance_01", "status": "no_tool_call", "actual_tool_calls": []},
    }
    for folder_name, result in fixtures.items():
        folder = outputs / folder_name
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(json.dumps(result))

    report = evaluate_batch_calls(inputs, outputs)

    assert report["expected"] == 3
    assert report["captured_results"] == 3
    assert report["tool_selection_passed"] == 2
    assert report["exact_arguments_passed"] == 1
    assert report["strict_tool_passed"] == 1
    assert report["official_score"] is False


def test_missing_result_files_reduce_coverage_instead_of_changing_denominator(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    recording = inputs / "finance_01_65e8cf8f4c7424fa062e54a3"
    recording.mkdir()
    (recording / "input.wav").write_bytes(b"RIFF")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    report = evaluate_batch_calls(inputs, outputs)
    assert report["expected"] == 1
    assert report["captured_results"] == 0
    assert report["missing_results"] == 1
    assert report["full_capture_coverage"] is False
