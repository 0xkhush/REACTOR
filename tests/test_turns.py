import asyncio

import pytest

from reactor.controller import Controller
from reactor.tools.base import ToolDefinition
from reactor.voice.turns import TurnBridge


SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}},
          "required": ["value"], "additionalProperties": False}


async def make_bridge():
    calls = []

    async def tool(value):
        calls.append(value)
        return {"value": value}

    controller = Controller("s", [ToolDefinition("write", True, SCHEMA, tool)])
    return TurnBridge(controller), controller, calls


async def test_correction_updates_only_changed_slot_and_cancels_obsolete_proposal():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.speech_started()
        first = await bridge.resolve("Boston Friday", mode="new", changes={"destination": "Boston", "date": "Friday"})
        await bridge.speech_started()
        second = await bridge.resolve("actually Chicago", mode="correction", changes={"destination": "Chicago"})
        assert first.request_id == second.request_id
        assert controller.snapshot()["slots"]["date"]["value"] == "Friday"
        old = await bridge.execute("write", {"value": "Boston"}, "old-call", request=first)
        assert old.status == "cancelled_before_dispatch"
        current = await bridge.execute("write", {"value": "Chicago"}, "new-call")
        assert current.status == "succeeded" and calls == ["Chicago"]
    finally:
        await controller.close()


async def test_same_provider_call_id_is_a_retry_but_new_id_is_an_intentional_repeat():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.speech_started()
        await bridge.resolve("add two", mode="new")
        first, duplicate = await asyncio.gather(
            bridge.execute("write", {"value": "item"}, "call-1"),
            bridge.execute("write", {"value": "item"}, "call-1"),
        )
        assert first.operation_id == duplicate.operation_id
        await bridge.execute("write", {"value": "item"}, "call-2")
        assert calls == ["item", "item"]
    finally:
        await controller.close()


async def test_new_input_holds_calls_and_acknowledgment_resumes_request():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.speech_started()
        initial = await bridge.resolve("start", mode="new")
        await bridge.speech_started()
        task = asyncio.create_task(bridge.execute("write", {"value": "same"}, "call-1"))
        await asyncio.sleep(0)
        assert not task.done() and not calls
        resumed = await bridge.resolve("thanks", mode="resume")
        assert resumed == initial
        assert (await asyncio.wait_for(task, 2)).status == "succeeded"
    finally:
        await controller.close()


async def test_model_call_before_first_final_transcript_waits_instead_of_hanging():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.speech_started()
        proposed = asyncio.create_task(bridge.execute("write", {"value": "ready"}, "call-1"))
        await asyncio.sleep(0)
        assert not proposed.done()
        await bridge.resolve("create it", mode="new")
        assert (await asyncio.wait_for(proposed, 2)).status == "succeeded"
        assert calls == ["ready"]
    finally:
        await bridge.close()
        await controller.close()


async def test_empty_first_transcript_creates_request_and_duplicate_final_event_is_ignored():
    bridge, controller, _ = await make_bridge()
    try:
        await bridge.speech_started()
        initial = await bridge.resolve("", mode="new")
        again = await bridge.resolve("", mode="new")
        assert initial == again
        assert controller.snapshot()["request_id"] == 1
    finally:
        await controller.close()


async def test_bridge_close_wakes_tool_waiting_for_unavailable_first_transcript():
    bridge, controller, _ = await make_bridge()
    try:
        waiting = asyncio.create_task(bridge.execute("write", {"value": "never"}, "call-1"))
        await asyncio.sleep(0)
        await bridge.close()
        with pytest.raises(RuntimeError, match="closed"):
            await asyncio.wait_for(waiting, 2)
    finally:
        await controller.close()
