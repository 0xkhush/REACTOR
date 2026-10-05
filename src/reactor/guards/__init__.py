"""REACTOR v4 Guarded Execution Module."""

from reactor.guards.boundary import ActorBoundaryGate
from reactor.guards.entity import EntityResolver
from reactor.guards.normalizer import ProposalNormalizer
from reactor.guards.pipeline import GuardedExecutionPipeline
from reactor.guards.policy import PolicyEngine
from reactor.guards.provenance import SlotProvenanceManager, SlotRecord, SlotStatus
from reactor.guards.recovery import RecoveryManager
from reactor.guards.types import (
    AdmissionResult,
    EntityResolutionResult,
    PolicyEvaluationResult,
    ResultVerificationResult,
    ToolSpec,
)
from reactor.guards.verifier import ResultVerifier

__all__ = [
    "ActorBoundaryGate",
    "EntityResolver",
    "ProposalNormalizer",
    "PolicyEngine",
    "SlotProvenanceManager",
    "SlotRecord",
    "SlotStatus",
    "RecoveryManager",
    "ResultVerifier",
    "GuardedExecutionPipeline",
    "AdmissionResult",
    "EntityResolutionResult",
    "PolicyEvaluationResult",
    "ResultVerificationResult",
    "ToolSpec",
]
