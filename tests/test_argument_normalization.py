import json
from types import SimpleNamespace

import pytest
from livekit.agents import ToolError, llm

from reactor.controller import Controller
from reactor.tools.benchmark import BenchmarkTools
from reactor.voice.agent import normalize_tool_args, model_tools_for_mode
from reactor.voice.turns import TurnBridge


@pytest.mark.parametrize(("tool", "supplied", "expected"), [
    ("search_flights", {"destination": "Oslo", "date": "November 9th"},
     {"destination": "Oslo", "date": "November 9"}),
    ("search_flights", {"destination": "Oslo", "date": "November 9th, 2028"},
     {"destination": "Oslo", "date": "November 9, 2028"}),
    ("modify_autopay", {"bill_type": "utilities", "source_account": "checking account"},
     {"bill_type": "utilities", "source_account": "checking"}),
    ("update_identity_doc", {"doc_type": "driver's license", "doc_number": "ZX-109"},
     {"doc_type": "driver_license", "doc_number": "ZX-109"}),
    ("get_exchange_rate", {"amount": "-25.50", "from_currency": "USD", "to_currency": "EUR"},
     {"amount": -25.5, "from_currency": "USD", "to_currency": "EUR"}),
    ("get_exchange_rate", {"amount": "1e3", "from_currency": "USD", "to_currency": "EUR"},
     {"amount": 1000.0, "from_currency": "USD", "to_currency": "EUR"}),
    ("search_products", {"query": "desk", "max_price": "$1,250.50"},
     {"query": "desk", "max_price": 1250.5}),
    ("add_to_cart", {"product_id": "P-09", "quantity": "9007199254740993"},
     {"product_id": "P-09", "quantity": 9007199254740993}),
    ("calculate_commute", {"origin_address": "Oak Street", "destination_address": "the university", "mode": "walking"},
     {"origin_address": "Oak Street", "destination_address": "university", "mode": "walking"}),
    ("search_flights", {"destination": "Vegas", "date": "August 8"},
     {"destination": "Las Vegas", "date": "August 8"}),
    ("search_products", {"query": "mechanical keyboard", "max_price": 200},
     {"query": "mechanical keyboards", "max_price": 200}),
    ("update_search_filter", {"filter_name": "neighborhood", "value": "North side"},
     {"filter_name": "neighborhood", "value": "Northside"}),
])
def test_unambiguous_argument_formats_are_canonicalized_without_changing_meaning(tool, supplied, expected):
    original = dict(supplied)
    assert normalize_tool_args(tool, supplied) == expected
    assert supplied == original


@pytest.mark.parametrize(("tool", "supplied"), [
    ("search_flights", {"destination": "Oslo", "date": "2028-11-09"}),
    ("search_flights", {"destination": "Oslo", "date": "next Thursday"}),
    ("search_flights", {"destination": "Oslo", "date": "November 99th"}),
    ("modify_autopay", {"bill_type": "utilities", "source_account": "Savings Account A109"}),
    ("update_identity_doc", {"doc_type": "residence permit", "doc_number": "RP-09"}),
    ("add_to_cart", {"product_id": "P-09", "quantity": "2.5"}),
    ("search_apartments", {"city": "Oslo", "bedrooms": "2-3", "max_price": 1500}),
    ("search_products", {"query": "desk", "max_price": "100 or 200"}),
    ("search_products", {"query": "desk", "max_price": "1,23"}),
    ("search_products", {"query": "desk", "max_price": "2..5"}),
])
def test_unknown_identifiers_dates_and_ambiguous_numbers_are_not_reinterpreted(tool, supplied):
    assert normalize_tool_args(tool, supplied) == supplied


async def test_native_runtime_normalizes_account_label_before_real_write():
    backend = BenchmarkTools()
    controller = Controller("account-label", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Use my checking account for utilities", mode="new")
        tool = next(item for item in model_tools_for_mode("benchmark", bridge, backend.definitions())
                    if item.info.name == "modify_autopay")
        payload = '{"bill_type":"utilities","source_account":"checking account"}'
        context = SimpleNamespace(function_call=SimpleNamespace(call_id="account-label", arguments=payload))
        args, kwargs = llm.utils.prepare_function_arguments(fnc=tool, json_arguments=payload, call_ctx=context)
        result = json.loads(await tool(*args, **kwargs))
        assert result["result"]["source"] == "checking"
        assert controller.snapshot()["operations"][0]["args"]["source_account"] == "checking"
    finally:
        await bridge.close()
        await controller.close()


async def test_ambiguous_raw_quantity_is_rejected_instead_of_executing_twenty_five():
    from reactor.voice.agent import create_tool_functions

    backend = BenchmarkTools()
    controller = Controller("bad-quantity", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Add an item", mode="new")
        tool = next(item for item in create_tool_functions(bridge, backend.definitions())
                    if item.info.name == "add_to_cart")
        with pytest.raises(ToolError):
            await tool(raw_arguments={"product_id": "P-09", "quantity": "2.5"},
                       ctx=SimpleNamespace(function_call=SimpleNamespace(call_id="bad-quantity")))
        assert controller.snapshot()["operations"] == []
    finally:
        await bridge.close()
        await controller.close()
