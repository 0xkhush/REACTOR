"""Records synthetic benchmark results into artifacts/tau_voice_v2/synthetic_test_results.json."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


def main():
    out_dir = ROOT / "artifacts" / "tau_voice_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "synthetic_test_results.json"

    # Run pytest on tests/test_v2_guardrails.py and capture detailed results
    tests = [
        ("TestEntityResolver", "test_exact_id_match", "Exact ID lookup returns RESOLVED with confidence 1.0"),
        ("TestEntityResolver", "test_exact_email_and_phone", "Exact secondary attributes (email/phone) resolve customer without hallucination"),
        ("TestEntityResolver", "test_exact_name_disambiguated_by_zip", "Ambiguous names are correctly disambiguated by ZIP code"),
        ("TestEntityResolver", "test_phonetic_similarity_with_margin", "Close match with >= 0.88 score and >= 0.10 margin resolves safely"),
        ("TestEntityResolver", "test_low_confidence_rejected", "Low confidence (< 0.88) or ambiguous tie (< 0.10 margin) rejected (NOT_FOUND / AMBIGUOUS)"),
        ("TestActorBoundaryGate", "test_authorized_agent_tool", "Agent tools (modify_billing) are admitted"),
        ("TestActorBoundaryGate", "test_unauthorized_user_tool_blocked", "User-device tools (toggle_airplane_mode) are strictly blocked from agent dispatch"),
        ("TestActorBoundaryGate", "test_nonexistent_tool_blocked", "Hallucinated / non-existent tool names blocked"),
        ("TestActorBoundaryGate", "test_premature_human_transfer_blocked", "Human transfer blocked when recovery budget remains and user didn't ask for human"),
        ("TestActorBoundaryGate", "test_human_transfer_permitted_on_user_escalation", "Human transfer allowed when user explicitly asks for representative"),
        ("TestActorBoundaryGate", "test_human_transfer_permitted_when_budget_exhausted", "Human transfer allowed when recovery budget is exhausted"),
        ("TestProposalNormalizer", "test_escaped_quote_and_whitespace_sanitization", "Nested escaped quotes and whitespace stripped cleanly"),
        ("TestProposalNormalizer", "test_missing_required_slots_rejected_without_fabrication", "Missing required schema slots rejected without inventing data"),
        ("TestProposalNormalizer", "test_type_coercion_and_enum_validation", "String integers coerced, invalid enum choices rejected"),
        ("TestPolicyEngine", "test_airline_basic_economy_cancellation_denied", "Airline basic economy cancellation without insurance is denied deterministically"),
        ("TestPolicyEngine", "test_retail_return_window_exceeded_denied", "Retail return exceeding 30/60 day return window is denied deterministically"),
        ("Integration", "test_bounded_recovery_and_reactor_safety", "Recovery advances intent revision, cancels in-flight proposals, guarantees 0 stale writes"),
    ]

    results = []
    start_time = time.time()
    for suite, test_name, description in tests:
        # Run individual test with pytest
        target = f"tests/test_v2_guardrails.py::{suite}::{test_name}" if suite != "Integration" else f"tests/test_v2_guardrails.py::{test_name}"
        ret = pytest.main(["-q", target])
        passed = (ret == pytest.ExitCode.OK)
        results.append({
            "suite": suite,
            "test_name": test_name,
            "description": description,
            "status": "PASSED" if passed else "FAILED",
            "passed": passed,
        })

    duration = time.time() - start_time
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_tests": total,
        "passed_tests": passed_count,
        "failed_tests": total - passed_count,
        "all_passed": (passed_count == total),
        "duration_seconds": round(duration, 3),
        "tests": results,
    }

    with open(out_file, "w") as fp:
        json.dump(payload, fp, indent=2)

    print(f"Synthetic test results written to {out_file}: {passed_count}/{total} passed in {duration:.2f}s")


if __name__ == "__main__":
    main()
