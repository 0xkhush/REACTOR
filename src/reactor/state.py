"""Explicit request revisions; no speech interpretation or benchmark answers."""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Literal


def copy_json(value: Any) -> Any:
    """Validate strict JSON values and detach them from caller-owned objects."""
    def validate(item):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child)
            return
        raise ValueError("value must contain only finite JSON types and string keys")

    try:
        validate(value)
        return json.loads(json.dumps(value, allow_nan=False))
    except RecursionError as exc:
        raise ValueError("JSON value is cyclic or too deeply nested") from exc


@dataclass(frozen=True)
class RequestToken:
    request_id: int
    intent_revision: int


@dataclass(frozen=True)
class Slot:
    value: Any
    intent_revision: int


@dataclass(frozen=True)
class Proposal:
    request: RequestToken
    action_id: str
    tool: str
    args: dict[str, Any]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Outcome:
    operation_id: str
    status: Literal["succeeded", "failed", "cancelled_before_dispatch", "outcome_unknown"]
    superseded: bool
    result: Any = None
    error: str | None = None


@dataclass
class Operation:
    operation_id: str
    proposal: Proposal
    state_modifying: bool
    status: str = "proposed"
    started_at: float | None = None
    ended_at: float | None = None
    result: Any = None
    error: str | None = None


class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.input_revision = 0
        self.intent_revision = 0
        self.request_id = 0
        self.resolved = False
        self._slots: dict[str, Slot] = {}

    def begin_input(self) -> int:
        self.input_revision += 1
        self.resolved = False
        return self.input_revision

    def resolve_input(self, input_revision: int, *, mode: str, changes=None) -> RequestToken:
        if input_revision != self.input_revision or input_revision == 0:
            raise ValueError("stale input revision")
        if self.resolved:
            raise ValueError("input already resolved")
        if mode not in ("new", "correction", "resume"):
            raise ValueError("unknown resolution mode")
        if mode != "new" and self.request_id == 0:
            raise ValueError("resolution requires a preceding request")
        changes = copy_json({} if changes is None else changes)
        if not isinstance(changes, dict):
            raise ValueError("slot changes must be an object")
        if mode == "resume" and changes:
            raise ValueError("resume cannot change slots")
        if mode == "new":
            self.request_id += 1
        if mode != "resume":
            self.intent_revision += 1
            for name, value in changes.items():
                self._slots[name] = Slot(value, self.intent_revision)
        self.resolved = True
        return RequestToken(self.request_id, self.intent_revision)

    def is_current(self, request: RequestToken) -> bool:
        return self.request_id > 0 and request == RequestToken(self.request_id, self.intent_revision)

    def snapshot(self) -> dict[str, Any]:
        return copy_json({
            "session_id": self.session_id,
            "input_revision": self.input_revision,
            "intent_revision": self.intent_revision,
            "request_id": self.request_id,
            "resolved": self.resolved,
            "slots": {name: asdict(slot) for name, slot in self._slots.items()},
        })
