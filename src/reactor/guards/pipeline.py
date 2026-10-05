"""Unified Guarded Execution Pipeline for REACTOR v4.

Sequences:
1. Actor Boundary Gate
2. Schema / Argument Normalization
3. Slot Provenance & Monotonic Revision Resolution
4. Multi-Signal Entity Resolution
5. Deterministic Policy Validation
6. Admission & Bounded Recovery Gate
7. REACTOR Execution Controller
8. Post-Tool Result Verification & Provenance Feedback
"""

from typing import Any, Dict, List, Optional, Tuple

from reactor.controller import Controller
from reactor.guards.boundary import ActorBoundaryGate
from reactor.guards.entity import EntityResolver
from reactor.guards.normalizer import ProposalNormalizer
from reactor.guards.policy import PolicyEngine
from reactor.guards.provenance import SlotProvenanceManager
from reactor.guards.recovery import RecoveryManager
from reactor.guards.types import AdmissionResult, ResultVerificationResult, ToolSpec
from reactor.guards.verifier import ResultVerifier
from reactor.state import Outcome, Proposal


class GuardedExecutionPipeline:
    """End-to-end execution pipeline protecting REACTOR against upstream model errors."""

    def __init__(
        self,
        tool_specs: Dict[str, ToolSpec],
        domain: str = "",
        entity_pool: Optional[List[Dict[str, Any]]] = None,
        max_recovery_budget: int = 2,
        tool_functions: Optional[Dict[str, Any]] = None,
        provenance_manager: Optional[SlotProvenanceManager] = None,
    ):
        self.domain = domain
        self.boundary_gate = ActorBoundaryGate(
            tool_specs=tool_specs,
            active_role="agent",
            active_domain=domain,
            max_recovery_budget=max_recovery_budget,
        )
        self.normalizer = ProposalNormalizer()
        self.entity_resolver = EntityResolver()
        self.policy_engine = PolicyEngine()
        self.provenance_manager = provenance_manager or SlotProvenanceManager()
        self.recovery_manager = RecoveryManager(max_attempts=max_recovery_budget)
        self.result_verifier = ResultVerifier()
        self.tool_specs = tool_specs
        self.entity_pool = entity_pool or []
        self.tool_functions = tool_functions or {}

    async def execute_proposal(
        self,
        controller: Controller,
        tool_name: str,
        raw_args: Dict[str, Any],
        action_id: str,
        user_utterance: str = "",
        policy_context: Optional[Dict[str, Any]] = None,
        revision: int = 1,
    ) -> Tuple[AdmissionResult, Optional[Outcome], Optional[ResultVerificationResult]]:
        """Validates and executes a proposal through guarded execution layers."""
        spec = self.tool_specs.get(tool_name)
        schema = spec.schema if spec else {}

        # 1. Actor Boundary Gate
        recovery_attempts = self.recovery_manager.get_attempt_count(action_id)
        admission = self.boundary_gate.check_admission(
            tool_name=tool_name,
            user_utterance=user_utterance,
            recovery_attempts=recovery_attempts,
        )
        if not admission.allowed:
            return admission, None, None

        # 2. Slot Provenance & Context Recovery:
        # If required schema parameters are missing from raw_args, inspect active valid slots
        merged_args = dict(raw_args)
        if schema and "required" in schema and isinstance(schema["required"], list):
            for req in schema["required"]:
                if req not in merged_args:
                    slot_rec = self.provenance_manager.get_slot(req)
                    if slot_rec is not None:
                        merged_args[req] = slot_rec.value

        # 3. Schema / Argument Normalization
        norm_args, norm_adm = self.normalizer.normalize_args(merged_args, schema)
        if not norm_adm.allowed:
            return norm_adm, None, None

        resolved_args = dict(norm_args)

        # Update slot provenance manager with newly supplied slots
        for k, v in resolved_args.items():
            if isinstance(v, (str, int, float, bool)):
                self.provenance_manager.update_slot(
                    slot_name=k,
                    value=v,
                    revision=revision,
                    source="user",
                )

        # 4. Multi-Signal Entity Resolution
        # If the tool performs customer lookup or accepts customer details, corroborate identity safely
        if self.entity_pool and any(k in resolved_args for k in ["name", "first_name", "user_id", "customer_id", "email", "phone"]):
            res_result = self.entity_resolver.resolve(resolved_args, self.entity_pool)
            if res_result.status == "RESOLVED" and res_result.entity:
                # Update canonical name fields if resolved
                ent = res_result.entity
                if "name" in ent and isinstance(ent["name"], dict):
                    if "first_name" in resolved_args:
                        resolved_args["first_name"] = ent["name"]["first_name"]
                    if "last_name" in resolved_args:
                        resolved_args["last_name"] = ent["name"]["last_name"]
                if "user_id" in ent and "user_id" in resolved_args:
                    resolved_args["user_id"] = ent["user_id"]
            elif res_result.status == "AMBIGUOUS":
                return (
                    AdmissionResult(
                        allowed=False,
                        code="AMBIGUOUS_ENTITY",
                        reason=f"Identity is ambiguous: {res_result.details}",
                        repairable=True,
                        suggested_clarification="Ask customer to confirm exact billing ZIP code or phone number.",
                    ),
                    None,
                    None,
                )

        # 5. Deterministic Policy Validation
        policy_ctx = dict(policy_context or {})
        if "tools" not in policy_ctx and self.tool_functions:
            policy_ctx["tools"] = self.tool_functions
        policy_res = self.policy_engine.evaluate_action(
            domain=self.domain,
            tool_name=tool_name,
            args=resolved_args,
            context=policy_ctx,
        )
        if policy_res.status != "ALLOWED":
            return (
                AdmissionResult(
                    allowed=False,
                    code=policy_res.code,
                    reason=policy_res.reason,
                    repairable=(policy_res.status in {"MISSING_INFORMATION", "REQUIRES_VERIFICATION"}),
                ),
                None,
                None,
            )

        # 6. REACTOR Controller Dispatch
        if controller._state.request_id > 0 and controller._state.resolved:
            from reactor.state import RequestToken
            current_token = RequestToken(controller._state.request_id, controller._state.intent_revision)
        else:
            rev = await controller.begin_input()
            current_token = await controller.resolve_input(rev, mode="new")

        prop = Proposal(
            request=current_token,
            action_id=action_id,
            tool=tool_name,
            args=resolved_args,
        )

        outcome = await controller.execute(prop)

        # 7. Post-Tool Result Verification & Slot Feedback
        verification = None
        if outcome.status == "succeeded":
            verification = self.result_verifier.verify(tool_name, outcome.result)
            # If tool returns structured object/dict, capture confirmed slots
            if isinstance(outcome.result, dict):
                for res_k, res_v in outcome.result.items():
                    if isinstance(res_v, (str, int, float, bool)):
                        self.provenance_manager.update_slot(
                            slot_name=res_k,
                            value=res_v,
                            revision=revision,
                            source="tool_result",
                            status="CONFIRMED",
                        )

        return AdmissionResult(allowed=True, code="OK", reason="Executed"), outcome, verification
