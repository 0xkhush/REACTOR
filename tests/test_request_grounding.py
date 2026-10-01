import pytest

from reactor.controller import Controller
from reactor.tools.benchmark import BenchmarkTools
from reactor.voice.turns import TurnBridge


@pytest.mark.parametrize(("transcript", "proposed", "expected"), [
    ("Fly to Oslo on November 9th", "2029-11-09", "November 9"),
    ("Fly to Oslo on November 9th, 2028", "2028-11-09", "2028-11-09"),
    ("Fly to Oslo on November 9th", "2029-11-10", "2029-11-10"),
    ("Fly to Oslo next Thursday", "2029-11-09", "2029-11-09"),
])
async def test_flight_year_grounding_changes_only_matching_user_month_day_without_a_year(transcript, proposed, expected):
    backend = BenchmarkTools()
    controller = Controller("date-grounding", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve(transcript, mode="new", event_id="turn")
        result = await bridge.execute("search_flights", {"destination": "Oslo", "date": proposed}, "flight")
        assert result.status == "succeeded"
        assert result.result["flights"][0]["date"] == expected
        assert controller.snapshot()["operations"][0]["args"]["date"] == expected
    finally:
        await bridge.close()
        await controller.close()


async def test_date_grounding_preserves_prior_explicit_year_through_followup_correction():
    backend = BenchmarkTools()
    controller = Controller("date-correction", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Fly to Oslo on November 9, 2028", mode="new", event_id="first")
        await bridge.resolve("Actually go to Bergen", mode="correction", event_id="correction")
        result = await bridge.execute("search_flights", {"destination": "Bergen", "date": "2028-11-09"}, "flight")
        assert result.result["flights"][0]["date"] == "2028-11-09"
    finally:
        await bridge.close()
        await controller.close()


async def test_late_generation_date_uses_originating_request_text_not_latest_request():
    backend = BenchmarkTools()
    controller = Controller("date-origin", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Fly to Oslo on November 9th", mode="new", event_id="first")
        await bridge.execute("search_flights", {"destination": "Oslo", "date": "2029-11-09"}, "first-call",
                             origin_id="old-generation")
        await bridge.resolve("Fly to Bergen on November 9, 2028", mode="new", event_id="second")
        late = await bridge.execute("search_flights", {"destination": "Oslo", "date": "2029-11-09"}, "late-call",
                                    origin_id="old-generation")
        assert late.superseded
        assert len(controller.snapshot()["operations"]) == 1
        assert controller.snapshot()["operations"][0]["args"]["date"] == "November 9"
    finally:
        await bridge.close()
        await controller.close()


@pytest.mark.parametrize(("identifier", "expected"), [
    ("Z Q 1 0 9", "ZQ109"), ("Z, Q, 1, 0, 9", "ZQ109"),
    ("ZQ-109", "ZQ-109"), ("Z Q - 1 0 9", "Z Q - 1 0 9"),
    ("CUSTOM CODE", "CUSTOM CODE"), ("AB 12", "AB 12"),
])
async def test_only_separate_single_character_identifier_tokens_are_joined(identifier, expected):
    backend = BenchmarkTools()
    controller = Controller("id-grounding", backend.definitions())
    bridge = TurnBridge(controller)
    try:
        await bridge.resolve("Track my order", mode="new")
        result = await bridge.execute("track_order", {"order_id": identifier}, "track")
        assert result.result["order_id"] == expected
    finally:
        await bridge.close()
        await controller.close()
