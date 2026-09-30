"""Start the resume-safe Mac inference batch detached from the terminal."""

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "artifacts" / "batch_inference"
    output.mkdir(parents=True, exist_ok=True)
    log = output / "night.log"
    with log.open("a", encoding="utf-8") as stream:
        worker = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "batch_infer.py")],
                                  cwd=ROOT, env=os.environ.copy(), stdin=subprocess.DEVNULL,
                                  stdout=stream, stderr=stream, start_new_session=True)
    keep_awake = subprocess.Popen(["caffeinate", "-i", "-w", str(worker.pid)], cwd=ROOT,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
    print(json.dumps({"batch_pid": worker.pid, "caffeinate_pid": keep_awake.pid,
                      "log": str(log), "manifest": str(output / "batch-manifest.json")}))


if __name__ == "__main__":
    main()
