import asyncio
from types import SimpleNamespace

import pytest
from livekit import rtc

from scripts import ready_inference


class Room:
    def __init__(self):
        self.remote_participants = {}
        self.handlers = {}

    def on(self, name, callback=None):
        if callback is None:
            return lambda function: self.on(name, function)
        self.handlers.setdefault(name, []).append(callback)
        return callback

    def off(self, name, callback):
        self.handlers[name].remove(callback)

    def emit(self, name, *args):
        for callback in list(self.handlers.get(name, [])):
            callback(*args)


def participant(identity="agent", *, ready=False, agent=True):
    return SimpleNamespace(identity=identity,
                           kind=rtc.ParticipantKind.PARTICIPANT_KIND_AGENT if agent
                           else rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD,
                           attributes={"reactor.ready": "1"} if ready else {})


async def test_waits_for_agent_ready_attribute_instead_of_streaming_after_fixed_sleep():
    room = Room()
    agent = participant()
    room.remote_participants[agent.identity] = agent
    waiting = asyncio.create_task(ready_inference.wait_for_agent_ready(room, timeout=1))
    try:
        await asyncio.sleep(0)
        assert not waiting.done()
        agent.attributes["reactor.ready"] = "1"
        room.emit("participant_attributes_changed", {"reactor.ready": "1"}, agent)
        assert await asyncio.wait_for(waiting, 1) is agent
        assert not any(room.handlers.values())
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


async def test_connected_agent_with_existing_ready_signal_is_accepted():
    room = Room()
    agent = participant(ready=True)
    room.remote_participants[agent.identity] = agent
    assert await ready_inference.wait_for_agent_ready(room, timeout=1) is agent


async def test_user_participant_cannot_fake_agent_readiness():
    room = Room()
    room.remote_participants["user"] = participant("user", ready=True, agent=False)
    with pytest.raises(TimeoutError):
        await ready_inference.wait_for_agent_ready(room, timeout=.01)
    assert not any(room.handlers.values())


async def test_disconnect_during_readiness_wait_fails_without_hanging():
    room = Room()
    waiting = asyncio.create_task(ready_inference.wait_for_agent_ready(room, timeout=1))
    await asyncio.sleep(0)
    room.emit("disconnected")
    with pytest.raises(ConnectionError):
        await waiting


def test_recorded_audio_keeps_initial_silence_and_absolute_arrival_offset():
    buffer = bytearray(20 * 2)
    frame = b"\x01\x00" * 4
    end = ready_inference.record_frame(buffer, frame, sample_rate=10, elapsed_seconds=.8, write_pos=0)
    assert end == 8
    assert buffer[:8] == b"\x00" * 8
    assert buffer[8:16] == frame
    assert buffer[16:] == b"\x00" * 24


def test_recording_cannot_write_past_fixed_window_or_overwrite_previous_frames():
    buffer = bytearray(5 * 2)
    end = ready_inference.record_frame(buffer, b"\x01\x00" * 4, sample_rate=10,
                                       elapsed_seconds=.4, write_pos=3)
    assert end == 5
    assert len(buffer) == 10
    assert buffer[6:] == b"\x01\x00" * 2


async def test_replay_receiver_failure_is_not_written_or_reported_as_success(monkeypatch, tmp_path):
    from reactor.config import AgentConfig

    room = Room()
    agent = participant(ready=True)
    room.remote_participants[agent.identity] = agent
    saved = []
    closed = []

    async def publish(*args):
        pass

    async def connect(*args):
        room.emit("track_subscribed", SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO), None, agent)

    async def disconnect():
        closed.append("room")

    room.connect = connect
    room.disconnect = disconnect
    room.local_participant = SimpleNamespace(publish_track=publish)

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("injected receiver failure")

        async def aclose(self):
            closed.append("stream")

    class Source:
        async def capture_frame(self, frame):
            pass

        async def wait_for_playout(self):
            pass

        async def aclose(self):
            closed.append("source")

    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0)

    monkeypatch.setattr(ready_inference.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(ready_inference.rtc, "Room", lambda: room)
    monkeypatch.setattr(ready_inference.rtc, "AudioSource", lambda *args: Source())
    monkeypatch.setattr(ready_inference.rtc, "AudioStream", lambda *args, **kwargs: Stream())
    monkeypatch.setattr(ready_inference.rtc, "LocalAudioTrack",
                        SimpleNamespace(create_audio_track=lambda *args: object()))
    monkeypatch.setattr(ready_inference, "load_config", lambda *args: AgentConfig(
        "wss://example.livekit.cloud", "test-key", "test-secret-" * 4, "test-google", free_quota_confirmed=True))
    monkeypatch.setattr(ready_inference, "require_ffmpeg", lambda: None)
    monkeypatch.setattr(ready_inference, "audio_helpers", lambda *args: SimpleNamespace(
        read_wav_pcm16=lambda *args: (b"\x00" * 1920, 48000, 1),
        write_wav=lambda *args: saved.append(args)))
    with pytest.raises(RuntimeError, match="injected receiver failure"):
        await ready_inference.run(tmp_path / "input.wav", tmp_path / "output.wav", "test-room")
    assert not saved
    assert set(closed) == {"stream", "room", "source"}
