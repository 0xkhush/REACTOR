"""Session-owned execution; logical action IDs come from the semantic adapter."""

import asyncio
import json
import time
from dataclasses import asdict, replace

from reactor.state import Operation, Outcome, Proposal, RequestToken, SessionState, copy_json
from reactor.tools.base import ToolDefinition
from reactor.trace import TraceError, TraceRecorder


class Controller:
    def __init__(self, session_id: str, tools: list[ToolDefinition], trace: TraceRecorder | None = None, *, cancel_in_flight: bool = True):
        self._state = SessionState(session_id)
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("duplicate tool names")
        self._trace = trace
        self._cancel_in_flight = cancel_in_flight
        self._lock = asyncio.Lock()
        self._write_lane = asyncio.Lock()
        self._input_ready = asyncio.Event()
        self._closed = False
        self._trace_error: TraceError | None = None
        self._identities: dict[tuple, str] = {}
        self._operations: dict[str, Operation] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._finished: dict[str, asyncio.Event] = {}

    def _check_open(self):
        if self._trace_error is not None:
            raise self._trace_error
        if self._closed:
            raise RuntimeError("session closed")

    def _event(self, name, **fields):
        if self._trace:
            try:
                self._trace.event(name, **fields)
            except TraceError as exc:
                self._trace_error = exc
                self._input_ready.set()
                raise

    async def begin_input(self) -> int:
        async with self._lock:
            self._check_open()
            revision = self._state.begin_input()
            self._input_ready.clear()
            self._event("input_started", input_revision=revision)
            return revision

    async def resolve_input(self, input_revision: int, *, mode: str, changes=None) -> RequestToken:
        async with self._lock:
            self._check_open()
            token = self._state.resolve_input(input_revision, mode=mode, changes=changes)
            self._event("input_resolved", mode=mode, request=asdict(token))
            self._input_ready.set()
            self._cancel_pending()
            return token

    async def execute(self, proposal: Proposal) -> Outcome:
        async with self._lock:
            self._check_open()
            if not isinstance(proposal.action_id, str) or not proposal.action_id.strip():
                raise ValueError("action_id must be nonblank")
            if proposal.tool not in self._tools:
                raise ValueError("unknown tool")
            tool = self._tools[proposal.tool]
            proposal = replace(proposal, args=tool.validate(proposal.args), depends_on=tuple(proposal.depends_on))
            identity = (proposal.request.request_id, proposal.request.intent_revision, proposal.action_id)
            existing = self._identities.get(identity)
            if existing:
                operation = self._operations[existing]
                if self._fingerprint(operation.proposal) != self._fingerprint(proposal):
                    raise ValueError("action identity conflict")
            else:
                for dependency in proposal.depends_on:
                    parent = self._operations.get(dependency)
                    if parent is None or parent.proposal.request != proposal.request:
                        raise ValueError("unknown or incompatible dependency")
                operation = Operation(f"op-{len(self._operations) + 1}", proposal, tool.state_modifying)
                self._event("proposed", operation_id=operation.operation_id, tool=proposal.tool,
                            request=asdict(proposal.request), args=proposal.args)
                self._operations[operation.operation_id] = operation
                self._identities[identity] = operation.operation_id
                self._finished[operation.operation_id] = asyncio.Event()
                task = asyncio.create_task(self._run(operation), name=operation.operation_id)
                self._tasks[operation.operation_id] = task
                task.add_done_callback(
                    lambda done, op_id=operation.operation_id: self._observe_task(op_id, done)
                )
            task = self._tasks[operation.operation_id]
        # Cancelling this wait never cancels execution. Pending invalidation can signal
        # completion before a predecessor or write lane becomes available.
        await self._finished[operation.operation_id].wait()
        if task.done() and not task.cancelled():
            task.result()
        while True:
            async with self._lock:
                if self._trace_error is not None:
                    raise self._trace_error
                if (operation.state_modifying or operation.status != "succeeded"
                        or self._state.resolved or self._closed
                        or not self._state.is_current(operation.proposal.request)):
                    return self._outcome(operation)
            # Speech can begin while a read runs. Resolve its relevance before delivery,
            # including cache hits, rather than leaking potentially obsolete evidence.
            await self._input_ready.wait()

    @staticmethod
    def _fingerprint(proposal: Proposal) -> str:
        # Python dict equality conflates True and 1. JSON preserves their distinct types.
        return json.dumps({
            "tool": proposal.tool, "args": proposal.args,
            "depends_on": list(proposal.depends_on),
        }, sort_keys=True, allow_nan=False, separators=(",", ":"))

    def _observe_task(self, operation_id, task):
        # Retrieve exceptions even if the caller has left; execute/close still observe them.
        if not task.cancelled():
            task.exception()
        self._finished[operation_id].set()

    def _cancel_pending(self):
        trace_failure = None
        for operation in self._operations.values():
            if (operation.status == "proposed" and (
                self._closed or not self._state.is_current(operation.proposal.request)
            )) or (
                self._cancel_in_flight and operation.status == "running" and operation.state_modifying and not self._closed and not self._state.is_current(operation.proposal.request)
            ):
                try:
                    self._cancel(operation, "session closed or request superseded")
                except TraceError as exc:
                    trace_failure = exc
                finally:
                    self._finished[operation.operation_id].set()
                    self._tasks[operation.operation_id].cancel()
        if trace_failure is not None:
            raise trace_failure

    async def _run(self, operation: Operation):
        try:
            for dependency in operation.proposal.depends_on:
                await asyncio.shield(self._tasks[dependency])
                parent = self._operations[dependency]
                if parent.status != "succeeded" or not self._state.is_current(parent.proposal.request):
                    self._cancel(operation, "dependency unavailable")
                    return
            if operation.state_modifying:
                async with self._write_lane:
                    await self._invoke(operation)
            else:
                await self._invoke(operation)
        except TraceError:
            if operation.status == "proposed":
                operation.status = "cancelled_before_dispatch"
                operation.error = "execution evidence unavailable"
            raise
        except asyncio.CancelledError:
            if operation.status == "proposed":
                self._cancel(operation, "execution owner cancelled before dispatch")
            elif not self._state.is_current(operation.proposal.request):
                if operation.status != "cancelled_in_flight":
                    self._cancel(operation, "execution owner cancelled in flight")
            raise

    def _cancel(self, operation: Operation, reason: str):
        if operation.status in ("cancelled_before_dispatch", "cancelled_in_flight"):
            return
        operation.status = "cancelled_before_dispatch" if operation.status == "proposed" else "cancelled_in_flight"
        operation.error = reason
        self._event(operation.status, operation_id=operation.operation_id, reason=reason)

    async def _admit(self, operation: Operation) -> bool:
        while True:
            async with self._lock:
                if self._closed or not self._state.is_current(operation.proposal.request):
                    self._cancel(operation, "session closed or request superseded")
                    return False
                if self._trace_error is not None:
                    raise self._trace_error
                if self._state.resolved:
                    self._event("launched", operation_id=operation.operation_id)
                    operation.status = "running"
                    operation.started_at = time.time()
                    return True
            await self._input_ready.wait()

    async def _invoke(self, operation: Operation):
        tool = self._tools[operation.proposal.tool]
        if not await self._admit(operation):
            return
        started = time.monotonic()
        try:
            operation.result = copy_json(await tool.invoke(operation.proposal.args))
            operation.status = (
                "failed" if isinstance(operation.result, dict) and operation.result.get("status") == "error"
                else "succeeded"
            )
            if operation.status == "failed":
                operation.error = "tool reported an error"
        except (Exception, asyncio.CancelledError) as exc:
            # Do not expose arbitrary backend exception strings (which can contain credentials).
            if isinstance(exc, asyncio.CancelledError) and (
                operation.status == "cancelled_in_flight" or not self._state.is_current(operation.proposal.request)
            ):
                if operation.status != "cancelled_in_flight":
                    self._cancel(operation, "operation cancelled in flight")
            else:
                operation.status = "outcome_unknown" if tool.state_modifying else "failed"
                operation.error = f"{type(exc).__name__}: tool did not provide a valid outcome"
        operation.ended_at = time.time()
        if self._trace:
            try:
                self._trace.tool_call(operation)
            except TraceError as exc:
                self._trace_error = exc
                self._input_ready.set()
                raise
        if operation.status != "cancelled_in_flight":
            self._event(operation.status, operation_id=operation.operation_id,
                        superseded=not self._state.is_current(operation.proposal.request),
                        duration_seconds=time.monotonic() - started)

    def _outcome(self, operation: Operation) -> Outcome:
        superseded = (not self._state.is_current(operation.proposal.request)
                      or (self._closed and not operation.state_modifying))
        hide_read = not operation.state_modifying and (superseded or not self._state.resolved)
        result = None if hide_read else copy_json(operation.result)
        return Outcome(operation.operation_id, operation.status, superseded, result, operation.error)

    def snapshot(self) -> dict:
        snapshot = self._state.snapshot()
        snapshot["trace_error"] = "execution evidence unavailable" if self._trace_error else None
        snapshot["operations"] = [
            {
                **asdict(self._outcome(operation)),
                "tool": operation.proposal.tool,
                "args": copy_json(operation.proposal.args),
                "request": asdict(operation.proposal.request),
            }
            for operation in self._operations.values()
        ]
        return snapshot

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._input_ready.set()
            try:
                self._cancel_pending()
            except TraceError:
                # Drain dispatched work before surfacing the latched evidence failure.
                pass
            tasks = list(self._tasks.values())
        await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)
        if self._trace_error is not None:
            raise self._trace_error
