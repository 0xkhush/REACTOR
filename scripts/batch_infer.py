"""Resume-safe FDB-v3 audio capture on Mac; Kaggle later runs Parakeet ASR."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

if __package__:
    from .evaluate_smoke import actual_calls_for_room
    from .smoke_fdb import ROOT, UPSTREAM, check_dataset, check_livekit_credentials, managed_worker, require_ffmpeg, verify_upstream
else:
    from evaluate_smoke import actual_calls_for_room
    from smoke_fdb import ROOT, UPSTREAM, check_dataset, check_livekit_credentials, managed_worker, require_ffmpeg, verify_upstream
from reactor.config import load_config


def pending_inputs(source: Path, output: Path, *, retry_failed: bool = False) -> list[Path]:
    pending = []
    for audio in sorted(source.glob("*/input.wav")):
        result_file = output / audio.parent.name / "result.json"
        if not result_file.is_file():
            pending.append(audio)
            continue
        try:
            status = json.loads(result_file.read_text()).get("status")
        except (ValueError, OSError):
            status = None
        if status == "completed" or status == "no_tool_call":
            continue
        if retry_failed and status == "inference_failed":
            # Retry only if the inference client did not leave an output WAV;
            # a present/partial recording may correspond to a live model request.
            if not (result_file.parent / "output.wav").exists():
                pending.append(audio)
            continue
        # Existing failures remain recorded rather than silently replayed.
    return pending


def report_progress(*, expected: int, terminal: dict[str, str]) -> dict:
    return {"expected": expected,
            "completed": sum(status == "completed" for status in terminal.values()),
            "no_tool_call": sum(status == "no_tool_call" for status in terminal.values()),
            "inference_failed": sum(status == "inference_failed" for status in terminal.values()),
            "remaining": max(0, expected - len(terminal)),
            "official_score": False, "mode": "audio_capture_no_asr"}


def relative_calls(calls: list[dict], stream_start: float | None) -> list[dict]:
    adjusted = json.loads(json.dumps(calls))
    if stream_start is None:
        return adjusted
    for call in adjusted:
        for key in ("timestamp_start", "timestamp_end"):
            if isinstance(call.get(key), (int, float)):
                call[key] = round(call[key] - stream_start, 2)
    return adjusted


def scrub(text: str, secrets) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix(".tmp")
    target.write_text(json.dumps(value, indent=2) + "\n")
    target.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "fdb_v3_data_released")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "batch_inference")
    parser.add_argument("--limit", type=int, default=None, help="Maximum new recordings to capture this run")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry pre-output connection failures; completed/no-tool runs stay fixed")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    config = load_config(ROOT / ".env.local")
    config.require_live_access()
    if config.mode != "benchmark":
        raise ValueError("Set REACTOR_MODE=benchmark for FDB batch inference")
    require_ffmpeg()
    source = verify_upstream(UPSTREAM)
    inputs = check_dataset(args.dataset)
    asyncio.run(check_livekit_credentials(config))
    args.output.mkdir(parents=True, exist_ok=True)
    pending = pending_inputs(args.dataset, args.output, retry_failed=args.retry_failed)
    if args.limit is not None:
        pending = pending[:args.limit]
    terminal = {}
    for old in args.output.glob("*/result.json"):
        try:
            terminal[old.parent.name] = json.loads(old.read_text())["status"]
        except (ValueError, KeyError):
            terminal[old.parent.name] = "inference_failed"
    if not pending:
        print(json.dumps(report_progress(expected=len(inputs), terminal=terminal), indent=2))
        return
    env = {**os.environ, "LIVEKIT_URL": config.livekit_url,
           "LIVEKIT_API_KEY": config.livekit_key, "LIVEKIT_API_SECRET": config.livekit_secret,
           "REACTOR_MODE": "benchmark"}
    secret_values = (config.livekit_key, config.livekit_secret, config.google_key)
    with managed_worker([sys.executable, "-m", "reactor.voice.agent", "dev", "--no-reload"],
                        env=env, secrets=secret_values, startup_seconds=6):
        for index, audio in enumerate(pending, 1):
            folder = args.output / audio.parent.name
            folder.mkdir(exist_ok=True)
            output = folder / "output.wav"
            room = "reactor-batch-" + uuid.uuid4().hex[:12]
            result = {"example_id": audio.parent.name.rsplit("_", 1)[0],
                      "room": room, "input": str(audio), "output": str(output),
                      "model": config.model, "provider": "gemini2_5",
                      "status": "inference_failed", "actual_tool_calls": []}
            start = time.monotonic()
            try:
                completed = subprocess.run([
                    sys.executable, str(source / "livekit_inference.py"),
                    "-i", str(audio), "-o", str(output), "--room", room,
                ], cwd=source, env=env, capture_output=True, text=True, timeout=110)
                if completed.returncode:
                    result["error"] = scrub("\n".join(completed.stderr.splitlines()[-5:]), secret_values)[:700]
                else:
                    stream_start = next((float(line.split(": ", 1)[1]) for line in completed.stdout.splitlines()
                                         if line.startswith("STREAM_START_TIME: ")), None)
                    result["stream_start_time"] = stream_start
                    result["actual_tool_calls"] = relative_calls(
                        actual_calls_for_room(Path("/tmp/agent_tool_calls.log"), room), stream_start
                    )
                    result["status"] = "completed" if result["actual_tool_calls"] else "no_tool_call"
            except subprocess.TimeoutExpired:
                result["error"] = "FDB audio replay exceeded 110 seconds"
            result["elapsed_seconds"] = round(time.monotonic() - start, 2)
            write_json(folder / "result.json", result)
            terminal[audio.parent.name] = result["status"]
            progress = report_progress(expected=len(inputs), terminal=terminal)
            write_json(args.output / "batch-manifest.json", progress)
            print(json.dumps({"index": index, "total_new": len(pending), "example": audio.parent.name,
                              "status": result["status"], "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    print(json.dumps(report_progress(expected=len(inputs), terminal=terminal), indent=2))


if __name__ == "__main__":
    main()
