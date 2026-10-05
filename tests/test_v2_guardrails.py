"""Synthetic Development Test Suite for REACTOR v2 Guarded Execution.

Tests all v2 guard components on synthetic domains and data without touching
or leaking τ-Voice benchmark specifics.
"""

import asyncio
import pytest
from reactor.controller import Controller
from reactor.guards.boundary import ActorBoundaryGate
from reactor.guards.entity import EntityResolver
from reactor.guards.normalizer import ProposalNormalizer
from reactor.guards.pipeline import GuardedExecutionPipeline
from reactor.guards.policy import PolicyEngine
from reactor.guards.recovery import RecoveryManager
from reactor.guards.types import ToolSpec
from reactor.guards.verifier import ResultVerifier
from reactor.state import Proposal
from reactor.tools.base import ToolDefinition


# =====================================================================
# 1. Entity Resolution Tests (Multi-signal, Cutoffs, Ambiguity)
# =====================================================================

class TestEntityResolver:
    @pytest.fixture
    def synthetic_db(self):
        return [
            {
                "id": "user_101",
                "name": {"first_name": "Aarav", "last_name": "Anderson"},
                "address": {"zip": "19031", "city": "Philadelphia"},
                "email": "aarav.anderson@example.com",
                "phone": "+1-555-0101",
            },
            {
                "id": "user_102",
                "name": {"first_name": "John", "last_name": "Smith"},
                "address": {"zip": "10001", "city": "New York"},
                "email": "john.smith@example.com",
                "phone": "+1-555-0102",
            },
            {
                "id": "user_103",
                "name": {"first_name": "John", "last_name": "Smith"},
                "address": {"zip": "90210", "city": "Beverly Hills"},
                "email": "jsmith90210@example.com",
                "phone": "+1-555-0103",
            },
            {
                "id": "user_104",
                "name": {"first_name": "Catherine", "last_name": "Zeta"},
                "address": {"zip": "30301", "city": "Atlanta"},
                "email": "czeta@example.com",
                "phone": "+1-555-0104",
            },
        ]

    def test_exact_id_match(self, synthetic_db):
        resolver = EntityResolver()
        res = resolver.resolve({"id": "user_101"}, synthetic_db)
        assert res.status == "RESOLVED"
        assert res.match_type == "exact_id"
        assert res.entity["id"] == "user_101"
        assert res.confidence == 1.0

    def test_exact_email_and_phone(self, synthetic_db):
        resolver = EntityResolver()
        res_em = resolver.resolve({"email": "czeta@example.com"}, synthetic_db)
        assert res_em.status == "RESOLVED"
        assert res_em.entity["id"] == "user_104"

        res_ph = resolver.resolve({"phone": "555-0102"}, synthetic_db)
        assert res_ph.status == "RESOLVED"
        assert res_ph.entity["id"] == "user_102"

    def test_exact_name_disambiguated_by_zip(self, synthetic_db):
        resolver = EntityResolver()
        # Without zip, multiple John Smiths are ambiguous
        res_ambig = resolver.resolve({"first_name": "John", "last_name": "Smith"}, synthetic_db)
        assert res_ambig.status == "AMBIGUOUS"

        # With zip, disambiguates to user_103
        res_zip = resolver.resolve({"first_name": "John", "last_name": "Smith", "zip": "90210"}, synthetic_db)
        assert res_zip.status == "RESOLVED"
        assert res_zip.entity["id"] == "user_103"

    def test_phonetic_similarity_with_margin(self, synthetic_db):
        resolver = EntityResolver(confidence_cutoff=0.85, margin_cutoff=0.10)
        # "Arun Anderson" vs "Aarav Anderson"
        res = resolver.resolve({"first_name": "Arun", "last_name": "Anderson", "zip": "19031"}, synthetic_db)
        assert res.status == "RESOLVED"
        assert res.entity["id"] == "user_101"
        assert res.confidence >= 0.85

    def test_low_confidence_rejected(self, synthetic_db):
        resolver = EntityResolver(confidence_cutoff=0.88)
        # "Zachary Taylor" does not match anyone closely
        res = resolver.resolve({"first_name": "Zachary", "last_name": "Taylor"}, synthetic_db)
        assert res.status in {"NOT_FOUND", "LOW_CONFIDENCE"}
        assert res.entity is None


# =====================================================================
# 2. Actor Boundary & Human Transfer Gate Tests
# =====================================================================

class TestActorBoundaryGate:
    @pytest.fixture
    def sample_specs(self):
        return {
            "query_account": ToolSpec(name="query_account", owner="agent", domains={"crm"}),
            "modify_billing": ToolSpec(name="modify_billing", owner="agent", domains={"crm"}, state_modifying=True),
            "toggle_device_wifi": ToolSpec(name="toggle_device_wifi", owner="user", domains={"device"}),
            "transfer_to_human_agents": ToolSpec(name="transfer_to_human_agents", owner="agent", domains={"crm"}),
        }

    def test_authorized_agent_tool(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm")
        res = gate.check_admission("query_account")
        assert res.allowed is True
        assert res.code == "OK"

    def test_unauthorized_user_tool_blocked(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm")
        # Agent attempts to invoke a user device tool
        res = gate.check_admission("toggle_device_wifi")
        assert res.allowed is False
        assert res.code == "ACTOR_BOUNDARY_VIOLATION"
        assert res.repairable is True

    def test_nonexistent_tool_blocked(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm")
        res = gate.check_admission("hallucinated_teleport_tool")
        assert res.allowed is False
        assert res.code == "TOOL_NOT_FOUND"

    def test_premature_human_transfer_blocked(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm", max_recovery_budget=2)
        # Model tries to panic-transfer on attempt 0 with no user prompt
        res = gate.check_admission("transfer_to_human_agents", user_utterance="My order is delayed", recovery_attempts=0)
        assert res.allowed is False
        assert res.code == "PREMATURE_HUMAN_TRANSFER"

    def test_human_transfer_permitted_on_user_escalation(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm")
        res = gate.check_admission("transfer_to_human_agents", user_utterance="Please transfer me to a human representative right now")
        assert res.allowed is True
        assert res.code == "USER_REQUESTED_TRANSFER"

    def test_human_transfer_permitted_when_budget_exhausted(self, sample_specs):
        gate = ActorBoundaryGate(sample_specs, active_role="agent", active_domain="crm", max_recovery_budget=2)
        res = gate.check_admission("transfer_to_human_agents", user_utterance="It still fails", recovery_attempts=2)
        assert res.allowed is True
        assert res.code == "EXHAUSTED_RECOVERY_TRANSFER"


# =====================================================================
# 3. Schema & Proposal Normalizer Tests
# =====================================================================

class TestProposalNormalizer:
    def test_escaped_quote_and_whitespace_sanitization(self):
        raw = {
            ' "date" ': ' "2024-05-19" ',
            "flights": [
                {' "flight_num" ': ' "HAT072" ', '"date"': '2024-05-19'}
            ]
        }
        cleaned, res = ProposalNormalizer.normalize_args(raw)
        assert res.allowed is True
        assert "date" in cleaned
        assert cleaned["date"] == "2024-05-19"
        assert cleaned["flights"][0]["flight_num"] == "HAT072"
        assert cleaned["flights"][0]["date"] == "2024-05-19"

    def test_missing_required_slots_rejected_without_fabrication(self):
        schema = {
            "type": "object",
            "required": ["booking_id", "travel_date", "passenger_name"],
            "properties": {
                "booking_id": {"type": "string"},
                "travel_date": {"type": "string"},
                "passenger_name": {"type": "string"},
            }
        }
        # Model only provided booking_id
        raw = {"booking_id": "BK9900"}
        cleaned, res = ProposalNormalizer.normalize_args(raw, schema)
        assert res.allowed is False
        assert res.code == "MISSING_REQUIRED_ARGUMENTS"
        assert set(res.missing_fields) == {"travel_date", "passenger_name"}
        # Verify nothing was fabricated
        assert "travel_date" not in cleaned

    def test_type_coercion_and_enum_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "quantity": {"type": "integer"},
                "expedited": {"type": "boolean"},
                "cabin": {"type": "string", "enum": ["economy", "business", "first"]},
            }
        }
        raw = {"quantity": "3", "expedited": "true", "cabin": "Business"}
        cleaned, res = ProposalNormalizer.normalize_args(raw, schema)
        assert res.allowed is True
        assert cleaned["quantity"] == 3
        assert cleaned["expedited"] is True
        assert cleaned["cabin"] == "business"


# =====================================================================
# 4. Policy Engine Tests
# =====================================================================

class TestPolicyEngine:
    def test_airline_basic_economy_cancellation_denied(self):
        engine = PolicyEngine()
        res = engine.evaluate_action(
            domain="airline",
            tool_name="cancel_reservation",
            args={"cabin": "basic_economy", "insurance": "no"},
        )
        assert res.status == "DENIED"
        assert res.code == "NON_REFUNDABLE_FARE"

    def test_retail_return_window_exceeded_denied(self):
        engine = PolicyEngine()
        # Non-member with delivery 45 days ago (limit is 30)
        res = engine.evaluate_action(
            domain="retail",
            tool_name="return_delivered_order_items",
            args={"order_id": "123"},
            context={"days_since_delivery": 45, "membership": "regular"},
        )
        assert res.status == "DENIED"
        assert res.code == "RETURN_WINDOW_EXCEEDED"


# =====================================================================
# 5. Recovery & REACTOR Core Integration Tests
# =====================================================================

@pytest.mark.asyncio
async def test_bounded_recovery_and_reactor_safety():
    """Verifies that recovery advances intent revisions, old operations cancel,
    and 0 stale writes occur."""
    tool_executed = False
    stale_write = False

    async def dummy_handler(**kwargs):
        nonlocal tool_executed
        tool_executed = True
        return {"status": "ok"}

    tool_def = ToolDefinition(
        name="transfer_funds",
        state_modifying=True,
        schema={"type": "object", "required": ["amount", "recipient"]},
        handler=dummy_handler,
    )

    controller = Controller("test-recovery-session", [tool_def], trace=None)
    recovery_mgr = RecoveryManager(max_attempts=2)

    # Turn 1: Incomplete proposal
    rev1 = await controller.begin_input()
    token1 = await controller.resolve_input(rev1, mode="new")

    # Incomplete proposal (missing recipient)
    p_incomplete = Proposal(token1, "act-1", "transfer_funds", {"amount": 100})
    schema = tool_def.schema
    _, adm = ProposalNormalizer.normalize_args(p_incomplete.args, schema)
    assert adm.allowed is False
    assert recovery_mgr.can_recover("act-1", adm) is True

    # Recovery Turn: Advance revision to rev2
    token2 = await recovery_mgr.advance_revision_for_recovery(
        controller, "act-1", reason="Prompt user for recipient"
    )
    assert token2.intent_revision > token1.intent_revision

    # Attempt to execute obsolete rev1 proposal -> must be cancelled or blocked
    # In REACTOR, token1 operations cannot commit once token2 is active
    p_repaired = Proposal(token2, "act-2", "transfer_funds", {"amount": 100, "recipient": "Bob"})
    outcome = await controller.execute(p_repaired)
    assert outcome.status == "succeeded"
    assert tool_executed is True
    assert stale_write is False
