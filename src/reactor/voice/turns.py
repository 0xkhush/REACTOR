"""Bridge explicit transcript decisions to session revisions and tool calls.

The speech model still performs semantic interpretation. This class does not infer
that "actually" changes a particular slot or prove interruption timing.
"""

import asyncio
import json
import re
from datetime import datetime

from reactor.controller import Controller
from reactor.state import Proposal, RequestToken, copy_json


def calendar_day(value):
    """Parse supported user date formats without assigning a missing year."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", value.strip(), flags=re.I)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%B %d, %Y"):
        try:
            date = datetime.strptime(text, fmt)
            return date.month, date.day, date.year
        except ValueError:
            pass
    for fmt in ("%m/%d", "%B %d", "%b %d"):
        try:
            # Leap year validates February 29 without implying a user-requested year.
            date = datetime.strptime(text + " 2000", fmt + " %Y")
            return date.month, date.day, None
        except ValueError:
            pass
    return None


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
        self._semantic_actions: dict[tuple, str] = {}
        self._flight_actions: list[dict] = []
        self._seen_events: set = set()
        self._provider_requests: dict[str, RequestToken] = {}
        self._provider_actions: dict[str, str] = {}
        self._origin_requests: dict[str, RequestToken] = {}

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
            if event_id is not None and event_id in self._seen_events:
                return self._request
            if (isinstance(event_id, (int, float)) and isinstance(self._last_event_id, (int, float))
                    and event_id < self._last_event_id):
                return self._request
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
            if event_id is not None:
                self._seen_events.add(event_id)
            self._last_transcript = transcript
            self._last_event_id = event_id
            self._input_revision = None
            self._ready.set()
            return token

    async def execute(self, tool: str, args: dict, call_id: str, *,
                      request: RequestToken | None = None, depends_on: tuple[str, ...] = (),
                      action_id: str | None = None, origin_id: str | None = None):
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("provider call_id must be nonblank")
        while request is None:
            async with self._lock:
                if self._closed:
                    raise RuntimeError("turn bridge closed")
                request = self._provider_requests.get(call_id)
                if request is None and origin_id is not None:
                    request = self._origin_requests.get(origin_id)
                if request is None:
                    request = self._request
            if request is None:
                await self._ready.wait()
        args = copy_json(args)
        fingerprint = json.dumps(args, sort_keys=True, allow_nan=False, separators=(",", ":"))
        key = (request.request_id, request.intent_revision, tool, fingerprint, tuple(depends_on))
        async with self._lock:
            if self._closed:
                raise RuntimeError("turn bridge closed")
            if origin_id is not None:
                request = self._origin_requests.setdefault(origin_id, request)
            request = self._provider_requests.setdefault(call_id, request)
            key = (request.request_id, request.intent_revision, tool, fingerprint, tuple(depends_on))
            intentional_repeat = bool(re.search(
                r"\b(?:twice|again|another|two identical|two separate|second identical)\b",
                self._last_transcript or "", re.I,
            ))
            if call_id in self._provider_actions:
                action_id = self._provider_actions[call_id]
            elif action_id is not None or intentional_repeat:
                action_id = action_id or call_id
            else:
                action_id = self._semantic_actions.setdefault(key, call_id)
            day = calendar_day(args.get("date")) if tool == "search_flights" else None
            if day is not None and not intentional_repeat:
                explicit_user_year = bool(re.search(r"\b(?:19|20)\d{2}\b", self._last_transcript or ""))
                for previous in self._flight_actions:
                    if (previous["request"] != request or previous["depends_on"] != tuple(depends_on)
                            or previous["args"].get("destination") != args.get("destination")):
                        continue
                    old_day = previous["day"]
                    same_day = old_day[:2] == day[:2]
                    compatible_year = old_day[2] == day[2] or (
                        not explicit_user_year and (old_day[2] is None or day[2] is None)
                    )
                    if same_day and compatible_year:
                        # Return the first admitted request's actual arguments/result;
                        # never mutate a reserved proposal or invent a new date.
                        action_id = previous["action_id"]
                        args = copy_json(previous["args"])
                        if old_day[2] is None and day[2] is not None:
                            previous["day"] = day
                        break
                else:
                    self._flight_actions.append({"request": request, "depends_on": tuple(depends_on),
                                                 "day": day, "args": copy_json(args), "action_id": action_id})
            self._provider_actions.setdefault(call_id, action_id)
        return await self.controller.execute(Proposal(request, action_id, tool, args, depends_on))

    async def close(self):
        async with self._lock:
            self._closed = True
            self._ready.set()
