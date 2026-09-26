"""Session-owned execution; logical action IDs come from the semantic adapter."""

import asyncio
import time
from dataclasses import asdict, replace

from reactor.state import Operation, Outcome, Proposal, RequestToken, SessionState, copy_json
from reactor.tools.base import ToolDefinition
from reactor.trace import TraceError, TraceRecorder


class Controller:
    def __init__(self, session_id: str, tools: list[ToolDefinition], trace: TraceRecorder | None = None):
        self._state = SessionState(session_id)
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("duplicate tool names")
        self._trace = trace
        self._lock = asyncio.Lock()
        self._write_lane = asyncio.Lock()
        self._closed = False
        self._trace_error: TraceError | None = None
        self._identities: dict[tuple, str] = {}
        self._operations: dict[str, Operation] = {}
        self._tasks: dict[str, asyncio.Task] = {}

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
                raise

    async def begin_input(self) -> int:
        async with self._lock:
            self._check_open()
            revision = self._state.begin_input()
            self._event("input_started", input_revision=revision)
            return revision

    async def resolve_input(self, input_revision: int, *, mode: str, changes=None) -> RequestToken:
        async with self._lock:
            self._check_open()
            token = self._state.resolve_input(input_revision, mode=mode, changes=changes)
            self._event("input_resolved", mode=mode, request=asdict(token))
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
                if operation.proposal != proposal:
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
                task = asyncio.create_task(self._run(operation), name=operation.operation_id)
                self._tasks[operation.operation_id] = task
                task.add_done_callback(self._observe_task)
            task = self._tasks[operation.operation_id]
        await asyncio.shield(task)
        async with self._lock:
            return self._outcome(operation)

    @staticmethod
    def _observe_task(task):
        # Retrieve exceptions even if the caller has left; execute/close still observe them.
        if not task.cancelled():
            task.exception()

    async def _run(self, operation: Operation):
        for dependency in operation.proposal.depends_on:
            await asyncio.shield(self._tasks[dependency])
            parent = self._operations[dependency]
            if parent.status != "succeeded" or not self._state.is_current(parent.proposal.request):
                operation.status = "cancelled_before_dispatch"
                self._event("cancelled_before_dispatch", operation_id=operation.operation_id,
                            reason="dependency unavailable")
                return
        if operation.state_modifying:
            async with self._write_lane:
                await self._invoke(operation)
        else:
            await self._invoke(operation)

    async def _invoke(self, operation: Operation):
        tool = self._tools[operation.proposal.tool]
        async with self._lock:
            self._check_open()
            self._event("launched", operation_id=operation.operation_id)
            operation.status = "running"
            operation.started_at = time.time()
        started = time.monotonic()
        operation.result = copy_json(await tool.invoke(operation.proposal.args))
        operation.status = (
            "failed" if isinstance(operation.result, dict) and operation.result.get("status") == "error"
            else "succeeded"
        )
        operation.ended_at = time.time()
        if self._trace:
            try:
                self._trace.tool_call(operation)
            except TraceError as exc:
                self._trace_error = exc
                raise
        self._event(operation.status, operation_id=operation.operation_id,
                    duration_seconds=time.monotonic() - started)

    def _outcome(self, operation: Operation) -> Outcome:
        superseded = not self._state.is_current(operation.proposal.request)
        result = None if superseded and not operation.state_modifying else copy_json(operation.result)
        return Outcome(operation.operation_id, operation.status, superseded, result, operation.error)

    def snapshot(self) -> dict:
        snapshot = self._state.snapshot()
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
            tasks = list(self._tasks.values())
        await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)
