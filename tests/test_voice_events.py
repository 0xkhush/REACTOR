import asyncio
import io
import json

from reactor.trace import TraceRecorder
from reactor.voice.events import EventTasks


async def test_event_task_failure_is_observed_and_logged_without_exception_text():
    stream = io.StringIO()
    owner = EventTasks(TraceRecorder("room", stream, io.StringIO()))

    async def fail():
        raise ValueError("private credential value")

    task = owner.spawn(fail())
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert owner.errors == ["ValueError"]
    assert json.loads(stream.getvalue())["event"] == "voice_event_error"
    assert "private credential value" not in stream.getvalue()
    await owner.drain()
