"""Credential-free dataset check or one gated live FDB-v3 recording."""

import argparse
import asyncio
from contextlib import contextmanager, nullcontext
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from livekit import api

from reactor.config import ConfigurationError, load_config
from reactor.tools.benchmark import REVISION, UPSTREAM


ROOT = Path(__file__).resolve().parents[1]


def require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to convert the FDB WAV files; install it before a live run")


async def check_livekit_credentials(config, *, factory=api.LiveKitAPI):
    """A room-list metadata call checks project authentication before model inference."""
    client = factory(url=config.livekit_url, api_key=config.livekit_key, api_secret=config.livekit_secret)
    try:
        try:
            await client.room.list_rooms(api.ListRoomsRequest())
        except Exception as exc:
            if getattr(exc, "status", None) == 401:
                raise ConfigurationError(
                    "LiveKit project URL and API key/secret were rejected (401); verify they belong to one project"
                ) from None
            raise RuntimeError(f"LiveKit credential preflight failed ({type(exc).__name__})") from None
    finally:
        await client.aclose()


@contextmanager
def managed_worker(command: list[str], *, startup_seconds: float = 5, cwd: Path = ROOT, env=None):
    """Start the local agent, then stop and reap it even if inference fails."""
    proc = subprocess.Popen(command, cwd=cwd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(startup_seconds)
        if proc.poll() is not None:
            raise RuntimeError("Local LiveKit worker exited during startup")
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


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
    parser.add_argument("--start-worker", action="store_true", help="Start and stop the local agent for this run")
    parser.add_argument("--dataset", type=Path, default=ROOT / "fdb_v3_data_released")
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    parser.add_argument("--input", type=Path, help="An input.wav inside the dataset")
    args = parser.parse_args()
    source = verify_upstream(args.upstream)
    files = check_dataset(args.dataset)
    if not args.run:
        if args.start_worker:
            parser.error("--start-worker requires --run")
        print(json.dumps({"mode": "offline_check", "upstream": REVISION, "recordings": len(files)}))
        return

    config = load_config(ROOT / ".env.local")
    config.require_live_access()
    if config.mode != "benchmark":
        raise ValueError("Set REACTOR_MODE=benchmark for a benchmark recording")
    require_ffmpeg()
    asyncio.run(check_livekit_credentials(config))
    input_path = args.input.resolve() if args.input else files[0]
    if input_path not in [path.resolve() for path in files]:
        raise ValueError("--input must be one of the dataset's input.wav recordings")
    room = f"reactor-smoke-{uuid.uuid4().hex[:12]}"
    output = ROOT / "artifacts" / f"{room}.wav"
    output.parent.mkdir(exist_ok=True)
    env = {**os.environ, "LIVEKIT_URL": config.livekit_url,
           "LIVEKIT_API_KEY": config.livekit_key, "LIVEKIT_API_SECRET": config.livekit_secret}
    worker = (managed_worker([sys.executable, "-m", "reactor.voice.agent", "dev"], env=env)
              if args.start_worker else nullcontext())
    with worker:
        subprocess.run([sys.executable, str(source / "livekit_inference.py"),
                        "-i", str(input_path), "-o", str(output), "--room", room],
                       cwd=source, env=env, check=True, timeout=90)
    calls = matching_calls(Path("/tmp/agent_tool_calls.log"), room)
    if not calls:
        raise RuntimeError("No actual tool calls were logged for the smoke room")
    print(json.dumps({"mode": "live_smoke", "room": room, "calls": calls,
                      "output_audio": str(output)}))


if __name__ == "__main__":
    main()
