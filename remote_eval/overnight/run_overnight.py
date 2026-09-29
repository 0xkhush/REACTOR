"""Private Kaggle GPU benchmark run; credentials only from Kaggle Secrets."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_REVISION = "b2622ba"
FDB_REVISION = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
PROVIDER = "gemini2_5"
DATASET = Path("/kaggle/input/datasets/zxkhush/reactor-fdb-v3-audio/recordings")
WORK = Path("/kaggle/working")
TEMP = Path("/kaggle/temp")
SECRET_NAMES = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GOOGLE_API_KEY")


def count_recordings(directory: Path) -> int:
    count = len(list(directory.glob("*/input.wav")))
    if not count:
        raise ValueError(f"No input.wav recordings found under {directory}")
    return count


def report_counts(*, expected: int, completed: int, failed: int) -> dict:
    return {"expected": expected, "completed": completed, "failed": failed,
            "missing": max(0, expected - completed - failed),
            "full_coverage": expected == completed and failed == 0,
            "official_score": False, "judge": "none"}


def scrub(text: str, secrets) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def read_secrets(client):
    values = {}
    for label in SECRET_NAMES:
        try:
            values[label] = client.get_secret(label)
        except Exception:
            raise RuntimeError("Enable and grant the four Kaggle Secrets to this private notebook") from None
        if not values[label]:
            raise RuntimeError("Missing Kaggle Secrets value for label: " + label)
    return values


def command(argv, *, cwd=None, env=None, timeout=1800, secrets=()):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} command exited {result.returncode}: " +
                           scrub("\n".join(result.stdout.splitlines()[-20:]), secrets))
    return result.stdout


def status_files(dataset: Path):
    reports = list(dataset.glob(f"*/result_{PROVIDER}.json"))
    completed = failed = 0
    for file in reports:
        try:
            ok = json.loads(file.read_text()).get("status") == "completed"
        except (ValueError, OSError):
            ok = False
        completed += ok
        failed += not ok
    return completed, failed


def main():
    report = {"status": "starting", "provider": PROVIDER, "model": MODEL,
              "repo_commit": REPO_REVISION, "fdb_commit": FDB_REVISION,
              "official_score": False, "judge": "none"}
    WORK.mkdir(parents=True, exist_ok=True)
    report_path = WORK / "reactor-run-manifest.json"
    credentials = {}
    worker = None
    credential_file = TEMP / "reactor" / ".env.local"
    try:
        expected = count_recordings(DATASET)
        report["expected_recordings"] = expected
        import torch
        report["cuda"] = torch.cuda.is_available()
        report["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        if not report["cuda"]:
            raise RuntimeError("Kaggle accelerator was not allocated")

        from kaggle_secrets import UserSecretsClient
        credentials = read_secrets(UserSecretsClient())
        report["secret_labels_present"] = list(SECRET_NAMES)

        repo = TEMP / "reactor"
        command(["git", "clone", "--filter=blob:none", "https://github.com/0xkhush/REACTOR.git", str(repo)], timeout=1200)
        command(["git", "-C", str(repo), "checkout", "--detach", REPO_REVISION], timeout=120)
        (repo / "vendor").mkdir(exist_ok=True)
        command([sys.executable, str(repo / "scripts" / "setup_fdb.py")], cwd=repo, timeout=1200)
        source = repo / "vendor" / "Full-Duplex-Bench" / "v3"

        command([sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
                 "nemo_toolkit[asr]==2.5.3", "pydub", "ffmpeg-python"],
                timeout=2400, secrets=credentials.values())
        command([sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo) + "[voice]"],
                timeout=1800, secrets=credentials.values())
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA became unavailable after dependency installation")

        result_dir = WORK / "fdb_v3_data_released"
        shutil.copytree(DATASET, result_dir, dirs_exist_ok=True)
        credential_file.parent.mkdir(parents=True, exist_ok=True)
        credential_file.write_text("\n".join(f"{label}={credentials[label]}" for label in SECRET_NAMES) +
                                   "\nGOOGLE_LIVE_MODEL=" + MODEL +
                                   "\nREACTOR_MODE=benchmark\nREACTOR_FREE_QUOTA_CONFIRMED=yes\n")
        credential_file.chmod(0o600)
        env = {**os.environ, **credentials, "GOOGLE_LIVE_MODEL": MODEL,
               "REACTOR_FREE_QUOTA_CONFIRMED": "yes"}
        worker = subprocess.Popen([sys.executable, "-m", "reactor.voice.agent", "dev", "--no-reload"],
                                  cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
        if worker.poll() is not None:
            raise RuntimeError("LiveKit worker exited before the first recording")

        report["status"] = "running"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        start = time.monotonic()
        try:
            command([sys.executable, "run_tool_benchmark_all_released.py", "--provider", PROVIDER,
                     "--root_dir", str(result_dir), "--force"], cwd=source, env=env,
                    timeout=21600, secrets=credentials.values())
        finally:
            report["inference_seconds"] = round(time.monotonic() - start, 1)
            completed, failed = status_files(result_dir)
            report.update(report_counts(expected=expected, completed=completed, failed=failed))
            report_path.write_text(json.dumps(report, indent=2) + "\n")
        report["status"] = "inference_complete" if report["full_coverage"] else "partial"
        if completed:
            for evaluator, name in [("evaluate_tool_calls.py", "tool_accuracy_exact.json"),
                                    ("evaluate_pass_rate.py", "strict_pass_exact.json")]:
                try:
                    command([sys.executable, evaluator, "--benchmark", "benchmark_data_v2.json",
                             "--results-dir", str(result_dir), "--provider", PROVIDER,
                             "--output", str(WORK / name)], cwd=source, env=env,
                            timeout=1800, secrets=credentials.values())
                except Exception as exc:
                    report.setdefault("evaluation_errors", []).append(type(exc).__name__)
    except BaseException as exc:
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        report["error_detail"] = scrub(str(exc), credentials.values())[:2000]
    finally:
        if worker and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
        credential_file.unlink(missing_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
