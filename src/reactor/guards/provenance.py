"""Slot Provenance and Monotonic Revision Tracking for REACTOR v4.

Tracks slot origin, revision history, and dependent slot validity outside
the frozen execution controller. Prevents stale/out-of-order slot overwrites
and cascades invalidation when parent context (e.g. order_id) changes.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set

SlotStatus = Literal["CONFIRMED", "UNCONFIRMED", "SUPERSEDED", "INVALIDATED"]


@dataclass(frozen=True)
class SlotRecord:
    """Historical and contextual record of a single slot value."""
    slot_name: str
    value: Any
    revision: int
    source: str = "user"  # "user", "agent", "tool_result", "inferred"
    confidence: float = 1.0
    status: SlotStatus = "CONFIRMED"
    timestamp: float = field(default_factory=time.time)


class SlotProvenanceManager:
    """Manages slot lifecycle, monotonic revision ordering, and dependent invalidation."""

    # Default generic parent-child slot dependencies
    DEFAULT_DEPENDENCIES = {
        "order_id": ["item_id", "items", "return_reason", "exchange_item", "order_status"],
        "reservation_id": ["flight_id", "flights", "cabin", "seat", "passenger_name"],
        "phone_number": ["line_id", "pin", "plan_id", "roaming_status"],
        "user_id": ["order_id", "reservation_id", "phone_number", "address", "email"],
    }

    def __init__(self, custom_dependencies: Optional[Dict[str, List[str]]] = None):
        self._slots: Dict[str, SlotRecord] = {}
        self._history: List[SlotRecord] = []
        self._dependencies: Dict[str, Set[str]] = {}
        
        # Initialize dependencies
        for parent, children in self.DEFAULT_DEPENDENCIES.items():
            self._dependencies[parent] = set(children)
        if custom_dependencies:
            for parent, children in custom_dependencies.items():
                if parent not in self._dependencies:
                    self._dependencies[parent] = set()
                self._dependencies[parent].update(children)

    def register_dependency(self, parent_slot: str, child_slot: str) -> None:
        """Registers a parent-child slot dependency."""
        if parent_slot not in self._dependencies:
            self._dependencies[parent_slot] = set()
        self._dependencies[parent_slot].add(child_slot)

    def update_slot(
        self,
        slot_name: str,
        value: Any,
        revision: int,
        source: str = "user",
        confidence: float = 1.0,
        status: SlotStatus = "CONFIRMED",
    ) -> bool:
        """Updates a slot value respecting monotonic revision ordering.
        
        Returns True if the update was accepted, False if rejected (stale revision).
        """
        existing = self._slots.get(slot_name)
        if existing is not None:
            # Monotonic revision check: reject older revision updates
            if revision < existing.revision:
                return False

            # If the value is changing, supersede the old record and invalidate dependents
            if existing.value != value:
                superseded_record = SlotRecord(
                    slot_name=existing.slot_name,
                    value=existing.value,
                    revision=existing.revision,
                    source=existing.source,
                    confidence=existing.confidence,
                    status="SUPERSEDED",
                    timestamp=existing.timestamp,
                )
                self._history.append(superseded_record)
                self._cascade_invalidation(slot_name, revision)

        new_record = SlotRecord(
            slot_name=slot_name,
            value=value,
            revision=revision,
            source=source,
            confidence=confidence,
            status=status,
            timestamp=time.time(),
        )
        self._slots[slot_name] = new_record
        self._history.append(new_record)
        return True

    def _cascade_invalidation(self, parent_slot: str, revision: int) -> None:
        """Invalidates all dependent child slots when a parent slot changes."""
        children = self._dependencies.get(parent_slot, set())
        for child in children:
            child_rec = self._slots.get(child)
            if child_rec is not None and child_rec.status not in {"SUPERSEDED", "INVALIDATED"}:
                inv_rec = SlotRecord(
                    slot_name=child_rec.slot_name,
                    value=child_rec.value,
                    revision=revision,
                    source="system_invalidation",
                    confidence=child_rec.confidence,
                    status="INVALIDATED",
                    timestamp=time.time(),
                )
                self._slots[child] = inv_rec
                self._history.append(inv_rec)
                # Recursively cascade if child also has dependents
                self._cascade_invalidation(child, revision)

    def invalidate_slot(self, slot_name: str, revision: int, reason: str = "") -> None:
        """Explicitly invalidates a slot and its dependents."""
        rec = self._slots.get(slot_name)
        if rec is not None:
            inv_rec = SlotRecord(
                slot_name=rec.slot_name,
                value=rec.value,
                revision=revision,
                source=f"invalidation:{reason}" if reason else "invalidation",
                confidence=rec.confidence,
                status="INVALIDATED",
                timestamp=time.time(),
            )
            self._slots[slot_name] = inv_rec
            self._history.append(inv_rec)
            self._cascade_invalidation(slot_name, revision)

    def confirm_slot(self, slot_name: str) -> bool:
        """Confirms an unconfirmed slot."""
        rec = self._slots.get(slot_name)
        if rec is not None and rec.status == "UNCONFIRMED":
            confirmed = SlotRecord(
                slot_name=rec.slot_name,
                value=rec.value,
                revision=rec.revision,
                source=rec.source,
                confidence=rec.confidence,
                status="CONFIRMED",
                timestamp=time.time(),
            )
            self._slots[slot_name] = confirmed
            self._history.append(confirmed)
            return True
        return False

    def get_slot(self, slot_name: str) -> Optional[SlotRecord]:
        """Returns the active record for a slot if valid."""
        rec = self._slots.get(slot_name)
        if rec and rec.status in {"CONFIRMED", "UNCONFIRMED"}:
            return rec
        return None

    def get_active_slots(self) -> Dict[str, Any]:
        """Returns a mapping of slot names to values for all active, valid slots."""
        return {
            name: rec.value
            for name, rec in self._slots.items()
            if rec.status in {"CONFIRMED", "UNCONFIRMED"}
        }

    def get_history(self, slot_name: Optional[str] = None) -> List[SlotRecord]:
        """Returns the audit trail for all slots or a specific slot."""
        if slot_name is None:
            return list(self._history)
        return [r for r in self._history if r.slot_name == slot_name]
