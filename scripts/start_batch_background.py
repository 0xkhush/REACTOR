"""Start the resume-safe Mac inference batch detached from the terminal."""

import json
import os
import subprocess
import sys
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    output = ROOT / "artifacts" / "batch_inference"
    output.mkdir(parents=True, exist_ok=True)
    log = output / "night.log"
    with log.open("a", encoding="utf-8") as stream:
        command = [sys.executable, str(ROOT / "scripts" / "batch_infer.py")]
        if args.retry_failed:
            command.append("--retry-failed")
        if args.limit:
            command.extend(["--limit", str(args.limit)])
        worker = subprocess.Popen(command,
                                  cwd=ROOT, env=os.environ.copy(), stdin=subprocess.DEVNULL,
                                  stdout=stream, stderr=stream, start_new_session=True)
    keep_awake = subprocess.Popen(["caffeinate", "-i", "-w", str(worker.pid)], cwd=ROOT,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
    print(json.dumps({"batch_pid": worker.pid, "caffeinate_pid": keep_awake.pid,
                      "log": str(log), "manifest": str(output / "batch-manifest.json")}))


if __name__ == "__main__":
    main()
