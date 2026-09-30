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
from reactor.voice.agent import create_tool_functions, resolve_transcript_mode, safe_transcript, tool_execution_summary
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

        async def execute(self, *args):
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
