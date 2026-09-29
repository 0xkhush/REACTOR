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
        import nemo.collections.asr as nemo_asr
        model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL).cuda()
        transcript = model.transcribe([str(audio)], timestamps=True)[0]
        report["word_count"] = len((getattr(transcript, "text", "") or "").split())
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
