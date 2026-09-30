"""Kaggle T4/NeMo preflight: transcribe one input, save a report, use no API keys."""

import json
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path


DATASET = Path("/kaggle/input/datasets/zxkhush/reactor-fdb-v3-audio")
OUTPUT = Path("/kaggle/working/gpu_probe_report.json")
MODEL = "nvidia/parakeet-tdt-0.6b-v2"


def choose_audio_sample(dataset: Path) -> Path:
    audio = list(dataset.glob("recordings/*/input.wav"))
    if not audio:
        raise FileNotFoundError("No recordings/*/input.wav found in the private audio dataset")
    return min(audio, key=lambda path: (path.stat().st_size, path.name))


def fresh_python(code: str, arguments: list[str]) -> str:
    completed = subprocess.run([sys.executable, "-c", code, *arguments], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200)
    if completed.returncode:
        raise RuntimeError("Fresh NeMo interpreter failed: " + completed.stdout[-1200:])
    return completed.stdout


def main():
    report = {"model": MODEL, "python": platform.python_version(), "status": "starting"}
    try:
        audio = choose_audio_sample(DATASET)
        import torch

        report["torch"] = torch.__version__
        report["cuda_available"] = torch.cuda.is_available()
        if not report["cuda_available"]:
            raise RuntimeError("Kaggle notebook has no CUDA GPU allocated")
        report["gpu"] = torch.cuda.get_device_name(0)
        report["sample"] = audio.parent.name

        # Run NeMo in a fresh process after installation so Kaggle's preinstalled
        # PyTorch remains importable when newly installed extras change modules.
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
                        "nemo_toolkit[asr]==2.5.3"], check=True, timeout=1800)
        start = time.monotonic()
        code = (
            "import json,sys\n"
            "import nemo.collections.asr as asr\n"
            "model=asr.models.ASRModel.from_pretrained(model_name=sys.argv[1]).cuda()\n"
            "result=model.transcribe([sys.argv[2]],timestamps=True)[0]\n"
            "print('REACTOR_ASR_JSON='+json.dumps({'words':len((getattr(result,'text','') or '').split())}))\n"
        )
        output = fresh_python(code, [MODEL, str(audio)])
        matches = [line.removeprefix("REACTOR_ASR_JSON=") for line in output.splitlines()
                   if line.startswith("REACTOR_ASR_JSON=")]
        if not matches:
            raise ValueError("NeMo produced no machine-readable transcript marker")
        report["word_count"] = json.loads(matches[-1])["words"]
        report["asr_seconds"] = round(time.monotonic() - start, 2)
        report["status"] = "ok"
    except BaseException as exc:
        # Kaggle may still persist /kaggle/working outputs when the probe fails.
        # Do not include exception text: external libraries may embed credentials.
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        report["error_detail"] = str(exc)[:1000]
        report["error_traceback_tail"] = traceback.format_exc()[-1200:]
        input_root = Path("/kaggle/input")
        report["mounted_datasets"] = sorted(p.name for p in input_root.iterdir()) if input_root.is_dir() else []
        report["audio_paths"] = [str(p.relative_to(input_root)) for p in list(input_root.rglob("input.wav"))[:3]] if input_root.is_dir() else []
        report["dataset_entries"] = sorted(p.name for p in DATASET.iterdir())[:10] if DATASET.is_dir() else []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
