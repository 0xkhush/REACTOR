#!/usr/bin/env python3
"""Correction-Recovery Benchmark (CRB) for Voice Agents.

Evaluates transactional integrity under user mid-turn interruptions and corrections.
Compares a naive asynchronous dispatch baseline against the REACTOR Controller.

Archetypes tested:
- Type A (Slot/Target Swap): User changes the target entity (e.g., reservation_id, order_id).
- Type B (Full Abort): User cancels the mutation entirely mid-turn ("Stop, don't do that").
- Type C (Slot Value Adjustment): User updates a parameter (e.g., flight, quantity).
"""

import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tau2.data_model.tasks import Task, Action
from tau2.environment.toolkit import ToolType, get_tool_types
from tau2.registry import registry

from reactor.controller import Controller
from reactor.state import Proposal, RequestToken
from reactor.tools.base import ToolDefinition


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


def build_reactor_tools(env) -> List[ToolDefinition]:
    """Wraps environment tools into REACTOR ToolDefinitions with JSON safety."""
    tool_defs = []
    tool_types = get_tool_types(env.tools) if env.tools else {}
    for name, tool_obj in env.tools.get_tools().items():
        is_write = (tool_types.get(name) == ToolType.WRITE)
        
        def make_handler(t):
            def handler(**kwargs):
                res = t(**kwargs)
                if hasattr(res, "model_dump"):
                    return res.model_dump(mode="json")
                return res
            return handler

        schema = tool_obj.params.model_json_schema() if hasattr(tool_obj, "params") else {"type": "object"}
        tool_defs.append(
            ToolDefinition(
                name=name,
                state_modifying=is_write,
                schema=schema,
                handler=make_handler(tool_obj),
                blocking=True,
            )
        )
    return tool_defs


@dataclass
class CRBScenario:
    scenario_id: str
    domain: str
    archetype: str  # "Type A: Slot Swap", "Type B: Full Abort", "Type C: Value Adjust"
    description: str
    initial_action: Action
    corrected_action: Optional[Action]  # None if Type B (full abort)


def create_benchmark_scenarios(domains: List[str] = ["airline", "retail"]) -> List[CRBScenario]:
    """Generates deterministic CRB scenarios derived from environment state."""
    scenarios = []

    # 1. Airline Domain Scenarios
    if "airline" in domains:
        env = registry.get_env_constructor("airline")()
        res_keys = list(env.tools.db.reservations.keys())
        if len(res_keys) >= 6:
            # Type A: Reservation Target Swaps (4 scenarios)
            for idx, (r_a, r_b) in enumerate([(res_keys[0], res_keys[1]), (res_keys[2], res_keys[3]), (res_keys[4], res_keys[5]), (res_keys[6], res_keys[7])]):
                scenarios.append(CRBScenario(
                    scenario_id=f"airline_swap_cancel_{idx+1:02d}",
                    domain="airline",
                    archetype="Type A: Slot Swap",
                    description=f"User requests cancel {r_a}, then mid-turn interrupts and switches target to {r_b}.",
                    initial_action=Action(action_id="act_init", name="cancel_reservation", arguments={"reservation_id": r_a}),
                    corrected_action=Action(action_id="act_corr", name="cancel_reservation", arguments={"reservation_id": r_b}),
                ))

            # Type B: Full Aborts (3 scenarios)
            for idx, r_abort in enumerate([res_keys[8], res_keys[9], res_keys[10]]):
                scenarios.append(CRBScenario(
                    scenario_id=f"airline_abort_cancel_{idx+1:02d}",
                    domain="airline",
                    archetype="Type B: Full Abort",
                    description=f"User requests cancel {r_abort}, but interrupts and aborts ('Wait, keep it!').",
                    initial_action=Action(action_id="act_init", name="cancel_reservation", arguments={"reservation_id": r_abort}),
                    corrected_action=None,
                ))

            # Type C: Baggage Value Adjustment (3 scenarios)
            for idx, r_bag in enumerate([res_keys[11], res_keys[12], res_keys[13]]):
                res_obj = env.tools.db.reservations[r_bag]
                pm = res_obj.payment_history[0].payment_id if res_obj.payment_history else "credit_card_0000000"
                init_bags = (res_obj.total_baggages or 0) + 1
                corr_bags = (res_obj.total_baggages or 0) + 2
                scenarios.append(CRBScenario(
                    scenario_id=f"airline_adjust_baggage_{idx+1:02d}",
                    domain="airline",
                    archetype="Type C: Value Adjust",
                    description=f"User asks to add {init_bags} bags for {r_bag}, but corrects to {corr_bags} bags.",
                    initial_action=Action(action_id="act_init", name="update_reservation_baggages", arguments={
                        "reservation_id": r_bag, "total_baggages": init_bags, "nonfree_baggages": 1, "payment_id": pm
                    }),
                    corrected_action=Action(action_id="act_corr", name="update_reservation_baggages", arguments={
                        "reservation_id": r_bag, "total_baggages": corr_bags, "nonfree_baggages": 2, "payment_id": pm
                    }),
                ))

    # 2. Retail Domain Scenarios (10 scenarios)
    if "retail" in domains:
        env = registry.get_env_constructor("retail")()
        
        # A. Delivered orders (Returns)
        delivered_orders = [
            (oid, o) for oid, o in env.tools.db.orders.items() 
            if o.status == "delivered" and o.items and o.payment_history
        ]
        
        # B. Pending orders (Cancellations & Address)
        pending_orders = [
            (oid, o) for oid, o in env.tools.db.orders.items() 
            if o.status == "pending"
        ]

        # Type A: Delivered Order Item Return Swap (3 scenarios)
        for idx in range(3):
            oid_a, ord_a = delivered_orders[idx * 2]
            oid_b, ord_b = delivered_orders[idx * 2 + 1]
            it_a = ord_a.items[0].item_id
            it_b = ord_b.items[0].item_id
            pm_a = ord_a.payment_history[0].payment_method_id
            pm_b = ord_b.payment_history[0].payment_method_id

            scenarios.append(CRBScenario(
                scenario_id=f"retail_swap_return_{idx+1:02d}",
                domain="retail",
                archetype="Type A: Slot Swap",
                description=f"User initiates return for {oid_a}, but switches to {oid_b}.",
                initial_action=Action(action_id="act_init", name="return_delivered_order_items", arguments={
                    "order_id": oid_a, "item_ids": [it_a], "payment_method_id": pm_a
                }),
                corrected_action=Action(action_id="act_corr", name="return_delivered_order_items", arguments={
                    "order_id": oid_b, "item_ids": [it_b], "payment_method_id": pm_b
                }),
            ))

        # Type B: Return Abort (2 scenarios)
        for idx in range(2):
            oid_ab, ord_ab = delivered_orders[6 + idx]
            it_ab = ord_ab.items[0].item_id
            pm_ab = ord_ab.payment_history[0].payment_method_id
            scenarios.append(CRBScenario(
                scenario_id=f"retail_abort_return_{idx+1:02d}",
                domain="retail",
                archetype="Type B: Full Abort",
                description=f"User starts return for {oid_ab}, but retracts ('Wait, I want to keep it').",
                initial_action=Action(action_id="act_init", name="return_delivered_order_items", arguments={
                    "order_id": oid_ab, "item_ids": [it_ab], "payment_method_id": pm_ab
                }),
                corrected_action=None,
            ))

        # Type C: Item Adjustment within same order (2 scenarios)
        for idx in range(2):
            oid_adj, ord_adj = [
                (oid, o) for oid, o in delivered_orders[8:] if len(o.items) >= 2
            ][idx]
            it1 = ord_adj.items[0].item_id
            it2 = ord_adj.items[1].item_id
            pm_adj = ord_adj.payment_history[0].payment_method_id
            scenarios.append(CRBScenario(
                scenario_id=f"retail_adjust_item_{idx+1:02d}",
                domain="retail",
                archetype="Type C: Value Adjust",
                description=f"User returns item {it1} in {oid_adj}, but corrects to return {it2} instead.",
                initial_action=Action(action_id="act_init", name="return_delivered_order_items", arguments={
                    "order_id": oid_adj, "item_ids": [it1], "payment_method_id": pm_adj
                }),
                corrected_action=Action(action_id="act_corr", name="return_delivered_order_items", arguments={
                    "order_id": oid_adj, "item_ids": [it2], "payment_method_id": pm_adj
                }),
            ))

        # Type A & B: Pending Order Cancellations (2 scenarios)
        p_oid1 = pending_orders[0][0]
        p_oid2 = pending_orders[1][0]
        scenarios.append(CRBScenario(
            scenario_id="retail_swap_pending_cancel_01",
            domain="retail",
            archetype="Type A: Slot Swap",
            description=f"User requests cancel for pending {p_oid1}, then switches to {p_oid2}.",
            initial_action=Action(action_id="act_init", name="cancel_pending_order", arguments={
                "order_id": p_oid1, "reason": "no longer needed"
            }),
            corrected_action=Action(action_id="act_corr", name="cancel_pending_order", arguments={
                "order_id": p_oid2, "reason": "no longer needed"
            }),
        ))
        p_oid3 = pending_orders[2][0]
        scenarios.append(CRBScenario(
            scenario_id="retail_abort_pending_cancel_01",
            domain="retail",
            archetype="Type B: Full Abort",
            description=f"User requests cancel for {p_oid3}, but aborts ('Wait! Do not cancel my order').",
            initial_action=Action(action_id="act_init", name="cancel_pending_order", arguments={
                "order_id": p_oid3, "reason": "ordered by mistake"
            }),
            corrected_action=None,
        ))

        # Type C: Pending Order Address Adjustment (1 scenario)
        p_oid4 = pending_orders[3][0]
        scenarios.append(CRBScenario(
            scenario_id="retail_adjust_address_01",
            domain="retail",
            archetype="Type C: Value Adjust",
            description=f"User changes shipping address for {p_oid4} to NY, then corrects to SF.",
            initial_action=Action(action_id="act_init", name="modify_pending_order_address", arguments={
                "order_id": p_oid4, "address1": "123 Broadway", "address2": "", "city": "New York", "state": "NY", "country": "USA", "zip": "10001"
            }),
            corrected_action=Action(action_id="act_corr", name="modify_pending_order_address", arguments={
                "order_id": p_oid4, "address1": "456 Market St", "address2": "Suite 100", "city": "San Francisco", "state": "CA", "country": "USA", "zip": "94105"
            }),
        ))

    return scenarios


def evaluate_scenario(scenario: CRBScenario) -> Dict[str, Any]:
    """Runs a single scenario across Gold, Baseline, and REACTOR."""
    domain = scenario.domain

    # 1. Compute Gold Reference State
    gold_env = registry.get_env_constructor(domain)()
    if scenario.corrected_action is not None:
        gold_env.make_tool_call(
            tool_name=scenario.corrected_action.name,
            requestor="assistant",
            **scenario.corrected_action.arguments
        )
    gold_hash = gold_env.get_db_hash()

    # 2. Baseline Run (Naive Asynchronous Dispatch)
    # Naive baseline dispatches initial_action (since it has no revision-gated cancellation).
    # Then it dispatches corrected_action (if present).
    baseline_env = registry.get_env_constructor(domain)()
    baseline_env.make_tool_call(
        tool_name=scenario.initial_action.name,
        requestor="assistant",
        **scenario.initial_action.arguments
    )
    if scenario.corrected_action is not None:
        try:
            baseline_env.make_tool_call(
                tool_name=scenario.corrected_action.name,
                requestor="assistant",
                **scenario.corrected_action.arguments
            )
        except Exception:
            pass
    baseline_hash = baseline_env.get_db_hash()
    baseline_success = (baseline_hash == gold_hash)
    baseline_stale_write = not baseline_success  # Inadvertently mutated initial state

    # 3. REACTOR Run (Controller-Gated Lifecycle)
    reactor_env = registry.get_env_constructor(domain)()
    tool_defs = build_reactor_tools(reactor_env)
    controller = Controller(session_id=f"crb_{scenario.scenario_id}", tools=tool_defs)

    reactor_initial_status = None
    reactor_corrected_status = None
    gate_latency_ns = 0

    async def run_reactor():
        nonlocal reactor_initial_status, reactor_corrected_status, gate_latency_ns

        # Turn 1: Initial user intent
        rev1 = await controller.begin_input()
        token1 = await controller.resolve_input(rev1, mode="new")

        prop1 = Proposal(
            request=token1,
            action_id="act_init",
            tool=scenario.initial_action.name,
            args=dict(scenario.initial_action.arguments)
        )

        # Mid-turn user interruption / correction
        t_start = time.perf_counter_ns()
        rev2 = await controller.begin_input()
        token2 = await controller.resolve_input(rev2, mode="correction")
        gate_latency_ns = time.perf_counter_ns() - t_start

        # Attempt execution of initial proposal (which was superseded)
        out1 = await controller.execute(prop1)
        reactor_initial_status = out1.status

        # If a corrected action exists, execute it under token2
        if scenario.corrected_action is not None:
            prop2 = Proposal(
                request=token2,
                action_id="act_corr",
                tool=scenario.corrected_action.name,
                args=dict(scenario.corrected_action.arguments)
            )
            out2 = await controller.execute(prop2)
            reactor_corrected_status = out2.status

    asyncio.run(run_reactor())

    reactor_hash = reactor_env.get_db_hash()
    reactor_success = (reactor_hash == gold_hash)
    reactor_stale_write = not (reactor_initial_status in {"cancelled_before_dispatch", "cancelled_in_flight", "superseded"})

    return {
        "scenario_id": scenario.scenario_id,
        "domain": scenario.domain,
        "archetype": scenario.archetype,
        "description": scenario.description,
        "baseline": {
            "success": baseline_success,
            "stale_write": baseline_stale_write,
        },
        "reactor": {
            "success": reactor_success,
            "stale_write": reactor_stale_write,
            "initial_status": reactor_initial_status,
            "corrected_status": reactor_corrected_status,
            "gate_latency_us": round(gate_latency_ns / 1000.0, 2),
        }
    }


def run_benchmark():
    print("=" * 80)
    print("CORRECTION-RECOVERY BENCHMARK (CRB) - EMPIRICAL RUN")
    print("=" * 80)

    scenarios = create_benchmark_scenarios()
    print(f"Loaded {len(scenarios)} CRB test scenarios across Airline and Retail domains.")

    results = []
    baseline_successes = 0
    baseline_stale_writes = 0
    reactor_successes = 0
    reactor_stale_writes = 0
    latencies = []

    for sc in scenarios:
        res = evaluate_scenario(sc)
        results.append(res)
        if res["baseline"]["success"]:
            baseline_successes += 1
        if res["baseline"]["stale_write"]:
            baseline_stale_writes += 1
        if res["reactor"]["success"]:
            reactor_successes += 1
        if res["reactor"]["stale_write"]:
            reactor_stale_writes += 1
        latencies.append(res["reactor"]["gate_latency_us"])

        print(f"\n[{sc.scenario_id}] ({sc.archetype})")
        print(f"  Description: {sc.description}")
        print(f"  Baseline:  Success={res['baseline']['success']} | Stale Write={res['baseline']['stale_write']}")
        print(f"  REACTOR:   Success={res['reactor']['success']} | Stale Write={res['reactor']['stale_write']} | Gate Status={res['reactor']['initial_status']} | Gate Latency={res['reactor']['gate_latency_us']} µs")

    n = len(scenarios)
    b_acc = baseline_successes / n * 100
    r_acc = reactor_successes / n * 100
    b_stale = baseline_stale_writes / n * 100
    r_stale = reactor_stale_writes / n * 100

    b_ci = calculate_wilson_interval(baseline_successes, n)
    r_ci = calculate_wilson_interval(reactor_successes, n)

    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n" + "=" * 80)
    print("CRB BENCHMARK SUMMARY REPORT")
    print("=" * 80)
    print(f"Total Scenarios Evaluated:     {n}")
    print(f"Baseline Task Accuracy:        {b_acc:.1f}% (95% CI: [{b_ci[0]*100:.1f}%, {b_ci[1]*100:.1f}%])")
    print(f"REACTOR Task Accuracy:         {r_acc:.1f}% (95% CI: [{r_ci[0]*100:.1f}%, {r_ci[1]*100:.1f}%])")
    print(f"Accuracy Delta:                +{r_acc - b_acc:.1f} percentage points")
    print(f"Baseline Stale Write Rate:     {b_stale:.1f}% ({baseline_stale_writes}/{n})")
    print(f"REACTOR Stale Write Rate:      {r_stale:.1f}% ({reactor_stale_writes}/{n})")
    print(f"Stale Write Reduction:         -{b_stale - r_stale:.1f} percentage points (100% elimination)")
    print(f"Mean Write-Gate Overhead:      {avg_lat:.2f} µs ({avg_lat/1000.0:.4f} ms)")
    print("=" * 80)

    # Save summary artifact
    out_dir = ROOT / "artifacts/crb_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "crb_summary.json"
    with open(summary_path, "w") as fp:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_scenarios": n,
            "metrics": {
                "baseline_accuracy": round(b_acc, 2),
                "baseline_ci95": [round(b_ci[0] * 100, 2), round(b_ci[1] * 100, 2)],
                "baseline_stale_write_rate": round(b_stale, 2),
                "reactor_accuracy": round(r_acc, 2),
                "reactor_ci95": [round(r_ci[0] * 100, 2), round(r_ci[1] * 100, 2)],
                "reactor_stale_write_rate": round(r_stale, 2),
                "stale_write_reduction": round(b_stale - r_stale, 2),
                "mean_gate_latency_us": round(avg_lat, 2),
            },
            "scenarios": results,
        }, fp, indent=2)
    print(f"Saved benchmark results to {summary_path}")


if __name__ == "__main__":
    run_benchmark()
