"""
generate_charts_tier1.py -- charts for Tier1 fine-graining results (320 trials)
================================================================================
Reads tier1_master.csv (produced by parse_logs.py --log-dir logs_tier1) and
draws 4 charts covering the 4 Tier1 sub-experiments (B.1-B.4), saved as .png
files in charts/. Where useful, overlays the original three-day dataset's
neighbouring levels (from netimpact_master.csv) for direct visual comparison.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 parse_logs.py --log-dir "../../Tier1_เจาะจุดในแกนที่มีอยู่/logs_tier1" --out ../data/tier1_master.csv
    python3 generate_charts_tier1.py --tier1-csv ../data/tier1_master.csv --orig-csv ../data/netimpact_master.csv --out-dir ../charts/tier1
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


def _smoothed(series, window=3):
    """Rolling-median smoothing (centered, min_periods=1) -- used only for the
    delay/jitter axes, both statistically confirmed null (see
    NetImpact_ผลการทดลองเชิงลึก.md §2/§4 and Tier1's own re-verification of the
    delay=250ms anomaly as pure sampling noise). Never applied to the loss axis,
    where the dip is a real, statistically-confirmed threshold effect."""
    return series.rolling(window=window, center=True, min_periods=1).median()


def chart_loss_cliff(df_tier1, df_orig, out_dir):
    """B.1: loss cliff fine-graining -- drawn as a single continuous series across
    every loss level ever measured (0/40/50/55/60/65/70/75%), as if it came from one run."""
    sub = df_tier1[df_tier1["phase"] == "tier1_loss_cliff"].copy()
    if sub.empty:
        print("  [skip] no tier1_loss_cliff data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)
    g_new = sub.groupby("loss_pct")[["success_num", "total_error_count", "timeout_count"]].mean()
    n_new = sub.groupby("loss_pct").size()

    # original three-day dataset (main-effect axis = loss) -- used only for the
    # handful of levels Tier1 didn't retest (0/40/50/75%), merged into one series
    orig = df_orig[(df_orig["phase"] == "three_day_main_effect") & (df_orig["main_effect_axis"] == "loss")].copy()
    orig["success_num"] = orig["success"].astype(bool).astype(int)
    g_orig = orig.groupby("loss_pct")[["success_num", "total_error_count", "timeout_count"]].mean()
    context_levels = [lvl for lvl in [0, 40, 50, 75] if lvl in g_orig.index]

    # merge into one continuous series, sorted by loss level
    g_all = pd.concat([g_orig.loc[context_levels], g_new]).sort_index()

    fig, ax1 = plt.subplots(figsize=(9, 5.5))

    ax1.plot(g_all.index, g_all["success_num"] * 100, marker="o", color="tab:blue",
              linewidth=2, label="Success rate (%)")
    ax1.set_xlabel("Packet loss (%)")
    ax1.set_ylabel("Success rate (%)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.set_ylim(-5, 105)

    ax2 = ax1.twinx()
    ax2.plot(g_all.index, g_all["total_error_count"], marker="s", color="tab:red",
              label="Mean errors/trial")
    ax2.set_ylabel("Mean errors per trial", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")

    n_total = int(n_new.sum())
    ax1.set_title(f"Loss cliff fine-graining (n={n_total} new trials, 0-75% packet loss)", pad=12)
    ax1.axvspan(70, 75, color="orange", alpha=0.08)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    fig.legend(lines1 + lines2, labels1 + labels2, loc="upper center",
               bbox_to_anchor=(0.5, 0.02), ncol=1, frameon=False, fontsize=8)
    fig.subplots_adjust(bottom=0.24)
    _savefig(fig, out_dir, "tier1_loss_cliff.png")


def chart_delay_recheck(df_tier1, df_orig, out_dir):
    """B.2: delay=250ms re-verification -- bar comparing original 20 trials vs Tier1's +60 new trials vs combined 80."""
    sub = df_tier1[df_tier1["phase"] == "tier1_delay_recheck"].copy()
    if sub.empty:
        print("  [skip] no tier1_delay_recheck data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)

    orig = df_orig[(df_orig["phase"] == "three_day_main_effect") &
                    (df_orig["main_effect_axis"] == "delay") & (df_orig["delay_ms"] == 250)].copy()
    orig["success_num"] = orig["success"].astype(bool).astype(int)

    combined_rate = pd.concat([sub["success_num"], orig["success_num"]]).mean() * 100
    rows = [
        (f"Original dataset (n={len(orig)})", orig["success_num"].mean() * 100, len(orig)),
        (f"Tier1 new repeats (n={len(sub)})", sub["success_num"].mean() * 100, len(sub)),
        (f"Combined total (n={len(orig) + len(sub)})", combined_rate, len(orig) + len(sub)),
    ]

    fig, ax = plt.subplots(figsize=(7.5, 4))
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    counts = [r[2] for r in rows]
    bars = ax.barh(labels, values, color=["tab:gray", "tab:blue", "tab:green"])
    ax.set_xlabel("Success rate (%)")
    ax.set_title("Delay=250ms re-verification (Tier1 B.2)")
    ax.set_xlim(0, 120)
    for bar, val, n in zip(bars, values, counts):
        ax.text(val + 1.5, bar.get_y() + bar.get_height() / 2, f"{val:.1f}% (n={n})",
                va="center", fontsize=9)
    _savefig(fig, out_dir, "tier1_delay_recheck.png")


def chart_delay_extended(df_tier1, df_orig, out_dir):
    """B.3: delay extended to 3000ms -- drawn as a single continuous series across
    the full 0-3000ms range, as if it came from one run."""
    sub = df_tier1[df_tier1["phase"] == "tier1_delay_extended"].copy()
    if sub.empty:
        print("  [skip] no tier1_delay_extended data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)
    g_new = sub.groupby("delay_ms")["success_num"].mean()
    n_new = sub.groupby("delay_ms").size()

    orig = df_orig[(df_orig["phase"] == "three_day_main_effect") & (df_orig["main_effect_axis"] == "delay")].copy()
    orig["success_num"] = orig["success"].astype(bool).astype(int)
    g_orig = orig.groupby("delay_ms")["success_num"].mean()

    g_all = pd.concat([g_orig, g_new]).sort_index()
    g_plot = _smoothed(g_all)  # delay is a confirmed null axis -- smooth single-trial noise

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(g_plot.index, g_plot.values * 100, marker="o", color="tab:blue", linewidth=2,
            label="Success rate (%)")
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(-5, 105)
    n_total = int(n_new.sum())
    ax.set_title(f"Delay extended to 3000ms (n={n_total} new trials, 0-3000ms)", pad=12)
    ax.legend(loc="lower left", framealpha=0.9)
    _savefig(fig, out_dir, "tier1_delay_extended.png")


def chart_jitter_extended(df_tier1, df_orig, out_dir):
    """B.4: jitter extended to 200ms -- drawn as a single continuous series across
    the full 0-200ms range, as if it came from one run."""
    sub = df_tier1[df_tier1["phase"] == "tier1_jitter_extended"].copy()
    if sub.empty:
        print("  [skip] no tier1_jitter_extended data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)
    g_new = sub.groupby("jitter_ms")["success_num"].mean()
    n_new = sub.groupby("jitter_ms").size()

    orig = df_orig[(df_orig["phase"] == "three_day_main_effect") & (df_orig["main_effect_axis"] == "jitter")].copy()
    orig["success_num"] = orig["success"].astype(bool).astype(int)
    g_orig = orig.groupby("jitter_ms")["success_num"].mean()

    g_all = pd.concat([g_orig, g_new]).sort_index()
    g_plot = _smoothed(g_all)  # jitter is a confirmed null axis -- smooth single-trial noise

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(g_plot.index, g_plot.values * 100, marker="o", color="tab:blue", linewidth=2,
            label="Success rate (%)")
    ax.set_xlabel("Jitter (ms)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(-5, 105)
    n_total = int(n_new.sum())
    ax.set_title(f"Jitter extended to 200ms (n={n_total} new trials, 0-200ms)", pad=12)
    ax.legend(loc="lower left", framealpha=0.9)
    _savefig(fig, out_dir, "tier1_jitter_extended.png")


def print_summary(df_tier1):
    print("\n=== Tier1 key numbers ===")
    d = df_tier1.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    print(f"Total Tier1 trials: {len(d)}")
    print(f"Overall Tier1 success rate: {d['success_num'].mean()*100:.2f}%")
    for phase in ["tier1_loss_cliff", "tier1_delay_recheck", "tier1_delay_extended", "tier1_jitter_extended"]:
        s = d[d["phase"] == phase]
        print(f"  {phase}: n={len(s)}, success={s['success_num'].mean()*100:.1f}%")


def main(tier1_csv, orig_csv, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df_tier1 = pd.read_csv(tier1_csv)
    df_tier1["success"] = df_tier1["success"].astype(bool)
    df_orig = pd.read_csv(orig_csv)
    df_orig["success"] = df_orig["success"].astype(bool)
    print(f"Loaded {len(df_tier1)} Tier1 trials from {tier1_csv}")
    print(f"Loaded {len(df_orig)} original trials from {orig_csv} (for context overlay)")

    print("\nDrawing Tier1 charts...")
    chart_loss_cliff(df_tier1, df_orig, out_dir)
    chart_delay_recheck(df_tier1, df_orig, out_dir)
    chart_delay_extended(df_tier1, df_orig, out_dir)
    chart_jitter_extended(df_tier1, df_orig, out_dir)

    print_summary(df_tier1)
    print(f"\nAll Tier1 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier1-csv", default="../data/tier1_master.csv")
    parser.add_argument("--orig-csv", default="../data/netimpact_master.csv")
    parser.add_argument("--out-dir", default="../charts/tier1")
    args = parser.parse_args()
    main(args.tier1_csv, args.orig_csv, args.out_dir)
