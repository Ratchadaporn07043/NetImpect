"""
generate_charts_tier2.py -- charts for Tier2 results (bandwidth axis + multi-round strict-reviewer)
================================================================================
Reads tier2_bandwidth_master.csv and tier2_multiround_master.csv (produced by
parse_logs.py) and draws 4 charts: bandwidth main-effect, bandwidth x loss
interaction, multiround success-by-scenario, and multiround rounds
distribution. Saved as .png files in charts/tier2/.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 parse_logs.py --log-dir "../../Tier2_แกนใหม่/logs_tier2_bandwidth" --out ../data/tier2_bandwidth_master.csv
    python3 parse_logs.py --log-dir "../../Tier2_แกนใหม่/logs_tier2_multiround" --out ../data/tier2_multiround_master.csv
    python3 generate_charts_tier2.py --bandwidth-csv ../data/tier2_bandwidth_master.csv --multiround-csv ../data/tier2_multiround_master.csv --out-dir ../charts/tier2
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


def chart_bandwidth_main_effect(df, out_dir):
    """Bandwidth main-effect: success rate is flat 100%, so show elapsed time + GT score instead."""
    sub = df[df["scenario_type"] == "main_effect"].copy()
    if sub.empty:
        print("  [skip] no bandwidth main_effect data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)
    g = sub.groupby("bandwidth_kbit").agg(
        success=("success_num", "mean"),
        elapsed=("elapsed_seconds", "mean"),
        gt=("ground_truth_score", "mean"),
        n=("success_num", "size"),
    ).sort_index(ascending=False)

    fig, ax1 = plt.subplots(figsize=(9, 5.5))
    ax1.plot(range(len(g)), g["elapsed"], marker="o", color="tab:brown", linewidth=2,
              label="Mean elapsed seconds/trial")
    ax1.set_xticks(range(len(g)))
    ax1.set_xticklabels([str(x) for x in g.index])
    ax1.set_xlabel("Bandwidth (kbit/s)")
    ax1.set_ylabel("Mean elapsed seconds per trial", color="tab:brown")
    ax1.tick_params(axis="y", labelcolor="tab:brown")

    ax2 = ax1.twinx()
    ax2.plot(range(len(g)), g["gt"], marker="s", color="tab:red", linewidth=2,
              label="Mean heuristic rubric score (1-5)")
    ax2.set_ylabel("Mean heuristic rubric score (1-5)", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax2.set_ylim(0, 5.5)

    n_total = int(g["n"].sum())
    ax1.set_title(f"Bandwidth main effect (Tier2, n={n_total} trials) -- success rate flat at 100% across all levels", pad=12)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    fig.legend(lines1 + lines2, labels1 + labels2, loc="upper center",
               bbox_to_anchor=(0.5, 0.02), ncol=2, frameon=False, fontsize=8)
    fig.subplots_adjust(bottom=0.22)
    _savefig(fig, out_dir, "tier2_bandwidth_main_effect.png")


def chart_bandwidth_x_loss(df, out_dir):
    """Bandwidth x loss interaction -- success rate heatmap (all cells should still be ~100%)."""
    sub = df[df["phase"] == "tier2_bandwidth_x_loss"].copy()
    if sub.empty:
        print("  [skip] no bandwidth x_loss data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)

    pivot = sub.pivot_table(index="bandwidth_kbit", columns="loss_pct", values="success_num", aggfunc="mean")
    pivot = pivot.sort_index(ascending=False)

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Packet loss (%)")
    ax.set_ylabel("Bandwidth (kbit/s)")
    ax.set_title(f"Bandwidth x Loss interaction: success rate (Tier2, n={len(sub)} trials)", pad=12)
    fig.colorbar(im, ax=ax, label="Success rate")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color="black" if 0.3 < val < 0.8 else "white", fontsize=9)

    _savefig(fig, out_dir, "tier2_bandwidth_x_loss.png")


def chart_multiround_success_by_scenario(df, out_dir):
    """Multiround success rate per scenario -- this is where the network effect finally shows up."""
    d = df.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    order = ["t2mr_baseline", "t2mr_moderate_delay", "t2mr_high_loss", "t2mr_combined_bad"]
    order = [s for s in order if s in d["scenario_name"].unique()]
    g = d.groupby("scenario_name")["success_num"].agg(["mean", "count"]).reindex(order)

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    bars = ax.barh(g.index, g["mean"] * 100, color="tab:red")
    ax.set_xlabel("Success rate (%)")
    ax.set_title(f"Multi-round + strict-reviewer: success rate by scenario (Tier2, n={int(g['count'].sum())} trials)")
    ax.set_xlim(0, 120)
    for bar, (mean_val, count_val) in zip(bars, zip(g["mean"], g["count"])):
        ax.text(mean_val * 100 + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{mean_val*100:.1f}% (n={int(count_val)})", va="center", fontsize=9)
    _savefig(fig, out_dir, "tier2_multiround_success_by_scenario.png")


def chart_multiround_rounds_distribution(df, out_dir):
    """Rounds distribution -- bimodal (3 = approved first pass, 6 = hit max rounds after a REVISE cycle)."""
    d = df.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    g = d.groupby("rounds")["success_num"].agg(["mean", "count"]).sort_index()

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    x = np.arange(len(g))
    bars = ax.bar(x, g["count"], color=["tab:green" if m == 1.0 else "tab:orange" for m in g["mean"]])
    ax.set_xticks(x)
    ax.set_xticklabels([str(int(r)) for r in g.index])
    ax.set_xlabel("Number of rounds")
    ax.set_ylabel("Number of trials")
    ax.set_title(f"Rounds distribution -- Tier2 multi-round hard tasks (n={len(d)})", pad=12)
    for xi, (mean_val, count_val) in zip(x, zip(g["mean"], g["count"])):
        ax.text(xi, count_val + 0.8, f"{mean_val*100:.0f}% success", ha="center", fontsize=9)
    _savefig(fig, out_dir, "tier2_multiround_rounds_distribution.png")


def print_summary(df_bw, df_mr):
    print("\n=== Tier2 key numbers ===")
    dbw = df_bw.copy()
    dbw["success_num"] = dbw["success"].astype(bool).astype(int)
    print(f"Bandwidth: n={len(dbw)}, overall success={dbw['success_num'].mean()*100:.2f}%")

    dmr = df_mr.copy()
    dmr["success_num"] = dmr["success"].astype(bool).astype(int)
    print(f"Multiround: n={len(dmr)}, overall success={dmr['success_num'].mean()*100:.2f}%")
    print(f"  mean rounds: {dmr['rounds'].mean():.2f}, rounds<=3 share: {(dmr['rounds']<=3).mean()*100:.1f}%")
    for s in ["t2mr_baseline", "t2mr_moderate_delay", "t2mr_high_loss", "t2mr_combined_bad"]:
        sub = dmr[dmr["scenario_name"] == s]
        if len(sub):
            print(f"  {s}: n={len(sub)}, success={sub['success_num'].mean()*100:.1f}%, "
                  f"mean rejections={sub['reviewer_rejections'].mean():.2f}")


def main(bandwidth_csv, multiround_csv, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df_bw = pd.read_csv(bandwidth_csv)
    df_bw["success"] = df_bw["success"].astype(bool)
    df_mr = pd.read_csv(multiround_csv)
    df_mr["success"] = df_mr["success"].astype(bool)
    print(f"Loaded {len(df_bw)} bandwidth trials from {bandwidth_csv}")
    print(f"Loaded {len(df_mr)} multiround trials from {multiround_csv}")

    print("\nDrawing Tier2 charts...")
    chart_bandwidth_main_effect(df_bw, out_dir)
    chart_bandwidth_x_loss(df_bw, out_dir)
    chart_multiround_success_by_scenario(df_mr, out_dir)
    chart_multiround_rounds_distribution(df_mr, out_dir)

    print_summary(df_bw, df_mr)
    print(f"\nAll Tier2 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bandwidth-csv", default="../data/tier2_bandwidth_master.csv")
    parser.add_argument("--multiround-csv", default="../data/tier2_multiround_master.csv")
    parser.add_argument("--out-dir", default="../charts/tier2")
    args = parser.parse_args()
    main(args.bandwidth_csv, args.multiround_csv, args.out_dir)
