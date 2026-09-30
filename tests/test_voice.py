import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError
from livekit.agents import llm
from livekit.agents import ToolError
from livekit.plugins.google.utils import create_tools_config

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


def test_runtime_tools_send_native_google_parameters_with_required_fields():
    tools = model_tools_for_mode("benchmark", object(), BenchmarkTools().definitions())
    declarations = create_tools_config(llm.ToolContext(tools))[0].function_declarations
    assert len(declarations) == 12
    commute = next(item for item in declarations if item.name == "calculate_commute")
    assert commute.parameters is not None
    assert set(commute.parameters.required) == {"origin_address", "destination_address"}
    assert set(commute.parameters.properties) == {"origin_address", "destination_address", "mode"}
    catalog = next(item for item in declarations if item.name == "search_products")
    assert catalog.parameters.properties["max_price"].nullable


@pytest.mark.parametrize(("tool_name", "arguments"), [
    ("get_exchange_rate", {"amount": True, "from_currency": "USD", "to_currency": "EUR"}),
    ("add_to_cart", {"product_id": "P37", "quantity": True}),
])
def test_native_argument_preparation_does_not_convert_booleans_into_numbers(tool_name, arguments):
    tool = next(tool for tool in model_tools_for_mode("benchmark", object(), BenchmarkTools().definitions())
                if tool.info.name == tool_name)
    with pytest.raises(PydanticValidationError):
        llm.utils.prepare_function_arguments(fnc=tool, json_arguments=json.dumps(arguments),
                                            call_ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="invalid")))


async def test_native_runtime_tools_preserve_call_ids_defaults_and_real_results():
    backend = BenchmarkTools()
    controller = Controller("native-schema", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Drive from 41 Oak Road to City Hall", mode="new")
        tool = next(tool for tool in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if tool.info.name == "calculate_commute")
        assert isinstance(tool, llm.FunctionTool)
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="native-1"))
        args, kwargs = llm.utils.prepare_function_arguments(
            fnc=tool, json_arguments='{"origin_address":"41 Oak Road","destination_address":"City Hall"}',
            call_ctx=context,
        )
        first = json.loads(await tool(*args, **kwargs))
        second = json.loads(await tool(*args, **kwargs))
        assert first["status"] == "succeeded"
        assert first["operation_id"] == second["operation_id"]
        assert controller.snapshot()["operations"][0]["args"] == {
            "origin_address": "41 Oak Road", "destination_address": "City Hall", "mode": "driving",
        }
    finally:
        await bridge.close()
        await controller.close()


async def test_native_handler_revalidates_provider_extras_instead_of_sdk_filtered_subset():
    backend = BenchmarkTools()
    controller = Controller("native-extra", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Change my filter", mode="new")
        tool = next(tool for tool in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if tool.info.name == "update_search_filter")
        payload = '{"filter_name":"max_price","value":2100,"undeclared":"secret-value"}'
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="native-extra", arguments=payload))
        args, kwargs = llm.utils.prepare_function_arguments(fnc=tool, json_arguments=payload, call_ctx=context)
        with pytest.raises(ToolError) as error:
            await tool(*args, **kwargs)
        assert "secret-value" not in str(error.value)
        assert controller.snapshot()["operations"] == []
    finally:
        await bridge.close()
        await controller.close()


async def test_rejected_proposal_gets_safe_repair_feedback_without_executing():
    backend = BenchmarkTools()
    controller = Controller("repair", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Change the filter", mode="new")
        tool = next(tool for tool in create_tool_functions(bridge, backend.definitions())
                    if tool.info.name == "update_search_filter")
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="repair-1"))
        with pytest.raises(ToolError) as rejected:
            await tool(raw_arguments={"private-key-value": "provider-secret-value"}, ctx=context)
        feedback = str(rejected.value)
        assert "filter_name" in feedback and "value" in feedback
        assert "not executed" in feedback.lower()
        assert "provider-secret-value" not in feedback and "private-key-value" not in feedback
        assert controller.snapshot()["operations"] == []
        repaired = json.loads(await tool(raw_arguments={"filter_name": "max_price", "value": "2100"},
                                         ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="repair-2"))))
        assert repaired["status"] == "succeeded"
        assert len(controller.snapshot()["operations"]) == 1
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize("value", [2100, 9007199254740993, True, "central district"])
async def test_filter_values_preserve_scalar_type_through_native_sdk_and_original_backend(value):
    backend = BenchmarkTools()
    controller = Controller("scalar-filter", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Update my filter", mode="new")
        tool = next(tool for tool in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if tool.info.name == "update_search_filter")
        args, kwargs = llm.utils.prepare_function_arguments(
            fnc=tool, json_arguments=json.dumps({"filter_name": "chosen_filter", "value": value}),
            call_ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="filter-1")),
        )
        result = json.loads(await tool(*args, **kwargs))
        returned = result["result"]["new_value"]
        assert returned == value
        assert type(returned) is type(value)
        assert isinstance(returned, bool) == isinstance(value, bool)
        assert isinstance(returned, str) == isinstance(value, str)
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize(("text", "expected"), [
    ("During the morning rush hour.", "resume"),
    ("Um, I just wanted to make sure it fits.", "resume"),
    ("Because I need to arrive on time.", "resume"),
    ("During lunch, also track order B17.", "new"),
    ("During lunch, please tell me the current status of order B17.", "new"),
    ("During lunch, I need another currency conversion.", "new"),
    ("I want to make sure you cancel the timer.", "new"),
    ("Actually, make it walking instead.", "correction"),
])
def test_clear_sentence_continuations_keep_request_identity_but_new_tasks_do_not(text, expected):
    assert resolve_transcript_mode(text, has_request=True) == expected


async def test_commute_continuation_and_equivalent_mode_do_not_execute_twice():
    backend = BenchmarkTools()
    calls = io.StringIO()
    controller = Controller("continuation", backend.definitions(), TraceRecorder("continuation", io.StringIO(), calls))
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Drive from 41 Oak Road to City Hall", mode="new")
        tool = next(tool for tool in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if tool.info.name == "calculate_commute")

        async def call(call_id, mode):
            args, kwargs = llm.utils.prepare_function_arguments(
                fnc=tool, json_arguments=json.dumps({"origin_address": "41 Oak Road",
                                                   "destination_address": "City Hall", "mode": mode}),
                call_ctx=SimpleNamespace(function_call=SimpleNamespace(call_id=call_id)),
            )
            return json.loads(await tool(*args, **kwargs))

        first = await call("commute-first", "drive")
        await bridge.speech_started()
        text = "During the morning rush hour."
        await bridge.resolve(text, mode=resolve_transcript_mode(text, has_request=True))
        second = await call("commute-second", "driving")
        assert first["operation_id"] == second["operation_id"]
        logged = [json.loads(line) for line in calls.getvalue().splitlines()]
        assert len(logged) == 1
        assert logged[0]["call"]["args"]["mode"] == "driving"
    finally:
        await bridge.close()
        await controller.close()


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


@pytest.mark.parametrize(("tool", "provided", "expected"), [
    ("calculate_commute", {"departure_address": "101 Main Street", "destination_address": "downtown"},
     {"origin_address": "101 Main Street", "destination_address": "downtown"}),
    ("calculate_commute", {"origin_address": "101 Main Street", "arrival_address": "downtown"},
     {"origin_address": "101 Main Street", "destination_address": "downtown"}),
    ("update_identity_doc", {"document_type": "passport", "document_number": "P123"},
     {"doc_type": "passport", "doc_number": "P123"}),
    ("modify_autopay", {"bill_type": "mortgage", "new_source_account": "savings"},
     {"bill_type": "mortgage", "source_account": "savings"}),
    ("get_exchange_rate", {"amount": 100, "source_currency": "USD", "target_currency": "EUR"},
     {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}),
    ("update_search_filter", {"filter_type": "pets_allowed", "value": "true"},
     {"filter_name": "pets_allowed", "value": "true"}),
])
def test_observed_provider_aliases_are_normalized_without_changing_values(tool, provided, expected):
    assert normalize_tool_args(tool, provided) == expected
    assert normalize_tool_args(tool, expected) == expected


async def test_observed_aliases_reach_real_commute_backend_and_incomplete_calls_stay_rejected():
    backend = BenchmarkTools()
    controller = Controller("commute-alias", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Drive from 101 Main Street to downtown", mode="new")
        tool = next(tool for tool in create_tool_functions(bridge, backend.definitions())
                    if tool.info.name == "calculate_commute")
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="commute-1"))
        outcome = json.loads(await tool(raw_arguments={
            "departure_address": "101 Main Street", "destination_address": "downtown",
        }, ctx=context))
        assert outcome["status"] == "succeeded"
        assert controller.snapshot()["operations"][0]["args"] == {
            "origin_address": "101 Main Street", "destination_address": "downtown", "mode": "driving",
        }
        with pytest.raises(ToolError):
            await tool(raw_arguments={"destination_address": "downtown"},
                       ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="commute-2")))
        assert len(controller.snapshot()["operations"]) == 1
    finally:
        await bridge.close()
        await controller.close()


async def test_absent_catalog_budget_is_recorded_as_declared_null_default():
    backend = BenchmarkTools()
    controller = Controller("catalog-default", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Find headphones", mode="new")
        tool = next(tool for tool in create_tool_functions(bridge, backend.definitions())
                    if tool.info.name == "search_products")
        result = json.loads(await tool(raw_arguments={"query": "headphones"},
                                       ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="catalog-default-1"))))
        assert result["status"] == "succeeded"
        assert controller.snapshot()["operations"][0]["args"] == {"query": "headphones", "max_price": None}
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
