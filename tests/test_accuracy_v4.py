import pytest

from reactor.controller import Controller
from reactor.tools.benchmark import BenchmarkTools
from reactor.voice.agent import normalize_tool_args
from reactor.voice.turns import TurnBridge


@pytest.mark.parametrize(("text", "proposed", "expected"), [
    ("Fly to Oslo on November 9th", "November 9, 2029", "November 9"),
    ("Fly to Oslo on November 9th", "Nov 9, 2029", "November 9"),
    ("Fly to Oslo on November 9th", "11/09/2029", "November 9"),
    ("Fly to Oslo on November 9th", "November 9 2029", "November 9"),
    ("Fly to Oslo on November 9, 2028", "November 9, 2028", "November 9, 2028"),
    ("Fly to Oslo on November 10th", "November 9, 2029", "November 9, 2029"),
    ("Fly to Oslo on November 9th", "November 99, 2029", "November 99, 2029"),
])
async def test_inferred_year_grounding_is_format_independent_without_discarding_stated_years(text, proposed, expected):
    backend = BenchmarkTools()
    controller = Controller("date-format", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve(text, mode="new")
        result = await bridge.execute("search_flights", {"destination": "Oslo", "date": proposed}, "flight")
        assert result.status == "succeeded"
        assert result.result["flights"][0]["date"] == expected
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize("address", ["the office", "my office", "Office", "the grocery store"])
def test_user_office_and_personal_location_wording_is_not_erased(address):
    assert normalize_tool_args("calculate_commute", {
        "origin_address": "my house", "destination_address": address, "mode": "driving",
    }) == {"origin_address": "my house", "destination_address": address, "mode": "driving"}
