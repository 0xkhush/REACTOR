"""Tests for τ-Voice adapter, contamination prevention, and metric calculators."""

import inspect
import re
from pathlib import Path
import pytest

from tau2.registry import registry
from tau2.environment.toolkit import ToolType, get_tool_types

from reactor.controller import Controller
from reactor.state import Proposal, RequestToken
from scripts.tau_voice_adapter import (
    TauVoiceToolAdapter,
    TauVoiceSession,
    calculate_wilson_interval,
    detect_user_correction,
)


def test_adapter_contains_no_expected_answer_mappings():
    """Anti-cheat verification: the adapter must contain NO task-id or answer mappings."""
    adapter_path = Path("scripts/tau_voice_adapter.py")
    assert adapter_path.is_file(), "Adapter file must exist"
    code = adapter_path.read_text()

    # Must not contain task-id checks
    assert not re.search(r"if\s+task(_id)?\s*==\s*['\"]\w+['\"]", code, re.I), \
        "Found hardcoded task_id condition in adapter!"
    
    # Must not contain expected tool overrides
    assert not re.search(r"expected_tool\s*=", code, re.I), \
        "Found hardcoded expected_tool assignment in adapter!"

    # Must not map utterances directly to tool names
    assert not re.search(r"if\s+['\"][^'\"]+['\"]\s+in\s+.*:\s*(?:tool|call)\s*=", code, re.I), \
        "Found hardcoded utterance-to-tool mapping in adapter!"


def test_wilson_confidence_interval():
    """Verify Wilson score confidence interval calculations."""
    low, high = calculate_wilson_interval(0, 0)
    assert low == 0.0 and high == 0.0

    low, high = calculate_wilson_interval(50, 50)
    assert low > 0.90 and high >= 0.9999

    # Test user prompt example: 87 / 278 -> ~31.3%, CI: [26.1%, 37.0%]
    low, high = calculate_wilson_interval(87, 278)
    assert 0.25 <= low <= 0.27
    assert 0.36 <= high <= 0.38


def test_detect_user_correction():
    """Verify generic detection of user interruptions and corrections."""
    assert detect_user_correction("Actually, change that to tomorrow") is True
    assert detect_user_correction("Wait no, cancel that order") is True
    assert detect_user_correction("No wait, I meant John Smith") is True
    assert detect_user_correction("Never mind, don't do that") is True
    assert detect_user_correction("Please book the flight for Emma Kim") is False
    assert detect_user_correction("") is False


def test_tool_definition_generation():
    """Verify that domain tools are converted to valid ToolDefinitions."""
    env = registry.get_env_constructor("airline")()
    tool_defs = TauVoiceToolAdapter.build_tool_definitions(env)
    assert len(tool_defs) > 0

    tool_types = get_tool_types(env.tools)
    for td in tool_defs:
        assert isinstance(td.name, str)
        assert isinstance(td.state_modifying, bool)
        assert td.state_modifying == (tool_types.get(td.name) == ToolType.WRITE)
        assert td.schema is not None
        assert td.blocking is True


@pytest.mark.asyncio
async def test_session_lifecycle_and_stale_execution_prevention():
    """Verify that superseded operations are rejected and stale executions are 0."""
    env = registry.get_env_constructor("retail")()
    session = TauVoiceSession("test-session-safety", env)

    # Turn 1: initial request
    tok1 = await session.handle_user_input("I want to find my user id", is_correction=False)
    assert tok1.intent_revision == 1

    # Turn 2: user interrupts with a correction before tool finishes
    tok2 = await session.handle_user_input("Wait no, my name is actually Yusuf Rossi", is_correction=True)
    assert tok2.intent_revision == 2
    assert session.correction_scenarios == 1

    # Propose call under obsolete token 1:
    prop_old = Proposal(tok1, "act-1", "find_user_id_by_name_zip", {"first_name": "Yusuf", "last_name": "Rossi", "zip": "19122"})
    outcome_old = await session.controller.execute(prop_old)

    # Controller must cancel obsolete proposal before dispatch
    assert outcome_old.status == "cancelled_before_dispatch"
    assert session.stale_executions == 0


def test_no_tau_contamination_in_reactor():
    """Verify zero contamination in the frozen reactor core."""
    reactor_dir = Path("src/reactor")
    for f in reactor_dir.rglob("*.py"):
        content = f.read_text(errors="ignore")
        assert not re.search(r"tau.?voice|τ.?voice", content, re.I), f"Contamination in {f}"
        assert "sierra" not in content.lower(), f"Contamination in {f}"
