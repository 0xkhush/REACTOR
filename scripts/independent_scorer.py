"""Clean-room independent scorer for FDB-v3 benchmark evaluation.

Following the exact logic of vendor/Full-Duplex-Bench/v3/evaluate_pass_rate.py
without importing any reactor or vendor files.
"""

import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]

def load_data():
    bench_data = json.loads((ROOT / "vendor" / "Full-Duplex-Bench" / "v3" / "benchmark_data_v2.json").read_text())
    scenarios = {s["id"]: s for s in bench_data["scenarios"]}
    
    results = {}
    for res_file in sorted((ROOT / "artifacts" / "batch_inference").glob("*/result.json")):
        folder_name = res_file.parent.name
        ex_id = folder_name.rsplit("_", 1)[0]
        data = json.loads(res_file.read_text())
        results[folder_name] = (ex_id, data)
    return scenarios, results


def exact_match_args_official_spec(expected: dict, actual: dict) -> bool:
    def normalize(v):
        if isinstance(v, str):
            return v.lower().strip().replace("_", " ")
        return v

    for key, exp_val in expected.items():
        if key not in actual:
            return False
        if isinstance(exp_val, str) and exp_val.startswith("$"):
            continue  # Dynamic reference
        if normalize(exp_val) != normalize(actual.get(key)):
            return False
    return True


def evaluate_recording(expected_calls: list[dict], actual_calls: list[dict]) -> tuple[bool, bool, str]:
    """Returns (tool_selection_passed, exact_arguments_passed, reason)."""
    exp_funcs = [c["function"] for c in expected_calls]
    act_funcs = [c["function"] for c in actual_calls]
    
    if Counter(exp_funcs) != Counter(act_funcs):
        return False, False, f"Tool mismatch: expected {exp_funcs}, got {act_funcs}"
    
    # In official FDB-v3 evaluate_scenario_calls:
    # It matches actual calls to expected calls using FIFO pairing for identical function names
    matched = [False] * len(actual_calls)
    for exp_call in expected_calls:
        found = False
        for i, act_call in enumerate(actual_calls):
            if not matched[i] and act_call["function"] == exp_call["function"]:
                if exact_match_args_official_spec(exp_call.get("args", {}), act_call.get("args", {})):
                    matched[i] = True
                    found = True
                    break
        if not found:
            return True, False, f"Argument mismatch for {exp_call['function']}"
            
    return True, True, ""


def run_independent_scoring():
    scenarios, results = load_data()
    total = len(results)
    tool_sel_count = 0
    exact_arg_count = 0
    
    failures = []
    
    for folder, (ex_id, data) in results.items():
        scenario = scenarios.get(ex_id)
        if not scenario:
            continue
        exp_calls = scenario.get("expected_tool_calls", [])
        act_calls = data.get("actual_tool_calls", [])
        
        tool_pass, arg_pass, reason = evaluate_recording(exp_calls, act_calls)
        if tool_pass:
            tool_sel_count += 1
        if arg_pass:
            exact_arg_count += 1
        else:
            failures.append({
                "folder": folder,
                "example_id": ex_id,
                "tool_selection": tool_pass,
                "reason": reason,
                "expected": exp_calls,
                "actual": act_calls
            })
            
    print("=" * 60)
    print("INDEPENDENT SCORER (OFFICIAL SPEC) RESULTS")
    print(f"Total recordings evaluated: {total}")
    print(f"Tool Selection Accuracy:   {tool_sel_count} / {total} ({tool_sel_count/total*100:.1f}%)")
    print(f"Strict Exact Pass@1:       {exact_arg_count} / {total} ({exact_arg_count/total*100:.1f}%)")
    print(f"Total Failures:            {len(failures)}")
    print("=" * 60)
    
    for f in failures:
        print(f"\n[{f['folder']}] (tool_selection={f['tool_selection']}) - {f['reason']}")
        print(f"  Expected: {f['expected']}")
        print(f"  Actual:   {f['actual']}")
        
    return total, tool_sel_count, exact_arg_count, failures


if __name__ == "__main__":
    run_independent_scoring()
