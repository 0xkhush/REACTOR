import pytest

from reactor.controller import Controller
from reactor.tools.timers import TimerService
from reactor.voice.turns import TurnBridge
from reactor.voice.kitchen import parse_timer_command
from reactor.voice.kitchen import dispatch_kitchen_command


def test_create_command_uses_latest_duration_after_self_correction():
    command = parse_timer_command(
        "Please create a timer called pasta for 10 minutes. Actually, make it seven minutes."
    )
    assert command == {"action": "create", "name": "pasta", "duration_seconds": 420}


def test_create_command_supports_numeric_seconds_and_default_name():
    assert parse_timer_command("Set a timer for 45 seconds") == {
        "action": "create", "name": "timer", "duration_seconds": 45,
    }


@pytest.mark.parametrize("transcript", [
    "Set a timer for ten minutes",  # unit/value understood, but no explicit action target? timer default name ok
])
def test_timer_create_handles_clear_default_name(transcript):
    assert parse_timer_command(transcript) == {
        "action": "create", "name": "timer", "duration_seconds": 600,
    }


def test_cancel_timer_by_explicit_name():
    assert parse_timer_command("Please cancel the timer called pasta") == {
        "action": "cancel", "name": "pasta",
    }


def test_list_timers_is_a_read_request():
    assert parse_timer_command("List my timers") == {"action": "list"}


@pytest.mark.parametrize("transcript", [
    "Set a timer for ten minutes or maybe later", "Set a timer for a while", "Cancel it",
])
def test_ambiguous_timer_text_falls_back_to_conversation(transcript):
    assert parse_timer_command(transcript) is None


@pytest.mark.parametrize("duration", ["0 seconds", "one hundred days", "100000 seconds"])
def test_invalid_or_unsupported_timer_durations_are_not_dispatched(duration):
    assert parse_timer_command(f"Set a timer for {duration}") is None


async def test_voice_router_creates_corrected_timer_and_cancels_by_name():
    timers = TimerService()
    controller = Controller("kitchen", timers.definitions())
    bridge = TurnBridge(controller)
    try:
        created = await dispatch_kitchen_command(
            bridge,
            "Please create a timer called pasta for 10 minutes. Actually, make it seven minutes.",
            event_id="turn-1",
        )
        assert created["handled"] is True
        assert created["timer"]["duration_seconds"] == 420
        assert created["timer"]["name"] == "pasta"

        cancelled = await dispatch_kitchen_command(
            bridge, "Please cancel the timer called pasta.", event_id="turn-2",
        )
        assert cancelled["handled"] is True
        assert cancelled["timer"]["state"] == "cancelled"
        assert len((await timers.list_timers())["timers"]) == 1
    finally:
        await bridge.close()
        await controller.close()
        await timers.close()


async def test_ambiguous_timer_command_is_not_executed():
    timers = TimerService()
    controller = Controller("kitchen", timers.definitions())
    bridge = TurnBridge(controller)
    try:
        result = await dispatch_kitchen_command(
            bridge, "Maybe set a timer for a while?", event_id="turn-ambiguous",
        )
        assert result is None
        assert controller.snapshot()["operations"] == []
    finally:
        await bridge.close()
        await controller.close()
        await timers.close()
