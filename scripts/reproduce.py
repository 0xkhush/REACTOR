"""Single-machine FDB-v3 exact-match reproduction; requires Linux CUDA and free model allowance."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from .smoke_fdb import ROOT, check_dataset, count_completed, verify_upstream, check_livekit_credentials
else:
    from smoke_fdb import ROOT, check_dataset, count_completed, verify_upstream, check_livekit_credentials
from reactor.config import load_config


def require_cuda():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("The pinned upstream Parakeet ASR runner requires NVIDIA CUDA")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "fdb_v3_data_released")
    parser.add_argument("--upstream", type=Path, default=ROOT / "vendor" / "Full-Duplex-Bench")
    parser.add_argument("--check", action="store_true", help="Offline data/config check; makes no API request")
    parser.add_argument("--use-llm", action="store_true", help="Use the upstream semantic judge; evaluator supplies OPENAI_API_KEY")
    args = parser.parse_args()
    args.upstream = args.upstream.resolve()
    args.dataset = args.dataset.resolve()
    source = verify_upstream(args.upstream)
    inputs = check_dataset(args.dataset)
    config = load_config(ROOT / ".env.local")
    if config.mode != "benchmark":
        raise RuntimeError("Reproduction requires REACTOR_MODE=benchmark")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Install ffmpeg before running the upstream ASR pipeline")
    if args.check:
        print(json.dumps({"mode": "offline_preflight", "recordings": len(inputs),
                          "model": config.model, "credentials_populated": True,
                          "hosted_requests": 0, "cuda_not_checked": True}))
        return
    config.require_live_access()
    if args.use_llm and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("--use-llm requires evaluator-supplied OPENAI_API_KEY")
    require_cuda()
    import asyncio
    asyncio.run(check_livekit_credentials(config))
    provider = "gemini2_5" if config.model.startswith("gemini-2.5-") else "gemini3_1" if config.model.startswith("gemini-3.1-") else None
    if provider is None:
        raise RuntimeError("Set GOOGLE_LIVE_MODEL to a supported FDB-v3 Gemini Live provider")
    env = {**os.environ, "LIVEKIT_URL": config.livekit_url,
           "LIVEKIT_API_KEY": config.livekit_key, "LIVEKIT_API_SECRET": config.livekit_secret}
    worker = subprocess.Popen([sys.executable, "-m", "reactor.voice.agent", "dev", "--no-reload"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(8)
        if worker.poll() is not None:
            raise RuntimeError("LiveKit worker exited during startup; run it manually for diagnostics")
        subprocess.run([sys.executable, "run_tool_benchmark_all_released.py", "--provider", provider,
                        "--root_dir", str(args.dataset), "--force"], cwd=source, env=env, check=True, timeout=21600)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    completed, failed = count_completed(args.dataset, provider)
    if completed != len(inputs) or failed:
        raise RuntimeError(f"Incomplete benchmark: {completed}/{len(inputs)} completed, {failed} failed")
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    for program, filename in [("evaluate_tool_calls.py", "tool_accuracy"),
                              ("evaluate_pass_rate.py", "strict_pass_rate")]:
        command = [sys.executable, program, "--benchmark", "benchmark_data_v2.json",
                        "--results-dir", str(args.dataset), "--provider", provider,
                        "--output", str(artifacts / f"{filename}_{provider}_{'semantic' if args.use_llm else 'exact'}.json")]
        if args.use_llm:
            command.append("--use-llm")
        subprocess.run(command, cwd=source, env=env, check=True, timeout=1800)
    print(f"{'Semantic' if args.use_llm else 'Exact-match development'} evaluation: {completed}/{len(inputs)} completed.")
    print("These local reports are not the organizers' scored rerun.")


if __name__ == "__main__":
    main()
