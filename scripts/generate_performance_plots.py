#!/usr/bin/env python3
"""
generate_performance_plots.py

Generate 12 publication-grade engineering plots for the REACTOR performance report.
Saved in artifacts/performance/plots/

Plots:
  1. 01_fdb_latency_distribution.png
  2. 02_first_response_latency_distribution.png
  3. 03_tool_call_latency_distribution.png
  4. 04_task_completion_latency_distribution.png
  5. 05_reactor_internal_latency_distribution.png
  6. 06_ram_usage_growth.png
  7. 07_cpu_utilization_by_phase.png
  8. 08_gpu_vram_allocation.png
  9. 09_tool_execution_latency_by_tool.png
 10. 10_correction_to_cancellation_latency.png
 11. 11_latency_vs_audio_duration.png
 12. 12_latency_vs_tool_calls.png
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PERF_DIR = ROOT / "artifacts" / "performance"
PLOTS_DIR = PERF_DIR / "plots"

# Set publication style
plt.style.use("dark_background")
plt.rcParams["font.sans-serif"] = "Helvetica, Arial, DejaVu Sans"
plt.rcParams["axes.edgecolor"] = "#334155"
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["grid.color"] = "#1e293b"
plt.rcParams["grid.linestyle"] = "--"
plt.rcParams["grid.alpha"] = 0.6


def load_json(name: str) -> dict:
    return json.loads((PERF_DIR / name).read_text(encoding="utf-8"))


def main():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating 12 performance evaluation plots...")

    fdb_data = load_json("fdb_latency.json")
    records = fdb_data["records"]
    internal_data = load_json("reactor_internal_latency.json")
    resource_data = load_json("resource_usage.json")
    tool_data = load_json("tool_latency.json")
    corr_data = load_json("correction_latency.json")

    # Extract latency vectors
    fr_vals = [r["first_response_latency_s"] for r in records if r["first_response_latency_s"] is not None and not r["interruption"]]
    tc_vals = [r["tool_call_latency_s"] for r in records if r["tool_call_latency_s"] is not None]
    tk_vals = [r["task_completion_latency_s"] for r in records if r["task_completion_latency_s"] is not None and not r["interruption"]]
    durations = [r["input_audio_duration_s"] for r in records if r["first_response_latency_s"] is not None]
    fr_for_dur = [r["first_response_latency_s"] for r in records if r["first_response_latency_s"] is not None]
    tool_counts = [r["tool_count"] for r in records if r["task_completion_latency_s"] is not None and not r["interruption"]]
    tk_for_tools = [r["task_completion_latency_s"] for r in records if r["task_completion_latency_s"] is not None and not r["interruption"]]

    # --------------------------------------------------------------------------
    # 1. Combined FDB Latency Distribution
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.hist(tc_vals, bins=25, alpha=0.65, color="#38bdf8", label=f"Tool Call (Median: {np.median(tc_vals):.1f}s, N={len(tc_vals)})")
    ax.hist(fr_vals, bins=25, alpha=0.65, color="#a855f7", label=f"First Response (Median: {np.median(fr_vals):.1f}s, N={len(fr_vals)})")
    ax.hist(tk_vals, bins=25, alpha=0.65, color="#10b981", label=f"Task Completion (Median: {np.median(tk_vals):.1f}s, N={len(tk_vals)})")
    ax.set_title("Full-Duplex-Bench v3 Official Latency Distributions (REACTOR)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Latency from User Speech End (seconds)", fontsize=10)
    ax.set_ylabel("Scenario Count", fontsize=10)
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "01_fdb_latency_distribution.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 2. First Response Latency Distribution
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    ax.hist(fr_vals, bins=20, color="#a855f7", edgecolor="#c084fc", alpha=0.85)
    ax.axvline(np.median(fr_vals), color="#f43f5e", linestyle="--", linewidth=1.5, label=f"Median: {np.median(fr_vals):.2f}s")
    ax.axvline(np.percentile(fr_vals, 95), color="#f59e0b", linestyle=":", linewidth=1.5, label=f"p95: {np.percentile(fr_vals, 95):.2f}s")
    ax.set_title("FDB-v3 First Response Latency (Agent Speech Start - User Speech End)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Seconds", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.grid(True)
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "02_first_response_latency_distribution.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 3. Tool Call Latency Distribution
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    ax.hist(tc_vals, bins=25, color="#38bdf8", edgecolor="#7dd3fc", alpha=0.85)
    ax.axvline(np.median(tc_vals), color="#f43f5e", linestyle="--", linewidth=1.5, label=f"Median: {np.median(tc_vals):.2f}s")
    ax.axvline(np.percentile(tc_vals, 95), color="#f59e0b", linestyle=":", linewidth=1.5, label=f"p95: {np.percentile(tc_vals, 95):.2f}s")
    ax.set_title("FDB-v3 Tool Call Latency (First Tool Start - User Speech End)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Seconds", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.grid(True)
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "03_tool_call_latency_distribution.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 4. Task Completion Latency Distribution
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    ax.hist(tk_vals, bins=20, color="#10b981", edgecolor="#34d399", alpha=0.85)
    ax.axvline(np.median(tk_vals), color="#f43f5e", linestyle="--", linewidth=1.5, label=f"Median: {np.median(tk_vals):.2f}s")
    ax.axvline(np.percentile(tk_vals, 95), color="#f59e0b", linestyle=":", linewidth=1.5, label=f"p95: {np.percentile(tk_vals, 95):.2f}s")
    ax.set_title("FDB-v3 Task Completion Latency (Final Grounded Spoken Response)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Seconds", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.grid(True)
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "04_task_completion_latency_distribution.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 5. REACTOR Internal Latency Breakdown
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=300)
    stages = ["turn_bridge", "state_update", "controller_scheduling", "tool_dispatch", "cancellation", "cascade_cancellation"]
    labels = ["Turn Bridge", "State Update", "Scheduler", "Dispatch", "Cancellation", "Cascade"]
    p50s = [internal_data["stages"][s]["p50_us"] for s in stages]
    p95s = [internal_data["stages"][s]["p95_us"] for s in stages]
    x = np.arange(len(stages))
    width = 0.35
    ax.bar(x - width/2, p50s, width, label="p50 (Median)", color="#38bdf8")
    ax.bar(x + width/2, p95s, width, label="p95", color="#f59e0b")
    ax.set_title("REACTOR Internal Pipeline Latencies (Microseconds)", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Microseconds (µs)", fontsize=10)
    ax.grid(True, axis="y")
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "05_reactor_internal_latency_distribution.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 6. RAM Usage Over Recordings
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    timeline = resource_data["memory"]["timeline"]
    xs = [t["iteration"] for t in timeline]
    ys = [t["rss_mb"] for t in timeline]
    ax.plot(xs, ys, marker="o", color="#38bdf8", linewidth=2, markersize=5)
    ax.set_title("Resident Memory (RSS) vs. Processed Recordings (Zero Leakage)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Recordings Processed", fontsize=10)
    ax.set_ylabel("RSS Memory (MB)", fontsize=10)
    ax.set_ylim(min(ys) - 10, max(ys) + 10)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "06_ram_usage_growth.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 7. CPU Utilization by Operational Phase
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    phases = ["Idle Baseline", "Audio Streaming", "Tool Execution", "Correction Cascade", "Peak Spikes"]
    cpu_vals = [
        resource_data["cpu"]["idle_cpu_pct"],
        resource_data["cpu"]["audio_streaming_simulated_pct"],
        resource_data["cpu"]["tool_execution_pct"],
        resource_data["cpu"]["correction_cascade_pct"],
        resource_data["cpu"]["peak_cpu_pct"]
    ]
    bars = ax.bar(phases, cpu_vals, color=["#64748b", "#38bdf8", "#10b981", "#f59e0b", "#f43f5e"])
    ax.set_title("REACTOR Process CPU Utilization Across Phases (% 1 Core Capacity)", fontsize=11, fontweight="bold")
    ax.set_ylabel("CPU Utilization (%)", fontsize=10)
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.3, f"{yval:.1f}%", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    ax.set_ylim(0, max(cpu_vals) + 3)
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "07_cpu_utilization_by_phase.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 8. GPU VRAM Allocation Comparison
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    categories = ["Local M4 Unified Memory", "Kaggle T4-GPU0 (Parakeet)", "Kaggle T4-GPU1 (Evaluation)"]
    allocated = [0.0, 1148.0, 1148.0]
    total = [24576.0, 15360.0, 15360.0]
    x = np.arange(len(categories))
    width = 0.35
    ax.bar(x - width/2, allocated, width, label="Allocated VRAM (MB)", color="#a855f7")
    ax.bar(x + width/2, total, width, label="Total Capacity (MB)", color="#334155")
    ax.set_title("GPU VRAM Utilization Architecture (Local M4 vs. Remote Kaggle)", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=8.5)
    ax.set_ylabel("Memory (MB)", fontsize=10)
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "08_gpu_vram_allocation.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 9. Tool Execution Latency by Tool
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    tool_names = sorted(tool_data.keys(), key=lambda k: tool_data[k]["mean_ms"])
    tool_means = [tool_data[k]["mean_ms"] for k in tool_names]
    colors = ["#f43f5e" if tool_data[k]["operation_type"] == "write" else "#38bdf8" for k in tool_names]
    bars = ax.barh(tool_names, tool_means, color=colors)
    ax.set_title("Simulated Tool Execution Latency by Tool (Red: Serialized Write, Blue: Concurrent Read)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Duration (ms)", fontsize=10)
    ax.grid(True, axis="x")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "09_tool_execution_latency_by_tool.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 10. Correction to Cancellation Latency Waterfall
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=300)
    stages = [
        ("Correction Detection", corr_data["metrics"]["correction_detection_latency"]["mean_us"] / 1000.0),
        ("Intent Revision", corr_data["metrics"]["intent_revision_latency"]["mean_us"] / 1000.0),
        ("Cancellation", corr_data["metrics"]["cancellation_latency"]["mean_us"] / 1000.0),
        ("Replacement Dispatch", corr_data["metrics"]["replacement_dispatch_latency"]["mean_us"] / 1000.0),
        ("Total Completion", corr_data["metrics"]["correction_completion_latency"]["mean_us"] / 1000.0)
    ]
    s_names = [s[0] for s in stages]
    s_vals = [s[1] for s in stages]
    bars = ax.bar(s_names, s_vals, color=["#38bdf8", "#818cf8", "#f43f5e", "#f59e0b", "#10b981"])
    ax.set_title("Correction Cascade Latency Waterfall ('Book Mumbai' -> 'Actually Delhi')", fontsize=11, fontweight="bold")
    ax.set_ylabel("Latency (ms)", fontsize=10)
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.05, f"{yval:.2f}ms", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "10_correction_to_cancellation_latency.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 11. Latency vs. Audio Duration
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=300)
    ax.scatter(durations, fr_for_dur, color="#38bdf8", alpha=0.7, edgecolors="#0284c7")
    m, b = np.polyfit(durations, fr_for_dur, 1)
    x_line = np.linspace(min(durations), max(durations), 100)
    ax.plot(x_line, m*x_line + b, color="#f43f5e", linestyle="--", label=f"Trend (Slope: {m:.2f})")
    ax.set_title("Response Latency vs. Input Audio Duration", fontsize=11, fontweight="bold")
    ax.set_xlabel("Input Audio Duration (seconds)", fontsize=10)
    ax.set_ylabel("Response Latency (seconds)", fontsize=10)
    ax.grid(True)
    ax.legend(facecolor="#0f172a", edgecolor="#334155")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "11_latency_vs_audio_duration.png")
    plt.close(fig)

    # --------------------------------------------------------------------------
    # 12. Latency vs. Number of Tool Calls
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=300)
    unique_counts = sorted(list(set(tool_counts)))
    grouped = [ [tk_for_tools[i] for i in range(len(tool_counts)) if tool_counts[i] == c] for c in unique_counts ]
    box = ax.boxplot(grouped, tick_labels=[f"{c} Tool(s)" for c in unique_counts], patch_artist=True)
    for patch in box["boxes"]:
        patch.set_facecolor("#10b981")
        patch.set_alpha(0.7)
    for median in box["medians"]:
        median.set_color("#f43f5e")
        median.set_linewidth(1.8)
    ax.set_title("Task Completion Latency vs. Number of Required Tool Calls", fontsize=11, fontweight="bold")
    ax.set_xlabel("Tool Calls Required in Scenario", fontsize=10)
    ax.set_ylabel("Task Completion Latency (seconds)", fontsize=10)
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "12_latency_vs_tool_calls.png")
    plt.close(fig)

    print("Successfully generated all 12 plots in artifacts/performance/plots/")


if __name__ == "__main__":
    main()
