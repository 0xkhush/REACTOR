"""Credential-free dataset check or one gated live FDB-v3 recording."""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from reactor.config import load_config
from reactor.tools.benchmark import REVISION, UPSTREAM


ROOT = Path(__file__).resolve().parents[1]


def check_dataset(root: Path) -> list[Path]:
    recordings = sorted(root.glob("*/input.wav"))
    if not recordings:
        raise ValueError(f"no input.wav recordings under {root}")
    return recordings


def matching_calls(log: Path, room: str) -> list[str]:
    if not log.exists():
        return []
    return [row["call"]["function"] for line in log.read_text().splitlines()
            if (row := json.loads(line)).get("room") == room]


def count_completed(root: Path, provider: str) -> tuple[int, int]:
    reports = list(root.glob(f"*/result_{provider}.json"))
    complete = sum(json.loads(report.read_text()).get("status") == "completed" for report in reports)
    return complete, len(reports) - complete


def verify_upstream(path: Path) -> Path:
    source = path / "v3"
    if not (source / "livekit_inference.py").is_file():
        raise FileNotFoundError("Run python scripts/setup_fdb.py before running FDB-v3")
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != REVISION:
        raise ValueError("FDB-v3 checkout is not at the pinned revision")
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Stream one example to an already-running agent")
    parser.add_argument("--dataset", type=Path, default=ROOT / "fdb_v3_data_released")
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    parser.add_argument("--input", type=Path, help="An input.wav inside the dataset")
    args = parser.parse_args()
    source = verify_upstream(args.upstream)
    files = check_dataset(args.dataset)
    if not args.run:
        print(json.dumps({"mode": "offline_check", "upstream": REVISION, "recordings": len(files)}))
        return

    config = load_config(ROOT / ".env.local")
    config.require_live_access()
    if config.mode != "benchmark":
        raise ValueError("Set REACTOR_MODE=benchmark for a benchmark recording")
    input_path = args.input.resolve() if args.input else files[0]
    if input_path not in [path.resolve() for path in files]:
        raise ValueError("--input must be one of the dataset's input.wav recordings")
    room = f"reactor-smoke-{uuid.uuid4().hex[:12]}"
    output = ROOT / "artifacts" / f"{room}.wav"
    output.parent.mkdir(exist_ok=True)
    env = {**os.environ, "LIVEKIT_URL": config.livekit_url,
           "LIVEKIT_API_KEY": config.livekit_key, "LIVEKIT_API_SECRET": config.livekit_secret}
    # This client assumes `python -m reactor.voice.agent dev` runs separately.
    subprocess.run([sys.executable, str(source / "livekit_inference.py"),
                    "-i", str(input_path), "-o", str(output), "--room", room],
                   cwd=source, env=env, check=True)
    calls = matching_calls(Path("/tmp/agent_tool_calls.log"), room)
    if not calls:
        raise RuntimeError("No actual tool calls were logged for the smoke room")
    print(json.dumps({"mode": "live_smoke", "room": room, "calls": calls,
                      "output_audio": str(output)}))


if __name__ == "__main__":
    main()
