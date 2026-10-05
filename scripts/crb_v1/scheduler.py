"""Deterministic Asynchronous Event Scheduler and Event Tracer for CRB-v1.

Provides precise virtual/real async timeline tracking with structured event records.
"""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class EventRecord:
    scenario_id: str
    operation_id: str
    revision: int
    timestamp_ms: float
    event: str
    system: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventTracer:
    """Collects an immutable sequence of benchmark events for audit."""

    def __init__(self, scenario_id: str, system: str):
        self.scenario_id = scenario_id
        self.system = system
        self.start_time_ns = time.perf_counter_ns()
        self.records: List[EventRecord] = []

    def now_ms(self) -> float:
        return (time.perf_counter_ns() - self.start_time_ns) / 1e6

    def record(
        self,
        event: str,
        operation_id: str = "",
        revision: int = 1,
        details: Optional[Dict[str, Any]] = None,
        override_ms: Optional[float] = None,
    ) -> EventRecord:
        ts = override_ms if override_ms is not None else self.now_ms()
        rec = EventRecord(
            scenario_id=self.scenario_id,
            operation_id=operation_id,
            revision=revision,
            timestamp_ms=round(ts, 3),
            event=event,
            system=self.system,
            details=details or {},
        )
        self.records.append(rec)
        return rec


class AsyncBenchmarkScheduler:
    """Coordinates deterministic async event delivery for benchmark scenarios."""

    def __init__(self, tracer: EventTracer):
        self.tracer = tracer
        self._start_perf = time.perf_counter_ns()

    def elapsed_ms(self) -> float:
        return (time.perf_counter_ns() - self._start_perf) / 1e6

    async def sleep_until_ms(self, target_ms: float):
        """Sleeps asynchronously until the target scenario offset has been reached."""
        cur = self.elapsed_ms()
        diff = target_ms - cur
        if diff > 0:
            await asyncio.sleep(diff / 1000.0)
