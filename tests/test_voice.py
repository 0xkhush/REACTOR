import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from livekit.agents import llm

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.trace import TraceRecorder
from reactor.tools.benchmark import BenchmarkTools
from reactor.tools.timers import TimerService
from reactor.voice.agent import (create_tool_functions, normalize_tool_args, resolve_transcript_mode,
                                 safe_transcript, tool_execution_summary, model_tools_for_mode)
from reactor.voice.agent import handle_kitchen_transcript
from reactor.voice.agent import ReactorVoiceAgent
from reactor.voice.agent import room_mode
from reactor.voice.turns import TurnBridge


def test_twelve_benchmark_tools_register_with_google_schema():
    definitions = BenchmarkTools().definitions()
    tools = create_tool_functions(object(), definitions)
    context = llm.ToolContext(tools)
    assert len(context.function_tools) == 12
    google_schema = context.parse_function_tools("google")
    assert google_schema


async def test_timer_tool_calls_flow_through_bridge_with_provider_call_id():
    timers = TimerService()
    controller = Controller("kitchen", timers.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        await bridge.resolve("set seven-minute timer", mode="new")
        tools = create_tool_functions(bridge, timers.definitions())
        create = next(tool for tool in tools if tool.info.name == "create_timer")
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="provider-1"))
        first = json.loads(await create(raw_arguments={"name": "pasta", "duration_seconds": 420}, ctx=context))
        second = json.loads(await create(raw_arguments={"name": "pasta", "duration_seconds": 420}, ctx=context))
        assert first["operation_id"] == second["operation_id"]
        assert len((await timers.list_timers())["timers"]) == 1
        cancel = next(tool for tool in tools if tool.info.name == "cancel_timer")
        cancelled = json.loads(await cancel(raw_arguments={"timer_id": first["result"]["timer_id"]},
                                            ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="provider-2"))))
        assert cancelled["result"]["state"] == "cancelled"
    finally:
        await bridge.close()
        await controller.close()
        await timers.close()


async def test_final_kitchen_transcript_interrupts_model_and_speaks_verified_timer_result():
    timers = TimerService()
    controller = Controller("kitchen", timers.definitions())
    bridge = TurnBridge(controller)

    class Session:
        def __init__(self):
            self.interrupted = False
            self.spoken = []

        async def interrupt(self, *, force):
            self.interrupted = force

        async def say(self, text, *, audio):
            assert hasattr(audio, "__aiter__")
            self.spoken.append(text)

    session = Session()
    try:
        result = await handle_kitchen_transcript(
            session, bridge,
            "Please create a timer called pasta for 10 minutes. Actually, make it seven minutes.",
            "event-1",
        )
        assert result["timer"]["duration_seconds"] == 420
        assert session.interrupted
        assert session.spoken == ["Timer pasta set for 420 seconds."]
        assert (await timers.list_timers())["timers"][0]["state"] == "running"
    finally:
        await bridge.close()
        await controller.close()
        await timers.close()


async def test_kitchen_discards_ungrounded_native_model_audio():
    from livekit import rtc

    async def provider_audio():
        yield rtc.AudioFrame(b"\x01\x00" * 480, 24000, 1, 480)

    agent = ReactorVoiceAgent("kitchen")
    frames = [frame async for frame in agent.realtime_audio_output_node(provider_audio(), {})]
    assert frames == []


async def test_exchange_rate_tool_uses_livekit_raw_arguments_and_controller():
    backend = BenchmarkTools()
    controller = Controller("finance", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        await bridge.resolve("Convert 500 USD to EUR", mode="new")
        tool = next(tool for tool in create_tool_functions(bridge, backend.definitions())
                    if tool.info.name == "get_exchange_rate")
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="finance-call-1"))
        args, kwargs = llm.utils.prepare_function_arguments(
            fnc=tool,
            json_arguments='{"amount":500,"from_currency":"USD","to_currency":"EUR"}',
            call_ctx=context,
        )
        result = json.loads(await tool(*args, **kwargs))
        assert result["status"] == "succeeded"
        assert result["result"]["converted_amount"] == 450
    finally:
        await bridge.close()
        await controller.close()


async def test_search_product_budget_alias_uses_declared_max_price_argument():
    backend = BenchmarkTools()
    controller = Controller("catalog", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        await bridge.resolve("Find headphones for less than $100", mode="new")
        tool = next(tool for tool in create_tool_functions(bridge, backend.definitions())
                    if tool.info.name == "search_products")
        proposed = {"query": "wireless headphones", "budget": 100}
        result = json.loads(await tool(raw_arguments=proposed,
                                       ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="catalog-1"))))
        assert result["status"] == "succeeded"
        assert controller.snapshot()["operations"][0]["args"] == {
            "query": "wireless headphones", "max_price": 100,
        }
        assert proposed["budget"] == 100
    finally:
        await bridge.close()
        await controller.close()


def test_budget_alias_normalizes_to_max_price_for_search_tools():
    assert normalize_tool_args("search_apartments", {
        "city": "Seattle", "bedrooms": 2, "budget": 2500,
    }) == {"city": "Seattle", "bedrooms": 2, "max_price": 2500}


def test_departure_date_alias_normalizes_to_fdb_flight_schema():
    assert normalize_tool_args("search_flights", {
        "destination": "Tokyo", "departure_date": "2026-07-15",
    }) == {"destination": "Tokyo", "date": "2026-07-15"}


def test_commute_and_order_and_autopay_aliases_normalize():
    assert normalize_tool_args("calculate_commute", {
        "origin": "Downtown", "destination": "Uptown",
    }) == {"origin_address": "Downtown", "destination_address": "Uptown"}
    assert normalize_tool_args("track_order", {
        "tracking_number": "TRK-123",
    }) == {"order_id": "TRK-123"}
    assert normalize_tool_args("modify_autopay", {
        "bill_type": "mortgage", "account": "savings",
    }) == {"bill_type": "mortgage", "source_account": "savings"}
    assert normalize_tool_args("update_search_filter", {
        "filter": "pets_allowed", "value": True,
    }) == {"filter_name": "pets_allowed", "value": True}
    assert normalize_tool_args("get_exchange_rate", {
        "amount": "$500", "from_currency": "USD", "to_currency": "EUR",
    }) == {"amount": 500.0, "from_currency": "USD", "to_currency": "EUR"}



async def test_model_proposal_is_logged_before_first_turn_resolves():
    timers = TimerService()
    log = io.StringIO()
    controller = Controller("room", timers.definitions(), TraceRecorder("room", log, io.StringIO()))
    bridge = TurnBridge(controller)
    try:
        await bridge.speech_started()
        tool = next(tool for tool in create_tool_functions(bridge, timers.definitions())
                    if tool.info.name == "list_timers")
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="first-proposal"))
        caller = asyncio.create_task(tool(raw_arguments={}, ctx=context))
        await asyncio.sleep(0)
        proposals = [json.loads(line) for line in log.getvalue().splitlines()
                     if json.loads(line).get("event") == "model_tool_proposal"]
        assert len(proposals) == 1
        assert proposals[0]["argument_types"] == {}
        assert not caller.done()
        await bridge.resolve("list timers", mode="new")
        assert json.loads(await caller)["status"] == "succeeded"
    finally:
        await bridge.close()
        await controller.close()
        await timers.close()


async def test_tool_bridge_failure_records_only_exception_type():
    log = io.StringIO()

    class BrokenBridge:
        controller = SimpleNamespace(_trace=TraceRecorder("room", log, io.StringIO()))

        async def execute(self, *args, **kwargs):
            raise ValueError("provider-secret-value")

    tool = next(tool for tool in create_tool_functions(BrokenBridge(), TimerService().definitions())
                if tool.info.name == "list_timers")
    ctx = SimpleNamespace(function_call=SimpleNamespace(call_id="tool-call-1"))
    with pytest.raises(ValueError):
        await tool(raw_arguments={}, ctx=ctx)
    lines = [json.loads(line) for line in log.getvalue().splitlines()]
    assert lines[-1]["event"] == "tool_bridge_error"
    assert lines[-1]["error_type"] == "ValueError"
    assert "provider-secret-value" not in log.getvalue()


def test_transcript_mode_is_conservative_and_has_no_benchmark_answers():
    assert resolve_transcript_mode("Actually Chicago", has_request=True) == "correction"
    assert resolve_transcript_mode("thanks", has_request=True) == "resume"
    assert resolve_transcript_mode("Track order A12", has_request=True) == "new"
    assert resolve_transcript_mode("actually Chicago", has_request=False) == "new"


def test_kitchen_mode_handles_timer_commands_locally_without_model_tool_calls():
    timers = TimerService()
    try:
        assert model_tools_for_mode("kitchen", object(), timers.definitions()) == []
        assert len(model_tools_for_mode("benchmark", object(), BenchmarkTools().definitions())) == 12
    finally:
        asyncio.run(timers.close())


def test_concurrent_smoke_and_batch_workers_use_mode_from_room_not_worker_environment():
    assert room_mode("kitchen", "reactor-batch-abc") == "benchmark"
    assert room_mode("benchmark", "reactor-kitchen-abc") == "kitchen"
    assert room_mode("kitchen", "eval-abc") == "benchmark"
    assert room_mode("kitchen", "console") == "kitchen"


def test_diagnostic_transcript_redacts_known_credentials_and_is_bounded():
    text = "Use lk-secret and google-secret " + "x" * 700
    safe = safe_transcript(text, ("lk-secret", "google-secret"))
    assert "lk-secret" not in safe and "google-secret" not in safe
    assert "[redacted]" in safe
    assert len(safe) <= 500


def test_tool_event_summary_records_errors_without_tool_arguments_or_output():
    event = SimpleNamespace(
        zipped=lambda: [(SimpleNamespace(name="get_exchange_rate", arguments='{"secret":"no"}'),
                         SimpleNamespace(is_error=True, output="private failure"))],
    )
    assert tool_execution_summary(event) == [{"tool": "get_exchange_rate", "is_error": True}]
