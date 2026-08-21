"""
generate_charts_tier4.py -- charts for Tier4 replication results (temporal + cross-model)
================================================================================
Reads netimpact_master.csv (original three-day, qwen3:8b), tier4_replicate2_master.csv
(temporal full replication, same model, different time) and tier4_llama_master.csv
(cross-model replication, main-effect only, llama3.1:8b). Draws 4 charts:
loss-cliff temporal comparison, overall-metric temporal comparison, cross-model
ground-truth-passed-by-task comparison, cross-model loss-cliff comparison.
Saved as .png in charts/tier4/.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 generate_charts_tier4.py --orig ../data/netimpact_master.csv \
        --replicate2 ../data/tier4_replicate2_master.csv \
        --llama ../data/tier4_llama_master.csv --out-dir ../charts/tier4
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.size"] = 10
plt.rcParams["figure.dpi"] = 110


def _savefig(fig, out_dir, filename):
    path = os.path.join(out_dir, filename)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> saved: {path}")


def chart_temporal_loss_cliff(orig, rep2, out_dir):
    """Success rate by loss_pct: original three-day run vs temporal replicate (same model)."""
    o = orig[(orig["phase"] == "three_day_main_effect") & (orig["main_effect_axis"] == "loss")]
    r = rep2[(rep2["phase"] == "three_day_main_effect") & (rep2["main_effect_axis"] == "loss")]

    levels = sorted(o["loss_pct"].unique())
    o_rates = [o[o["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]
    r_rates = [r[r["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]

    x = np.arange(len(levels))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - width / 2, o_rates, width, label="Original run", color="tab:blue")
    ax.bar(x + width / 2, r_rates, width, label="Temporal replicate", color="tab:orange")
    ax.set_xticks(x)
    ax.set_xticklabels([str(lv) for lv in levels])
    ax.set_xlabel("Packet loss (%)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Temporal replication: loss cliff, qwen3:8b (n=20/level each run)", pad=12)
    ax.legend()
    _savefig(fig, out_dir, "tier4_temporal_loss_cliff.png")


def chart_temporal_summary(orig, rep2, out_dir):
    """Overall success rate + mean heuristic rubric score: original vs replicate2."""
    metrics = ["Overall success rate (%)", "Mean heuristic rubric score (x20, for scale)"]
    o_vals = [orig["success"].mean() * 100, orig["ground_truth_score"].mean() * 20]
    r_vals = [rep2["success"].mean() * 100, rep2["ground_truth_score"].mean() * 20]

    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, o_vals, width, label="Original (n=1,544)", color="tab:blue")
    ax.bar(x + width / 2, r_vals, width, label="Temporal replicate (n=1,544)", color="tab:orange")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 110)
    ax.set_title("Temporal replication: overall metrics, qwen3:8b", pad=12)
    for i, (ov, rv) in enumerate(zip(o_vals, r_vals)):
        ax.text(i - width / 2, ov + 2, f"{ov:.1f}", ha="center", fontsize=9)
        ax.text(i + width / 2, rv + 2, f"{rv:.1f}", ha="center", fontsize=9)
    ax.legend()
    _savefig(fig, out_dir, "tier4_temporal_summary.png")


def chart_crossmodel_groundtruth_by_task(qwen, llama, out_dir):
    """Heuristic rubric pass rate by task: qwen3:8b vs llama3.1:8b (main-effect data, n=210/task each)."""
    tasks = ["coding_task", "data_analysis", "planning_decision", "research_summary"]
    q_rates = [qwen[qwen["task_name"] == t]["ground_truth_passed"].mean() * 100 for t in tasks]
    l_rates = [llama[llama["task_name"] == t]["ground_truth_passed"].mean() * 100 for t in tasks]

    x = np.arange(len(tasks))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - width / 2, q_rates, width, label="qwen3:8b (n=210/task)", color="tab:blue")
    ax.bar(x + width / 2, l_rates, width, label="llama3.1:8b (n=210/task)", color="tab:red")
    ax.set_xticks(x)
    ax.set_xticklabels(tasks, rotation=15)
    ax.set_ylabel("Heuristic rubric pass rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Cross-model replication: heuristic rubric pass rate collapses on 2/4 tasks for llama3.1:8b\n"
                 "(task completion / rounds / answer length are similar -- heuristic rubric itself doesn't transfer)",
                 pad=12, fontsize=9.5)
    for i, (qv, lv) in enumerate(zip(q_rates, l_rates)):
        ax.text(i - width / 2, qv + 2, f"{qv:.0f}%", ha="center", fontsize=9)
        ax.text(i + width / 2, lv + 2, f"{lv:.0f}%", ha="center", fontsize=9)
    ax.legend()
    _savefig(fig, out_dir, "tier4_crossmodel_groundtruth_by_task.png")


def chart_crossmodel_loss_cliff(qwen, llama, out_dir):
    """Success (task completion) by loss_pct: qwen3:8b vs llama3.1:8b main-effect."""
    q = qwen[qwen["main_effect_axis"] == "loss"]
    l = llama[llama["main_effect_axis"] == "loss"]

    levels = sorted(q["loss_pct"].unique())
    q_rates = [q[q["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]
    l_rates = [l[l["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]

    x = np.arange(len(levels))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - width / 2, q_rates, width, label="qwen3:8b (n=20/level)", color="tab:blue")
    ax.bar(x + width / 2, l_rates, width, label="llama3.1:8b (n=20/level)", color="tab:red")
    ax.set_xticks(x)
    ax.set_xticklabels([str(lv) for lv in levels])
    ax.set_xlabel("Packet loss (%)")
    ax.set_ylabel("Task-completion success rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Cross-model: loss cliff shape holds for both models (Fisher exact p=0.34 at 75% loss, n too small to confirm difference)",
                 pad=12, fontsize=9.5)
    ax.legend()
    _savefig(fig, out_dir, "tier4_crossmodel_loss_cliff.png")


def print_summary(orig, rep2, qwen, llama):
    print("\n=== Tier4 key numbers ===")
    print("-- Temporal replication (qwen3:8b, same 3-day design, n=1,544 each) --")
    print(f"overall success: original={orig['success'].mean()*100:.2f}% vs replicate2={rep2['success'].mean()*100:.2f}%")
    print(f"overall ground_truth mean: original={orig['ground_truth_score'].mean():.3f} vs replicate2={rep2['ground_truth_score'].mean():.3f}")
    o75 = orig[(orig['phase']=='three_day_main_effect') & (orig['main_effect_axis']=='loss') & (orig['loss_pct']==75)]['success']
    r75 = rep2[(rep2['phase']=='three_day_main_effect') & (rep2['main_effect_axis']=='loss') & (rep2['loss_pct']==75)]['success']
    print(f"loss=75% success: original={o75.mean()*100:.1f}% (n={len(o75)}) vs replicate2={r75.mean()*100:.1f}% (n={len(r75)})")

    print("\n-- Cross-model replication (main-effect only, n=840 each) --")
    print(f"overall success: qwen={qwen['success'].mean()*100:.2f}% vs llama={llama['success'].mean()*100:.2f}%")
    print(f"overall ground_truth mean: qwen={qwen['ground_truth_score'].mean():.3f} vs llama={llama['ground_truth_score'].mean():.3f}")
    print(f"overall elapsed_seconds mean: qwen={qwen['elapsed_seconds'].mean():.1f}s vs llama={llama['elapsed_seconds'].mean():.1f}s")
    for t in ["coding_task", "data_analysis", "planning_decision", "research_summary"]:
        qp = qwen[qwen["task_name"] == t]["ground_truth_passed"].mean() * 100
        lp = llama[llama["task_name"] == t]["ground_truth_passed"].mean() * 100
        print(f"  {t}: qwen pass={qp:.1f}% vs llama pass={lp:.1f}%")


def main(orig_path, rep2_path, llama_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    orig = pd.read_csv(orig_path)
    rep2 = pd.read_csv(rep2_path)
    llama = pd.read_csv(llama_path)
    qwen = orig[orig["phase"] == "three_day_main_effect"]

    print(f"Loaded original n={len(orig)}, replicate2 n={len(rep2)}, llama n={len(llama)}")
    print("\nDrawing Tier4 charts...")
    chart_temporal_loss_cliff(orig, rep2, out_dir)
    chart_temporal_summary(orig, rep2, out_dir)
    chart_crossmodel_groundtruth_by_task(qwen, llama, out_dir)
    chart_crossmodel_loss_cliff(qwen, llama, out_dir)

    print_summary(orig, rep2, qwen, llama)
    print(f"\nAll Tier4 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--orig", default="../data/netimpact_master.csv")
    parser.add_argument("--replicate2", default="../data/tier4_replicate2_master.csv")
    parser.add_argument("--llama", default="../data/tier4_llama_master.csv")
    parser.add_argument("--out-dir", default="../charts/tier4")
    args = parser.parse_args()
    main(args.orig, args.replicate2, args.llama, args.out_dir)
