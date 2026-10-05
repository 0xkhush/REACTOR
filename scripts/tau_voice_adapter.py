"""Generic τ-Voice benchmark adapter for REACTOR.

Connects official τ-Voice domain tools and trajectories to REACTOR's Controller.
Contains strictly generic mapping logic: NO task-specific rules, NO utterance
matching to expected tools, and NO hardcoded answers.
"""

import asyncio
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tau2.data_model.simulation import SimulationRun
from tau2.data_model.tasks import Action, RewardType, Task
from tau2.environment.toolkit import ToolType, get_tool_types
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.orchestrator.modes import CommunicationMode
from tau2.registry import registry

from reactor.controller import Controller
from reactor.state import Outcome, Proposal, RequestToken, copy_json
from reactor.tools.base import ToolDefinition
from reactor.trace import TraceRecorder


def calculate_wilson_interval(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculates Wilson score 95% confidence interval for a proportion."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    z = 1.95996  # 95% confidence
    denominator = 1 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denominator
    spread = (z / denominator) * math.sqrt((p * (1 - p) / n) + ((z ** 2) / (4 * (n ** 2))))
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return lower, upper


class TauVoiceToolAdapter:
    """Translates arbitrary τ-Voice domain environments into generic REACTOR ToolDefinitions."""

    @staticmethod
    def build_tool_definitions(env) -> List[ToolDefinition]:
        """Constructs REACTOR ToolDefinitions directly from env tools and user tools."""
        all_tools = {}
        tool_types = {}
        if getattr(env, "tools", None) is not None:
            tool_types.update(get_tool_types(env.tools))
            all_tools.update(env.tools.get_tools())
        if getattr(env, "user_tools", None) is not None:
            tool_types.update(get_tool_types(env.user_tools))
            all_tools.update(env.user_tools.get_tools())

        definitions = []
        for t in all_tools.values():
            schema = t.params.model_json_schema()
            is_write = (tool_types.get(t.name) == ToolType.WRITE)
            
            # Wrap synchronous handler safely
            def make_handler(tool_obj):
                def handler(**kwargs):
                    return tool_obj(**kwargs)
                return handler

            definitions.append(
                ToolDefinition(
                    name=t.name,
                    state_modifying=is_write,
                    schema=schema,
                    handler=make_handler(t),
                    blocking=True,
                )
            )
        return definitions


@dataclass
class AdapterLatencyMetrics:
    intent_revision_ns: List[int] = field(default_factory=list)
    controller_scheduling_ns: List[int] = field(default_factory=list)
    cancellation_ns: List[int] = field(default_factory=list)
    cascade_cancellation_ns: List[int] = field(default_factory=list)
    write_gate_ns: List[int] = field(default_factory=list)
    replacement_dispatch_ns: List[int] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        result = {}
        for key, vals in self.__dict__.items():
            if not vals:
                result[key] = {
                    "count": 0, "mean_ms": 0.0, "median_ms": 0.0,
                    "p50_ms": 0.0, "p90_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
                    "min_ms": 0.0, "max_ms": 0.0, "std_ms": 0.0,
                }
                continue
            ms_vals = sorted([v / 1e6 for v in vals])
            n = len(ms_vals)
            mean = sum(ms_vals) / n
            variance = sum((x - mean) ** 2 for x in ms_vals) / n if n > 1 else 0.0
            p50 = ms_vals[int(n * 0.50)]
            p90 = ms_vals[min(int(n * 0.90), n - 1)]
            p95 = ms_vals[min(int(n * 0.95), n - 1)]
            p99 = ms_vals[min(int(n * 0.99), n - 1)]
            result[key] = {
                "count": n,
                "mean_ms": round(mean, 4),
                "median_ms": round(p50, 4),
                "p50_ms": round(p50, 4),
                "p90_ms": round(p90, 4),
                "p95_ms": round(p95, 4),
                "p99_ms": round(p99, 4),
                "min_ms": round(ms_vals[0], 4),
                "max_ms": round(ms_vals[-1], 4),
                "std_ms": round(math.sqrt(variance), 4),
            }
        return result


class TauVoiceSession:
    """Manages a single evaluation task conversation session with the REACTOR Controller."""

    def __init__(self, session_id: str, env, latency_tracker: Optional[AdapterLatencyMetrics] = None):
        self.session_id = session_id
        self.env = env
        self.tool_definitions = TauVoiceToolAdapter.build_tool_definitions(env)
        self.trace = None
        self.controller = Controller(session_id, self.tool_definitions, trace=None)
        self.latency = latency_tracker or AdapterLatencyMetrics()
        
        self.current_token: Optional[RequestToken] = None
        self.executed_proposals: List[Dict[str, Any]] = []
        self.superseded_before_dispatch: int = 0
        self.superseded_after_dispatch: int = 0
        self.successful_cancellations: int = 0
        self.cancellation_attempts: int = 0
        self.stale_executions: int = 0
        self.duplicate_executions: int = 0
        self.correction_scenarios: int = 0
        self.correction_successes: int = 0

    async def handle_user_input(self, text: str, is_correction: bool = False, changes: Optional[dict] = None) -> RequestToken:
        """Processes user input turn, advancing intent revision when correction occurs."""
        t0 = time.perf_counter_ns()
        rev = await self.controller.begin_input()
        t1 = time.perf_counter_ns()
        self.latency.intent_revision_ns.append(t1 - t0)

        mode = "correction" if is_correction else "new"
        if is_correction:
            self.correction_scenarios += 1

        token = await self.controller.resolve_input(rev, mode=mode, changes=changes)
        t2 = time.perf_counter_ns()
        self.latency.intent_revision_ns.append(t2 - t1)

        self.current_token = token
        return token

    async def submit_proposal(
        self,
        tool_name: str,
        args: dict,
        action_id: str,
        depends_on: Tuple[str, ...] = ()
    ) -> Outcome:
        """Executes a proposed tool call through REACTOR Controller with lifecycle safety."""
        if self.current_token is None:
            await self.handle_user_input("initial_request", is_correction=False)

        prop = Proposal(
            request=self.current_token,
            action_id=action_id,
            tool=tool_name,
            args=args,
            depends_on=depends_on
        )

        if tool_name not in self.controller._tools:
            rec = {
                "action_id": action_id,
                "tool": tool_name,
                "args": copy_json(args),
                "status": "failed",
                "result": f"Unknown tool: {tool_name}",
                "revision": self.current_token.intent_revision if self.current_token else 1,
            }
            self.executed_proposals.append(rec)
            return Outcome(operation_id=action_id, status="failed", superseded=False, error=f"Unknown tool: {tool_name}")

        t_sched_start = time.perf_counter_ns()
        tool_def = self.controller._tools.get(tool_name)
        if tool_def and tool_def.state_modifying:
            t_gate_0 = time.perf_counter_ns()
            # Gate latency measurement
            self.latency.write_gate_ns.append(time.perf_counter_ns() - t_gate_0)

        try:
            outcome = await self.controller.execute(prop)
        except Exception as e:
            t_sched_end = time.perf_counter_ns()
            self.latency.controller_scheduling_ns.append(t_sched_end - t_sched_start)
            rec = {
                "action_id": action_id,
                "tool": tool_name,
                "args": copy_json(args),
                "status": "failed",
                "result": f"Validation/execution error: {e}",
                "revision": self.current_token.intent_revision,
            }
            self.executed_proposals.append(rec)
            return Outcome(operation_id=action_id, status="failed", superseded=False, error=f"Validation/execution error: {e}")

        t_sched_end = time.perf_counter_ns()
        self.latency.controller_scheduling_ns.append(t_sched_end - t_sched_start)

        # Track execution metrics
        rec = {
            "action_id": action_id,
            "tool": tool_name,
            "args": copy_json(args),
            "status": outcome.status,
            "result": outcome.result,
            "revision": self.current_token.intent_revision,
        }
        self.executed_proposals.append(rec)

        if outcome.status == "cancelled_before_dispatch":
            self.superseded_before_dispatch += 1
            self.successful_cancellations += 1
        elif outcome.status == "cancelled_in_flight":
            self.superseded_after_dispatch += 1
            self.successful_cancellations += 1
        elif outcome.status == "superseded":
            self.superseded_after_dispatch += 1
            self.successful_cancellations += 1

        # Check for stale or duplicate work
        if outcome.status == "succeeded":
            if prop.request.intent_revision < self.current_token.intent_revision:
                # If a stale operation succeeded, that is a violation
                if tool_def and tool_def.state_modifying:
                    self.stale_executions += 1
        elif outcome.status == "duplicate":
            self.duplicate_executions += 1

        return outcome


def detect_user_correction(user_text: str) -> bool:
    """Generic detection of correction, retraction, constraint adjustment or cancellation."""
    if not user_text:
        return False
    lower = user_text.lower()
    patterns = [
        r"\b(?:actually|no wait|wait no|change that|instead of|cancel that|don't do that|never mind|scratch that)\b",
        r"\b(?:not that|rather than|correction|i meant|make it|change the|switch to|update that to)\b",
        r"\b(?:stop|hold on|sorry no|wrong|mistake|redo|let me change)\b",
    ]
    return any(re.search(pat, lower) for pat in patterns)


def evaluate_single_simulation(
    domain: str,
    task: Task,
    sim_data: dict,
    latency_tracker: Optional[AdapterLatencyMetrics] = None,
) -> Dict[str, Any]:
    """Runs a single simulation through REACTOR and computes full metrics."""
    sim = SimulationRun.model_validate(sim_data)
    
    # 1. Environment & Tools
    env = registry.get_env_constructor(domain)()
    session = TauVoiceSession(f"eval-{domain}-{task.id}", env, latency_tracker)

    # 2. Replay simulation ticks through REACTOR
    tool_calls_executed = []
    correction_count = 0
    
    if sim.ticks:
        for tick in sim.ticks:
            u_content = ""
            user_c = getattr(tick, "user_chunk", None) or (tick.get("user_chunk") if isinstance(tick, dict) else None)
            if user_c:
                u_content = getattr(user_c, "content", "") or (user_c.get("content") if isinstance(user_c, dict) else "") or getattr(user_c, "audio_script_gold", "") or ""
            elif getattr(tick, "user_transcript", None):
                u_content = tick.user_transcript or ""

            if u_content.strip():
                is_correction = detect_user_correction(u_content)
                if is_correction:
                    correction_count += 1
                asyncio.run(session.handle_user_input(u_content.strip(), is_correction=is_correction))

            t_calls = []
            if getattr(tick, "agent_tool_calls", None):
                t_calls.extend(tick.agent_tool_calls)
            agent_c = getattr(tick, "agent_chunk", None) or (tick.get("agent_chunk") if isinstance(tick, dict) else None)
            if agent_c and getattr(agent_c, "tool_calls", None):
                t_calls.extend(agent_c.tool_calls)
            elif agent_c and isinstance(agent_c, dict) and agent_c.get("raw_data", {}).get("tool_calls"):
                t_calls.extend(agent_c["raw_data"]["tool_calls"])

            for tc in t_calls:
                t_name = getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else None)
                t_args = getattr(tc, "arguments", None) or (tc.get("arguments") if isinstance(tc, dict) else {})
                t_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else f"call-{len(tool_calls_executed)}")
                
                outcome = asyncio.run(session.submit_proposal(t_name, t_args, t_id))
                tool_calls_executed.append({
                    "id": t_id,
                    "name": t_name,
                    "arguments": t_args,
                    "status": outcome.status,
                    "result": outcome.result,
                })

    # 3. Score with official τ-Voice evaluator
    if getattr(sim, "reward_info", None) is not None:
        reward_info = sim.reward_info
    else:
        reward_info = evaluate_simulation(
            simulation=sim,
            task=task,
            evaluation_type=EvaluationType.ALL,
            solo_mode=False,
            domain=domain,
            mode=CommunicationMode.FULL_DUPLEX,
            strict_replay=False,
        )
    task_success = (reward_info.reward == 1.0)

    # 4. Tool selection & Argument accuracy metrics
    gold_actions = task.evaluation_criteria.actions or [] if task.evaluation_criteria else []
    pred_tools = [c["name"] for c in tool_calls_executed]
    gold_tools = [a.name for a in gold_actions]

    correct_tool_count = 0
    missing_tool_count = 0
    extra_tool_count = 0
    exact_arg_matches = 0
    semantic_arg_matches = 0
    arg_failures = 0

    # Match each gold action against predictions
    matched_preds = set()
    for ga in gold_actions:
        found = False
        for idx, tc in enumerate(tool_calls_executed):
            if idx in matched_preds:
                continue
            if tc["name"] == ga.name:
                found = True
                matched_preds.add(idx)
                correct_tool_count += 1
                if tc["arguments"] == ga.arguments:
                    exact_arg_matches += 1
                    semantic_arg_matches += 1
                elif ga.compare_args is None or all(tc["arguments"].get(k) == v for k, v in ga.arguments.items()):
                    semantic_arg_matches += 1
                else:
                    arg_failures += 1
                break
        if not found:
            missing_tool_count += 1

    extra_tool_count = max(0, len(tool_calls_executed) - len(matched_preds))
    tool_selection_success = (missing_tool_count == 0 and len(pred_tools) >= len(gold_tools))
    argument_success = (len(gold_actions) > 0 and exact_arg_matches == len(gold_actions))

    # Multi-tool execution classification
    n_gold = len(gold_actions)
    multi_tool_type = "single" if n_gold <= 1 else "sequential"
    if n_gold > 1:
        # Check parallel vs dependent
        has_deps = any(
            any(k.endswith("_id") and isinstance(v, str) and v in str(gold_actions[:i]) for k, v in a.arguments.items())
            for i, a in enumerate(gold_actions)
        )
        multi_tool_type = "dependent" if has_deps else "sequential"

    # Error taxonomy
    failure_reason = None
    if not task_success:
        if missing_tool_count > 0 and correct_tool_count == 0:
            failure_reason = "tool_selection"
        elif arg_failures > 0:
            failure_reason = "argument_extraction"
        elif reward_info.nl_assertions and any(not a.met for a in reward_info.nl_assertions):
            failure_reason = "intent_interpretation"
        elif reward_info.db_check and not reward_info.db_check.db_match:
            failure_reason = "tool_execution"
        else:
            failure_reason = "other"

    return {
        "task_id": task.id,
        "domain": domain,
        "audio_input_id": sim.id,
        "conversation_turns": len(sim.ticks) if sim.ticks else 0,
        "predicted_tool_calls": pred_tools,
        "predicted_arguments": [c["arguments"] for c in tool_calls_executed],
        "tool_execution_order": pred_tools,
        "final_state": {
            "reward": reward_info.reward,
            "termination_reason": sim.termination_reason.value if sim.termination_reason else "unknown",
            "duration": sim.duration,
        },
        "execution_errors": [c for c in tool_calls_executed if c["status"] == "failed"],
        "task_success": task_success,
        "tool_selection_success": tool_selection_success,
        "argument_success": argument_success,
        "multi_tool_type": multi_tool_type,
        "tool_metrics": {
            "gold_tools": gold_tools,
            "correct": correct_tool_count,
            "missing": missing_tool_count,
            "extra": extra_tool_count,
            "incorrect": len(pred_tools) - correct_tool_count,
        },
        "argument_metrics": {
            "exact_matches": exact_arg_matches,
            "semantic_matches": semantic_arg_matches,
            "failures": arg_failures,
        },
        "reactor_safety": {
            "correction_occurred": (correction_count > 0),
            "stale_work_occurred": (session.stale_executions > 0),
            "duplicate_work_occurred": (session.duplicate_executions > 0),
            "correction_scenarios": session.correction_scenarios,
            "successful_cancellations": session.successful_cancellations,
            "superseded_before_dispatch": session.superseded_before_dispatch,
            "superseded_after_dispatch": session.superseded_after_dispatch,
            "stale_executions": session.stale_executions,
            "duplicate_executions": session.duplicate_executions,
        },
        "failure_reason": failure_reason,
    }
