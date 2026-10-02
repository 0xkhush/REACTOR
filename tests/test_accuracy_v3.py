import json
from types import SimpleNamespace

import pytest
from livekit.agents import llm
from livekit.plugins.google.utils import create_tools_config

from reactor.controller import Controller
from reactor.tools.benchmark import BenchmarkTools
from reactor.voice.agent import model_tools_for_mode, native_function_tool, normalize_tool_args
from reactor.voice.turns import TurnBridge


@pytest.mark.parametrize(("transcript", "proposed", "expected"), [
    ("Track order R Q 7 8", "RQ-78", "RQ78"),
    ("The number is R Q 78. Please track it", "RQ-78", "RQ78"),
    ("Track order RQ78", "RQ-78", "RQ78"),
    ("Track order RQ78", "RQ 78", "RQ78"),
    ("Track order RQ-78", "RQ-78", "RQ-78"),
    ("Track order R Q dash 78", "RQ-78", "RQ-78"),
    ("Track order R Q - 78", "RQ-78", "RQ-78"),
    ("Track order RS78", "RQ-78", "RQ-78"),
    ("Track order RQ789", "RQ-78", "RQ-78"),
    ("Track order R Q 7 8 9", "RQ-78", "RQ-78"),
    ("Track order R Q 7 8 9: where is it?", "RQ-78", "RQ-78"),
    ("Track order R Q 7 8 9) please", "RQ-78", "RQ-78"),
    ("Track order R Q 7 8 9\" please", "RQ-78", "RQ-78"),
    ("Track order R Q 78 99", "RQ-78", "RQ-78"),
    ("Track order IS33", "IS-33", "IS33"),
    ("Track order K9 after a 1 hour delay", "A-1", "A-1"),
    ("Track RQ-78 and RQ78", "RQ-78", "RQ-78"),
])
async def test_id_separator_repairs_require_matching_identifier_evidence(transcript, proposed, expected):
    backend = BenchmarkTools()
    controller = Controller("separator-proof", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve(transcript, mode="new")
        result = await bridge.execute("track_order", {"order_id": proposed}, "track")
        assert result.result["order_id"] == expected
        assert controller.snapshot()["operations"][0]["args"]["order_id"] == expected
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize(("tool", "first_text", "correction", "arguments", "field"), [
    ("track_order", "Track order RQ78", "Actually use R Q dash 78", {"order_id": "RQ-78"}, "order_id"),
    ("update_identity_doc", "Update passport number RQ78", "Actually use R Q dash 78",
     {"doc_type": "passport", "doc_number": "RQ-78"}, "doc_number"),
])
async def test_later_spoken_separator_correction_has_priority_over_old_compact_evidence(tool, first_text, correction, arguments, field):
    backend = BenchmarkTools()
    controller = Controller("separator-correction", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve(first_text, mode="new")
        await bridge.resolve(correction, mode="correction")
        result = await bridge.execute(tool, arguments, "corrected")
        assert result.status == "succeeded"
        assert controller.snapshot()["operations"][0]["args"][field] == "RQ-78"
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize(("tool", "supplied", "expected"), [
    ("get_card_benefits", {"card_type": "gold card"}, {"card_type": "gold"}),
    ("get_card_benefits", {"card_type": "travel credit card"}, {"card_type": "travel"}),
    ("get_card_benefits", {"card_type": "Acme Explorer Card"}, {"card_type": "Acme Explorer Card"}),
    ("calculate_commute", {"origin_address": "14 Rose Av", "destination_address": "the university"},
     {"origin_address": "14 Rose Ave", "destination_address": "university"}),
    ("calculate_commute", {"origin_address": "14 Rose Blvd", "destination_address": "The Dalles"},
     {"origin_address": "14 Rose Blvd", "destination_address": "The Dalles"}),
])
def test_known_api_labels_are_canonical_but_brands_and_named_places_are_preserved(tool, supplied, expected):
    assert normalize_tool_args(tool, supplied) == expected


async def test_card_category_repair_flows_through_native_dispatch_and_original_backend():
    backend = BenchmarkTools()
    controller = Controller("card-category", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("What are the benefits of my gold card?", mode="new")
        tool = next(item for item in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if item.info.name == "get_card_benefits")
        payload = '{"card_type":"gold card"}'
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="gold", arguments=payload))
        args, kwargs = llm.utils.prepare_function_arguments(fnc=tool, json_arguments=payload, call_ctx=context)
        result = json.loads(await tool(*args, **kwargs))
        assert result["status"] == "succeeded"
        assert result["result"]["card_type"] == "gold"
    finally:
        await bridge.close()
        await controller.close()


def test_native_google_parameters_receive_contract_field_descriptions():
    from reactor.tools.base import ToolDefinition
    from reactor.voice.agent import create_tool_functions

    async def calculate(origin_address, destination_address):
        return {}

    definition = ToolDefinition("calculate_commute", False, {
        "type": "object", "properties": {
            "origin_address": {"type": "string", "description": "A user-provided location label is sufficient."},
            "destination_address": {"type": "string"},
        }, "required": ["origin_address", "destination_address"], "additionalProperties": False,
    }, calculate)
    raw = create_tool_functions(object(), [definition])[0]
    native = native_function_tool(raw, definition)
    declaration = create_tools_config(llm.ToolContext([native]))[0].function_declarations[0]
    assert declaration.parameters.properties["origin_address"].description == "A user-provided location label is sufficient."
