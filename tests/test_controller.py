import asyncio
import io
import json

import pytest
from jsonschema.exceptions import ValidationError

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.base import ToolDefinition
from reactor.trace import TraceError, TraceRecorder


EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
NAMED = {
    "type": "object", "properties": {"name": {"type": "string"}},
    "required": ["name"], "additionalProperties": False,
}


async def resolve(controller, mode="new", changes=None):
    return await controller.resolve_input(await controller.begin_input(), mode=mode, changes=changes)


@pytest.mark.parametrize("write", [True, False])
async def test_concurrent_duplicates_share_execution_and_result(write):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handler():
        calls.append("called")
        entered.set()
        await release.wait()
        return {"status": "success", "n": len(calls)}

    diagnostics, telemetry = io.StringIO(), io.StringIO()
    controller = Controller("s1", [ToolDefinition("tool", write, EMPTY, handler)],
                            TraceRecorder("s1", diagnostics, telemetry))
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "action-1", "tool", {})
        first = asyncio.create_task(controller.execute(proposal))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(controller.execute(proposal))
        release.set()
        a, b = await asyncio.gather(first, second)
        assert a.operation_id == b.operation_id
        assert a.status == b.status == "succeeded"
        assert calls == ["called"]
        records = [json.loads(line) for line in telemetry.getvalue().splitlines()]
        assert len(records) == 1
        assert records[0]["room"] == "s1"
        assert records[0]["call"]["function"] == "tool"
        assert records[0]["call"]["timestamp_end"] >= records[0]["call"]["timestamp_start"]
        new = await resolve(controller)
        await controller.execute(Proposal(new, "action-1", "tool", {}))
        assert calls == ["called", "called"]
    finally:
        release.set()
        await controller.close()


async def test_action_id_conflict_rejected_but_intentional_second_action_allowed():
    calls = []

    async def handler(name):
        calls.append(name)
        return {"name": name}

    controller = Controller("s1", [ToolDefinition("write", True, NAMED, handler)])
    try:
        request = await resolve(controller)
        await controller.execute(Proposal(request, "a", "write", {"name": "one"}))
        with pytest.raises(ValueError, match="action identity conflict"):
            await controller.execute(Proposal(request, "a", "write", {"name": "two"}))
        await controller.execute(Proposal(request, "b", "write", {"name": "one"}))
        assert calls == ["one", "one"]
    finally:
        await controller.close()


async def test_schema_rejection_does_not_execute_or_reserve_action():
    calls = []

    async def handler(name):
        calls.append(name)
        return {"name": name}

    controller = Controller("s1", [ToolDefinition("write", True, NAMED, handler)])
    try:
        request = await resolve(controller)
        with pytest.raises(ValidationError):
            await controller.execute(Proposal(request, "a", "write", {"name": 123}))
        assert controller.snapshot()["operations"] == []
        await controller.execute(Proposal(request, "a", "write", {"name": "valid"}))
        assert calls == ["valid"]
    finally:
        await controller.close()


async def test_chain_passes_real_result_and_blocks_failed_or_unknown_dependencies():
    used = []

    async def search():
        return {"name": "returned-product"}

    async def fail():
        return {"status": "error", "message": "not available"}

    async def book(name):
        used.append(name)
        return {"status": "success"}

    controller = Controller("s1", [
        ToolDefinition("search", False, EMPTY, search),
        ToolDefinition("fail", False, EMPTY, fail),
        ToolDefinition("book", True, NAMED, book),
    ])
    try:
        request = await resolve(controller)
        found = await controller.execute(Proposal(request, "s", "search", {}))
        result = await controller.execute(Proposal(
            request, "b", "book", {"name": found.result["name"]}, (found.operation_id,),
        ))
        assert result.status == "succeeded"
        failed = await controller.execute(Proposal(request, "f", "fail", {}))
        blocked = await controller.execute(Proposal(
            request, "blocked", "book", {"name": "bad"}, (failed.operation_id,),
        ))
        assert blocked.status == "cancelled_before_dispatch"
        with pytest.raises(ValueError, match="dependency"):
            await controller.execute(Proposal(request, "unknown", "book", {"name": "bad"}, ("missing",)))
        assert used == ["returned-product"]
    finally:
        await controller.close()


async def test_separate_sessions_do_not_deduplicate_each_other():
    calls = []

    async def handler():
        calls.append(1)
        return {"n": len(calls)}

    tools = [ToolDefinition("tool", True, EMPTY, handler)]
    first, second = Controller("one", tools), Controller("two", tools)
    try:
        a, b = await resolve(first), await resolve(second)
        await first.execute(Proposal(a, "same", "tool", {}))
        await second.execute(Proposal(b, "same", "tool", {}))
        assert len(calls) == 2
        assert len(first.snapshot()["operations"]) == 1
        assert len(second.snapshot()["operations"]) == 1
    finally:
        await first.close()
        await second.close()


async def test_trace_failure_preserves_success_and_stops_new_dispatch():
    class BrokenStream:
        def write(self, value):
            raise OSError("disk full")

    calls = []

    async def handler():
        calls.append(1)
        return {"status": "success"}

    controller = Controller("s1", [ToolDefinition("write", True, EMPTY, handler)],
                            TraceRecorder("s1", io.StringIO(), BrokenStream()))
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "a", "write", {})
        with pytest.raises(TraceError):
            await controller.execute(proposal)
        assert controller.snapshot()["operations"][0]["status"] == "succeeded"
        with pytest.raises(TraceError):
            await controller.execute(proposal)
        assert calls == [1]
    finally:
        await controller.close()


async def test_inputs_results_and_snapshots_cannot_mutate_history():
    result = {"list": ["original"]}

    async def handler(name):
        return result

    telemetry = io.StringIO()
    controller = Controller("s1", [ToolDefinition("read", False, NAMED, handler)],
                            TraceRecorder("s1", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        args = {"name": "original"}
        proposal = Proposal(request, "a", "read", args)
        outcome = await controller.execute(proposal)
        before = telemetry.getvalue()
        args["name"] = "changed"
        result["list"].append("changed")
        outcome.result["list"].append("also changed")
        snapshot = controller.snapshot()
        snapshot["operations"][0]["result"]["list"].append("snapshot changed")
        assert controller.snapshot()["operations"][0]["result"] == {"list": ["original"]}
        assert telemetry.getvalue() == before
        assert json.loads(before)["call"]["args"] == {"name": "original"}
    finally:
        await controller.close()
