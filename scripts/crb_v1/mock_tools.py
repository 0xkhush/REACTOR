"""Instrumented Asynchronous Mock Tools and Mutation Tracer for CRB-v1.

Implements realistic tool latencies and granular mutation tracing across 4 modes:
1. Pure read
2. Single atomic mutation (at completion)
3. Partial multi-stage mutation (staged over time)
4. Multi-step discrete mutation
"""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Set

from scripts.crb_v1.scheduler import EventTracer


@dataclass
class MutationRecord:
    scenario_id: str
    operation_id: str
    revision: int
    system: str
    mutation: str
    timestamp_ms: float
    committed: bool
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MutationTracker:
    """Immutable ledger of all committed and attempted state changes."""

    def __init__(self, scenario_id: str, system: str):
        self.scenario_id = scenario_id
        self.system = system
        self.mutations: List[MutationRecord] = []
        self._state_store: Dict[str, Any] = {}

    def get_state(self) -> Dict[str, Any]:
        return dict(self._state_store)

    def set_initial_state(self, initial_state: Dict[str, Any]):
        self._state_store = dict(initial_state)

    def record_mutation(
        self,
        operation_id: str,
        revision: int,
        mutation_name: str,
        timestamp_ms: float,
        payload: Dict[str, Any],
        apply_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> MutationRecord:
        if apply_fn:
            apply_fn(self._state_store)
        rec = MutationRecord(
            scenario_id=self.scenario_id,
            operation_id=operation_id,
            revision=revision,
            system=self.system,
            mutation=mutation_name,
            timestamp_ms=round(timestamp_ms, 3),
            committed=True,
            payload=payload,
        )
        self.mutations.append(rec)
        return rec


class InstrumentedAsyncTool:
    """Asynchronous tool executing over simulated latency and logging mutations."""

    def __init__(
        self,
        name: str,
        state_modifying: bool,
        duration_ms: float,
        mode: str = "atomic",  # "read", "atomic", "partial", "multi_step"
        stages: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.state_modifying = state_modifying
        self.duration_ms = duration_ms
        self.mode = mode
        # stages format: [{'offset_ms': 50, 'mutation': 'sub_mut_1', 'payload': {...}, 'apply': fn}]
        self.stages = stages or []

    async def execute(
        self,
        args: Dict[str, Any],
        operation_id: str,
        revision: int,
        tracer: EventTracer,
        mutation_tracker: MutationTracker,
    ) -> Dict[str, Any]:
        t_start = tracer.now_ms()
        tracer.record(
            "TOOL_STARTED",
            operation_id=operation_id,
            revision=revision,
            details={"args": args, "mode": self.mode, "duration_ms": self.duration_ms},
        )

        try:
            if not self.state_modifying or self.mode == "read":
                # Mode 1: Pure read
                await asyncio.sleep(self.duration_ms / 1000.0)
                res = {"status": "ok", "read_result": f"read_data_for_{self.name}"}

            elif self.mode == "atomic":
                # Mode 2: Mutation commits at completion
                await asyncio.sleep(self.duration_ms / 1000.0)
                t_commit = tracer.now_ms()
                key = args.get("id") or args.get("order_id") or args.get("reservation_id") or "target"
                val = args.get("value") or args.get("reason") or "mutated"

                def apply(s):
                    s[str(key)] = val

                mutation_tracker.record_mutation(
                    operation_id=operation_id,
                    revision=revision,
                    mutation_name=self.name,
                    timestamp_ms=t_commit,
                    payload=args,
                    apply_fn=apply,
                )
                tracer.record(
                    "MUTATION_COMMITTED",
                    operation_id=operation_id,
                    revision=revision,
                    details={"mutation": self.name, "payload": args},
                    override_ms=t_commit,
                )
                res = {"status": "ok", "result": f"committed_{self.name}"}

            elif self.mode in ("partial", "multi_step"):
                # Mode 3 & 4: Staged mutations
                sorted_stages = sorted(self.stages, key=lambda s: s["offset_ms"])
                prev_offset = 0.0

                for st in sorted_stages:
                    sleep_dur = st["offset_ms"] - prev_offset
                    if sleep_dur > 0:
                        await asyncio.sleep(sleep_dur / 1000.0)
                    prev_offset = st["offset_ms"]

                    t_stage = tracer.now_ms()
                    st_name = st.get("mutation", f"{self.name}_stage")
                    st_payload = st.get("payload", args)
                    st_apply = st.get("apply")

                    mutation_tracker.record_mutation(
                        operation_id=operation_id,
                        revision=revision,
                        mutation_name=st_name,
                        timestamp_ms=t_stage,
                        payload=st_payload,
                        apply_fn=st_apply,
                    )
                    tracer.record(
                        "MUTATION_COMMITTED",
                        operation_id=operation_id,
                        revision=revision,
                        details={"mutation": st_name, "stage_offset_ms": st["offset_ms"]},
                        override_ms=t_stage,
                    )

                remaining = self.duration_ms - prev_offset
                if remaining > 0:
                    await asyncio.sleep(remaining / 1000.0)
                res = {"status": "ok", "result": f"completed_multi_{self.name}"}

            else:
                await asyncio.sleep(self.duration_ms / 1000.0)
                res = {"status": "ok"}

            t_end = tracer.now_ms()
            tracer.record(
                "TOOL_COMPLETED",
                operation_id=operation_id,
                revision=revision,
                details={"elapsed_ms": round(t_end - t_start, 2)},
            )
            return res

        except asyncio.CancelledError:
            t_cancel = tracer.now_ms()
            tracer.record(
                "TOOL_CANCELLED",
                operation_id=operation_id,
                revision=revision,
                details={"interrupted_at_ms": round(t_cancel, 2)},
            )
            raise
