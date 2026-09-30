import asyncio
import io
import json

import pytest

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.benchmark import BenchmarkTools
from reactor.trace import TraceRecorder


UPSTREAM_NAMES = {
    "search_flights", "book_flight", "update_identity_doc", "get_card_benefits",
    "get_exchange_rate", "modify_autopay", "search_apartments", "calculate_commute",
    "update_search_filter", "track_order", "search_products", "add_to_cart",
}
UPSTREAM_WRITES = {
    "book_flight", "update_identity_doc", "modify_autopay", "update_search_filter", "add_to_cart",
}


def benchmark():
    try:
        return BenchmarkTools()
    except FileNotFoundError:
        pytest.skip("Run python scripts/setup_fdb.py before upstream integration tests")


def test_all_upstream_names_are_exposed_without_scenario_metadata():
    tools = benchmark()
    definitions = {tool.name: tool for tool in tools.definitions()}
    assert set(definitions) == UPSTREAM_NAMES
    assert {name for name, tool in definitions.items() if tool.state_modifying} == UPSTREAM_WRITES
    assert all(tool.blocking for tool in definitions.values())
    assert "benchmark_data" not in repr(tools)
    assert definitions["search_products"].schema["properties"]["max_price"]["type"] == ["number", "null"]
    assert definitions["calculate_commute"].schema["properties"]["mode"]["default"] == "driving"


async def test_search_apartments_and_filters_accept_flexible_arguments():
    tools = benchmark()
    definitions = {tool.name: tool for tool in tools.definitions()}
    # apartment search without bedrooms/max_price should succeed using backend defaults
    apt_res = await definitions["search_apartments"].invoke({"city": "San Francisco"})
    assert apt_res["status"] == "success"
    assert apt_res["city"] == "San Francisco"

    # filter update with boolean or int should succeed
    filter_res_bool = await definitions["update_search_filter"].invoke({"filter_name": "pets_allowed", "value": True})
    assert filter_res_bool["status"] == "success"
    filter_res_int = await definitions["update_search_filter"].invoke({"filter_name": "max_price", "value": 3500})
    assert filter_res_int["status"] == "success"



async def test_chained_calls_use_upstream_returned_id_and_one_cart_write():
    backend = benchmark()
    stream = io.StringIO()
    controller = Controller("room-1", backend.definitions(), TraceRecorder("room-1", io.StringIO(), stream))
    try:
        token = await controller.resolve_input(await controller.begin_input(), mode="new")
        search = await controller.execute(Proposal(token, "search", "search_products", {"query": "headphones"}))
        product_id = search.result["products"][0]["product_id"]
        cart = Proposal(token, "cart", "add_to_cart", {"product_id": product_id, "quantity": 2},
                        (search.operation_id,))
        first, duplicate = await asyncio.gather(controller.execute(cart), controller.execute(cart))
        assert first.operation_id == duplicate.operation_id
        assert first.result["product_id"] == product_id
        assert first.result["quantity"] == 2
        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert [(line["call"]["function"], line["room"]) for line in lines] == [
            ("search_products", "room-1"), ("add_to_cart", "room-1")
        ]
        assert all(set(line["call"]) == {"function", "args", "timestamp_start", "timestamp_end"} for line in lines)
    finally:
        await controller.close()


async def test_mock_latency_does_not_block_input_revision():
    backend = benchmark()
    backend.registry.injector.default_profile.fixed_ms = 250
    controller = Controller("room-2", backend.definitions())
    try:
        token = await controller.resolve_input(await controller.begin_input(), mode="new")
        task = asyncio.create_task(controller.execute(Proposal(token, "search", "search_products", {"query": "soap"})))
        async def launched():
            while not controller.snapshot()["operations"] or controller.snapshot()["operations"][0]["status"] != "running":
                await asyncio.sleep(0)
        await asyncio.wait_for(launched(), 2)
        revision = await asyncio.wait_for(controller.begin_input(), 0.2)
        await controller.resolve_input(revision, mode="correction", changes={"query": "shampoo"})
        outcome = await asyncio.wait_for(task, 2)
        assert outcome.superseded and outcome.result is None
    finally:
        await controller.close()


def test_each_room_has_separate_registry_state():
    first, second = benchmark(), benchmark()
    assert first.registry is not second.registry
    assert first.registry.logger is not second.registry.logger
