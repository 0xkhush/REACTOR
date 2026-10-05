"""Generic Schema-Driven Proposal Normalizer for REACTOR v2.

Sanitizes escaped quotes, trims formatting whitespace, normalizes basic types,
and verifies required schema slots without ever fabricating missing values.
"""

from typing import Any, Dict, List, Optional, Tuple

from reactor.guards.types import AdmissionResult


class ProposalNormalizer:
    """Sanitizes tool proposals and enforces schema constraints."""

    @staticmethod
    def normalize_args(
        args: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], AdmissionResult]:
        """Normalizes proposal arguments against schema.
        
        Never invents missing values; rejects incomplete calls cleanly.
        """
        cleaned = ProposalNormalizer._recursive_sanitize(args)

        if not schema:
            return cleaned, AdmissionResult(allowed=True, code="OK", reason="No schema constraints")

        props = schema.get("properties", {})
        required = schema.get("required", [])

        # 1. Type coercion where unambiguous
        coerced = {}
        for k, v in cleaned.items():
            param_spec = props.get(k, {})
            expected_type = param_spec.get("type")
            if expected_type == "integer" and isinstance(v, str) and v.isdigit():
                coerced[k] = int(v)
            elif expected_type == "number" and isinstance(v, str):
                try:
                    coerced[k] = float(v)
                except ValueError:
                    coerced[k] = v
            elif expected_type == "boolean" and isinstance(v, str):
                if v.lower() in {"true", "yes", "1"}:
                    coerced[k] = True
                elif v.lower() in {"false", "no", "0"}:
                    coerced[k] = False
                else:
                    coerced[k] = v
            else:
                coerced[k] = v

        # 2. Check for missing required slots
        missing = [r for r in required if r not in coerced or coerced[r] is None or coerced[r] == ""]
        if missing:
            return coerced, AdmissionResult(
                allowed=False,
                code="MISSING_REQUIRED_ARGUMENTS",
                reason=f"Missing required parameters: {', '.join(missing)}",
                repairable=True,
                missing_fields=missing,
                suggested_clarification=f"Prompt customer to provide missing {', '.join(missing)}.",
            )

        # 3. Enum validation
        for k, v in coerced.items():
            param_spec = props.get(k, {})
            allowed_enums = param_spec.get("enum")
            if allowed_enums and v not in allowed_enums:
                # Check case-insensitive match
                ci_map = {str(e).lower(): e for e in allowed_enums}
                if str(v).lower() in ci_map:
                    coerced[k] = ci_map[str(v).lower()]
                else:
                    return coerced, AdmissionResult(
                        allowed=False,
                        code="INVALID_ENUM_VALUE",
                        reason=f"Value '{v}' for parameter '{k}' not in permitted options: {allowed_enums}",
                        repairable=True,
                        missing_fields=[k],
                    )

        return coerced, AdmissionResult(allowed=True, code="OK", reason="Arguments normalized and valid")

    @staticmethod
    def _recursive_sanitize(val: Any) -> Any:
        """Strips accidental escaped quote characters and trailing whitespace."""
        if isinstance(val, str):
            # Strip literal leading/trailing quote marks that models emit as JSON artifacts
            s = val.strip()
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                s = s[1:-1].strip()
            return s
        if isinstance(val, dict):
            cleaned_dict = {}
            for k, v in val.items():
                k_clean = str(k).strip()
                if (k_clean.startswith('"') and k_clean.endswith('"')) or (k_clean.startswith("'") and k_clean.endswith("'")):
                    k_clean = k_clean[1:-1].strip()
                cleaned_dict[k_clean] = ProposalNormalizer._recursive_sanitize(v)
            return cleaned_dict
        if isinstance(val, list):
            return [ProposalNormalizer._recursive_sanitize(elem) for elem in val]
        return val
