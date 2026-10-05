"""Independent Synthetic Validation Test Suite for REACTOR v4 Guardrails.

Validates:
1. Multi-Signal Entity Resolver (17 tests)
2. Environment-Grounded Policy Engine (20 tests)
3. Slot Provenance & Monotonic Revision Manager (16 tests)
4. Actor Boundary & Recovery Bounds (18 tests)
5. End-to-End Guarded Pipeline Integration (21 tests)

Total: 92 tests. Uses strictly synthetic schemas, data, and tools.
"""

import asyncio
import pytest
from typing import Any, Dict

from reactor.controller import Controller
from reactor.guards.boundary import ActorBoundaryGate
from reactor.guards.entity import EntityResolver
from reactor.guards.normalizer import ProposalNormalizer
from reactor.guards.pipeline import GuardedExecutionPipeline
from reactor.guards.policy import PolicyEngine
from reactor.guards.provenance import SlotProvenanceManager, SlotRecord
from reactor.guards.recovery import RecoveryManager
from reactor.guards.types import ToolSpec
from reactor.guards.verifier import ResultVerifier
from reactor.state import Proposal
from reactor.tools.base import ToolDefinition


# =====================================================================
# Fixtures for Synthetic Data
# =====================================================================

@pytest.fixture
def synthetic_customer_pool():
    return [
        {
            "id": "cust_101",
            "name": {"first_name": "Eleanor", "last_name": "Vance"},
            "address": {"zip": "01234", "city": "Hill House"},
            "email": "eleanor.vance@synthetic.org",
            "phone": "+1-555-0111",
        },
        {
            "id": "cust_102",
            "name": {"first_name": "Luke", "last_name": "Sanderson"},
            "address": {"zip": "01234", "city": "Hill House"},
            "email": "luke.s@synthetic.org",
            "phone": "+1-555-0122",
        },
        {
            "id": "cust_103",
            "name": {"first_name": "Theodora", "last_name": "Crain"},
            "address": {"zip": "90210", "city": "Beverly Hills"},
            "email": "theo.crain@synthetic.org",
            "phone": "+1-555-0133",
        },
        {
            "id": "cust_104",
            "name": {"first_name": "Theodora", "last_name": "Crain"},
            "address": {"zip": "10001", "city": "New York"},
            "email": "theodora.ny@synthetic.org",
            "phone": "+1-555-0144",
        },
        {
            "id": "cust_105",
            "name": {"first_name": "Arthur", "last_name": "Pendelton"},
            "address": {"zip": "75001", "city": "Dallas"},
            "email": "artie.p@synthetic.org",
            "phone": "+1-555-0155",
        },
    ]


@pytest.fixture
def synthetic_tool_specs():
    return {
        "get_order_details": ToolSpec(
            name="get_order_details",
            owner="agent",
            domains={"retail"},
            state_modifying=False,
            schema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        ),
        "cancel_pending_order": ToolSpec(
            name="cancel_pending_order",
            owner="agent",
            domains={"retail"},
            state_modifying=True,
            schema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["order_id"],
            },
        ),
        "return_delivered_order_items": ToolSpec(
            name="return_delivered_order_items",
            owner="agent",
            domains={"retail"},
            state_modifying=True,
            schema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}, "item_id": {"type": "string"}},
                "required": ["order_id", "item_id"],
            },
        ),
        "toggle_airplane_mode": ToolSpec(
            name="toggle_airplane_mode",
            owner="user",
            domains={"device"},
            state_modifying=True,
            schema={"type": "object", "properties": {}},
        ),
        "cancel_reservation": ToolSpec(
            name="cancel_reservation",
            owner="agent",
            domains={"airline"},
            state_modifying=True,
            schema={
                "type": "object",
                "properties": {"reservation_id": {"type": "string"}},
                "required": ["reservation_id"],
            },
        ),
        "suspend_line": ToolSpec(
            name="suspend_line",
            owner="agent",
            domains={"telecom"},
            state_modifying=True,
            schema={
                "type": "object",
                "properties": {"phone_number": {"type": "string"}, "pin": {"type": "string"}},
                "required": ["phone_number"],
            },
        ),
    }


# =====================================================================
# 1. Multi-Signal Entity Resolution Tests (17 tests)
# =====================================================================

class TestV4EntityResolver:
    def test_exact_id_lookup(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"id": "cust_101"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_101"

    def test_exact_user_id_lookup(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"user_id": "cust_102"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_102"

    def test_exact_customer_id_lookup(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"customer_id": "cust_103"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_103"

    def test_exact_reservation_id_alias(self, synthetic_customer_pool):
        resolver = EntityResolver()
        pool = [{"reservation_id": "RES-8899", "name": "Test User"}]
        res = resolver.resolve({"reservation_id": "RES-8899"}, pool, id_field="reservation_id")
        assert res.status == "RESOLVED"
        assert res.entity["reservation_id"] == "RES-8899"

    def test_exact_email_lookup(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"email": "eleanor.vance@synthetic.org"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_101"

    def test_exact_phone_10digit(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"phone": "555-0122"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_102"

    def test_exact_phone_suffix(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"phone": "0133"}, synthetic_customer_pool)
        # 4 digits is below 7 digits minimum safety cutoff
        assert res.status != "RESOLVED"

    def test_exact_name_unique(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"name": "Eleanor Vance"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_101"

    def test_exact_first_last_keys(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"first_name": "Luke", "last_name": "Sanderson"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_102"

    def test_exact_name_disambiguated_by_zip(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"name": "Theodora Crain", "zip": "90210"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_103"

    def test_duplicate_name_ambiguous_without_zip(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"name": "Theodora Crain"}, synthetic_customer_pool)
        assert res.status == "AMBIGUOUS"

    def test_exact_name_conflicting_zip_low_confidence(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({"name": "Eleanor Vance", "zip": "99999"}, synthetic_customer_pool)
        assert res.status in {"LOW_CONFIDENCE", "NOT_FOUND"}

    def test_fuzzy_name_above_cutoff_resolves(self, synthetic_customer_pool):
        resolver = EntityResolver(confidence_cutoff=0.88)
        # Eleanor Vanc is 12/13 match -> ratio 0.96
        res = resolver.resolve({"name": "Eleanor Vanc"}, synthetic_customer_pool)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "cust_101"

    def test_fuzzy_name_below_cutoff_low_confidence(self, synthetic_customer_pool):
        resolver = EntityResolver(confidence_cutoff=0.88)
        res = resolver.resolve({"name": "Eleanor Rogers"}, synthetic_customer_pool)
        assert res.status in {"LOW_CONFIDENCE", "NOT_FOUND"}

    def test_fuzzy_collision_within_margin_ambiguous(self):
        resolver = EntityResolver(confidence_cutoff=0.80, margin_cutoff=0.10)
        pool = [
            {"id": "1", "name": "Marianne Davis", "zip": "10001"},
            {"id": "2", "name": "Maryanne Davis", "zip": "10002"},
        ]
        res = resolver.resolve({"name": "Maryann Davis"}, pool)
        assert res.status == "AMBIGUOUS"

    def test_empty_pool_returns_not_found(self):
        resolver = EntityResolver()
        res = resolver.resolve({"name": "Someone"}, [])
        assert res.status == "NOT_FOUND"

    def test_empty_query_returns_not_found(self, synthetic_customer_pool):
        resolver = EntityResolver()
        res = resolver.resolve({}, synthetic_customer_pool)
        assert res.status == "NOT_FOUND"


# =====================================================================
# 2. Environment-Grounded Policy Engine Tests (20 tests)
# =====================================================================

class TestV4PolicyEngine:
    def test_airline_cancel_standard_cabin_allowed(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"reservation_id": "R123", "cabin": "economy"},
        )
        assert res.status == "ALLOWED"

    def test_airline_cancel_basic_economy_without_insurance_denied(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"reservation_id": "R123", "cabin": "basic_economy", "insurance": False},
        )
        assert res.status == "DENIED"
        assert res.code == "NON_REFUNDABLE_FARE"

    def test_airline_cancel_basic_economy_with_insurance_allowed(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"reservation_id": "R123", "cabin": "basic_economy", "insurance": True},
        )
        assert res.status == "ALLOWED"

    def test_airline_cancel_reads_cabin_from_environment_tool(self):
        policy = PolicyEngine()
        tools = {"get_reservation_details": lambda reservation_id: {"cabin": "basic_economy", "insurance": False}}
        res = policy.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"reservation_id": "R123"},
            context={"tools": tools},
        )
        assert res.status == "DENIED"
        assert res.code == "NON_REFUNDABLE_FARE"

    def test_airline_cancel_reads_insurance_from_environment_tool(self):
        policy = PolicyEngine()
        tools = {"get_reservation_details": lambda reservation_id: {"cabin": "basic_economy", "insurance": True}}
        res = policy.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"reservation_id": "R123"},
            context={"tools": tools},
        )
        assert res.status == "ALLOWED"

    def test_airline_update_flights_empty_flights_denied(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="airline",
            tool_name="update_reservation_flights",
            args={"reservation_id": "R123", "flights": []},
        )
        assert res.status == "MISSING_INFORMATION"

    def test_airline_update_flights_valid_flights_allowed(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="airline",
            tool_name="update_reservation_flights",
            args={"reservation_id": "R123", "flights": [{"flight_id": "FL100"}]},
        )
        assert res.status == "ALLOWED"

    def test_retail_cancel_order_status_pending_allowed(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "pending"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="cancel_pending_order",
            args={"order_id": "ORD-1"},
            context={"tools": tools},
        )
        assert res.status == "ALLOWED"

    def test_retail_cancel_order_status_delivered_denied(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="cancel_pending_order",
            args={"order_id": "ORD-1"},
            context={"tools": tools},
        )
        assert res.status == "DENIED"
        assert res.code == "INVALID_ORDER_STATUS"

    def test_retail_cancel_reads_status_from_tool_dict(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "shipped"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="cancel_pending_order",
            args={"order_id": "ORD-1"},
            context={"tools": tools},
        )
        assert res.status == "DENIED"

    def test_retail_cancel_reads_status_from_tool_object(self):
        class OrderObj:
            status = "in_transit"
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: OrderObj()}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="cancel_pending_order",
            args={"order_id": "ORD-1"},
            context={"tools": tools},
        )
        assert res.status == "DENIED"

    def test_retail_return_delivered_order_allowed(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools, "days_since_delivery": 10},
        )
        assert res.status == "ALLOWED"

    def test_retail_return_pending_order_denied(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "pending"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools},
        )
        assert res.status == "DENIED"
        assert res.code == "INVALID_ORDER_STATUS"

    def test_retail_return_within_30_days_allowed(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools, "days_since_delivery": 25, "membership": "regular"},
        )
        assert res.status == "ALLOWED"

    def test_retail_return_past_30_days_regular_denied(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools, "days_since_delivery": 35, "membership": "regular"},
        )
        assert res.status == "DENIED"
        assert res.code == "RETURN_WINDOW_EXCEEDED"

    def test_retail_return_past_30_days_gold_member_allowed(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools, "days_since_delivery": 45, "membership": "gold"},
        )
        assert res.status == "ALLOWED"

    def test_retail_return_past_60_days_gold_member_denied(self):
        policy = PolicyEngine()
        tools = {"get_order_details": lambda order_id: {"status": "delivered"}}
        res = policy.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "ORD-1", "item_id": "ITEM-1"},
            context={"tools": tools, "days_since_delivery": 65, "membership": "gold"},
        )
        assert res.status == "DENIED"
        assert res.code == "RETURN_WINDOW_EXCEEDED"

    def test_telecom_sensitive_action_unauthenticated_requires_verification(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="telecom",
            tool_name="suspend_line",
            args={"phone_number": "+1-555-0100"},
            context={"customer_verified": False},
        )
        assert res.status == "REQUIRES_VERIFICATION"
        assert res.code == "KYC_VERIFICATION_REQUIRED"

    def test_telecom_sensitive_action_with_pin_allowed(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="telecom",
            tool_name="suspend_line",
            args={"phone_number": "+1-555-0100", "pin": "1234"},
            context={"customer_verified": False},
        )
        assert res.status == "ALLOWED"

    def test_telecom_sensitive_action_already_verified_allowed(self):
        policy = PolicyEngine()
        res = policy.evaluate_action(
            domain="telecom",
            tool_name="suspend_line",
            args={"phone_number": "+1-555-0100"},
            context={"customer_verified": True},
        )
        assert res.status == "ALLOWED"


# =====================================================================
# 3. Slot Provenance & Monotonic Revision Tests (16 tests)
# =====================================================================

class TestV4SlotProvenance:
    def test_provenance_initial_slot_creation(self):
        mgr = SlotProvenanceManager()
        ok = mgr.update_slot("order_id", "ORD-100", revision=1)
        assert ok is True
        slot = mgr.get_slot("order_id")
        assert slot is not None
        assert slot.value == "ORD-100"
        assert slot.revision == 1

    def test_provenance_monotonic_revision_accepts_higher_revision(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("order_id", "ORD-100", revision=1)
        ok = mgr.update_slot("order_id", "ORD-200", revision=2)
        assert ok is True
        assert mgr.get_slot("order_id").value == "ORD-200"

    def test_provenance_monotonic_revision_rejects_lower_revision(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("order_id", "ORD-200", revision=2)
        # Attempt to overwrite with older revision 1
        ok = mgr.update_slot("order_id", "ORD-100", revision=1)
        assert ok is False
        assert mgr.get_slot("order_id").value == "ORD-200"

    def test_provenance_monotonic_revision_same_revision_accepted(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("order_id", "ORD-100", revision=1)
        ok = mgr.update_slot("order_id", "ORD-101", revision=1)
        assert ok is True
        assert mgr.get_slot("order_id").value == "ORD-101"

    def test_provenance_value_change_supersedes_old_record(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("order_id", "ORD-100", revision=1)
        mgr.update_slot("order_id", "ORD-200", revision=2)
        history = mgr.get_history("order_id")
        assert len(history) == 3  # initial, superseded record, new record
        assert history[1].status == "SUPERSEDED"
        assert history[1].value == "ORD-100"

    def test_provenance_history_preserves_audit_trail(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("seat", "12A", revision=1, source="user")
        mgr.update_slot("seat", "14B", revision=2, source="agent")
        history = mgr.get_history("seat")
        assert len(history) >= 2
        assert history[0].source == "user"

    def test_provenance_parent_slot_change_invalidates_child_slot(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("order_id", "ORD-1", revision=1)
        mgr.update_slot("item_id", "ITEM-A", revision=1)
        
        # Changing order_id should invalidate dependent item_id
        mgr.update_slot("order_id", "ORD-2", revision=2)
        assert mgr.get_slot("item_id") is None
        history = mgr.get_history("item_id")
        assert any(r.status == "INVALIDATED" for r in history)

    def test_provenance_custom_dependency_registration(self):
        mgr = SlotProvenanceManager()
        mgr.register_dependency("car_id", "insurance_tier")
        mgr.update_slot("car_id", "CAR-1", revision=1)
        mgr.update_slot("insurance_tier", "full", revision=1)
        mgr.update_slot("car_id", "CAR-2", revision=2)
        assert mgr.get_slot("insurance_tier") is None

    def test_provenance_cascading_invalidation_multilevel(self):
        mgr = SlotProvenanceManager()
        mgr.register_dependency("user_id", "order_id")
        # order_id -> item_id is in DEFAULT_DEPENDENCIES
        mgr.update_slot("user_id", "U1", revision=1)
        mgr.update_slot("order_id", "ORD-1", revision=1)
        mgr.update_slot("item_id", "ITEM-1", revision=1)
        
        mgr.update_slot("user_id", "U2", revision=2)
        assert mgr.get_slot("order_id") is None
        assert mgr.get_slot("item_id") is None

    def test_provenance_explicit_invalidation(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("phone_number", "+1-555-0100", revision=1)
        mgr.invalidate_slot("phone_number", revision=2, reason="user_cancelled")
        assert mgr.get_slot("phone_number") is None

    def test_provenance_confirm_unconfirmed_slot(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("address", "123 Main St", revision=1, status="UNCONFIRMED")
        rec = mgr.get_slot("address")
        assert rec.status == "UNCONFIRMED"
        ok = mgr.confirm_slot("address")
        assert ok is True
        assert mgr.get_slot("address").status == "CONFIRMED"

    def test_provenance_get_active_slots_excludes_superseded(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("k1", "v1", revision=1)
        mgr.update_slot("k1", "v2", revision=2)
        active = mgr.get_active_slots()
        assert active["k1"] == "v2"

    def test_provenance_get_active_slots_excludes_invalidated(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("k1", "v1", revision=1)
        mgr.invalidate_slot("k1", revision=2)
        active = mgr.get_active_slots()
        assert "k1" not in active

    def test_provenance_history_filtering_by_slot_name(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("alpha", "1", revision=1)
        mgr.update_slot("beta", "2", revision=1)
        assert len(mgr.get_history("alpha")) == 1
        assert len(mgr.get_history("beta")) == 1
        assert len(mgr.get_history()) == 2

    def test_provenance_unconfirmed_slot_is_accessible_in_active(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("tentative_date", "2026-11-01", revision=1, status="UNCONFIRMED")
        assert "tentative_date" in mgr.get_active_slots()

    def test_provenance_invalidated_slot_returns_none_from_get_slot(self):
        mgr = SlotProvenanceManager()
        mgr.update_slot("token", "xyz", revision=1)
        mgr.invalidate_slot("token", revision=2)
        assert mgr.get_slot("token") is None


# =====================================================================
# 4. Actor Boundary & Recovery Bounds Tests (18 tests)
# =====================================================================

class TestV4RecoveryAndBounds:
    def test_recovery_fresh_action_zero_attempts(self):
        rec = RecoveryManager()
        assert rec.get_attempt_count("act_1") == 0

    def test_recovery_record_failure_increments_count(self):
        rec = RecoveryManager()
        c = rec.record_failure("act_1")
        assert c == 1
        assert rec.get_attempt_count("act_1") == 1

    def test_recovery_exhausted_when_limit_reached(self):
        rec = RecoveryManager(max_attempts=2)
        rec.record_failure("act_1")
        assert not rec.is_exhausted("act_1")
        rec.record_failure("act_1")
        assert rec.is_exhausted("act_1")

    def test_recovery_reset_clears_counter(self):
        rec = RecoveryManager()
        rec.record_failure("act_1")
        rec.reset("act_1")
        assert rec.get_attempt_count("act_1") == 0

    def test_boundary_agent_tool_allowed(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail")
        adm = gate.check_admission("get_order_details")
        assert adm.allowed is True

    def test_boundary_user_device_tool_denied(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail")
        adm = gate.check_admission("toggle_airplane_mode")
        assert adm.allowed is False
        assert adm.code == "ACTOR_BOUNDARY_VIOLATION"

    def test_boundary_cross_domain_tool_denied(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail")
        adm = gate.check_admission("cancel_reservation")
        assert adm.allowed is False
        assert adm.code == "DOMAIN_MISMATCH"

    def test_boundary_system_internal_tool_denied(self, synthetic_tool_specs):
        specs = dict(synthetic_tool_specs)
        specs["sys_reset"] = ToolSpec(name="sys_reset", owner="system", domains={"retail"})
        gate = ActorBoundaryGate(specs, active_role="agent", active_domain="retail")
        adm = gate.check_admission("sys_reset")
        assert adm.allowed is False

    def test_boundary_device_tool_clarification_suggested(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail")
        adm = gate.check_admission("toggle_airplane_mode")
        assert "instruct user" in adm.suggested_clarification.lower()

    def test_boundary_unknown_tool_with_recovery_allowed_retry(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail", max_recovery_budget=2)
        adm = gate.check_admission("nonexistent_tool", recovery_attempts=0)
        assert adm.allowed is False
        assert adm.code == "TOOL_NOT_FOUND"

    def test_boundary_unknown_tool_exhausted_denied(self, synthetic_tool_specs):
        gate = ActorBoundaryGate(synthetic_tool_specs, active_role="agent", active_domain="retail", max_recovery_budget=1)
        adm = gate.check_admission("nonexistent_tool", recovery_attempts=2)
        assert adm.allowed is False
        assert adm.repairable is False

    def test_normalizer_valid_args_allowed(self):
        norm = ProposalNormalizer()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        args, adm = norm.normalize_args({"name": "Alice"}, schema)
        assert adm.allowed is True
        assert args["name"] == "Alice"

    def test_normalizer_sanitizes_nested_quotes(self):
        norm = ProposalNormalizer()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        args, adm = norm.normalize_args({' "name" ': ' "Alice" '}, schema)
        assert adm.allowed is True
        assert args["name"] == "Alice"

    def test_normalizer_missing_required_repairable(self):
        norm = ProposalNormalizer()
        schema = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
        args, adm = norm.normalize_args({}, schema)
        assert adm.allowed is False
        assert adm.code == "MISSING_REQUIRED_ARGUMENTS"
        assert adm.repairable is True

    def test_normalizer_type_coercion_string_to_int(self):
        norm = ProposalNormalizer()
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        args, adm = norm.normalize_args({"count": "42"}, schema)
        assert adm.allowed is True
        assert args["count"] == 42

    def test_normalizer_type_coercion_boolean(self):
        norm = ProposalNormalizer()
        schema = {"type": "object", "properties": {"active": {"type": "boolean"}}}
        args, adm = norm.normalize_args({"active": "true"}, schema)
        assert adm.allowed is True
        assert args["active"] is True

    def test_verifier_valid_tool_result_satisfied(self):
        verifier = ResultVerifier()
        res = verifier.verify("any_tool", {"status": "success", "id": "123"})
        assert res.status == "SATISFIED"

    def test_verifier_error_result_flagged(self):
        verifier = ResultVerifier()
        res = verifier.verify("any_tool", {"error": "Connection timed out"})
        assert res.status == "FAILED"


# =====================================================================
# 5. End-to-End Pipeline Integration Tests (21 tests)
# =====================================================================

class TestV4PipelineIntegration:
    @pytest.fixture
    def setup_pipeline_and_controller(self, synthetic_tool_specs, synthetic_customer_pool):
        # Create controller with synthetic tools
        async def cancel_order_handler(**kwargs):
            return {"cancelled": True, "order_id": kwargs.get("order_id")}

        async def get_order_handler(**kwargs):
            return {"order_id": kwargs.get("order_id"), "status": "pending"}

        tools = [
            ToolDefinition(
                name="cancel_pending_order",
                state_modifying=True,
                schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["order_id"],
                },
                handler=cancel_order_handler,
            ),
            ToolDefinition(
                name="get_order_details",
                state_modifying=False,
                schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                handler=get_order_handler,
            ),
        ]
        controller = Controller(session_id="test_session_v4", tools=tools)
        pipeline = GuardedExecutionPipeline(
            tool_specs=synthetic_tool_specs,
            domain="retail",
            entity_pool=synthetic_customer_pool,
            tool_functions={"get_order_details": lambda order_id: {"status": "pending"}},
        )
        return pipeline, controller

    @pytest.mark.asyncio
    async def test_pipeline_executes_valid_proposal_successfully(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-123", "reason": "changed mind"},
            action_id="act_1",
        )
        assert adm.allowed is True
        assert outcome is not None
        assert outcome.status == "succeeded"
        assert outcome.result["cancelled"] is True

    @pytest.mark.asyncio
    async def test_pipeline_blocks_user_device_tool_before_controller(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="toggle_airplane_mode",
            raw_args={},
            action_id="act_device",
        )
        assert adm.allowed is False
        assert adm.code == "ACTOR_BOUNDARY_VIOLATION"
        assert outcome is None

    @pytest.mark.asyncio
    async def test_pipeline_recovers_missing_slot_from_provenance(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # Prepopulate active slot in provenance
        pipeline.provenance_manager.update_slot("order_id", "ORD-555", revision=1)
        
        # Missing order_id in raw_args will be recovered from provenance
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"reason": "too late"},
            action_id="act_recover_slot",
        )
        assert adm.allowed is True
        assert outcome.status == "succeeded"
        assert outcome.result["order_id"] == "ORD-555"

    @pytest.mark.asyncio
    async def test_pipeline_stores_user_args_in_provenance(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-999"},
            action_id="act_store",
            revision=2,
        )
        slot = pipeline.provenance_manager.get_slot("order_id")
        assert slot is not None
        assert slot.value == "ORD-999"
        assert slot.revision == 2

    @pytest.mark.asyncio
    async def test_pipeline_captures_tool_result_into_provenance(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-888"},
            action_id="act_tool_res",
        )
        # outcome result contained cancelled: True
        slot = pipeline.provenance_manager.get_slot("cancelled")
        assert slot is not None
        assert slot.value is True
        assert slot.source == "tool_result"

    @pytest.mark.asyncio
    async def test_pipeline_disambiguates_entity_with_zip(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # In customer pool: Theodora Crain in 90210 has id cust_103
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1", "name": "Theodora Crain", "zip": "90210"},
            action_id="act_ent_zip",
        )
        # Should resolve cleanly without AMBIGUOUS block
        assert adm.allowed is True

    @pytest.mark.asyncio
    async def test_pipeline_halts_on_ambiguous_entity(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # In customer pool: two Theodora Crains without zip is ambiguous
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1", "name": "Theodora Crain"},
            action_id="act_ambig",
        )
        assert adm.allowed is False
        assert adm.code == "AMBIGUOUS_ENTITY"

    @pytest.mark.asyncio
    async def test_pipeline_applies_policy_check_before_execution(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # Set tool function that returns delivered status
        pipeline.tool_functions["get_order_details"] = lambda order_id: {"status": "delivered"}
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-DELIVERED"},
            action_id="act_pol_check",
        )
        assert adm.allowed is False
        assert adm.code == "INVALID_ORDER_STATUS"

    @pytest.mark.asyncio
    async def test_pipeline_blocks_policy_violating_action(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="return_delivered_order_items",
            raw_args={"order_id": "ORD-1", "item_id": "ITM-1"},
            action_id="act_ret_check",
            policy_context={
                "days_since_delivery": 90,
                "tools": {"get_order_details": lambda order_id: {"status": "delivered"}},
            },
        )
        assert adm.allowed is False
        assert adm.code == "RETURN_WINDOW_EXCEEDED"

    @pytest.mark.asyncio
    async def test_pipeline_verifies_post_tool_execution(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="act_ver",
        )
        assert ver is not None
        assert ver.status == "SATISFIED"

    @pytest.mark.asyncio
    async def test_pipeline_multi_turn_order_slot_persistence(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # Turn 1: user talks about ORD-777
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="get_order_details",
            raw_args={"order_id": "ORD-777"},
            action_id="t1",
            revision=1,
        )
        assert pipeline.provenance_manager.get_slot("order_id").value == "ORD-777"
        
        # Turn 2: user says "cancel it", tool missing order_id
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"reason": "late"},
            action_id="t2",
            revision=2,
        )
        assert adm.allowed is True
        assert outcome.result["order_id"] == "ORD-777"

    @pytest.mark.asyncio
    async def test_pipeline_multi_turn_order_id_switch_invalidates_item(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        pipeline.provenance_manager.update_slot("order_id", "ORD-1", revision=1)
        pipeline.provenance_manager.update_slot("item_id", "ITEM-1", revision=1)
        
        # New order_id in turn 2
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="get_order_details",
            raw_args={"order_id": "ORD-2"},
            action_id="t2_switch",
            revision=2,
        )
        assert pipeline.provenance_manager.get_slot("item_id") is None

    @pytest.mark.asyncio
    async def test_pipeline_controller_token_generation_automatic(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        assert controller._state.request_id == 0
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="act_auto_token",
        )
        assert outcome.status == "succeeded"

    @pytest.mark.asyncio
    async def test_pipeline_idempotency_same_action_id(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm1, out1, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="idemp_1",
        )
        # Execute again with same action_id
        adm2, out2, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="idemp_1",
        )
        assert out1.status == "succeeded"
        assert out2.status == "succeeded"
        assert out1.result == out2.result

    @pytest.mark.asyncio
    async def test_pipeline_revision_ordering_in_session(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        pipeline.provenance_manager.update_slot("status", "in_review", revision=5)
        # Attempt to set older revision
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1", "status": "draft"},
            action_id="act_rev_order",
            revision=2,
        )
        # Stale revision should be rejected by provenance manager
        assert pipeline.provenance_manager.get_slot("status").value == "in_review"

    @pytest.mark.asyncio
    async def test_pipeline_handles_read_only_tool_without_side_effects(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, ver = await pipeline.execute_proposal(
            controller=controller,
            tool_name="get_order_details",
            raw_args={"order_id": "ORD-READONLY"},
            action_id="act_read",
        )
        assert adm.allowed is True
        assert outcome.status == "succeeded"

    @pytest.mark.asyncio
    async def test_pipeline_state_modifying_tool_tracked(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        spec = pipeline.tool_specs["cancel_pending_order"]
        assert spec.state_modifying is True

    @pytest.mark.asyncio
    async def test_pipeline_bounded_retry_escalation(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        # Unknown tool
        adm1, _, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="unknown_action",
            raw_args={},
            action_id="act_escalate",
        )
        pipeline.recovery_manager.record_failure("act_escalate")
        adm2, _, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="unknown_action",
            raw_args={},
            action_id="act_escalate",
        )
        pipeline.recovery_manager.record_failure("act_escalate")
        adm3, _, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="unknown_action",
            raw_args={},
            action_id="act_escalate",
        )
        assert adm3.allowed is False
        assert adm3.repairable is False

    @pytest.mark.asyncio
    async def test_pipeline_policy_context_inspection(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        adm, outcome, _ = await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="act_ctx",
            policy_context={"tools": {"get_order_details": lambda order_id: {"status": "pending"}}},
        )
        assert adm.allowed is True

    @pytest.mark.asyncio
    async def test_pipeline_zero_stale_writes_guarantee(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="act_stale_check",
        )
        # Verify controller preserves zero stale writes invariant
        stale_writes = sum(
            1 for op in controller._operations.values()
            if op.state_modifying and op.status == "succeeded" and not controller._state.is_current(op.proposal.request)
        )
        assert stale_writes == 0

    @pytest.mark.asyncio
    async def test_pipeline_zero_duplicate_execution_guarantee(self, setup_pipeline_and_controller):
        pipeline, controller = setup_pipeline_and_controller
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="dup_test",
        )
        await pipeline.execute_proposal(
            controller=controller,
            tool_name="cancel_pending_order",
            raw_args={"order_id": "ORD-1"},
            action_id="dup_test",
        )
        # Duplicate action_id was deduplicated by controller
        assert len(controller._identities) == 1
        assert len(controller._operations) == 1
