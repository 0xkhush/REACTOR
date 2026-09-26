import math

import pytest

from reactor.state import SessionState


def test_correction_preserves_slots_and_supersedes_old_request():
    state = SessionState("s1")
    first = state.resolve_input(
        state.begin_input(), mode="new",
        changes={"destination": "Boston", "date": "Friday"},
    )
    second = state.resolve_input(
        state.begin_input(), mode="correction", changes={"destination": "Chicago"},
    )
    assert state.snapshot()["slots"] == {
        "destination": {"value": "Chicago", "intent_revision": 2},
        "date": {"value": "Friday", "intent_revision": 1},
    }
    assert second.request_id == first.request_id
    assert not state.is_current(first)
    assert state.is_current(second)


def test_late_interpretation_cannot_overwrite_newer_input():
    state = SessionState("s1")
    old = state.begin_input()
    latest = state.begin_input()
    request = state.resolve_input(latest, mode="new", changes={"n": 7})
    with pytest.raises(ValueError, match="stale input"):
        state.resolve_input(old, mode="correction", changes={"n": 10})
    assert state.is_current(request)
    assert state.snapshot()["slots"]["n"]["value"] == 7


def test_resume_preserves_request_while_new_intent_changes_identity():
    state = SessionState("s1")
    request = state.resolve_input(state.begin_input(), mode="new")
    revision = state.begin_input()
    assert not state.resolved
    assert state.is_current(request)
    resumed = state.resolve_input(revision, mode="resume")
    assert resumed == request
    new = state.resolve_input(state.begin_input(), mode="new")
    assert new.request_id != request.request_id
    assert not state.is_current(request)


@pytest.mark.parametrize("mode", ["correction", "resume"])
def test_first_request_cannot_be_a_correction_or_resume(mode):
    state = SessionState("s1")
    with pytest.raises(ValueError, match="preceding request"):
        state.resolve_input(state.begin_input(), mode=mode)


def test_input_can_only_be_resolved_once():
    state = SessionState("s1")
    revision = state.begin_input()
    state.resolve_input(revision, mode="new")
    with pytest.raises(ValueError, match="already resolved"):
        state.resolve_input(revision, mode="new")


def test_resume_rejects_slot_changes_without_resolving_input():
    state = SessionState("s1")
    state.resolve_input(state.begin_input(), mode="new")
    revision = state.begin_input()
    with pytest.raises(ValueError, match="resume"):
        state.resolve_input(revision, mode="resume", changes={"n": 4})
    assert not state.resolved
    state.resolve_input(revision, mode="resume")


def test_slot_values_and_snapshots_are_detached_from_callers():
    state = SessionState("s1")
    changes = {"items": ["a"]}
    state.resolve_input(state.begin_input(), mode="new", changes=changes)
    changes["items"].append("b")
    snapshot = state.snapshot()
    snapshot["slots"]["items"]["value"].append("c")
    assert state.snapshot()["slots"]["items"]["value"] == ["a"]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {1: "x"}, (1, 2), object()])
def test_invalid_json_does_not_partially_update_state(value):
    state = SessionState("s1")
    revision = state.begin_input()
    with pytest.raises(ValueError):
        state.resolve_input(revision, mode="new", changes={"x": value})
    assert state.snapshot()["intent_revision"] == 0
    assert state.snapshot()["slots"] == {}
    assert not state.resolved


def test_state_is_session_local():
    first, second = SessionState("a"), SessionState("b")
    first.resolve_input(first.begin_input(), mode="new", changes={"n": 7})
    assert second.snapshot()["slots"] == {}


def test_invalid_mode_does_not_resolve_input():
    state = SessionState("s1")
    with pytest.raises(ValueError, match="mode"):
        state.resolve_input(state.begin_input(), mode="typo")
    assert not state.resolved
