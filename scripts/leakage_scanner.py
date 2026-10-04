"""Adversarial static leakage audit scanner across the REACTOR codebase."""

import json
import glob
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1. Load benchmark scenarios
benchmark_path = ROOT / "vendor" / "Full-Duplex-Bench" / "v3" / "benchmark_data_v2.json"
benchmark_v2 = json.loads(benchmark_path.read_text()) if benchmark_path.exists() else {"scenarios": []}
metadata_files = list((ROOT / "fdb_v3_data_released").glob("*/metadata.json"))

scenario_ids = set()
expected_values = {}  # value -> list of (scenario, func, key)
expected_tools = set()

for s in benchmark_v2.get("scenarios", []):
    scenario_ids.add(s["id"])
    for call in s.get("expected_tool_calls", []):
        func = call.get("function")
        if func:
            expected_tools.add(func)
        for k, v in call.get("args", {}).items():
            if isinstance(v, str) and len(v.strip()) >= 3:
                expected_values.setdefault(v.strip(), []).append((s["id"], func, k))

for mf in metadata_files:
    m = json.loads(mf.read_text())
    scenario_ids.add(m["id"])
    for call in m.get("expected_tool_calls", []):
        func = call.get("function")
        if func:
            expected_tools.add(func)
        for k, v in call.get("args", {}).items():
            if isinstance(v, str) and len(v.strip()) >= 3:
                expected_values.setdefault(v.strip(), []).append((m["id"], func, k))

print(f"Loaded {len(scenario_ids)} scenario IDs, {len(expected_tools)} tool names, {len(expected_values)} argument values.")

# Directories to scan
scan_dirs = ["src", "scripts", "tests", "docs", "frontend/src"]
extensions = (".py", ".ts", ".tsx", ".js", ".json", ".md", ".sh")

candidates = []

for sdir in scan_dirs:
    dir_path = ROOT / sdir
    if not dir_path.exists():
        continue
    for root, dirs, files in os.walk(dir_path):
        if any(ignored in root for ignored in ("node_modules", ".next", "__pycache__", ".git")):
            continue
        for file in files:
            if not file.endswith(extensions):
                continue
            path = Path(root) / file
            rel_path = str(path.relative_to(ROOT))
            try:
                lines = path.read_text(errors="ignore").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines, 1):
                # 1. Scenario ID match
                for sc_id in scenario_ids:
                    if re.search(r"\b" + re.escape(sc_id) + r"\b", line):
                        if rel_path.startswith("src/reactor/"):
                            cls = "confirmed leakage" if ("if" in line or "==" in line) else "suspicious"
                        elif rel_path.startswith("tests/"):
                            cls = "legitimate test fixture"
                        elif rel_path.startswith("scripts/"):
                            cls = "legitimate benchmark interface"
                        elif rel_path.startswith("frontend/"):
                            cls = "benchmark metadata"
                        elif rel_path.startswith("docs/"):
                            cls = "benchmark metadata"
                        else:
                            cls = "generic information"
                        candidates.append({
                            "file": rel_path,
                            "line": idx,
                            "matched_benchmark_value": sc_id,
                            "category": "scenario_id",
                            "classification": cls,
                            "snippet": line.strip()[:120]
                        })

                # 2. Check for literal string matches of benchmark expected argument values in src/reactor
                if rel_path.startswith("src/reactor/"):
                    for val, meta in expected_values.items():
                        if val.lower() in {
                            "all", "car", "day", "one", "two", "yes", "true", "none", "null",
                            "auto", "home", "visa", "rent", "city", "date", "name", "card",
                            "fast", "type", "mode", "view", "user", "call", "test", "item"
                        }:
                            continue
                        # Look for string literal in quotes
                        pattern = r"['\"][^'\"]*" + re.escape(val) + r"[^'\"]*['\"]"
                        if re.search(pattern, line, re.I):
                            # Distinguish generic instructions from specific values
                            is_in_guidance = "FIELD_GUIDANCE" in line or "CONTRACTS" in line or rel_path.endswith("benchmark.py")
                            cls = "legitimate benchmark interface" if is_in_guidance else "suspicious"
                            candidates.append({
                                "file": rel_path,
                                "line": idx,
                                "matched_benchmark_value": val,
                                "category": f"expected_arg_value ({meta[0][0]}: {meta[0][1]}.{meta[0][2]})",
                                "classification": cls,
                                "snippet": line.strip()[:120]
                            })

out_file = ROOT / "leakage_candidates.json"
out_file.write_text(json.dumps(candidates, indent=2) + "\n")
print(f"Wrote {len(candidates)} candidates to {out_file}")

src_matches = [c for c in candidates if c["file"].startswith("src/reactor/")]
print(f"\nTotal matches inside src/reactor/: {len(src_matches)}")
for m in src_matches:
    print(f"[{m['classification'].upper()}] {m['file']}:{m['line']} -> '{m['matched_benchmark_value']}' ({m['category']})\n  Line: {m['snippet']}")
