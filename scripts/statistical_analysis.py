"""Statistical analysis of REACTOR benchmark results on NTU Full-Duplex-Bench v3."""

import json
import math
import glob
import numpy as np
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]

def wilson_interval(successes: int, total: int, confidence: float = 0.95):
    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054  # 95%
    p = successes / total
    denom = 1 + (z**2) / total
    centre = (p + (z**2) / (2 * total)) / denom
    spread = (z * math.sqrt((p * (1 - p) / total) + (z**2) / (4 * total**2))) / denom
    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return lower, upper

def bootstrap_interval(data: list[int], n_bootstrap: int = 10000, confidence: float = 0.95):
    rng = np.random.default_rng(42)
    means = []
    arr = np.array(data)
    n = len(arr)
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=n, replace=True)
        means.append(sample.mean())
    alpha = (1.0 - confidence) / 2.0
    lower = float(np.percentile(means, 100 * alpha))
    upper = float(np.percentile(means, 100 * (1.0 - alpha)))
    return lower, upper

def main():
    exact_data = json.load(open(ROOT / "artifacts" / "batch_inference" / "batch-call-exact.json"))
    metadata_map = {}
    for mf in (ROOT / "fdb_v3_data_released").glob("*/metadata.json"):
        folder = mf.parent.name
        metadata_map[folder] = json.load(open(mf))

    exact_results = []
    tool_sel_results = []
    domain_results = defaultdict(lambda: {"total": 0, "exact_pass": 0, "tool_pass": 0})
    disfluency_results = defaultdict(lambda: {"total": 0, "exact_pass": 0, "tool_pass": 0})

    for ex in exact_data["examples"]:
        folder = ex["folder"]
        meta = metadata_map.get(folder, {})
        domain = meta.get("domain", folder.split("_")[0])
        disfluencies = meta.get("disfluency_features", ["NONE"])

        is_exact = 1 if ex["passed"] else 0
        is_tool = 1 if ex["tool_selection_passed"] else 0

        exact_results.append(is_exact)
        tool_sel_results.append(is_tool)

        domain_results[domain]["total"] += 1
        domain_results[domain]["exact_pass"] += is_exact
        domain_results[domain]["tool_pass"] += is_tool

        for d in disfluencies:
            disfluency_results[d]["total"] += 1
            disfluency_results[d]["exact_pass"] += is_exact
            disfluency_results[d]["tool_pass"] += is_tool

    n = len(exact_results)
    exact_k = sum(exact_results)
    tool_k = sum(tool_sel_results)

    exact_wilson = wilson_interval(exact_k, n)
    exact_boot = bootstrap_interval(exact_results)
    tool_wilson = wilson_interval(tool_k, n)

    print("=" * 65)
    print("STATISTICAL ANALYSIS REPORT: REACTOR on FDB-v3")
    print("=" * 65)
    print(f"Total Evaluated Sample Size (N): {n}")
    print(f"\n1. Strict Exact Tool + Argument Match (Pass@1):")
    print(f"   Accuracy: {exact_k} / {n} ({exact_k/n*100:.1f}%)")
    print(f"   Wilson 95% CI:    [{exact_wilson[0]*100:.2f}%, {exact_wilson[1]*100:.2f}%]")
    print(f"   Bootstrap 95% CI: [{exact_boot[0]*100:.2f}%, {exact_boot[1]*100:.2f}%]")

    print(f"\n2. Tool Selection Accuracy:")
    print(f"   Accuracy: {tool_k} / {n} ({tool_k/n*100:.1f}%)")
    print(f"   Wilson 95% CI:    [{tool_wilson[0]*100:.2f}%, {tool_wilson[1]*100:.2f}%]")

    arg_acc = exact_k / tool_k if tool_k > 0 else 0
    arg_wilson = wilson_interval(exact_k, tool_k)
    print(f"\n3. Conditional Argument Accuracy (given correct tool selection):")
    print(f"   Accuracy: {exact_k} / {tool_k} ({arg_acc*100:.1f}%)")
    print(f"   Wilson 95% CI:    [{arg_wilson[0]*100:.2f}%, {arg_wilson[1]*100:.2f}%]")

    print("\n4. Per-Domain Performance Breakdown:")
    print(f"{'Domain':<22} | {'Exact Pass':<12} | {'Exact %':<8} | {'Tool Pass':<12} | {'Tool %':<8}")
    print("-" * 65)
    for dom, stats in sorted(domain_results.items()):
        e_pct = stats["exact_pass"] / stats["total"] * 100
        t_pct = stats["tool_pass"] / stats["total"] * 100
        print(f"{dom:<22} | {stats['exact_pass']:>2}/{stats['total']:<8} | {e_pct:>6.1f}% | {stats['tool_pass']:>2}/{stats['total']:<8} | {t_pct:>6.1f}%")

    print("\n5. Per-Disfluency Type Breakdown:")
    print(f"{'Disfluency Type':<25} | {'Exact Pass':<12} | {'Exact %':<8} | {'Total':<6}")
    print("-" * 65)
    for dis, stats in sorted(disfluency_results.items()):
        e_pct = stats["exact_pass"] / stats["total"] * 100
        print(f"{dis:<25} | {stats['exact_pass']:>2}/{stats['total']:<8} | {e_pct:>6.1f}% | {stats['total']:<6}")

    stats_output = {
        "n": n,
        "exact_pass": exact_k,
        "exact_pass_pct": exact_k / n,
        "exact_wilson_ci": exact_wilson,
        "exact_bootstrap_ci": exact_boot,
        "tool_selection_pass": tool_k,
        "tool_selection_pct": tool_k / n,
        "tool_selection_wilson_ci": tool_wilson,
        "domains": dict(domain_results),
        "disfluencies": dict(disfluency_results)
    }
    (ROOT / "artifacts" / "statistical_analysis.json").write_text(json.dumps(stats_output, indent=2))
    print(f"\nSaved statistical summary to artifacts/statistical_analysis.json")


if __name__ == "__main__":
    main()
