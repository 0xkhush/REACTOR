import json
import subprocess
import sys

from reactor.demo import run_demo


async def test_offline_demo_corrects_deduplicates_and_cancels_timer():
    result = await run_demo()
    assert result["mode"] == "scripted_offline"
    assert result["obsolete_proposal"]["status"] == "cancelled_before_dispatch"
    assert result["created_timer"]["duration_seconds"] == 420
    assert result["duplicate_operation_id"] == result["create_operation_id"]
    assert result["cancellation"]["state"] == "cancelled"
    assert len(result["timers"]) == 1


def test_demo_cli_outputs_machine_readable_json():
    result = subprocess.run([sys.executable, "-m", "reactor.demo"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mode"] == "scripted_offline"
