"""Bridge explicit transcript decisions to session revisions and tool calls.

The speech model still performs semantic interpretation. This class does not infer
that "actually" changes a particular slot or prove interruption timing.
"""

import asyncio

from reactor.controller import Controller
from reactor.state import Proposal, RequestToken


class TurnBridge:
    def __init__(self, controller: Controller):
        self.controller = controller
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._request: RequestToken | None = None
        self._input_revision: int | None = None
        self._closed = False
        self._last_transcript: str | None = None
        self._last_event_id = None

    @property
    def has_request(self) -> bool:
        return self._request is not None

    async def speech_started(self) -> int:
        async with self._lock:
            if self._closed:
                raise RuntimeError("turn bridge closed")
            if self._input_revision is None:
                self._input_revision = await self.controller.begin_input()
            return self._input_revision

    async def resolve(self, transcript: str, *, mode: str, changes=None,
                      event_id=None) -> RequestToken:
        async with self._lock:
            if self._closed:
                raise RuntimeError("turn bridge closed")
            if self._input_revision is None:
                if self._request is not None:
                    if (event_id is not None and event_id == self._last_event_id
                            or event_id is None and transcript == self._last_transcript):
                        # Retransmission of the same final event is not a new user turn.
                        return self._request
                self._input_revision = await self.controller.begin_input()
            revision = self._input_revision
            token = await self.controller.resolve_input(revision, mode=mode, changes=changes)
            self._request = token
            self._last_transcript = transcript
            self._last_event_id = event_id
            self._input_revision = None
            self._ready.set()
            return token

    async def execute(self, tool: str, args: dict, call_id: str, *,
                      request: RequestToken | None = None, depends_on: tuple[str, ...] = ()):
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("provider call_id must be nonblank")
        while request is None:
            async with self._lock:
                if self._closed:
                    raise RuntimeError("turn bridge closed")
                request = self._request
            if request is None:
                await self._ready.wait()
        return await self.controller.execute(Proposal(request, call_id, tool, args, depends_on))

    async def close(self):
        async with self._lock:
            self._closed = True
            self._ready.set()
