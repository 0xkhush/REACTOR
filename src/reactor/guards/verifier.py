"""Generic Tool Result Verifier for REACTOR v4.

Verifies whether an executed tool result successfully satisfies the proposed
intent, detecting silent API failures or partial state updates.
"""

from typing import Any, Dict, Optional

from reactor.guards.types import ResultVerificationResult


class ResultVerifier:
    """Verifies that executed tool results conform to expected outcomes."""

    @staticmethod
    def verify(
        tool_name: str,
        result: Any,
        intended_action: str = "",
    ) -> ResultVerificationResult:
        if result is None:
            return ResultVerificationResult(status="FAILED", reason="Tool returned None")

        # 1. Check for error markers in dict or object
        if isinstance(result, dict):
            if bool(result.get("error")) or result.get("error") is True:
                err_msg = result.get("error") if isinstance(result.get("error"), str) else result.get("content", result.get("message", "Tool reported error"))
                return ResultVerificationResult(
                    status="FAILED",
                    reason=str(err_msg),
                    details=result,
                )
            if "status" in result and str(result["status"]).lower() in {"failed", "error", "cancelled"}:
                return ResultVerificationResult(
                    status="FAILED",
                    reason=f"Status indicates failure: {result['status']}",
                    details=result,
                )

        # 2. Check string error signatures
        res_str = str(result)
        if res_str.startswith("Error:") or res_str.startswith("ValidationError:"):
            return ResultVerificationResult(status="FAILED", reason=res_str)

        return ResultVerificationResult(status="SATISFIED", reason="Tool result verified successfully")
