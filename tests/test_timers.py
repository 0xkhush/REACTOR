import asyncio
import math

import pytest

from reactor.controller import Controller
from reactor.state import Proposal
from reactor.tools.timers import TimerService


class ManualClock:
    def __init__(self):
        self.now = 100.0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def __call__(self):
        return self.now

    async def sleep(self, delay):
        self.entered.set()
        await self.release.wait()


async def test_cancel_is_verified_idempotent_and_session_local():
    first, second = TimerService(), TimerService()
    try:
        timer = await first.create_timer("pasta", 420)
        assert timer["state"] == "running"
        assert (await second.list_timers())["timers"] == []
        cancelled = await first.cancel_timer(timer["timer_id"])
        assert cancelled["state"] == "cancelled"
        assert (await first.list_timers())["timers"][0]["state"] == "cancelled"
        assert (await first.cancel_timer(timer["timer_id"]))["state"] == "cancelled"
    finally:
        await first.close()
        await second.close()


@pytest.mark.parametrize("duration", [0, -1, True, math.inf, -math.inf, math.nan, 86401, "7"])
async def test_invalid_duration_creates_no_timer(duration):
    timers = TimerService()
    try:
        with pytest.raises(ValueError):
            await timers.create_timer("pasta", duration)
        assert (await timers.list_timers())["timers"] == []
    finally:
        await timers.close()


@pytest.mark.parametrize("name", ["", "  ", None, 7])
async def test_invalid_name_is_rejected(name):
    timers = TimerService()
    try:
        with pytest.raises(ValueError):
            await timers.create_timer(name, 10)
    finally:
        await timers.close()


async def test_deadline_wins_over_late_cancellation():
    clock = ManualClock()
    timers = TimerService(clock=clock, sleep=clock.sleep)
    try:
        timer = await timers.create_timer("pasta", 7)
        await asyncio.wait_for(clock.entered.wait(), 2)
        clock.now = 107
        result = await timers.cancel_timer(timer["timer_id"])
        assert result["state"] == "completed"
        assert result["remaining_seconds"] == 0
    finally:
        await timers.close()


async def test_cancellation_before_deadline_cannot_be_overwritten_by_expiry():
    clock = ManualClock()
    timers = TimerService(clock=clock, sleep=clock.sleep)
    try:
        timer = await timers.create_timer("pasta", 7)
        await asyncio.wait_for(clock.entered.wait(), 2)
        await timers.cancel_timer(timer["timer_id"])
        clock.now = 108
        clock.release.set()
        assert (await timers.list_timers())["timers"][0]["state"] == "cancelled"
    finally:
        await timers.close()


async def test_running_timer_completes_and_reports_monotonic_remaining_time():
    clock = ManualClock()
    timers = TimerService(clock=clock, sleep=clock.sleep)
    try:
        await timers.create_timer("pasta", 7)
        await asyncio.wait_for(clock.entered.wait(), 2)
        clock.now = 103
        assert (await timers.list_timers())["timers"][0]["remaining_seconds"] == 4
        clock.now = 108
        clock.release.set()
        await asyncio.sleep(0)
        assert (await timers.list_timers())["timers"][0]["state"] == "completed"
    finally:
        await timers.close()


async def test_same_name_allowed_with_distinct_ids_and_unknown_id_errors():
    timers = TimerService()
    try:
        first = await timers.create_timer("pasta", 7)
        second = await timers.create_timer("pasta", 7)
        assert first["timer_id"] != second["timer_id"]
        with pytest.raises(ValueError, match="unknown timer"):
            await timers.cancel_timer("missing")
        first["name"] = "mutated"
        assert (await timers.list_timers())["timers"][0]["name"] == "pasta"
    finally:
        await timers.close()


async def test_close_drains_owned_tasks_and_rejects_creation():
    clock = ManualClock()
    timers = TimerService(clock=clock, sleep=clock.sleep)
    before = set(asyncio.all_tasks())
    await timers.create_timer("pasta", 7)
    await asyncio.wait_for(clock.entered.wait(), 2)
    await timers.close()
    await timers.close()
    assert not (set(asyncio.all_tasks()) - before)
    assert (await timers.list_timers())["timers"][0]["state"] == "cancelled"
    with pytest.raises(RuntimeError, match="closed"):
        await timers.create_timer("another", 7)


async def test_timer_tools_run_through_controller_with_duplicate_protection():
    timers = TimerService()
    controller = Controller("kitchen", timers.definitions())
    try:
        request = await controller.resolve_input(await controller.begin_input(), mode="new")
        proposal = Proposal(request, "start", "create_timer", {"name": "pasta", "duration_seconds": 420})
        first, duplicate = await asyncio.gather(controller.execute(proposal), controller.execute(proposal))
        assert first.result["timer_id"] == duplicate.result["timer_id"]
        listing = await controller.execute(Proposal(request, "list", "list_timers", {}))
        assert len(listing.result["timers"]) == 1
        assert listing.result["timers"][0]["duration_seconds"] == 420
        cancelled = await controller.execute(Proposal(
            request, "cancel", "cancel_timer", {"timer_id": first.result["timer_id"]},
        ))
        assert cancelled.result["state"] == "cancelled"
    finally:
        await controller.close()
        await timers.close()
