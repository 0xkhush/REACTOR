import asyncio
import json
from types import SimpleNamespace

from livekit.agents import llm

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.benchmark import BenchmarkTools
from reactor.tools.timers import TimerService
from reactor.voice.agent import create_tool_functions, resolve_transcript_mode
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


def test_transcript_mode_is_conservative_and_has_no_benchmark_answers():
    assert resolve_transcript_mode("Actually Chicago", has_request=True) == "correction"
    assert resolve_transcript_mode("thanks", has_request=True) == "resume"
    assert resolve_transcript_mode("Track order A12", has_request=True) == "new"
    assert resolve_transcript_mode("actually Chicago", has_request=False) == "new"
