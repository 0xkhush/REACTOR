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


async def test_equivalent_proposals_in_one_request_coalesce_but_new_request_repeats():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.speech_started()
        await bridge.resolve("add two", mode="new")
        first, duplicate = await asyncio.gather(
            bridge.execute("write", {"value": "item"}, "call-1"),
            bridge.execute("write", {"value": "item"}, "call-retry-new-id"),
        )
        assert first.operation_id == duplicate.operation_id
        await bridge.resolve("add another item", mode="new")
        await bridge.execute("write", {"value": "item"}, "call-2")
        assert calls == ["item", "item"]
    finally:
        await controller.close()


async def test_search_flight_format_variant_same_calendar_day_coalesces():
    calls = []

    async def search(destination, date):
        calls.append((destination, date))
        return {"destination": destination, "date": date}

    schema = {"type": "object", "properties": {
        "destination": {"type": "string"}, "date": {"type": "string"},
    }, "required": ["destination", "date"], "additionalProperties": False}
    controller = Controller("s", [ToolDefinition("search_flights", False, schema, search)])
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        await bridge.resolve("Tokyo July 15", mode="new")
        first, repeat = await asyncio.gather(
            bridge.execute("search_flights", {"destination": "Tokyo", "date": "07/15"}, "call-a"),
            bridge.execute("search_flights", {"destination": "Tokyo", "date": "2026-07-15"}, "call-b"),
        )
        assert first.operation_id == repeat.operation_id
        assert first.result["date"] == "07/15"
        assert calls == [("Tokyo", "07/15")]
    finally:
        await bridge.close()
        await controller.close()


async def test_search_flights_with_distinct_explicit_years_remain_distinct_actions():
    calls = []

    async def search(destination, date):
        calls.append(date)
        return {"date": date}

    schema = {"type": "object", "properties": {
        "destination": {"type": "string"}, "date": {"type": "string"},
    }, "required": ["destination", "date"], "additionalProperties": False}
    controller = Controller("s", [ToolDefinition("search_flights", False, schema, search)])
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        await bridge.resolve("compare dates", mode="new")
        first = await bridge.execute("search_flights", {"destination": "Tokyo", "date": "2026-07-15"}, "a")
        second = await bridge.execute("search_flights", {"destination": "Tokyo", "date": "2027-07-15"}, "b")
        assert first.operation_id != second.operation_id
        assert calls == ["2026-07-15", "2027-07-15"]
    finally:
        await bridge.close()
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


async def test_new_final_transcript_without_speech_state_event_starts_a_new_request():
    bridge, controller, calls = await make_bridge()
    try:
        first = await bridge.resolve("track order A", mode="new")
        second = await bridge.resolve("track order B", mode="new")
        assert second.request_id == first.request_id + 1
        old = await bridge.execute("write", {"value": "A"}, "old", request=first)
        new = await bridge.execute("write", {"value": "B"}, "new")
        assert old.status == "cancelled_before_dispatch"
        assert new.status == "succeeded"
        assert calls == ["B"]
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


async def test_late_provider_call_id_stays_bound_to_original_intent():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.resolve("write Boston", mode="new", event_id=1)
        first = await bridge.execute("write", {"value": "Boston"}, "call-1")
        await bridge.resolve("write Chicago", mode="new", event_id=2)
        replay = await bridge.execute("write", {"value": "Boston"}, "call-1")
        assert replay.operation_id == first.operation_id
        assert replay.superseded
        assert calls == ["Boston"]
    finally:
        await bridge.close()
        await controller.close()


async def test_old_final_or_duplicate_cannot_resolve_new_input():
    bridge, controller, _ = await make_bridge()
    try:
        await bridge.resolve("Boston", mode="new", event_id=1)
        current = await bridge.resolve("Chicago", mode="new", event_id=2)
        revision = await bridge.speech_started()
        await bridge.resolve("Chicago", mode="new", event_id=2)
        await bridge.resolve("Boston", mode="new", event_id=1)
        assert not controller.snapshot()["resolved"]
        assert controller.snapshot()["input_revision"] == revision
        assert controller.snapshot()["request_id"] == current.request_id
        next_request = await bridge.resolve("Seattle", mode="new", event_id=3)
        assert next_request.request_id == current.request_id + 1
    finally:
        await bridge.close()
        await controller.close()


async def test_explicit_identical_actions_in_one_request_can_be_distinguished():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.resolve("perform two identical actions", mode="new")
        first = await bridge.execute("write", {"value": "item"}, "a", action_id="first-item")
        second = await bridge.execute("write", {"value": "item"}, "b", action_id="second-item")
        assert first.operation_id != second.operation_id
        assert calls == ["item", "item"]
    finally:
        await bridge.close()
        await controller.close()


async def test_spoken_intentional_twice_is_not_silently_coalesced():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.resolve("Do the same action twice", mode="new")
        await bridge.execute("write", {"value": "item"}, "a")
        await bridge.execute("write", {"value": "item"}, "b")
        assert calls == ["item", "item"]
    finally:
        await bridge.close()
        await controller.close()


async def test_late_new_call_from_known_generation_keeps_original_request():
    bridge, controller, calls = await make_bridge()
    try:
        await bridge.resolve("write Boston", mode="new", event_id="first-turn")
        await bridge.execute("write", {"value": "Boston"}, "first-call", origin_id="generation-1")
        await bridge.resolve("write Chicago", mode="new", event_id="second-turn")
        late = await bridge.execute("write", {"value": "Boston-old"}, "late-call", origin_id="generation-1")
        assert late.status == "cancelled_before_dispatch" and late.superseded
        assert calls == ["Boston"]
    finally:
        await bridge.close()
        await controller.close()
