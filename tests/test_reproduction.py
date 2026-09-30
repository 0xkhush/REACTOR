import json
import subprocess
import sys


def test_reproduction_help_exposes_offline_preflight_and_semantic_judge_option():
    result = subprocess.run([sys.executable, "scripts/reproduce.py", "--help"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "--check" in result.stdout
    assert "--use-llm" in result.stdout


def test_reproduction_module_invocation_supports_help():
    result = subprocess.run([sys.executable, "-m", "scripts.reproduce", "--help"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
