"""Four Experimental Systems for CRB-v1.

System A: Naive Dispatch (No cancellation, immediate execution)
System B: AsyncCancel (Cooperative asyncio.Task.cancel() on correction)
System C: HoldConfirm (300 ms hold window before dispatch)
System D: REACTOR (Unmodified Controller)
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from reactor.controller import Controller
from reactor.state import Proposal, RequestToken
from reactor.tools.base import ToolDefinition

from scripts.crb_v1.mock_tools import InstrumentedAsyncTool, MutationTracker
from scripts.crb_v1.scheduler import EventTracer


class BaseSystemRunner:
    def __init__(
        self,
        system_name: str,
        tracer: EventTracer,
        mutation_tracker: MutationTracker,
        tools: Dict[str, InstrumentedAsyncTool],
    ):
        self.system_name = system_name
        self.tracer = tracer
        self.mutation_tracker = mutation_tracker
        self.tools = tools
        self.cancellation_latencies_ms: List[float] = []
        self.gate_latencies_us: List[float] = []

    async def run_scenario(self, scenario_spec: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# System A: Naive Dispatch
# -----------------------------------------------------------------------------
class NaiveDispatchRunner(BaseSystemRunner):
    """Dispatches immediately, ignores corrections, never cancels."""

    async def run_scenario(self, scenario_spec: Dict[str, Any]) -> Dict[str, Any]:
        t0 = self.tracer.now_ms()
        self.tracer.record("USER_INTENT", revision=1, details={"scenario": scenario_spec["scenario_id"]})

        # Launch initial operation
        init_act = scenario_spec["initial_action"]
        tool_init = self.tools[init_act["name"]]
        op_init_id = "op_init"

        self.tracer.record("PROPOSAL_CREATED", operation_id=op_init_id, revision=1, details=init_act)
        self.tracer.record("OPERATION_ADMITTED", operation_id=op_init_id, revision=1)

        task_init = asyncio.create_task(
            tool_init.execute(
                init_act["arguments"],
                operation_id=op_init_id,
                revision=1,
                tracer=self.tracer,
                mutation_tracker=self.mutation_tracker,
            )
        )

        # Wait for correction offset
        corr_offset_ms = scenario_spec.get("correction_offset_ms", 50.0)
        await asyncio.sleep(corr_offset_ms / 1000.0)

        # Correction arrives
        corr_act = scenario_spec.get("corrected_action")
        self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})

        # Naive: does not cancel task_init; waits for it to complete
        try:
            await task_init
        except Exception as e:
            pass

        # Then dispatches corrected action if present
        if corr_act:
            tool_corr = self.tools[corr_act["name"]]
            op_corr_id = "op_corr"
            self.tracer.record("PROPOSAL_CREATED", operation_id=op_corr_id, revision=2, details=corr_act)
            self.tracer.record("OPERATION_ADMITTED", operation_id=op_corr_id, revision=2)
            try:
                await tool_corr.execute(
                    corr_act["arguments"],
                    operation_id=op_corr_id,
                    revision=2,
                    tracer=self.tracer,
                    mutation_tracker=self.mutation_tracker,
                )
            except Exception:
                pass

        return {
            "system": self.system_name,
            "scenario_id": scenario_spec["scenario_id"],
            "elapsed_ms": self.tracer.now_ms() - t0,
        }


# -----------------------------------------------------------------------------
# System B: AsyncCancel
# -----------------------------------------------------------------------------
class AsyncCancelRunner(BaseSystemRunner):
    """Conventional cooperative cancellation via asyncio.Task.cancel()."""

    async def run_scenario(self, scenario_spec: Dict[str, Any]) -> Dict[str, Any]:
        t0 = self.tracer.now_ms()
        self.tracer.record("USER_INTENT", revision=1, details={"scenario": scenario_spec["scenario_id"]})

        init_act = scenario_spec["initial_action"]
        tool_init = self.tools[init_act["name"]]
        op_init_id = "op_init"

        self.tracer.record("PROPOSAL_CREATED", operation_id=op_init_id, revision=1, details=init_act)
        self.tracer.record("OPERATION_ADMITTED", operation_id=op_init_id, revision=1)

        task_init = asyncio.create_task(
            tool_init.execute(
                init_act["arguments"],
                operation_id=op_init_id,
                revision=1,
                tracer=self.tracer,
                mutation_tracker=self.mutation_tracker,
            )
        )

        corr_offset_ms = scenario_spec.get("correction_offset_ms", 50.0)
        await asyncio.sleep(corr_offset_ms / 1000.0)

        # Correction arrives
        corr_act = scenario_spec.get("corrected_action")
        t_corr = self.tracer.now_ms()
        self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})

        # Cancel running task
        self.tracer.record("CANCELLATION_REQUESTED", operation_id=op_init_id, revision=1)
        task_init.cancel()

        try:
            await task_init
        except asyncio.CancelledError:
            t_cancelled = self.tracer.now_ms()
            cancel_lat = t_cancelled - t_corr
            self.cancellation_latencies_ms.append(cancel_lat)
        except Exception:
            pass

        # Dispatch corrected action if present
        if corr_act:
            tool_corr = self.tools[corr_act["name"]]
            op_corr_id = "op_corr"
            self.tracer.record("PROPOSAL_CREATED", operation_id=op_corr_id, revision=2, details=corr_act)
            self.tracer.record("OPERATION_ADMITTED", operation_id=op_corr_id, revision=2)
            try:
                await tool_corr.execute(
                    corr_act["arguments"],
                    operation_id=op_corr_id,
                    revision=2,
                    tracer=self.tracer,
                    mutation_tracker=self.mutation_tracker,
                )
            except Exception:
                pass

        return {
            "system": self.system_name,
            "scenario_id": scenario_spec["scenario_id"],
            "elapsed_ms": self.tracer.now_ms() - t0,
        }


# -----------------------------------------------------------------------------
# System C: HoldConfirm
# -----------------------------------------------------------------------------
class HoldConfirmRunner(BaseSystemRunner):
    """Holds proposal for fixed 300 ms window before dispatch; cancels on mid-hold correction."""

    def __init__(
        self,
        system_name: str,
        tracer: EventTracer,
        mutation_tracker: MutationTracker,
        tools: Dict[str, InstrumentedAsyncTool],
        hold_ms: float = 300.0,
    ):
        super().__init__(system_name, tracer, mutation_tracker, tools)
        self.hold_ms = hold_ms

    async def run_scenario(self, scenario_spec: Dict[str, Any]) -> Dict[str, Any]:
        t0 = self.tracer.now_ms()
        self.tracer.record("USER_INTENT", revision=1, details={"scenario": scenario_spec["scenario_id"]})

        init_act = scenario_spec["initial_action"]
        tool_init = self.tools[init_act["name"]]
        op_init_id = "op_init"

        self.tracer.record("PROPOSAL_CREATED", operation_id=op_init_id, revision=1, details=init_act)

        corr_offset_ms = scenario_spec.get("correction_offset_ms", 50.0)

        # Hold window vs Correction timing
        if corr_offset_ms < self.hold_ms:
            # Correction arrives DURING hold window -> initial proposal suppressed before dispatch
            await asyncio.sleep(corr_offset_ms / 1000.0)
            corr_act = scenario_spec.get("corrected_action")
            self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})
            self.tracer.record("TOOL_CANCELLED", operation_id=op_init_id, revision=1, details={"reason": "suppressed_in_hold_window"})

            if corr_act:
                # Wait hold window for corrected action
                await asyncio.sleep(self.hold_ms / 1000.0)
                tool_corr = self.tools[corr_act["name"]]
                op_corr_id = "op_corr"
                self.tracer.record("PROPOSAL_CREATED", operation_id=op_corr_id, revision=2, details=corr_act)
                self.tracer.record("OPERATION_ADMITTED", operation_id=op_corr_id, revision=2)
                try:
                    await tool_corr.execute(
                        corr_act["arguments"],
                        operation_id=op_corr_id,
                        revision=2,
                        tracer=self.tracer,
                        mutation_tracker=self.mutation_tracker,
                    )
                except Exception:
                    pass
        else:
            # Hold expires before correction -> initial proposal is dispatched
            await asyncio.sleep(self.hold_ms / 1000.0)
            self.tracer.record("OPERATION_ADMITTED", operation_id=op_init_id, revision=1)
            task_init = asyncio.create_task(
                tool_init.execute(
                    init_act["arguments"],
                    operation_id=op_init_id,
                    revision=1,
                    tracer=self.tracer,
                    mutation_tracker=self.mutation_tracker,
                )
            )
            # Sleep until correction arrives
            rem_sleep = corr_offset_ms - self.hold_ms
            if rem_sleep > 0:
                await asyncio.sleep(rem_sleep / 1000.0)

            corr_act = scenario_spec.get("corrected_action")
            self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})
            try:
                await task_init
            except Exception:
                pass

            if corr_act:
                await asyncio.sleep(self.hold_ms / 1000.0)
                tool_corr = self.tools[corr_act["name"]]
                op_corr_id = "op_corr"
                self.tracer.record("PROPOSAL_CREATED", operation_id=op_corr_id, revision=2, details=corr_act)
                self.tracer.record("OPERATION_ADMITTED", operation_id=op_corr_id, revision=2)
                try:
                    await tool_corr.execute(
                        corr_act["arguments"],
                        operation_id=op_corr_id,
                        revision=2,
                        tracer=self.tracer,
                        mutation_tracker=self.mutation_tracker,
                    )
                except Exception:
                    pass

        return {
            "system": self.system_name,
            "scenario_id": scenario_spec["scenario_id"],
            "elapsed_ms": self.tracer.now_ms() - t0,
        }


# -----------------------------------------------------------------------------
# System D: REACTOR (Unmodified Controller)
# -----------------------------------------------------------------------------
class ReactorRunner(BaseSystemRunner):
    """Executes proposals through unchanged REACTOR Controller."""

    def __init__(
        self,
        system_name: str,
        tracer: EventTracer,
        mutation_tracker: MutationTracker,
        tools: Dict[str, InstrumentedAsyncTool],
    ):
        super().__init__(system_name, tracer, mutation_tracker, tools)
        self.controller: Optional[Controller] = None
        self._init_controller()

    def _init_controller(self):
        tool_defs = []
        for name, t_obj in self.tools.items():
            # Build async handler calling InstrumentedAsyncTool
            def make_handler(tool_instance):
                async def handler(**kwargs):
                    # In REACTOR, the tool handler executes when admitted
                    rev = getattr(handler, "active_revision", 1)
                    op_id = getattr(handler, "active_op_id", "op")
                    return await tool_instance.execute(
                        kwargs,
                        operation_id=op_id,
                        revision=rev,
                        tracer=self.tracer,
                        mutation_tracker=self.mutation_tracker,
                    )
                return handler

            h = make_handler(t_obj)
            tool_defs.append(
                ToolDefinition(
                    name=name,
                    state_modifying=t_obj.state_modifying,
                    schema={"type": "object"},
                    handler=h,
                    blocking=False,  # Coroutine handler
                )
            )
        self.controller = Controller(session_id=f"crb_{self.system_name}_{self.tracer.scenario_id}", tools=tool_defs)

    async def run_scenario(self, scenario_spec: Dict[str, Any]) -> Dict[str, Any]:
        t0 = self.tracer.now_ms()
        self.tracer.record("USER_INTENT", revision=1, details={"scenario": scenario_spec["scenario_id"]})

        init_act = scenario_spec["initial_action"]
        t_gate_start = time.perf_counter_ns()
        rev1 = await self.controller.begin_input()
        token1 = await self.controller.resolve_input(rev1, mode="new")
        t_gate_end = time.perf_counter_ns()
        self.gate_latencies_us.append((t_gate_end - t_gate_start) / 1000.0)

        op_init_id = "op_init"
        self.tracer.record("PROPOSAL_CREATED", operation_id=op_init_id, revision=1, details=init_act)

        # Set active revision and op_id on handler
        tool_def = self.controller._tools[init_act["name"]]
        tool_def.handler.active_revision = 1
        tool_def.handler.active_op_id = op_init_id

        prop1 = Proposal(
            request=token1,
            action_id=op_init_id,
            tool=init_act["name"],
            args=init_act["arguments"],
        )

        timing_class = scenario_spec.get("timing_class", "in_flight")
        corr_offset_ms = scenario_spec.get("correction_offset_ms", 50.0)

        if timing_class == "pre_dispatch":
            # Scenario Class A: Correction arrives BEFORE execute(prop1) is called
            await asyncio.sleep(corr_offset_ms / 1000.0)
            corr_act = scenario_spec.get("corrected_action")
            self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})

            t_gate_start2 = time.perf_counter_ns()
            rev2 = await self.controller.begin_input()
            token2 = await self.controller.resolve_input(rev2, mode="correction")
            self.gate_latencies_us.append((time.perf_counter_ns() - t_gate_start2) / 1000.0)

            # Now prop1 attempts execution (should be cancelled_before_dispatch)
            out1 = await self.controller.execute(prop1)
            self.tracer.record("TOOL_CANCELLED", operation_id=op_init_id, revision=1, details={"status": out1.status, "reason": out1.error})

            if corr_act:
                tool_def_corr = self.controller._tools[corr_act["name"]]
                tool_def_corr.handler.active_revision = 2
                tool_def_corr.handler.active_op_id = "op_corr"
                prop2 = Proposal(
                    request=token2,
                    action_id="op_corr",
                    tool=corr_act["name"],
                    args=corr_act["arguments"],
                )
                self.tracer.record("PROPOSAL_CREATED", operation_id="op_corr", revision=2, details=corr_act)
                self.tracer.record("OPERATION_ADMITTED", operation_id="op_corr", revision=2)
                await self.controller.execute(prop2)

        else:
            # Scenario Class B, C, D: Tool A is admitted and actively running in-flight!
            self.tracer.record("OPERATION_ADMITTED", operation_id=op_init_id, revision=1)
            exec_task = asyncio.create_task(self.controller.execute(prop1))

            # Allow tool to start running
            await asyncio.sleep(corr_offset_ms / 1000.0)

            # User correction arrives while Tool A is actively running!
            corr_act = scenario_spec.get("corrected_action")
            t_corr = self.tracer.now_ms()
            self.tracer.record("USER_CORRECTION", revision=2, details={"corrected_action": corr_act})

            t_gate_start2 = time.perf_counter_ns()
            rev2 = await self.controller.begin_input()
            token2 = await self.controller.resolve_input(rev2, mode="correction")
            self.gate_latencies_us.append((time.perf_counter_ns() - t_gate_start2) / 1000.0)

            # Wait for initial execution task to complete
            out1 = await exec_task
            t_out1 = self.tracer.now_ms()
            self.cancellation_latencies_ms.append(t_out1 - t_corr)

            if corr_act:
                tool_def_corr = self.controller._tools[corr_act["name"]]
                tool_def_corr.handler.active_revision = 2
                tool_def_corr.handler.active_op_id = "op_corr"
                prop2 = Proposal(
                    request=token2,
                    action_id="op_corr",
                    tool=corr_act["name"],
                    args=corr_act["arguments"],
                )
                self.tracer.record("PROPOSAL_CREATED", operation_id="op_corr", revision=2, details=corr_act)
                self.tracer.record("OPERATION_ADMITTED", operation_id="op_corr", revision=2)
                await self.controller.execute(prop2)

        return {
            "system": self.system_name,
            "scenario_id": scenario_spec["scenario_id"],
            "elapsed_ms": self.tracer.now_ms() - t0,
        }
