"""Kaggle T4 ASR and exact-match scoring over captured REACTOR audio/tool logs."""

import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


FDB_SHA = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"
REACTOR_SHA = "b2622ba1a52373c647a8c98e43cccba60a95f77f"
PROVIDER = "gemini2_5"
MODEL = "nvidia/parakeet-tdt-0.6b-v2"
AUDIO_DATASET = Path("/kaggle/input/datasets/zxkhush/reactor-fdb-v3-audio/recordings")
RESULTS_DATASET = Path("/kaggle/input/datasets/zxkhush/reactor-fdb-v3-results")
WORK = Path("/kaggle/working/reactor-asr-eval")
FOLDER = re.compile(r"^(.+)_([0-9a-f]{24})$")


def prepare_workspace(work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    return work


def publish_reports(work: Path, destination: Path) -> Path:
    work, destination = work.resolve(), destination.resolve()
    if destination == work or work in destination.parents:
        raise ValueError("Published report directory must be outside the temporary workspace")
    report_source = work / "reports"
    if not report_source.is_dir():
        raise FileNotFoundError("ASR evaluation reports are missing")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    shutil.copytree(report_source, destination / "reports")
    shutil.rmtree(work)
    return destination


def normalize_words(hypothesis):
    text = getattr(hypothesis, "text", "") or (hypothesis if isinstance(hypothesis, str) else "")
    timestamp = getattr(hypothesis, "timestamp", {}) or {}
    words = timestamp.get("word", []) if isinstance(timestamp, dict) else []
    chunks = [{"text": word["word"].strip(), "timestamp": [float(word["start"]), float(word["end"])]}
              for word in words]
    if not text and chunks:
        text = " ".join(chunk["text"] for chunk in chunks)
    return " ".join(text.split()), chunks


def speech_end(chunks):
    if not chunks:
        return 0.0
    for current, following in zip(chunks, chunks[1:]):
        if following["timestamp"][0] - current["timestamp"][1] > 2.0:
            return current["timestamp"][1]
    return chunks[-1]["timestamp"][1]


def relative_call_times(calls: list[dict], stream_start: float | None) -> list[dict]:
    calls = json.loads(json.dumps(calls))
    if stream_start is not None:
        for call in calls:
            for key in ("timestamp_start", "timestamp_end"):
                if isinstance(call.get(key), (int, float)) and call[key] >= stream_start - 120:
                    call[key] = round(call[key] - stream_start, 2)
    return calls


def strict_coverage(*, expected: int, results: int):
    return {"expected": expected, "results": results,
            "missing": max(0, expected - results),
            "full_coverage": expected == results, "official_score": False}


def result_coverage(expected: int, results: list[dict]) -> dict:
    completed = sum(result.get("status") == "completed" for result in results)
    no_tool = sum(result.get("status") == "no_tool_call" for result in results)
    failures = sum(result.get("status") in ("inference_failed", "no_output", "no_capture_result")
                   for result in results)
    return {"expected_recordings": expected, "captured_results": len(results),
            "remaining": max(0, expected - len(results)), "completed": completed,
            "no_tool_call": no_tool, "inference_failed": failures,
            "full_coverage": len(results) == expected and failures == 0,
            "official_score": False}


def command(args, *, cwd=None, timeout=1800):
    subprocess.run(args, cwd=cwd, check=True, timeout=timeout)


def checkout_pinned(remote: str, destination: Path, revision: str) -> Path:
    if destination.exists():
        try:
            actual = subprocess.check_output(
                ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except subprocess.CalledProcessError:
            raise RuntimeError(f"Existing path is not a pinned Git checkout: {destination}") from None
        if actual != revision:
            subprocess.run(["git", "-C", str(destination), "fetch", "origin", revision],
                           check=True, timeout=1200)
            subprocess.run(["git", "-C", str(destination), "checkout", "--detach", revision],
                           check=True, timeout=120)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    command(["git", "clone", "--filter=blob:none", remote, str(destination)], timeout=1200)
    command(["git", "-C", str(destination), "checkout", "--detach", revision], timeout=120)
    return destination


def safe_extract(zip_path: Path, destination: Path):
    with zipfile.ZipFile(zip_path) as archive:
        root = destination.resolve()
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError("Results archive contains an unsafe path")
        archive.extractall(destination)


def locate_results_source(dataset: Path) -> Path:
    extracted = dataset / "results"
    archive = dataset / "results.zip"
    if extracted.is_dir():
        return extracted
    if archive.is_file():
        return archive
    raise FileNotFoundError(f"Kaggle results dataset has no results/ folder or results.zip: {dataset}")


def clone_sources():
    prepare_workspace(WORK)
    repo = WORK / "REACTOR"
    checkout_pinned("https://github.com/0xkhush/REACTOR.git", repo, REACTOR_SHA)
    fdb = repo / "vendor" / "Full-Duplex-Bench"
    checkout_pinned("https://github.com/DanielLin94144/Full-Duplex-Bench.git", fdb, FDB_SHA)
    return repo, fdb / "v3"


def transcribe_all(dataset: Path, upstream: Path, result_payloads: dict):
    import torch
    import nemo.collections.asr as nemo_asr
    from pydub import AudioSegment

    if not torch.cuda.is_available():
        raise RuntimeError("Kaggle notebook did not allocate a CUDA GPU")
    print("GPU:", torch.cuda.get_device_name(0), "PyTorch CUDA:", torch.version.cuda)
    model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL).cuda()
    benchmark = json.loads((upstream / "benchmark_data_v2.json").read_text())
    scenarios = {item["id"]: item for item in benchmark["scenarios"]}
    folders = sorted(dataset.glob("*_*"))
    captured_results = []
    for index, folder in enumerate(folders, 1):
        match = FOLDER.fullmatch(folder.name)
        if not match:
            continue
        example_id = match.group(1)
        input_path = folder / "input.wav"
        captured = result_payloads.get(folder.name, {})
        result = {
            "pid": match.group(2), "example_id": example_id,
            "category": scenarios.get(example_id, {}).get("domain", "unknown"),
            "title": scenarios.get(example_id, {}).get("title", example_id),
            "provider": PROVIDER, "room_name": captured.get("room"),
            "stream_start_time": captured.get("stream_start_time"),
            "actual_tool_calls": relative_call_times(
                captured.get("actual_tool_calls", []), captured.get("stream_start_time")),
        }
        input_mono = folder / "input_mono.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-ac", "1", str(input_mono)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        input_hyp = model.transcribe([str(input_mono)], timestamps=True)[0]
        input_text, input_chunks = normalize_words(input_hyp)
        result["input_transcript"] = input_text
        result["input_asr_chunks"] = input_chunks
        user_end = speech_end(input_chunks)
        result["user_speech_end_rel"] = user_end

        output_path = folder / f"output_{PROVIDER}.wav"
        if output_path.is_file():
            output_hyp = model.transcribe([str(output_path)], timestamps=True)[0]
            output_text, output_chunks = normalize_words(output_hyp)
            result["transcript"] = output_text
            result["asr_chunks"] = output_chunks
            audio = AudioSegment.from_file(str(output_path))
            first_speech = output_chunks[0]["timestamp"][0] if output_chunks else len(audio) / 1000.0
            result["latency"] = {"input_duration_s": round(len(AudioSegment.from_file(str(input_path)))/1000, 3),
                                 "output_duration_s": round(len(audio)/1000, 3),
                                 "first_speech_s": round(first_speech, 3)}
            result["perceived_total_latency"] = round(first_speech - user_end, 3)
            result["status"] = captured.get("status", "completed")
        else:
            result["transcript"] = ""
            result["asr_chunks"] = []
            result["latency"] = {"error": "captured output WAV missing"}
            result["status"] = captured.get("status", "no_capture_result")
        (folder / f"result_{PROVIDER}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        captured_results.append(result)
        if index % 10 == 0 or index == len(folders):
            print(json.dumps({"transcribed": index, "total": len(folders)}), flush=True)
    reports = WORK / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "run_manifest.json").write_text(json.dumps({
        **result_coverage(len(folders), captured_results), "provider": PROVIDER,
        "model": "gemini-2.5-flash-native-audio-preview-12-2025",
        "judge": "none", "score_mode": "exact_match_tool_only",
        "asr_model": MODEL,
    }, indent=2) + "\n")


def call_timestamps_relative(calls: list[dict], stream_start: float | None) -> list[dict]:
    return relative_call_times(calls, stream_start)


def parse_results_bundle(capture_dir: Path, dataset: Path) -> dict:
    payloads = {}
    for folder in capture_dir.iterdir():
        if not folder.is_dir() or not FOLDER.fullmatch(folder.name):
            continue
        result_path = folder / "result.json"
        if not result_path.is_file():
            continue
        payload = json.loads(result_path.read_text())
        payloads[folder.name] = payload
        target = dataset / folder.name
        target.mkdir(parents=True, exist_ok=True)
        audio = folder / "output.wav"
        if audio.is_file():
            shutil.copy2(audio, target / f"output_{PROVIDER}.wav")
    return payloads


def stage_inputs(audio_root: Path, dataset: Path):
    dataset.mkdir(parents=True, exist_ok=True)
    for input_path in audio_root.glob("*/input.wav"):
        target = dataset / input_path.parent.name
        target.mkdir(exist_ok=True)
        shutil.copy2(input_path, target / "input.wav")


def install_asr():
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
                    "nemo_toolkit[asr]==2.5.3", "pydub", "ffmpeg-python"],
                   check=True, timeout=2400)


def run_evaluators(upstream: Path, dataset: Path, reports: Path):
    reports.mkdir(parents=True, exist_ok=True)
    for script, name in [("evaluate_tool_calls.py", "tool_accuracy_exact.json"),
                         ("evaluate_pass_rate.py", "strict_pass_exact.json")]:
        subprocess.run([sys.executable, str(upstream / script), "--benchmark",
                        str(upstream / "benchmark_data_v2.json"), "--results-dir", str(dataset),
                        "--provider", PROVIDER, "--output", str(reports / name)],
                       cwd=upstream, check=True, timeout=1800)


def main():
    if "--diagnose" in sys.argv:
        print(json.dumps({"mode": "offline_diagnostic", "asr_model": MODEL,
                          "benchmark_revision": FDB_SHA, "judge": "none"}))
        return
    if "--worker" in sys.argv:
        upstream = WORK / "REACTOR" / "vendor" / "Full-Duplex-Bench" / "v3"
        dataset = WORK / "fdb_v3_data_released"
        payload_file = WORK / "capture-payloads.json"
        payloads = json.loads(payload_file.read_text()) if payload_file.is_file() else {}
        transcribe_all(dataset, upstream, payloads)
        return
    results_source = locate_results_source(RESULTS_DATASET)
    if not AUDIO_DATASET.is_dir():
        raise FileNotFoundError("Attach both private Kaggle datasets: audio inputs and batch results")
    prepare_workspace(WORK)
    repo, upstream = clone_sources()
    dataset = WORK / "fdb_v3_data_released"
    stage_inputs(AUDIO_DATASET, dataset)
    capture = WORK / "captured-results"
    if results_source.is_file():
        capture.mkdir(parents=True, exist_ok=True)
        safe_extract(results_source, capture)
    else:
        capture = results_source
    payloads = parse_results_bundle(capture, dataset)
    (WORK / "capture-payloads.json").write_text(json.dumps(payloads))
    install_asr()
    worker = subprocess.run([sys.executable, __file__, "--worker"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=21600)
    if worker.returncode:
        raise RuntimeError("Parakeet worker failed: " + "\n".join(worker.stdout.splitlines()[-30:]))
    run_evaluators(upstream, dataset, WORK / "reports")
    result_files = list(dataset.glob(f"*/result_{PROVIDER}.json"))
    status_results = [json.loads(path.read_text()) for path in result_files]
    with (WORK / "reports" / "captured_results.jsonl").open("w") as evidence:
        for result in status_results:
            evidence.write(json.dumps(result, ensure_ascii=False) + "\n")
    report = {**result_coverage(len(list(AUDIO_DATASET.glob("*/input.wav"))), status_results),
              "provider": PROVIDER, "asr_model": MODEL, "benchmark_revision": FDB_SHA,
              "judge": "none", "score_mode": "exact_match_tool_only"}
    (WORK / "reports" / "run_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    destination = publish_reports(WORK, Path("/kaggle/working/reactor-final-results"))
    print(json.dumps({**report, "published_reports": str(destination / "reports")}, indent=2))


if __name__ == "__main__":
    main()
