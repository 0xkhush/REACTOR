import asyncio
import shutil

import pytest
from livekit import rtc

from reactor.voice.speech import local_audio


@pytest.mark.skipif(not shutil.which("ffmpeg") or not (shutil.which("say") or shutil.which("espeak-ng") or shutil.which("espeak")),
                    reason="Local speech engine is not installed")
async def test_local_speech_produces_real_pcm_frames_without_model_api():
    frames = [frame async for frame in local_audio("Timer confirmed.")]
    assert frames
    assert all(frame.sample_rate == 24000 and frame.num_channels == 1 for frame in frames)
    assert any(any(frame.data) for frame in frames)


async def test_local_speech_reports_missing_engine(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="speech engine"):
        _ = [frame async for frame in local_audio("Hello")]
