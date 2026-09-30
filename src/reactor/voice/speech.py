"""Free local speech for authoritative kitchen results; no hosted TTS calls."""

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from livekit import rtc


def synthesize(text: str) -> bytes:
    say, espeak = shutil.which("say"), shutil.which("espeak-ng") or shutil.which("espeak")
    ffmpeg = shutil.which("ffmpeg")
    if not (say or espeak) or not ffmpeg:
        raise RuntimeError("Install a local speech engine (macOS say or espeak-ng) and ffmpeg for kitchen confirmations")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("Kitchen speech must contain 1–1000 characters")
    with tempfile.TemporaryDirectory(prefix="reactor-speech-") as directory:
        audio = Path(directory) / ("speech.aiff" if say else "speech.wav")
        command = [say, "-v", "Samantha", "-o", str(audio), text] if say else [espeak, "-w", str(audio), text]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        result = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "24000",
                                 "-f", "s16le", "pipe:1"], check=True, capture_output=True, timeout=20)
        return result.stdout


async def local_audio(text: str):
    pcm = await asyncio.to_thread(synthesize, text)
    for offset in range(0, len(pcm), 960):  # 20 ms of mono PCM16 at 24 kHz
        chunk = pcm[offset:offset + 960]
        yield rtc.AudioFrame(chunk, sample_rate=24000, num_channels=1, samples_per_channel=len(chunk) // 2)
