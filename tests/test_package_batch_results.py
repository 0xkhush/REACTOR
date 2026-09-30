import json
import zipfile

from scripts.package_batch_results import package_results


def test_package_results_excludes_keys_answers_and_unrelated_audio(tmp_path):
    source = tmp_path / "batch"
    case = source / "finance_01_65e8cf8f4c7424fa062e54a3"
    case.mkdir(parents=True)
    (case / "output.wav").write_bytes(b"RIFF-AGENT-AUDIO")
    (case / "result.json").write_text(json.dumps({"status": "completed", "actual_tool_calls": []}))
    (case / "metadata.json").write_text('{"expected_tool_calls":"ANSWER"}')
    (source / ".env.local").write_text("GOOGLE_API_KEY=TOPSECRET")
    dest = tmp_path / "private-upload"

    report = package_results(source, dest, dataset_id="zxkhush/reactor-fdb-v3-results")

    assert report["examples"] == 1
    with zipfile.ZipFile(dest / "results.zip") as archive:
        assert set(archive.namelist()) == {
            case.name + "/output.wav", case.name + "/result.json",
        }
        assert b"TOPSECRET" not in archive.read(case.name + "/result.json")
    assert "TOPSECRET" not in (dest / "manifest.json").read_text()


def test_package_results_marks_partial_coverage_in_manifest(tmp_path):
    source = tmp_path / "batch"
    source.mkdir()
    (source / "batch-manifest.json").write_text(json.dumps({"expected": 100, "remaining": 98}))
    case = source / "travel_01_65e8cf8f4c7424fa062e54a3"
    case.mkdir()
    (case / "result.json").write_text('{"status":"no_tool_call"}')
    destination = tmp_path / "out"
    report = package_results(source, destination, dataset_id="zxkhush/reactor-fdb-v3-results")
    assert report["expected"] == 100
    assert report["remaining"] == 98
    assert report["examples"] == 1
