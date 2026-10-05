"""Generic Deterministic Policy Validation Engine for REACTOR v4.

Evaluates business constraints (refund eligibility, cancellation windows,
fare classes, verification requirements) before tool execution.
Inspects authoritative state via read-only tools or context.
"""

from typing import Any, Dict, List, Optional

from reactor.guards.types import PolicyEvaluationResult


class PolicyEngine:
    """Enforces enterprise business policies deterministically."""

    def __init__(self, policy_rules: Optional[Dict[str, Any]] = None):
        self._rules = policy_rules or {}

    def _get_val(self, obj: Any, key: str, default: Any = None) -> Any:
        """Safely extracts a property from either a dict or an object instance."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def evaluate_action(
        self,
        domain: str,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyEvaluationResult:
        """Evaluates whether the proposed action complies with domain policies."""
        ctx = context or {}

        # 1. Airline policies: Fare class and cancellation rules
        if domain == "airline":
            if tool_name == "cancel_reservation":
                cabin = args.get("cabin") or ctx.get("cabin")
                ins_raw = args.get("insurance") if "insurance" in args else ctx.get("insurance")
                has_insurance = ins_raw is True or str(ins_raw).strip().lower() in {"yes", "true", "1"}
                
                # Check entity details from environment if available
                res_id = args.get("reservation_id")
                tools = ctx.get("tools", {})
                if res_id and "get_reservation_details" in tools:
                    try:
                        r_info = tools["get_reservation_details"](reservation_id=res_id)
                        c = self._get_val(r_info, "cabin")
                        if c is not None:
                            cabin = c
                        ins = self._get_val(r_info, "insurance")
                        if ins is not None:
                            has_insurance = ins is True or str(ins).strip().lower() in {"yes", "true", "1"}
                    except Exception:
                        pass

                if cabin == "basic_economy" and not has_insurance:
                    return PolicyEvaluationResult(
                        status="DENIED",
                        code="NON_REFUNDABLE_FARE",
                        reason="Basic economy tickets are non-refundable without travel insurance.",
                        details={"cabin": cabin, "insurance": has_insurance},
                    )

            if tool_name == "update_reservation_flights":
                flights = args.get("flights") or []
                if not flights:
                    return PolicyEvaluationResult(
                        status="MISSING_INFORMATION",
                        code="NO_FLIGHTS_SPECIFIED",
                        reason="Flight modification requires at least one target flight segment.",
                    )

        # 2. Retail policies: Return / exchange windows and order status
        elif domain == "retail":
            tools = ctx.get("tools", {})
            order_id = args.get("order_id")
            o_info = None
            if order_id and "get_order_details" in tools:
                try:
                    o_info = tools["get_order_details"](order_id=order_id)
                except Exception:
                    pass

            order_status = self._get_val(o_info, "status") if o_info is not None else None

            if tool_name == "cancel_pending_order":
                if order_status is not None and str(order_status).strip().lower() != "pending":
                    return PolicyEvaluationResult(
                        status="DENIED",
                        code="INVALID_ORDER_STATUS",
                        reason=f"Only pending orders can be cancelled. Order status is '{order_status}'.",
                        details={"order_id": order_id, "status": order_status},
                    )

            if tool_name in {"return_delivered_order_items", "exchange_delivered_order_items"}:
                if order_status is not None and str(order_status).strip().lower() != "delivered":
                    return PolicyEvaluationResult(
                        status="DENIED",
                        code="INVALID_ORDER_STATUS",
                        reason=f"Only delivered orders can be returned or exchanged. Order status is '{order_status}'.",
                        details={"order_id": order_id, "status": order_status},
                    )

                days_since_delivery = ctx.get("days_since_delivery")
                is_member = str(ctx.get("membership", "")).lower() in {"gold", "silver"}
                max_window = 60 if is_member else 30
                if days_since_delivery is not None and days_since_delivery > max_window:
                    return PolicyEvaluationResult(
                        status="DENIED",
                        code="RETURN_WINDOW_EXCEEDED",
                        reason=f"Return window of {max_window} days exceeded ({days_since_delivery} days since delivery).",
                        details={"days": days_since_delivery, "max_window": max_window},
                    )

        # 3. Telecom policies: Customer verification before line modifications
        elif domain == "telecom":
            if tool_name in {"suspend_line", "resume_line", "refuel_data", "enable_roaming", "disable_roaming"}:
                is_verified = ctx.get("customer_verified", False)
                has_auth = bool(args.get("dob") or args.get("pin"))
                if not is_verified and not has_auth:
                    return PolicyEvaluationResult(
                        status="REQUIRES_VERIFICATION",
                        code="KYC_VERIFICATION_REQUIRED",
                        reason="Line modification requires prior customer authentication (DOB or PIN verification).",
                    )

        return PolicyEvaluationResult(status="ALLOWED", code="OK", reason="Action permitted by policy")
