"""Generic Actor Boundary Gate for REACTOR v2.

Enforces tool ownership, domain boundaries, and human escalation policies
without hardcoding benchmark tool names or scenarios.
"""

import re
from typing import Dict, Optional, Set

from reactor.guards.types import AdmissionResult, ToolSpec


class ActorBoundaryGate:
    """Enforces capability and actor boundaries on proposed tool invocations."""

    def __init__(
        self,
        tool_specs: Dict[str, ToolSpec],
        active_role: str = "agent",
        active_domain: Optional[str] = None,
        max_recovery_budget: int = 2,
    ):
        self._specs = tool_specs
        self._role = active_role
        self._domain = active_domain
        self._max_budget = max_recovery_budget
        self._escalation_patterns = [
            r"\b(?:speak|talk|transfer|connect)\s+(?:me\s+|us\s+)?(?:to\s+)?(?:a\s+)?(?:human|representative|agent|person|supervisor|operator)\b",
            r"\b(?:give\s+me|connect\s+me\s+to|let\s+me\s+speak\s+to)\s+(?:a\s+)?(?:human|person|supervisor|representative|agent|operator)\b",
            r"\b(?:operator|live\s+agent|human\s+agent|human\s+representative)\b",
        ]

    def check_admission(
        self,
        tool_name: str,
        user_utterance: str = "",
        recovery_attempts: int = 0,
        has_unrecoverable_error: bool = False,
    ) -> AdmissionResult:
        """Determines if the proposed tool is authorized for execution."""
        spec = self._specs.get(tool_name)
        if spec is None:
            return AdmissionResult(
                allowed=False,
                code="TOOL_NOT_FOUND",
                reason=f"Tool '{tool_name}' does not exist in the environment",
                repairable=False,
            )

        # 1. Role ownership check (agent vs user device tools vs system tools)
        if spec.owner != self._role:
            return AdmissionResult(
                allowed=False,
                code="ACTOR_BOUNDARY_VIOLATION",
                reason=(
                    f"Tool '{tool_name}' is owned by '{spec.owner}', not the active actor '{self._role}'. "
                    "Agents must instruct the user verbally rather than programmatically dispatching user device tools."
                ),
                repairable=True,
                suggested_clarification=f"Instruct user to perform {tool_name} directly on device.",
            )

        # 2. Domain compatibility check
        if self._domain and spec.domains and self._domain not in spec.domains:
            return AdmissionResult(
                allowed=False,
                code="DOMAIN_MISMATCH",
                reason=f"Tool '{tool_name}' is not registered for domain '{self._domain}'",
                repairable=False,
            )

        # 3. Human Transfer Gate
        if tool_name in {"transfer_to_human_agents", "escalate_to_human"}:
            return self._check_human_transfer(
                user_utterance=user_utterance,
                recovery_attempts=recovery_attempts,
                has_unrecoverable_error=has_unrecoverable_error,
            )

        return AdmissionResult(allowed=True, code="OK", reason="Authorized")

    def _check_human_transfer(
        self,
        user_utterance: str,
        recovery_attempts: int,
        has_unrecoverable_error: bool,
    ) -> AdmissionResult:
        """Enforces conditions under which transfer to human is permitted."""
        # Condition A: Explicit user request
        if user_utterance:
            lower = user_utterance.lower()
            if any(re.search(pat, lower) for pat in self._escalation_patterns):
                return AdmissionResult(
                    allowed=True,
                    code="USER_REQUESTED_TRANSFER",
                    reason="Explicit user request for human assistance recognized.",
                )

        # Condition B: Unrecoverable system failure
        if has_unrecoverable_error:
            return AdmissionResult(
                allowed=True,
                code="UNRECOVERABLE_ERROR_TRANSFER",
                reason="Transfer permitted due to unrecoverable system exception.",
            )

        # Condition C: Exhausted bounded recovery attempts
        if recovery_attempts >= self._max_budget:
            return AdmissionResult(
                allowed=True,
                code="EXHAUSTED_RECOVERY_TRANSFER",
                reason=f"Recovery budget of {self._max_budget} attempts exhausted; escalation permitted.",
            )

        # Otherwise: Premature surrender is blocked
        return AdmissionResult(
            allowed=False,
            code="PREMATURE_HUMAN_TRANSFER",
            reason=(
                "Premature human transfer rejected: the automated system has remaining recovery budget "
                f"({recovery_attempts}/{self._max_budget}) and the user did not request a representative."
            ),
            repairable=True,
            suggested_clarification="Attempt automated problem diagnosis or ask customer for clarifying details.",
        )
