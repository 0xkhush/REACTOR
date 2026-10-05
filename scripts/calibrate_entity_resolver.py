#!/usr/bin/env python3
"""Independent Synthetic Calibration for REACTOR Multi-Signal Entity Resolver.

Evaluates candidate confidence_cutoff and margin_cutoff parameters against
an independent synthetic benchmark of customer profiles, typos, ambiguous
collisions, and out-of-pool distractors.

Zero tolerance for False Positives (resolving to the wrong customer or resolving when ambiguous).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from reactor.guards.entity import EntityResolver

# 1. Independent Synthetic Candidate Directory (NOT derived from τ-Voice)
SYNTHETIC_CANDIDATE_POOL = [
    {
        "id": "CUST-1001",
        "name": {"first_name": "Alexander", "last_name": "Hamilton"},
        "email": "a.hamilton@treasury.gov",
        "phone": "+1-212-555-0101",
        "address": {"street": "57 Wall St", "city": "New York", "state": "NY", "zip": "10005"},
    },
    {
        "id": "CUST-1002",
        "name": {"first_name": "Alexandra", "last_name": "Hamilton"},
        "email": "alex.hamilton@nyu.edu",
        "phone": "+1-212-555-0102",
        "address": {"street": "10 Washington Sq", "city": "New York", "state": "NY", "zip": "10012"},
    },
    {
        "id": "CUST-1003",
        "name": {"first_name": "Thomas", "last_name": "Jefferson"},
        "email": "tjefferson@monticello.org",
        "phone": "+1-434-555-0199",
        "address": {"street": "931 Thomas Jefferson Pkwy", "city": "Charlottesville", "state": "VA", "zip": "22902"},
    },
    {
        "id": "CUST-1004",
        "name": {"first_name": "John", "last_name": "Adams"},
        "email": "jadams@massachusetts.gov",
        "phone": "+1-617-555-0144",
        "address": {"street": "1250 Hancock St", "city": "Quincy", "state": "MA", "zip": "02169"},
    },
    {
        "id": "CUST-1005",
        "name": {"first_name": "John", "last_name": "Adams"},
        "email": "john.adams.boston@attorney.com",
        "phone": "+1-617-555-0999",
        "address": {"street": "100 Beacon St", "city": "Boston", "state": "MA", "zip": "02108"},
    },
    {
        "id": "CUST-1006",
        "name": {"first_name": "Benjamin", "last_name": "Franklin"},
        "email": "ben@poorrichard.org",
        "phone": "+1-215-555-0188",
        "address": {"street": "316 Market St", "city": "Philadelphia", "state": "PA", "zip": "19106"},
    },
    {
        "id": "CUST-1007",
        "name": {"first_name": "George", "last_name": "Washington"},
        "email": "gw@mtvernon.org",
        "phone": "+1-703-555-0111",
        "address": {"street": "3200 Mount Vernon Memorial Hwy", "city": "Mount Vernon", "state": "VA", "zip": "22121"},
    },
    {
        "id": "CUST-1008",
        "name": {"first_name": "James", "last_name": "Madison"},
        "email": "jmadison@constitution.org",
        "phone": "+1-540-555-0133",
        "address": {"street": "11350 Constitution Hwy", "city": "Orange", "state": "VA", "zip": "22960"},
    },
    {
        "id": "CUST-1009",
        "name": {"first_name": "James", "last_name": "Monroe"},
        "email": "jmonroe@highland.org",
        "phone": "+1-434-555-0155",
        "address": {"street": "2050 James Monroe Pkwy", "city": "Charlottesville", "state": "VA", "zip": "22902"},
    },
]

# 2. Independent Calibration Test Cases
@dataclass(frozen=True)
class CalibrationTestCase:
    name: str
    query: Dict[str, Any]
    allowed_statuses: Set[str]  # set of acceptable statuses (e.g. {"RESOLVED"}, or {"AMBIGUOUS"}, or {"NOT_FOUND", "LOW_CONFIDENCE"})
    expected_id: Optional[str] = None


CALIBRATION_TEST_CASES = [
    # Exact Identifiers
    CalibrationTestCase("exact_id_match", {"customer_id": "CUST-1001"}, {"RESOLVED"}, "CUST-1001"),
    CalibrationTestCase("exact_email_match", {"email": "tjefferson@monticello.org"}, {"RESOLVED"}, "CUST-1003"),
    CalibrationTestCase("exact_phone_match", {"phone": "+1-617-555-0144"}, {"RESOLVED"}, "CUST-1004"),
    CalibrationTestCase("phone_suffix_match", {"phone": "555-0188"}, {"RESOLVED"}, "CUST-1006"),

    # Exact Names (Unique)
    CalibrationTestCase("exact_name_unique", {"name": "George Washington"}, {"RESOLVED"}, "CUST-1007"),
    CalibrationTestCase("first_last_separate", {"first_name": "James", "last_name": "Madison"}, {"RESOLVED"}, "CUST-1008"),
    CalibrationTestCase("exact_name_with_corroborating_zip", {"name": "Alexander Hamilton", "zip": "10005"}, {"RESOLVED"}, "CUST-1001"),

    # Disambiguation with Exact Duplicates in Pool
    # Both CUST-1004 and CUST-1005 are named "John Adams". Without ZIP it is AMBIGUOUS.
    CalibrationTestCase("duplicate_names_without_zip", {"name": "John Adams"}, {"AMBIGUOUS"}, None),
    # With ZIP 02169 it resolves to CUST-1004
    CalibrationTestCase("duplicate_name_disambiguated_quincy", {"name": "John Adams", "zip": "02169"}, {"RESOLVED"}, "CUST-1004"),
    # With ZIP 02108 it resolves to CUST-1005
    CalibrationTestCase("duplicate_name_disambiguated_boston", {"name": "John Adams", "zip": "02108"}, {"RESOLVED"}, "CUST-1005"),

    # Typo / Phonetic variations (should resolve cleanly if high similarity and unique)
    CalibrationTestCase("minor_typo_one_char", {"name": "George Washingtn"}, {"RESOLVED"}, "CUST-1007"),  # sim ~ 0.97
    CalibrationTestCase("minor_typo_first_name", {"name": "Jams Madison"}, {"RESOLVED"}, "CUST-1008"),    # sim ~ 0.96
    CalibrationTestCase("minor_typo_with_zip", {"name": "Tomas Jefferson", "zip": "22902"}, {"RESOLVED"}, "CUST-1003"), # sim ~ 0.97

    # Fuzzy Collision / Ambiguity (Alex Hamilton could be Alexander or Alexandra)
    CalibrationTestCase("fuzzy_collision_alex_hamilton", {"name": "Alex Hamilton"}, {"AMBIGUOUS"}, None),

    # Conflicting attribute test: exact name but conflicting ZIP code should NOT resolve to CUST-1007
    CalibrationTestCase("exact_name_conflicting_zip", {"name": "George Washington", "zip": "90210"}, {"NOT_FOUND", "LOW_CONFIDENCE"}, None),

    # Negative / Out-of-pool
    CalibrationTestCase("completely_unrelated", {"name": "Abraham Lincoln"}, {"NOT_FOUND", "LOW_CONFIDENCE"}, None),
    CalibrationTestCase("unrelated_with_zip", {"name": "Theodore Roosevelt", "zip": "10005"}, {"NOT_FOUND", "LOW_CONFIDENCE"}, None),
    CalibrationTestCase("distant_partial", {"name": "Alexandria Jones"}, {"NOT_FOUND", "LOW_CONFIDENCE"}, None),
]


def evaluate_thresholds(
    confidence_cutoff: float,
    margin_cutoff: float,
) -> Dict[str, Any]:
    resolver = EntityResolver(confidence_cutoff=confidence_cutoff, margin_cutoff=margin_cutoff)
    tp = 0
    fp = 0
    tn = 0
    fn = 0
    total = len(CALIBRATION_TEST_CASES)

    for tc in CALIBRATION_TEST_CASES:
        res = resolver.resolve(tc.query, SYNTHETIC_CANDIDATE_POOL)
        
        if "RESOLVED" in tc.allowed_statuses:
            if res.status == "RESOLVED":
                matched_id = res.entity.get("id") if res.entity else None
                if matched_id == tc.expected_id:
                    tp += 1
                else:
                    fp += 1  # Catastrophic: resolved to wrong customer
            else:
                fn += 1
        else:
            # Expected AMBIGUOUS, NOT_FOUND, or LOW_CONFIDENCE
            if res.status == "RESOLVED":
                fp += 1  # Resolved when it should have been rejected/ambiguous
            else:
                if res.status in tc.allowed_statuses:
                    tn += 1
                else:
                    # Still a rejection of RESOLVED, so not a false positive
                    tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "confidence_cutoff": confidence_cutoff,
        "margin_cutoff": margin_cutoff,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "total": total,
    }


def run_grid_search() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    conf_candidates = [0.80, 0.82, 0.85, 0.88, 0.90, 0.92]
    margin_candidates = [0.05, 0.08, 0.10, 0.12, 0.15]

    all_results = []
    best_config = None
    best_score = (-1, -1, -1)  # (fp == 0, f1, precision)

    for c in conf_candidates:
        for m in margin_candidates:
            res = evaluate_thresholds(c, m)
            all_results.append(res)
            # Mandatory safety invariant: FP == 0 must be prioritized
            safety_rank = 1 if res["fp"] == 0 else 0
            score_key = (safety_rank, res["f1"], res["precision"], -res["confidence_cutoff"])
            if score_key > best_score:
                best_score = score_key
                best_config = res

    return best_config, all_results


def main():
    print("=" * 60)
    print("REACTOR v4 Multi-Signal Entity Resolver Calibration")
    print("=" * 60)
    best_config, all_results = run_grid_search()

    print(f"Tested {len(all_results)} parameter combinations.")
    print(f"Optimal Configuration:")
    print(f"  Confidence Cutoff : {best_config['confidence_cutoff']}")
    print(f"  Margin Cutoff     : {best_config['margin_cutoff']}")
    print(f"  Precision         : {best_config['precision']:.4f}")
    print(f"  Recall            : {best_config['recall']:.4f}")
    print(f"  F1 Score          : {best_config['f1']:.4f}")
    print(f"  False Positives   : {best_config['fp']} (Zero-tolerance safety invariant)")
    print(f"  True Positives    : {best_config['tp']}")
    print(f"  True Negatives    : {best_config['tn']}")
    print(f"  False Negatives   : {best_config['fn']}")

    output_path = Path("artifacts/tau_voice_v4/calibration_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "best_configuration": best_config,
                "all_configurations": all_results,
                "dataset_size": len(CALIBRATION_TEST_CASES),
                "pool_size": len(SYNTHETIC_CANDIDATE_POOL),
            },
            f,
            indent=2,
        )
    print(f"\nCalibration saved to {output_path}")


if __name__ == "__main__":
    main()
