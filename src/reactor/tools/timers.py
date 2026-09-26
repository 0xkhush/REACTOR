"""Session-local kitchen timers with verified cancellation and monotonic deadlines."""

import asyncio
import math
import time
from dataclasses import dataclass

from reactor.tools.base import ToolDefinition


@dataclass
class Timer:
    timer_id: str
    name: str
    duration_seconds: float
    deadline: float
    state: str = "running"


class TimerService:
    def __init__(self, *, clock=time.monotonic, sleep=asyncio.sleep):
        self._clock = clock
        self._sleep = sleep
        self._timers: dict[str, Timer] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._closed = False

    def _reconcile(self, timer: Timer):
        if timer.state == "running" and self._clock() >= timer.deadline:
            timer.state = "completed"

    def _view(self, timer: Timer) -> dict:
        self._reconcile(timer)
        return {
            "timer_id": timer.timer_id,
            "name": timer.name,
            "duration_seconds": timer.duration_seconds,
            "state": timer.state,
            "remaining_seconds": max(0.0, timer.deadline - self._clock()) if timer.state == "running" else 0.0,
        }

    async def _expire(self, timer: Timer):
        while timer.state == "running":
            await self._sleep(max(0.0, timer.deadline - self._clock()))
            self._reconcile(timer)

    async def create_timer(self, name: str, duration_seconds: float) -> dict:
        if self._closed:
            raise RuntimeError("timer service closed")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("timer name must be nonblank")
        if (type(duration_seconds) not in (int, float)
                or not 0 < duration_seconds <= 86400
                or not math.isfinite(duration_seconds)):
            raise ValueError("duration must be finite and between 0 (exclusive) and 86400 seconds")
        timer = Timer(f"timer-{len(self._timers) + 1}", name.strip(), float(duration_seconds),
                      self._clock() + duration_seconds)
        self._timers[timer.timer_id] = timer
        self._tasks[timer.timer_id] = asyncio.create_task(self._expire(timer), name=timer.timer_id)
        return self._view(timer)

    async def list_timers(self) -> dict:
        return {"timers": [self._view(timer) for timer in self._timers.values()]}

    async def cancel_timer(self, timer_id: str) -> dict:
        if timer_id not in self._timers:
            raise ValueError("unknown timer ID")
        timer = self._timers[timer_id]
        self._reconcile(timer)
        if timer.state == "running":
            timer.state = "cancelled"
        task = self._tasks[timer_id]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return self._view(timer)

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("create_timer", True, {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "pattern": r"\S"},
                    "duration_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 86400},
                },
                "required": ["name", "duration_seconds"], "additionalProperties": False,
            }, self.create_timer),
            ToolDefinition("list_timers", False, {
                "type": "object", "properties": {}, "additionalProperties": False,
            }, self.list_timers),
            ToolDefinition("cancel_timer", True, {
                "type": "object", "properties": {"timer_id": {"type": "string", "minLength": 1}},
                "required": ["timer_id"], "additionalProperties": False,
            }, self.cancel_timer),
        ]

    async def close(self) -> None:
        self._closed = True
        for timer in self._timers.values():
            self._reconcile(timer)
            if timer.state == "running":
                timer.state = "cancelled"
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
