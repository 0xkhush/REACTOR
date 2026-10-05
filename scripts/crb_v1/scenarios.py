"""CRB-v1 Suite: 40 Diverse Asynchronous Concurrency Scenarios.

Stratified across 4 classes:
- Class A: Pre-Dispatch (10 scenarios)
- Class B: In-Flight (10 scenarios)
- Class C: Partial Mutation (10 scenarios)
- Class D: Rapid Multi-Correction & Concurrency Isolation (10 scenarios)
"""

from typing import Any, Dict, List, Tuple
from scripts.crb_v1.mock_tools import InstrumentedAsyncTool


def build_scenario_suite() -> Tuple[List[Dict[str, Any]], Dict[str, InstrumentedAsyncTool]]:
    tools: Dict[str, InstrumentedAsyncTool] = {}
    scenarios: List[Dict[str, Any]] = []

    # Helper to register tools
    def reg_tool(name: str, duration_ms: float = 150.0, mode: str = "atomic", stages: list = None, state_modifying: bool = True):
        tools[name] = InstrumentedAsyncTool(
            name=name,
            state_modifying=state_modifying,
            duration_ms=duration_ms,
            mode=mode,
            stages=stages or [],
        )

    # -------------------------------------------------------------------------
    # Register Core Tools
    # -------------------------------------------------------------------------
    reg_tool("cancel_reservation", 150.0)
    reg_tool("update_reservation_baggages", 150.0)
    reg_tool("select_seat", 150.0)
    reg_tool("update_passenger_details", 150.0)
    reg_tool("rebook_flight", 150.0)
    reg_tool("process_refund", 150.0)
    reg_tool("change_destination", 150.0)
    reg_tool("get_flight_status", 150.0, mode="read", state_modifying=False)

    reg_tool("return_delivered_order_items", 150.0)
    reg_tool("cancel_pending_order", 150.0)
    reg_tool("modify_shipping_address", 150.0)
    reg_tool("modify_item_quantity", 150.0)
    reg_tool("upgrade_shipping_method", 150.0)
    reg_tool("exchange_order_items", 150.0)
    reg_tool("get_order_history", 150.0, mode="read", state_modifying=False)

    # Staged Tools for Partial Mutation
    reg_tool("rebook_flight_staged", 150.0, mode="partial", stages=[
        {"offset_ms": 40.0, "mutation": "cancel_old_seat", "payload": {"stage": 1}, "apply": lambda s: s.update({"rebook_stage_1": "cancelled_old"})},
        {"offset_ms": 80.0, "mutation": "charge_fare_difference", "payload": {"stage": 2}, "apply": lambda s: s.update({"rebook_stage_2": "charged_fare"})},
        {"offset_ms": 120.0, "mutation": "confirm_new_seat", "payload": {"stage": 3}, "apply": lambda s: s.update({"rebook_stage_3": "confirmed_new"})},
    ])
    reg_tool("update_baggage_staged", 150.0, mode="partial", stages=[
        {"offset_ms": 50.0, "mutation": "reserve_hold_space", "payload": {"stage": 1}, "apply": lambda s: s.update({"bag_stage_1": "hold_reserved"})},
        {"offset_ms": 100.0, "mutation": "charge_baggage_fee", "payload": {"stage": 2}, "apply": lambda s: s.update({"bag_stage_2": "fee_charged"})},
    ])
    reg_tool("exchange_items_staged", 150.0, mode="partial", stages=[
        {"offset_ms": 40.0, "mutation": "return_old_item", "payload": {"stage": 1}, "apply": lambda s: s.update({"exch_stage_1": "returned_old"})},
        {"offset_ms": 80.0, "mutation": "refund_item_difference", "payload": {"stage": 2}, "apply": lambda s: s.update({"exch_stage_2": "refunded_diff"})},
        {"offset_ms": 120.0, "mutation": "dispatch_new_item", "payload": {"stage": 3}, "apply": lambda s: s.update({"exch_stage_3": "dispatched_new"})},
    ])
    reg_tool("bundle_return_staged", 150.0, mode="partial", stages=[
        {"offset_ms": 50.0, "mutation": "return_item_a", "payload": {"stage": 1}, "apply": lambda s: s.update({"bundle_stage_1": "returned_a"})},
        {"offset_ms": 100.0, "mutation": "return_item_b", "payload": {"stage": 2}, "apply": lambda s: s.update({"bundle_stage_2": "returned_b"})},
    ])

    # -------------------------------------------------------------------------
    # CLASS A: Pre-Dispatch (10 Scenarios)
    # -------------------------------------------------------------------------
    scenarios.extend([
        {
            "scenario_id": "CRB_PD_01_air_cancel",
            "domain": "airline",
            "timing_class": "pre_dispatch",
            "template": "entity_swap",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_4WQ150", "value": "cancelled"}},
            "corrected_action": {"name": "cancel_reservation", "arguments": {"id": "RES_VAAOXJ", "value": "cancelled"}},
            "gold_final_state": {"RES_VAAOXJ": "cancelled"},
        },
        {
            "scenario_id": "CRB_PD_02_air_baggage",
            "domain": "airline",
            "timing_class": "pre_dispatch",
            "template": "parameter_adjust",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "update_reservation_baggages", "arguments": {"id": "RES_BAG_01", "value": "2_bags"}},
            "corrected_action": {"name": "update_reservation_baggages", "arguments": {"id": "RES_BAG_01", "value": "1_bag"}},
            "gold_final_state": {"RES_BAG_01": "1_bag"},
        },
        {
            "scenario_id": "CRB_PD_03_air_seat",
            "domain": "airline",
            "timing_class": "pre_dispatch",
            "template": "parameter_adjust",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "select_seat", "arguments": {"id": "SEAT_ASSIGN", "value": "12A"}},
            "corrected_action": {"name": "select_seat", "arguments": {"id": "SEAT_ASSIGN", "value": "14C"}},
            "gold_final_state": {"SEAT_ASSIGN": "14C"},
        },
        {
            "scenario_id": "CRB_PD_04_air_dob",
            "domain": "airline",
            "timing_class": "pre_dispatch",
            "template": "parameter_adjust",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "update_passenger_details", "arguments": {"id": "PAX_DOB", "value": "1980-01-01"}},
            "corrected_action": {"name": "update_passenger_details", "arguments": {"id": "PAX_DOB", "value": "1985-05-12"}},
            "gold_final_state": {"PAX_DOB": "1985-05-12"},
        },
        {
            "scenario_id": "CRB_PD_05_air_abort",
            "domain": "airline",
            "timing_class": "pre_dispatch",
            "template": "full_abort",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_PGAGLM", "value": "cancelled"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PD_06_ret_return",
            "domain": "retail",
            "timing_class": "pre_dispatch",
            "template": "entity_swap",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_W4817420", "value": "returned"}},
            "corrected_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_W6304490", "value": "returned"}},
            "gold_final_state": {"ORD_W6304490": "returned"},
        },
        {
            "scenario_id": "CRB_PD_07_ret_cancel_order",
            "domain": "retail",
            "timing_class": "pre_dispatch",
            "template": "entity_swap",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_W5918442", "reason": "no longer needed"}},
            "corrected_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_W2974929", "reason": "no longer needed"}},
            "gold_final_state": {"ORD_W2974929": "no longer needed"},
        },
        {
            "scenario_id": "CRB_PD_08_ret_address",
            "domain": "retail",
            "timing_class": "pre_dispatch",
            "template": "parameter_adjust",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "modify_shipping_address", "arguments": {"id": "SHIP_ADDR", "value": "123 Broadway"}},
            "corrected_action": {"name": "modify_shipping_address", "arguments": {"id": "SHIP_ADDR", "value": "456 Market St"}},
            "gold_final_state": {"SHIP_ADDR": "456 Market St"},
        },
        {
            "scenario_id": "CRB_PD_09_ret_qty",
            "domain": "retail",
            "timing_class": "pre_dispatch",
            "template": "parameter_adjust",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "modify_item_quantity", "arguments": {"id": "ITEM_QTY_01", "value": "5"}},
            "corrected_action": {"name": "modify_item_quantity", "arguments": {"id": "ITEM_QTY_01", "value": "2"}},
            "gold_final_state": {"ITEM_QTY_01": "2"},
        },
        {
            "scenario_id": "CRB_PD_10_ret_abort",
            "domain": "retail",
            "timing_class": "pre_dispatch",
            "template": "full_abort",
            "correction_offset_ms": 20.0,
            "initial_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_W1840144", "value": "returned"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
    ])

    # -------------------------------------------------------------------------
    # CLASS B: In-Flight (10 Scenarios)
    # -------------------------------------------------------------------------
    scenarios.extend([
        {
            "scenario_id": "CRB_IF_01_air_cancel",
            "domain": "airline",
            "timing_class": "in_flight",
            "template": "entity_swap",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_IF_01", "value": "cancelled"}},
            "corrected_action": {"name": "cancel_reservation", "arguments": {"id": "RES_IF_02", "value": "cancelled"}},
            "gold_final_state": {"RES_IF_02": "cancelled"},
        },
        {
            "scenario_id": "CRB_IF_02_air_rebook",
            "domain": "airline",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "rebook_flight", "arguments": {"id": "REBOOK_FLIGHT", "value": "FLIGHT_AM_0800"}},
            "corrected_action": {"name": "rebook_flight", "arguments": {"id": "REBOOK_FLIGHT", "value": "FLIGHT_PM_1800"}},
            "gold_final_state": {"REBOOK_FLIGHT": "FLIGHT_PM_1800"},
        },
        {
            "scenario_id": "CRB_IF_03_air_baggage",
            "domain": "airline",
            "timing_class": "in_flight",
            "template": "full_abort",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "update_reservation_baggages", "arguments": {"id": "RES_BAG_IF", "value": "extra_bag_paid"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_IF_04_air_refund",
            "domain": "airline",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "process_refund", "arguments": {"id": "REFUND_TYPE", "value": "card_refund"}},
            "corrected_action": {"name": "process_refund", "arguments": {"id": "REFUND_TYPE", "value": "travel_voucher"}},
            "gold_final_state": {"REFUND_TYPE": "travel_voucher"},
        },
        {
            "scenario_id": "CRB_IF_05_air_destination",
            "domain": "airline",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "change_destination", "arguments": {"id": "FLIGHT_DEST", "value": "ORD"}},
            "corrected_action": {"name": "change_destination", "arguments": {"id": "FLIGHT_DEST", "value": "LAX"}},
            "gold_final_state": {"FLIGHT_DEST": "LAX"},
        },
        {
            "scenario_id": "CRB_IF_06_ret_return",
            "domain": "retail",
            "timing_class": "in_flight",
            "template": "entity_swap",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_RET_IF_01", "value": "returned"}},
            "corrected_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_RET_IF_02", "value": "returned"}},
            "gold_final_state": {"ORD_RET_IF_02": "returned"},
        },
        {
            "scenario_id": "CRB_IF_07_ret_cancel_order",
            "domain": "retail",
            "timing_class": "in_flight",
            "template": "full_abort",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_CANCEL_IF", "reason": "no longer needed"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_IF_08_ret_shipping",
            "domain": "retail",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "upgrade_shipping_method", "arguments": {"id": "SHIP_METHOD", "value": "overnight"}},
            "corrected_action": {"name": "upgrade_shipping_method", "arguments": {"id": "SHIP_METHOD", "value": "standard"}},
            "gold_final_state": {"SHIP_METHOD": "standard"},
        },
        {
            "scenario_id": "CRB_IF_09_ret_exchange",
            "domain": "retail",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "exchange_order_items", "arguments": {"id": "ITEM_SIZE", "value": "Large"}},
            "corrected_action": {"name": "exchange_order_items", "arguments": {"id": "ITEM_SIZE", "value": "Medium"}},
            "gold_final_state": {"ITEM_SIZE": "Medium"},
        },
        {
            "scenario_id": "CRB_IF_10_ret_address",
            "domain": "retail",
            "timing_class": "in_flight",
            "template": "parameter_adjust",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "modify_shipping_address", "arguments": {"id": "SHIP_ADDR_IF", "value": "101 Pine St"}},
            "corrected_action": {"name": "modify_shipping_address", "arguments": {"id": "SHIP_ADDR_IF", "value": "202 Oak St"}},
            "gold_final_state": {"SHIP_ADDR_IF": "202 Oak St"},
        },
    ])

    # -------------------------------------------------------------------------
    # CLASS C: Partial Mutation (10 Scenarios)
    # -------------------------------------------------------------------------
    # Staged durations: 150ms. Stages commit at 40ms, 80ms, 120ms (or 50ms, 100ms)
    scenarios.extend([
        {
            "scenario_id": "CRB_PM_01_air_rebook_10pct",
            "domain": "airline",
            "timing_class": "partial_mutation",
            "template": "partial_early",
            "expected_stages_count": 3,
            "correction_offset_ms": 15.0,  # 10% - Before Stage 1 (40ms)
            "initial_action": {"name": "rebook_flight_staged", "arguments": {"id": "STAGED_REBOOK"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_02_air_rebook_30pct",
            "domain": "airline",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage1",
            "expected_stages_count": 3,
            "correction_offset_ms": 55.0,  # 36% - After Stage 1 (40ms), before Stage 2 (80ms)
            "initial_action": {"name": "rebook_flight_staged", "arguments": {"id": "STAGED_REBOOK"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_03_air_rebook_60pct",
            "domain": "airline",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage2",
            "expected_stages_count": 3,
            "correction_offset_ms": 95.0,  # 63% - After Stage 2 (80ms), before Stage 3 (120ms)
            "initial_action": {"name": "rebook_flight_staged", "arguments": {"id": "STAGED_REBOOK"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_04_air_baggage_20pct",
            "domain": "airline",
            "timing_class": "partial_mutation",
            "template": "partial_early",
            "expected_stages_count": 2,
            "correction_offset_ms": 25.0,  # Before Stage 1 (50ms)
            "initial_action": {"name": "update_baggage_staged", "arguments": {"id": "STAGED_BAG"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_05_air_baggage_50pct",
            "domain": "airline",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage1",
            "expected_stages_count": 2,
            "correction_offset_ms": 75.0,  # After Stage 1 (50ms), before Stage 2 (100ms)
            "initial_action": {"name": "update_baggage_staged", "arguments": {"id": "STAGED_BAG"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_06_ret_exchange_15pct",
            "domain": "retail",
            "timing_class": "partial_mutation",
            "template": "partial_early",
            "expected_stages_count": 3,
            "correction_offset_ms": 20.0,  # Before Stage 1 (40ms)
            "initial_action": {"name": "exchange_items_staged", "arguments": {"id": "STAGED_EXCH"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_07_ret_exchange_40pct",
            "domain": "retail",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage1",
            "expected_stages_count": 3,
            "correction_offset_ms": 60.0,  # After Stage 1 (40ms), before Stage 2 (80ms)
            "initial_action": {"name": "exchange_items_staged", "arguments": {"id": "STAGED_EXCH"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_08_ret_exchange_70pct",
            "domain": "retail",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage2",
            "expected_stages_count": 3,
            "correction_offset_ms": 105.0,  # After Stage 2 (80ms), before Stage 3 (120ms)
            "initial_action": {"name": "exchange_items_staged", "arguments": {"id": "STAGED_EXCH"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_09_ret_bundle_20pct",
            "domain": "retail",
            "timing_class": "partial_mutation",
            "template": "partial_early",
            "expected_stages_count": 2,
            "correction_offset_ms": 25.0,  # Before Stage 1 (50ms)
            "initial_action": {"name": "bundle_return_staged", "arguments": {"id": "STAGED_BUNDLE"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_PM_10_ret_bundle_50pct",
            "domain": "retail",
            "timing_class": "partial_mutation",
            "template": "partial_mid_stage1",
            "expected_stages_count": 2,
            "correction_offset_ms": 75.0,  # After Stage 1 (50ms), before Stage 2 (100ms)
            "initial_action": {"name": "bundle_return_staged", "arguments": {"id": "STAGED_BUNDLE"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
    ])

    # -------------------------------------------------------------------------
    # CLASS D: Rapid Corrections & Concurrency Isolation (10 Scenarios)
    # -------------------------------------------------------------------------
    scenarios.extend([
        {
            "scenario_id": "CRB_RC_01_air_rapid_10ms",
            "domain": "airline",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 10.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_01", "value": "cancelled"}},
            "corrected_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_02", "value": "cancelled"}},
            "gold_final_state": {"RES_RAPID_02": "cancelled"},
        },
        {
            "scenario_id": "CRB_RC_02_air_rapid_25ms",
            "domain": "airline",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 25.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_03", "value": "cancelled"}},
            "corrected_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_04", "value": "cancelled"}},
            "gold_final_state": {"RES_RAPID_04": "cancelled"},
        },
        {
            "scenario_id": "CRB_RC_03_air_rapid_50ms",
            "domain": "airline",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_05", "value": "cancelled"}},
            "corrected_action": {"name": "cancel_reservation", "arguments": {"id": "RES_RAPID_06", "value": "cancelled"}},
            "gold_final_state": {"RES_RAPID_06": "cancelled"},
        },
        {
            "scenario_id": "CRB_RC_04_air_concurrency_isolate",
            "domain": "airline",
            "timing_class": "concurrency_isolation",
            "template": "independent_concurrent",
            "correction_offset_ms": 50.0,
            # Initial write action is cancelled; independent read action must NOT be falsely cancelled!
            "initial_action": {"name": "cancel_reservation", "arguments": {"id": "RES_ISO_01", "value": "cancelled"}},
            "corrected_action": {"name": "get_flight_status", "arguments": {"flight_num": "HAT170"}},
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_RC_05_air_rapid_destination",
            "domain": "airline",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 30.0,
            "initial_action": {"name": "change_destination", "arguments": {"id": "DEST_RAPID", "value": "DFW"}},
            "corrected_action": {"name": "change_destination", "arguments": {"id": "DEST_RAPID", "value": "LAX"}},
            "gold_final_state": {"DEST_RAPID": "LAX"},
        },
        {
            "scenario_id": "CRB_RC_06_ret_rapid_10ms",
            "domain": "retail",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 10.0,
            "initial_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_RAPID_01", "reason": "no longer needed"}},
            "corrected_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_RAPID_02", "reason": "no longer needed"}},
            "gold_final_state": {"ORD_RAPID_02": "no longer needed"},
        },
        {
            "scenario_id": "CRB_RC_07_ret_rapid_25ms",
            "domain": "retail",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 25.0,
            "initial_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_RAPID_03", "value": "returned"}},
            "corrected_action": {"name": "return_delivered_order_items", "arguments": {"id": "ORD_RAPID_04", "value": "returned"}},
            "gold_final_state": {"ORD_RAPID_04": "returned"},
        },
        {
            "scenario_id": "CRB_RC_08_ret_rapid_50ms",
            "domain": "retail",
            "timing_class": "rapid_correction",
            "template": "rapid_cascade",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "modify_shipping_address", "arguments": {"id": "ADDR_RAPID", "value": "New York, NY"}},
            "corrected_action": {"name": "modify_shipping_address", "arguments": {"id": "ADDR_RAPID", "value": "San Francisco, CA"}},
            "gold_final_state": {"ADDR_RAPID": "San Francisco, CA"},
        },
        {
            "scenario_id": "CRB_RC_09_ret_concurrency_isolate",
            "domain": "retail",
            "timing_class": "concurrency_isolation",
            "template": "independent_concurrent",
            "correction_offset_ms": 50.0,
            "initial_action": {"name": "cancel_pending_order", "arguments": {"id": "ORD_ISO_01", "reason": "ordered by mistake"}},
            "corrected_action": {"name": "get_order_history", "arguments": {"user_id": "user_123"}},
            "gold_final_state": {},
        },
        {
            "scenario_id": "CRB_RC_10_ret_rapid_exchange_abort",
            "domain": "retail",
            "timing_class": "rapid_correction",
            "template": "rapid_abort",
            "correction_offset_ms": 30.0,
            "initial_action": {"name": "exchange_order_items", "arguments": {"id": "ITEM_EXCH_RAPID", "value": "shoes_size_10"}},
            "corrected_action": None,
            "gold_final_state": {},
        },
    ])

    return scenarios, tools
