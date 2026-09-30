import json
import zipfile

import pytest

from scripts.archive_evidence import archive_evaluation


def test_archiver_preserves_only_explicit_reports_not_secrets_or_scratch(tmp_path):
    source = tmp_path / "reports"
    source.mkdir()
    manifest = {"expected_recordings": 100, "captured_results": 100,
                "completed": 37, "no_tool_call": 63, "inference_failed": 0,
                "full_coverage": True, "official_score": False, "judge": "none"}
    (source / "run_manifest.json").write_text(json.dumps(manifest))
    (source / "strict_pass_exact.json").write_text(json.dumps({"total_scenarios": 100, "passed": 12, "failed": 88}))
    (source / "tool_accuracy_exact.json").write_text(json.dumps({"total_scenarios": 100}))
    (source / ".env.local").write_text("GOOGLE_API_KEY=never-upload-this")
    target = tmp_path / "evidence"
    summary = archive_evaluation(source, target)
    assert summary["strict_passed"] == 12
    with zipfile.ZipFile(target / "FDB_v3_exact_reports.zip") as archive:
        assert set(archive.namelist()) == {"run_manifest.json", "strict_pass_exact.json", "tool_accuracy_exact.json"}
        assert b"never-upload-this" not in b"".join(archive.read(name) for name in archive.namelist())


def test_archiver_rejects_inconsistent_denominators(tmp_path):
    source = tmp_path / "reports"
    source.mkdir()
    (source / "run_manifest.json").write_text('{"expected_recordings":100,"judge":"none"}')
    (source / "strict_pass_exact.json").write_text('{"total_scenarios":27,"passed":10,"failed":17}')
    (source / "tool_accuracy_exact.json").write_text('{"total_scenarios":27}')
    with pytest.raises(ValueError, match="denominator"):
        archive_evaluation(source, tmp_path / "out")
