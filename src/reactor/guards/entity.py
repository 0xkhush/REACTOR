"""Generic Multi-Signal Entity Resolver for REACTOR v2.

Ranks candidates via:
1. Exact stable identifier (ID, reservation, order)
2. Exact secondary attribute (email, phone)
3. Exact name + corroborating attribute (ZIP code)
4. High-confidence similarity (>= 0.88) with strict margin separation (>= 0.10)

Never silently selects ambiguous or low-confidence identities.
"""

import difflib
from typing import Any, Dict, List, Optional, Tuple

from reactor.guards.types import EntityResolutionResult


class EntityResolver:
    """Safe, multi-signal entity resolution across local entity directories."""

    def __init__(
        self,
        confidence_cutoff: float = 0.88,
        margin_cutoff: float = 0.10,
    ):
        self.confidence_cutoff = confidence_cutoff
        self.margin_cutoff = margin_cutoff

    def resolve(
        self,
        query: Dict[str, Any],
        entity_pool: List[Dict[str, Any]],
        id_field: str = "id",
    ) -> EntityResolutionResult:
        """Resolves an entity from available candidate pool using multi-signal corroboration."""
        if not entity_pool:
            return EntityResolutionResult(status="NOT_FOUND", details="Entity pool is empty")

        # 1. Exact stable identifier match
        target_id = query.get(id_field) or query.get("user_id") or query.get("customer_id") or query.get("reservation_id")
        if target_id:
            tid_clean = str(target_id).strip().lower()
            id_matches = [
                e for e in entity_pool
                if str(e.get(id_field, "")).strip().lower() == tid_clean
                or str(e.get("user_id", "")).strip().lower() == tid_clean
                or str(e.get("customer_id", "")).strip().lower() == tid_clean
            ]
            if len(id_matches) == 1:
                return EntityResolutionResult(
                    status="RESOLVED",
                    entity=id_matches[0],
                    confidence=1.0,
                    match_type="exact_id",
                    details=f"Matched exact ID '{target_id}'",
                )

        # 2. Exact secondary attribute match (email or phone)
        target_email = query.get("email")
        if target_email and "@" in str(target_email):
            em_clean = str(target_email).strip().lower()
            em_matches = [e for e in entity_pool if str(e.get("email", "")).strip().lower() == em_clean]
            if len(em_matches) == 1:
                return EntityResolutionResult(
                    status="RESOLVED",
                    entity=em_matches[0],
                    confidence=1.0,
                    match_type="exact_email",
                    details=f"Matched exact email '{target_email}'",
                )

        target_phone = query.get("phone") or query.get("phone_number")
        if target_phone:
            digits = "".join(ch for ch in str(target_phone) if ch.isdigit())
            if len(digits) >= 7:
                match_digits = digits[-10:] if len(digits) >= 10 else digits[-7:]
                ph_matches = [
                    e for e in entity_pool
                    if "".join(ch for ch in str(e.get("phone", e.get("phone_number", ""))) if ch.isdigit()).endswith(match_digits)
                ]
                if len(ph_matches) == 1:
                    return EntityResolutionResult(
                        status="RESOLVED",
                        entity=ph_matches[0],
                        confidence=1.0,
                        match_type="exact_phone",
                        details=f"Matched exact phone suffix '{match_digits}'",
                    )

        # 3. Exact Name + Corroborating Attribute (ZIP / postal code)
        first = str(query.get("first_name", "")).strip().lower()
        last = str(query.get("last_name", "")).strip().lower()
        full_name = str(query.get("name", query.get("full_name", ""))).strip().lower()
        if not full_name and (first or last):
            full_name = f"{first} {last}".strip()

        zip_code = str(query.get("zip", query.get("zip_code", query.get("postal_code", "")))).strip()

        if full_name:
            # Check exact name match first
            exact_names = []
            for e in entity_pool:
                e_name = self._extract_name(e).lower()
                if e_name == full_name:
                    exact_names.append(e)

            if len(exact_names) == 1:
                # Disambiguate or corroborate with ZIP if provided
                if not zip_code or self._extract_zip(exact_names[0]) == zip_code:
                    return EntityResolutionResult(
                        status="RESOLVED",
                        entity=exact_names[0],
                        confidence=1.0,
                        match_type="exact_name",
                        details=f"Matched exact name '{full_name}'",
                    )
            elif len(exact_names) > 1:
                if zip_code:
                    zip_filtered = [e for e in exact_names if self._extract_zip(e) == zip_code]
                    if len(zip_filtered) == 1:
                        return EntityResolutionResult(
                            status="RESOLVED",
                            entity=zip_filtered[0],
                            confidence=1.0,
                            match_type="exact_name_and_zip",
                            details=f"Disambiguated '{full_name}' using ZIP '{zip_code}'",
                        )
                return EntityResolutionResult(
                    status="AMBIGUOUS",
                    details=f"Found {len(exact_names)} candidates with exact name '{full_name}'",
                )

        # 4. Multi-Signal Candidate Scoring (Similarity + Corroboration)
        if not full_name:
            return EntityResolutionResult(status="NOT_FOUND", details="No identifier or name provided")

        scored_candidates: List[Tuple[float, Dict[str, Any]]] = []
        for e in entity_pool:
            e_name = self._extract_name(e).lower()
            sim = difflib.SequenceMatcher(None, full_name, e_name).ratio()
            
            # Corroboration boost/penalty based on ZIP
            if zip_code:
                e_zip = self._extract_zip(e)
                if e_zip == zip_code:
                    sim = min(1.0, sim + 0.05)  # slight boost for matching ZIP
                elif e_zip and zip_code and e_zip != zip_code:
                    sim = max(0.0, sim - 0.15)  # penalty for conflicting ZIP

            scored_candidates.append((sim, e))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        if not scored_candidates or scored_candidates[0][0] < self.confidence_cutoff:
            best_score = scored_candidates[0][0] if scored_candidates else 0.0
            return EntityResolutionResult(
                status="NOT_FOUND" if best_score < 0.6 else "LOW_CONFIDENCE",
                confidence=round(best_score, 4),
                details=f"Top candidate similarity {best_score:.2f} below safety cutoff {self.confidence_cutoff}",
            )

        top_score, top_match = scored_candidates[0]
        if len(scored_candidates) > 1 and (top_score - scored_candidates[1][0]) < self.margin_cutoff:
            return EntityResolutionResult(
                status="AMBIGUOUS",
                confidence=round(top_score, 4),
                details=(
                    f"Top candidate '{self._extract_name(top_match)}' ({top_score:.2f}) is within safety margin "
                    f"{self.margin_cutoff} of second candidate ({scored_candidates[1][0]:.2f})"
                ),
            )

        return EntityResolutionResult(
            status="RESOLVED",
            entity=top_match,
            confidence=round(top_score, 4),
            match_type="high_confidence_similarity",
            details=f"Resolved '{full_name}' -> '{self._extract_name(top_match)}' (conf={top_score:.2f})",
        )

    def _extract_name(self, entity: Dict[str, Any]) -> str:
        name_obj = entity.get("name")
        if isinstance(name_obj, dict):
            fn = name_obj.get("first_name", "")
            ln = name_obj.get("last_name", "")
            return f"{fn} {ln}".strip()
        if isinstance(name_obj, str):
            return name_obj.strip()
        fn = entity.get("first_name", "")
        ln = entity.get("last_name", "")
        if fn or ln:
            return f"{fn} {ln}".strip()
        return str(entity.get("full_name", ""))

    def _extract_zip(self, entity: Dict[str, Any]) -> str:
        addr = entity.get("address")
        if isinstance(addr, dict):
            return str(addr.get("zip", addr.get("zip_code", ""))).strip()
        return str(entity.get("zip", entity.get("zip_code", ""))).strip()
