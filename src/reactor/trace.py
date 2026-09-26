"""Append-only JSONL diagnostics and the FDB-v3 actual-call record format."""

import json
import time
from typing import TextIO

from reactor.state import Operation, copy_json


class TraceError(RuntimeError):
    """Execution evidence could not be recorded; do not dispatch more actions."""


class TraceRecorder:
    def __init__(self, session_id: str, diagnostic_stream: TextIO, tool_stream: TextIO):
        self.session_id = session_id
        self.diagnostic_stream = diagnostic_stream
        self.tool_stream = tool_stream

    @staticmethod
    def _write(stream: TextIO, record: dict) -> None:
        try:
            line = json.dumps(copy_json(record), allow_nan=False) + "\n"
            written = stream.write(line)
            if written != len(line):
                raise OSError("incomplete trace write")
            stream.flush()
        except Exception as exc:
            raise TraceError("unable to record execution evidence") from exc

    def event(self, name: str, **fields) -> None:
        self._write(self.diagnostic_stream, {
            **fields, "session_id": self.session_id,
            "timestamp": time.time(), "event": name,
        })

    def tool_call(self, operation: Operation) -> None:
        self._write(self.tool_stream, {
            "room": self.session_id,
            "call": {
                "function": operation.proposal.tool,
                "args": operation.proposal.args,
                "timestamp_start": operation.started_at,
                "timestamp_end": operation.ended_at,
            },
        })
