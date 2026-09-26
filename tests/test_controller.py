import asyncio
import io
import json
import threading

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
        with pytest.raises(TraceError):
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


async def wait_for_operations(controller, count):
    async def wait():
        while len(controller.snapshot()["operations"]) < count:
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 2)


async def test_correction_prevents_queued_write_from_dispatching():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def write(name):
        calls.append(name)
        if name == "first":
            entered.set()
            await release.wait()
        return {"status": "success", "name": name}

    telemetry = io.StringIO()
    controller = Controller("s1", [ToolDefinition("write", True, NAMED, write)],
                            TraceRecorder("s1", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        first = asyncio.create_task(controller.execute(Proposal(request, "a", "write", {"name": "first"})))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(controller.execute(Proposal(request, "b", "write", {"name": "second"})))
        await wait_for_operations(controller, 2)
        assert controller.snapshot()["operations"][1]["status"] == "proposed"
        await resolve(controller, "correction", {"name": "third"})
        release.set()
        a, b = await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert calls == ["first"]
        assert a.status == "succeeded" and a.superseded
        assert a.result == {"status": "success", "name": "first"}
        assert b.status == "cancelled_before_dispatch"
        assert len(telemetry.getvalue().splitlines()) == 1
    finally:
        release.set()
        await controller.close()


async def test_obsolete_proposal_never_calls_tool():
    calls = []

    async def handler():
        calls.append(1)
        return {}

    telemetry = io.StringIO()
    controller = Controller("s", [ToolDefinition("write", True, EMPTY, handler)],
                            TraceRecorder("s", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        await resolve(controller, "correction", {"n": 7})
        result = await controller.execute(Proposal(request, "a", "write", {}))
        assert result.status == "cancelled_before_dispatch"
        assert calls == []
        assert telemetry.getvalue() == ""
    finally:
        await controller.close()


async def test_late_read_is_hidden_and_dependent_write_is_cancelled():
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    async def read():
        entered.set()
        await release.wait()
        return {"destination": "Boston"}

    async def write():
        writes.append(1)
        return {}

    telemetry = io.StringIO()
    controller = Controller("s", [ToolDefinition("read", False, EMPTY, read),
                                  ToolDefinition("write", True, EMPTY, write)],
                            TraceRecorder("s", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "read", "read", {})
        first = asyncio.create_task(controller.execute(proposal))
        await asyncio.wait_for(entered.wait(), 2)
        parent_id = controller.snapshot()["operations"][0]["operation_id"]
        second = asyncio.create_task(controller.execute(Proposal(request, "write", "write", {}, (parent_id,))))
        await wait_for_operations(controller, 2)
        await resolve(controller, "correction", {"destination": "Chicago"})
        release.set()
        a, b = await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert a.status == "succeeded" and a.superseded and a.result is None
        assert b.status == "cancelled_before_dispatch"
        assert writes == []
        cached = await controller.execute(proposal)
        assert cached.superseded and cached.result is None
        assert len(telemetry.getvalue().splitlines()) == 1
    finally:
        release.set()
        await controller.close()


@pytest.mark.parametrize("finish", ["resume", "close"])
async def test_unresolved_input_holds_new_write_until_resolution_or_shutdown(finish):
    calls = []

    async def handler():
        calls.append(1)
        return {}

    controller = Controller("s", [ToolDefinition("write", True, EMPTY, handler)])
    try:
        request = await resolve(controller)
        revision = await controller.begin_input()
        task = asyncio.create_task(controller.execute(Proposal(request, "a", "write", {})))
        await wait_for_operations(controller, 1)
        # Allow the owned task to run; it must wait rather than invoke the tool.
        await asyncio.sleep(0)
        assert calls == []
        if finish == "resume":
            resumed = await controller.resolve_input(revision, mode="resume")
            assert resumed == request
        else:
            await asyncio.wait_for(controller.close(), 2)
        outcome = await asyncio.wait_for(task, 2)
        assert outcome.status == ("succeeded" if finish == "resume" else "cancelled_before_dispatch")
        assert calls == ([1] if finish == "resume" else [])
    finally:
        await controller.close()


async def test_cancelled_caller_does_not_lose_blocking_write_outcome():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def write():
        calls.append(1)
        entered.set()
        if not release.wait(5):
            raise TimeoutError("test worker not released")
        return {"status": "success", "receipt": "confirmed"}

    telemetry = io.StringIO()
    controller = Controller("s", [ToolDefinition("write", True, EMPTY, write, blocking=True)],
                            TraceRecorder("s", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "a", "write", {})
        caller = asyncio.create_task(controller.execute(proposal))
        assert await asyncio.to_thread(entered.wait, 2)
        revision = await asyncio.wait_for(controller.begin_input(), 1)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        await controller.resolve_input(revision, mode="resume")
        release.set()
        result = await asyncio.wait_for(controller.execute(proposal), 2)
        assert result.status == "succeeded" and result.result["receipt"] == "confirmed"
        assert calls == [1]
        assert len(telemetry.getvalue().splitlines()) == 1
    finally:
        release.set()
        await controller.close()


@pytest.mark.parametrize("write", [True, False])
@pytest.mark.parametrize("failure", ["exception", "invalid_json", "cancelled"])
async def test_dispatched_failures_have_truthful_terminal_outcomes(write, failure):
    calls = []

    async def handler():
        calls.append(1)
        if failure == "exception":
            raise OSError("backend connection lost")
        if failure == "cancelled":
            raise asyncio.CancelledError()
        return {"value": float("nan")}

    telemetry = io.StringIO()
    controller = Controller("s", [ToolDefinition("tool", write, EMPTY, handler)],
                            TraceRecorder("s", io.StringIO(), telemetry))
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "a", "tool", {})
        outcome = await controller.execute(proposal)
        assert outcome.status == ("outcome_unknown" if write else "failed")
        assert outcome.error and outcome.result is None
        await controller.execute(proposal)
        assert calls == [1]
        assert len(telemetry.getvalue().splitlines()) == 1
    finally:
        await controller.close()


async def test_close_drains_dispatched_write_and_rejects_new_requests():
    entered, release = asyncio.Event(), asyncio.Event()

    async def write():
        entered.set()
        await release.wait()
        return {"status": "success"}

    controller = Controller("s", [ToolDefinition("write", True, EMPTY, write)])
    try:
        request = await resolve(controller)
        task = asyncio.create_task(controller.execute(Proposal(request, "a", "write", {})))
        await asyncio.wait_for(entered.wait(), 2)
        closing = asyncio.create_task(controller.close())
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(RuntimeError, match="closed"):
            await controller.begin_input()
        release.set()
        await asyncio.wait_for(closing, 2)
        assert (await task).status == "succeeded"
        await controller.close()
    finally:
        release.set()
        await controller.close()


async def test_independent_reads_overlap():
    both_entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def read(name):
        calls.append(name)
        if len(calls) == 2:
            both_entered.set()
        await release.wait()
        return {"name": name}

    controller = Controller("s", [ToolDefinition("read", False, NAMED, read)])
    try:
        request = await resolve(controller)
        tasks = [asyncio.create_task(controller.execute(Proposal(request, name, "read", {"name": name})))
                 for name in ("a", "b")]
        await asyncio.wait_for(both_entered.wait(), 2)
        release.set()
        outcomes = await asyncio.gather(*tasks)
        assert [outcome.result for outcome in outcomes] == [{"name": "a"}, {"name": "b"}]
    finally:
        release.set()
        await controller.close()


@pytest.mark.parametrize("mode", ["resume", "correction"])
async def test_read_delivery_waits_for_input_resolution(mode):
    entered, release = asyncio.Event(), asyncio.Event()

    async def read():
        entered.set()
        await release.wait()
        return {"destination": "Boston"}

    controller = Controller("s", [ToolDefinition("read", False, EMPTY, read)])
    try:
        request = await resolve(controller)
        proposal = Proposal(request, "a", "read", {})
        caller = asyncio.create_task(controller.execute(proposal))
        await asyncio.wait_for(entered.wait(), 2)
        revision = await controller.begin_input()
        release.set()

        async def completed():
            while controller.snapshot()["operations"][0]["status"] != "succeeded":
                await asyncio.sleep(0)

        await asyncio.wait_for(completed(), 2)
        cached = asyncio.create_task(controller.execute(proposal))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not caller.done() and not cached.done()
        assert controller.snapshot()["operations"][0]["result"] is None
        await controller.resolve_input(revision, mode=mode)
        a, b = await asyncio.wait_for(asyncio.gather(caller, cached), 2)
        assert a.superseded == b.superseded == (mode == "correction")
        assert a.result == b.result == (None if mode == "correction" else {"destination": "Boston"})
    finally:
        release.set()
        await controller.close()


@pytest.mark.parametrize("dependency", [False, True])
async def test_superseded_pending_work_returns_before_predecessor_finishes(dependency):
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    async def predecessor():
        entered.set()
        await release.wait()
        return {"status": "success"}

    async def pending():
        writes.append(1)
        return {}

    controller = Controller("s", [
        ToolDefinition("first", not dependency, EMPTY, predecessor),
        ToolDefinition("second", True, EMPTY, pending),
    ])
    first = second = None
    try:
        request = await resolve(controller)
        first = asyncio.create_task(controller.execute(Proposal(request, "a", "first", {})))
        await asyncio.wait_for(entered.wait(), 2)
        parent_id = controller.snapshot()["operations"][0]["operation_id"]
        second = asyncio.create_task(controller.execute(Proposal(
            request, "b", "second", {}, (parent_id,) if dependency else (),
        )))
        await wait_for_operations(controller, 2)
        await resolve(controller, "correction")
        outcome = await asyncio.wait_for(asyncio.shield(second), 0.2)
        assert outcome.status == "cancelled_before_dispatch"
        assert not release.is_set() and not first.done()
        assert writes == []
    finally:
        release.set()
        await controller.close()
        await asyncio.gather(*(task for task in (first, second) if task), return_exceptions=True)


@pytest.mark.parametrize("first,second", [(True, 1), (False, 0), ({"items": [True]}, {"items": [1]})])
async def test_distinct_json_types_conflict_for_same_action(first, second):
    calls = []

    async def handler(value):
        calls.append(value)
        return {"value": value}

    schema = {"type": "object", "properties": {"value": {}}, "required": ["value"]}
    controller = Controller("s", [ToolDefinition("write", True, schema, handler)])
    try:
        request = await resolve(controller)
        await controller.execute(Proposal(request, "a", "write", {"value": first}))
        with pytest.raises(ValueError, match="identity conflict"):
            await controller.execute(Proposal(request, "a", "write", {"value": second}))
        assert len(calls) == 1
    finally:
        await controller.close()


async def test_argument_object_key_order_does_not_create_a_conflict():
    calls = []

    async def handler(value):
        calls.append(value)
        return {"value": value}

    schema = {"type": "object", "properties": {"value": {"type": "object"}}}
    controller = Controller("s", [ToolDefinition("write", True, schema, handler)])
    try:
        request = await resolve(controller)
        a = await controller.execute(Proposal(request, "a", "write", {"value": {"x": 1, "y": 2}}))
        b = await controller.execute(Proposal(request, "a", "write", {"value": {"y": 2, "x": 1}}))
        assert a.operation_id == b.operation_id
        assert len(calls) == 1
    finally:
        await controller.close()


async def test_shutdown_surfaces_detached_execution_telemetry_failure():
    class BrokenStream:
        def write(self, value):
            raise OSError("disk full")

    entered, release = asyncio.Event(), asyncio.Event()

    async def write():
        entered.set()
        await release.wait()
        return {"status": "success", "receipt": "written"}

    controller = Controller("s", [ToolDefinition("write", True, EMPTY, write)],
                            TraceRecorder("s", io.StringIO(), BrokenStream()))
    request = await resolve(controller)
    caller = asyncio.create_task(controller.execute(Proposal(request, "a", "write", {})))
    await asyncio.wait_for(entered.wait(), 2)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    with pytest.raises(TraceError):
        await controller.close()
    snapshot = controller.snapshot()
    assert snapshot["trace_error"] is not None
    assert snapshot["operations"][0]["status"] == "succeeded"
    assert snapshot["operations"][0]["result"]["receipt"] == "written"


async def test_close_drains_running_work_even_if_pending_cancellation_logging_fails():
    class SwitchableStream(io.StringIO):
        broken = False

        def write(self, value):
            if self.broken:
                raise OSError("disk full")
            return super().write(value)

    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def write(name):
        calls.append(name)
        entered.set()
        await release.wait()
        return {"name": name}

    diagnostics = SwitchableStream()
    controller = Controller("s", [ToolDefinition("write", True, NAMED, write)],
                            TraceRecorder("s", diagnostics, io.StringIO()))
    request = await resolve(controller)
    tasks = [asyncio.create_task(controller.execute(Proposal(request, name, "write", {"name": name})))
             for name in ("first", "second", "third")]
    await asyncio.wait_for(entered.wait(), 2)
    await wait_for_operations(controller, 3)
    diagnostics.broken = True
    closing = asyncio.create_task(controller.close())
    try:
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        with pytest.raises(TraceError):
            await asyncio.wait_for(asyncio.shield(closing), 2)
        assert calls == ["first"]
        assert [op["status"] for op in controller.snapshot()["operations"]] == [
            "succeeded", "cancelled_before_dispatch", "cancelled_before_dispatch",
        ]
    finally:
        release.set()
        await asyncio.gather(closing, *tasks, return_exceptions=True)
