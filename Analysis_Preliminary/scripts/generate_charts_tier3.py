"""
generate_charts_tier3.py -- charts for Tier3 dual-judge LLM evaluation results
================================================================================
Reads tier3_dual_judge_report.csv + tier3_dual_judge_report_summary.json
(produced by Tier3_โครงสร้างพื้นฐาน/run_dual_judge_sample.py) and draws 3 charts:
score distribution per rater (heuristic / judge_a / judge_b), a pass/fail
confusion matrix between the two judges, and a heuristic-vs-judge_b scatter
showing the leniency gap on heuristic-fail trials. Saved as .png in charts/tier3/.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 generate_charts_tier3.py --csv ../data/tier3_dual_judge_report.csv --summary-json ../data/tier3_dual_judge_report_summary.json --out-dir ../charts/tier3
"""
import argparse
import json
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


def chart_score_distribution(df, summary, out_dir):
    """Score distribution (1-5) for heuristic vs judge_a (qwen3:8b) vs judge_b (llama3.1:8b)."""
    levels = [1, 2, 3, 4, 5]
    heuristic_counts = df["heuristic_score"].value_counts().reindex(levels, fill_value=0)
    a_counts = df["judge_a_score"].value_counts().reindex(levels, fill_value=0)
    b_counts = df["judge_b_score"].value_counts().reindex(levels, fill_value=0)

    x = np.arange(len(levels))
    width = 0.27

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(x - width, heuristic_counts.values, width, label="Heuristic", color="tab:green")
    ax.bar(x, a_counts.values, width, label=f"Judge A ({summary['judge_a_model']})", color="tab:blue")
    ax.bar(x + width, b_counts.values, width, label=f"Judge B ({summary['judge_b_model']})", color="tab:red")
    ax.set_xticks(x)
    ax.set_xticklabels([str(l) for l in levels])
    ax.set_xlabel("Score (1-5)")
    ax.set_ylabel("Number of trials")
    n_a_null = df["judge_a_score"].isna().sum()
    ax.set_title(f"Score distribution: Heuristic vs two LLM judges (n={len(df)} sampled trials, "
                 f"Judge A failed to score {n_a_null} trials)", pad=12)
    ax.legend()
    _savefig(fig, out_dir, "tier3_score_distribution.png")


def chart_pass_fail_confusion(df, summary, out_dir):
    """Confusion matrix: judge_a_passed x judge_b_passed (only rows where both are non-null)."""
    sub = df.dropna(subset=["judge_a_passed", "judge_b_passed"]).copy()
    sub["judge_a_passed"] = sub["judge_a_passed"].astype(bool)
    sub["judge_b_passed"] = sub["judge_b_passed"].astype(bool)

    pivot = pd.crosstab(sub["judge_a_passed"], sub["judge_b_passed"])
    pivot = pivot.reindex(index=[True, False], columns=[True, False], fill_value=0)

    fig, ax = plt.subplots(figsize=(5.5, 5))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Passed", "Failed"])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Passed", "Failed"])
    ax.set_xlabel(f"Judge B ({summary['judge_b_model']})")
    ax.set_ylabel(f"Judge A ({summary['judge_a_model']})")
    kappa = summary.get("cohens_kappa_pass_fail")
    ax.set_title(f"Pass/Fail agreement (n={len(sub)}, Cohen's kappa={kappa})", pad=12)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(pivot.values[i, j]), ha="center", va="center", fontsize=16,
                    color="black")
    fig.colorbar(im, ax=ax, label="Count")
    _savefig(fig, out_dir, "tier3_pass_fail_confusion.png")


def chart_leniency_gap(df, summary, out_dir):
    """Highlight: on trials the heuristic evaluator flagged as FAILING, what did each judge say?"""
    bad = df[df["heuristic_score"] < 4].copy()
    if bad.empty:
        print("  [skip] no heuristic-fail trials found")
        return

    labels = [f"Judge A\n({summary['judge_a_model']})", f"Judge B\n({summary['judge_b_model']})"]
    pass_rate = [
        bad["judge_a_passed"].mean(skipna=True) * 100,
        bad["judge_b_passed"].mean(skipna=True) * 100,
    ]
    ns = [bad["judge_a_passed"].notna().sum(), bad["judge_b_passed"].notna().sum()]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, pass_rate, color=["tab:blue", "tab:red"])
    ax.set_ylabel("Share rated 'passed' (%)")
    ax.set_ylim(0, 115)
    ax.set_title(f"Leniency check: judge verdict on the {len(bad)} trials heuristic flagged as FAILING", pad=12)
    for bar, val, n in zip(bars, pass_rate, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 3, f"{val:.0f}% (n={n})",
                ha="center", fontsize=10)
    ax.axhline(0, color="gray", linewidth=0.8)
    _savefig(fig, out_dir, "tier3_leniency_gap.png")


def print_summary(df, summary):
    print("\n=== Tier3 dual-judge key numbers ===")
    print(f"n_samples: {summary['n_samples']}")
    print(f"judge_a ({summary['judge_a_model']}) null/failed calls: {df['judge_a_score'].isna().sum()}")
    print(f"judge_b ({summary['judge_b_model']}) null/failed calls: {df['judge_b_score'].isna().sum()}")
    print(f"judge_a pass rate: {df['judge_a_passed'].mean(skipna=True)*100:.1f}%")
    print(f"judge_b pass rate: {df['judge_b_passed'].mean(skipna=True)*100:.1f}%")
    print(f"heuristic pass rate: {df['heuristic_passed'].mean()*100:.1f}%")
    print(f"cohens_kappa_pass_fail: {summary['cohens_kappa_pass_fail']}")
    print(f"quadratic_weighted_kappa_score: {summary['quadratic_weighted_kappa_score']}")
    print(f"pearson_r_score: {summary['pearson_r_score']}")
    print(f"exact_score_agreement_rate: {summary['exact_score_agreement_rate']}")

    bad = df[df["heuristic_score"] < 4]
    print(f"\nheuristic-flagged-fail trials: {len(bad)}")
    print(f"  judge_a passed rate on these: {bad['judge_a_passed'].mean(skipna=True)*100:.1f}%")
    print(f"  judge_b passed rate on these: {bad['judge_b_passed'].mean(skipna=True)*100:.1f}%")


def main(csv_path, summary_json_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.read_csv(csv_path)
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    print(f"Loaded {len(df)} dual-judge trials from {csv_path}")

    print("\nDrawing Tier3 charts...")
    chart_score_distribution(df, summary, out_dir)
    chart_pass_fail_confusion(df, summary, out_dir)
    chart_leniency_gap(df, summary, out_dir)

    print_summary(df, summary)
    print(f"\nAll Tier3 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="../data/tier3_dual_judge_report.csv")
    parser.add_argument("--summary-json", default="../data/tier3_dual_judge_report_summary.json")
    parser.add_argument("--out-dir", default="../charts/tier3")
    args = parser.parse_args()
    main(args.csv, args.summary_json, args.out_dir)
