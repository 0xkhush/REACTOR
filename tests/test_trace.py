import io
import json

import pytest

from reactor.trace import TraceError, TraceRecorder


def test_events_are_immutable_json_lines():
    stream = io.StringIO()
    trace = TraceRecorder("room", stream, io.StringIO())
    values = {"items": ["one"]}
    trace.event("proposed", args=values)
    values["items"].append("two")
    trace.event("cancelled", reason="new intent")
    first, second = map(json.loads, stream.getvalue().splitlines())
    assert first["args"] == {"items": ["one"]}
    assert first["session_id"] == second["session_id"] == "room"
    assert isinstance(first["timestamp"], float)
    assert second["event"] == "cancelled"


def test_non_json_event_is_rejected_before_any_line_is_written():
    stream = io.StringIO()
    trace = TraceRecorder("room", stream, io.StringIO())
    with pytest.raises(TraceError):
        trace.event("bad", value=float("nan"))
    assert stream.getvalue() == ""
