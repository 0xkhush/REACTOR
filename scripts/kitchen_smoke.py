"""One bounded LiveKit kitchen extension smoke with a synthesized self-correction."""

import asyncio
import json
import os
import subprocess
import sys
import uuid
import wave
from pathlib import Path

if __package__:
    from .smoke_fdb import ROOT, UPSTREAM, check_livekit_credentials, managed_worker, matching_calls, require_ffmpeg, verify_upstream
else:
    from smoke_fdb import ROOT, UPSTREAM, check_livekit_credentials, managed_worker, matching_calls, require_ffmpeg, verify_upstream
from reactor.config import load_config


def join_wav_turns(first: Path, second: Path, output: Path, *, pause_seconds: float,
                   trailing_seconds: float, lead_seconds: float = 0):
    chunks = []
    for path in (first, second):
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 48000:
                raise ValueError("Both speech turns must be mono PCM16 at 48000 Hz")
            chunks.append(wav.readframes(wav.getnframes()))
    silence = lambda seconds: b"\x00" * (int(48000 * seconds) * 2)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(silence(lead_seconds) + chunks[0] + silence(pause_seconds) +
                        chunks[1] + silence(trailing_seconds))


def speech_wav(text: str, name: str, folder: Path) -> Path:
    aiff = folder / (name + ".aiff")
    target = folder / (name + ".wav")
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), text], check=True, timeout=30)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", "-ac", "1",
                    "-acodec", "pcm_s16le", str(target)],
                   check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


def main():
    if sys.platform != "darwin":
        raise RuntimeError("This smoke generator needs the Mac say command")
    require_ffmpeg()
    config = load_config(ROOT / ".env.local")
    config.require_live_access()
    if config.mode != "kitchen":
        raise ValueError("Set REACTOR_MODE=kitchen for the extension smoke")
    asyncio.run(check_livekit_credentials(config))
    source = verify_upstream(UPSTREAM)
    folder = ROOT / "artifacts" / "kitchen-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    first = speech_wav("Please create a timer called pasta for ten minutes. Actually, make it seven minutes.", "first", folder)
    second = speech_wav("Please cancel the timer called pasta.", "second", folder)
    recording = folder / "conversation.wav"
    join_wav_turns(first, second, recording, pause_seconds=8, trailing_seconds=24, lead_seconds=12)
    room = "reactor-kitchen-" + uuid.uuid4().hex[:12]
    output = folder / (room + "-agent.wav")
    env = {**os.environ, "LIVEKIT_URL": config.livekit_url,
           "LIVEKIT_API_KEY": config.livekit_key, "LIVEKIT_API_SECRET": config.livekit_secret,
           "REACTOR_MODE": "kitchen"}
    with managed_worker([sys.executable, "-m", "reactor.voice.agent", "dev", "--no-reload"], env=env,
                        secrets=(config.livekit_key, config.livekit_secret, config.google_key)) as worker:
        subprocess.run([sys.executable, str(source / "livekit_inference.py"), "-i", str(recording),
                        "-o", str(output), "--room", room],
                       cwd=source, env=env, check=True, timeout=100)
        calls = matching_calls(Path("/tmp/agent_tool_calls.log"), room)
        if "create_timer" not in calls or "cancel_timer" not in calls:
            print("Worker diagnostics (redacted):", "\n".join(worker.recent_output), file=sys.stderr)
    result = {"room": room, "calls": calls, "output_audio": str(output),
              "extension_calls_complete": "create_timer" in calls and "cancel_timer" in calls}
    print(json.dumps(result, indent=2))
    if not result["extension_calls_complete"]:
        raise RuntimeError("Voice extension did not make both required timer calls")


if __name__ == "__main__":
    main()
