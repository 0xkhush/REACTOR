"""Type definitions for REACTOR v2 Guarded Execution."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set


@dataclass(frozen=True)
class AdmissionResult:
    """Outcome of proposal admission check."""
    allowed: bool
    reason: str = "OK"
    code: str = "OK"
    repairable: bool = False
    missing_fields: List[str] = field(default_factory=list)
    suggested_clarification: Optional[str] = None


@dataclass(frozen=True)
class EntityResolutionResult:
    """Outcome of entity resolution lookup."""
    status: Literal["RESOLVED", "NOT_FOUND", "AMBIGUOUS", "LOW_CONFIDENCE"]
    entity: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    match_type: str = "none"
    details: Optional[str] = None


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Outcome of deterministic business policy evaluation."""
    status: Literal["ALLOWED", "DENIED", "MISSING_INFORMATION", "REQUIRES_VERIFICATION"]
    reason: str = "OK"
    code: str = "OK"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultVerificationResult:
    """Outcome of post-tool result consistency verification."""
    status: Literal["SATISFIED", "PARTIAL", "FAILED", "INCONSISTENT"]
    reason: str = "OK"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    """Specification of tool ownership, domain boundaries, and side effects."""
    name: str
    owner: Literal["agent", "user", "system"] = "agent"
    domains: Set[str] = field(default_factory=set)
    state_modifying: bool = False
    requires_auth: bool = False
    schema: Dict[str, Any] = field(default_factory=dict)
