"""Generic Bounded Recovery Protocol for REACTOR v4.

Manages recovery budgets, structured rejection feedback, and coordinates
intent revision advancement to ensure superseded proposals are automatically
cancelled by the REACTOR execution controller.
"""

from typing import Any, Dict, List, Optional, Tuple

from reactor.controller import Controller
from reactor.guards.types import AdmissionResult


class RecoveryManager:
    """Coordinates structured recovery attempts and enforces recovery budgets."""

    def __init__(self, max_attempts: int = 2):
        self.max_attempts = max_attempts
        self._attempts: Dict[str, int] = {}  # task_id/action_id -> count

    def get_attempt_count(self, key: str) -> int:
        return self._attempts.get(key, 0)

    def record_attempt(self, key: str) -> int:
        count = self._attempts.get(key, 0) + 1
        self._attempts[key] = count
        return count

    def record_failure(self, key: str) -> int:
        """Alias for record_attempt."""
        return self.record_attempt(key)

    def is_exhausted(self, key: str) -> bool:
        """Checks if recovery budget for this action/task has been reached."""
        return self.get_attempt_count(key) >= self.max_attempts

    def reset(self, key: str) -> None:
        """Resets the attempt counter for an action."""
        self._attempts.pop(key, None)

    def can_recover(self, key: str, admission: AdmissionResult) -> bool:
        if not admission.repairable:
            return False
        return not self.is_exhausted(key)

    async def advance_revision_for_recovery(
        self,
        controller: Controller,
        key: str,
        reason: str,
        recovery_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Advances REACTOR intent revision so invalid in-flight proposals become stale."""
        self.record_attempt(key)
        rev = await controller.begin_input()
        token = await controller.resolve_input(
            rev,
            mode="correction",
            changes={"recovery_reason": reason, "recovery_context": recovery_context or {}},
        )
        return token
