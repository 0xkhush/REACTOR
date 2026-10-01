"""Replay original audio only after REACTOR explicitly signals session readiness.

The upstream checkout stays pinned/unmodified. WAV helpers come from its client;
startup waiting and arrival-aligned capture are local benchmark harness behavior.
"""

import argparse
import asyncio
import importlib.util
import time
from pathlib import Path

from livekit import api, rtc

if __package__:
    from .smoke_fdb import ROOT, UPSTREAM, require_ffmpeg, verify_upstream
else:
    from smoke_fdb import ROOT, UPSTREAM, require_ffmpeg, verify_upstream
from reactor.config import load_config


READY_ATTRIBUTE = "reactor.ready"
CAPTURE_RATE = 24000
PUBLISH_RATE = 48000


async def wait_for_agent_ready(room, *, timeout=180):
    changed = asyncio.Event()
    disconnected = False

    def notify(*args):
        changed.set()

    def disconnect(*args):
        nonlocal disconnected
        disconnected = True
        changed.set()

    registrations = [("participant_connected", notify), ("participant_attributes_changed", notify),
                     ("disconnected", disconnect)]
    for name, callback in registrations:
        room.on(name, callback)

    async def wait():
        while True:
            changed.clear()
            if disconnected:
                raise ConnectionError("Room disconnected before agent readiness")
            candidates = [participant for participant in room.remote_participants.values()
                          if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
                          and participant.attributes.get(READY_ATTRIBUTE) == "1"]
            if len(candidates) > 1:
                raise RuntimeError("Multiple ready agents; benchmark room is not isolated")
            if candidates:
                return candidates[0]
            await changed.wait()

    try:
        return await asyncio.wait_for(wait(), timeout)
    finally:
        for name, callback in registrations:
            room.off(name, callback)


def record_frame(buffer, frame, *, sample_rate, elapsed_seconds, write_pos):
    samples = len(frame) // 2
    start = max(write_pos, round(elapsed_seconds * sample_rate) - samples, 0)
    end = min(start + samples, len(buffer) // 2)
    if start < end:
        buffer[start * 2:end * 2] = frame[:(end - start) * 2]
    return max(write_pos, min(end, len(buffer) // 2))


def audio_helpers(upstream=UPSTREAM):
    source = verify_upstream(upstream)
    spec = importlib.util.spec_from_file_location("fdb_replay_audio_helpers", source / "livekit_inference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run(input_wav: Path, output_wav: Path, room_name: str, *, ready_timeout=180, upstream=UPSTREAM):
    config = load_config(ROOT / ".env.local")
    config.require_live_access()
    require_ffmpeg()
    helpers = audio_helpers(upstream)
    pcm, rate, channels = helpers.read_wav_pcm16(str(input_wav), PUBLISH_RATE)
    duration = len(pcm) / (2 * rate * channels)
    output = bytearray(round(duration * CAPTURE_RATE) * 2)
    room = rtc.Room()
    source = rtc.AudioSource(rate, channels)
    started = asyncio.Event()
    stop = asyncio.Event()
    streams = []
    stream_start = None
    selected_identity = None

    async def receive(track, identity):
        stream = rtc.AudioStream(track, sample_rate=CAPTURE_RATE, num_channels=1)
        position = 0
        try:
            await started.wait()
            if identity != selected_identity:
                return
            async for event in stream:
                if stop.is_set():
                    break
                position = record_frame(output, bytes(event.frame.data), sample_rate=CAPTURE_RATE,
                                        elapsed_seconds=time.monotonic() - stream_start, write_pos=position)
                if position >= len(output) // 2:
                    break
        finally:
            await stream.aclose()

    @room.on("track_subscribed")
    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            streams.append(asyncio.create_task(receive(track, participant.identity)))

    token = (api.AccessToken(config.livekit_key, config.livekit_secret)
             .with_identity("wav-file-user").with_name("WAV File User")
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    try:
        await asyncio.wait_for(room.connect(config.livekit_url, token), 30)
        local_track = rtc.LocalAudioTrack.create_audio_track("wav-input", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(local_track, options)
        ready_start = time.monotonic()
        participant = await wait_for_agent_ready(room, timeout=ready_timeout)
        selected_identity = participant.identity
        print(f"AGENT_READY_WAIT_SECONDS: {time.monotonic() - ready_start:.3f}", flush=True)
        stream_start = time.monotonic()
        print(f"STREAM_START_TIME: {time.time()}", flush=True)
        started.set()
        chunk_samples = rate // 50
        chunk_bytes = chunk_samples * channels * 2
        # Keep the audio samples unchanged and pace them against a monotonic
        # clock rather than accumulating an additional sleep after each frame.
        total_chunks = (len(pcm) + chunk_bytes - 1) // chunk_bytes
        silence_chunks = 75  # same 1.5-second trailing silence as upstream
        for index in range(total_chunks + silence_chunks):
            if index < total_chunks:
                chunk = pcm[index * chunk_bytes:(index + 1) * chunk_bytes]
            else:
                chunk = b"\x00" * chunk_bytes
            await source.capture_frame(rtc.AudioFrame(data=chunk, sample_rate=rate, num_channels=channels,
                                                      samples_per_channel=len(chunk) // (2 * channels)))
            await asyncio.sleep(max(0, stream_start + (index + 1) * .02 - time.monotonic()))
        await source.wait_for_playout()
        stop.set()
        for task in streams:
            if not task.done():
                task.cancel()
        received = await asyncio.gather(*streams, return_exceptions=True)
        for result in received:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        helpers.write_wav(str(output_wav), bytes(output), CAPTURE_RATE, 1)
    finally:
        stop.set()
        for task in streams:
            task.cancel()
        await asyncio.gather(*streams, return_exceptions=True)
        await room.disconnect()
        await source.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--room", required=True)
    parser.add_argument("--ready-timeout", type=float, default=180)
    parser.add_argument("--upstream", type=Path, default=UPSTREAM)
    args = parser.parse_args()
    asyncio.run(run(args.input, args.output, args.room, ready_timeout=args.ready_timeout, upstream=args.upstream))


if __name__ == "__main__":
    main()
