"""
generate_charts_tier5.py -- charts for Tier5 mitigation comparison results
================================================================================
Reads tier5_none_master.csv, tier5_adaptive_master.csv, tier5_cache_master.csv
(produced by Tier5_Mitigation/run_tier5_mitigation_comparison.py, loss main-effect
axis re-run under 3 conditions: none / adaptive_timeout / context_cache). Draws 3
charts: loss-cliff success-rate comparison across all 11 levels, a zoomed detail
view at loss=75% (success/error/timeout/retry), and an elapsed-time tradeoff view.
Saved as .png in charts/tier5/.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 generate_charts_tier5.py --none ../data/tier5_none_master.csv \
        --adaptive ../data/tier5_adaptive_master.csv \
        --cache ../data/tier5_cache_master.csv --out-dir ../charts/tier5
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


def chart_loss_cliff_comparison(none, adt, cache, out_dir):
    """Success rate by loss_pct across all 3 conditions."""
    levels = sorted(none["loss_pct"].unique())
    n_rates = [none[none["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]
    a_rates = [adt[adt["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]
    c_rates = [cache[cache["loss_pct"] == lv]["success"].mean() * 100 for lv in levels]

    x = np.arange(len(levels))
    width = 0.27

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - width, n_rates, width, label="none (control)", color="tab:gray")
    ax.bar(x, a_rates, width, label="adaptive_timeout", color="tab:green")
    ax.bar(x + width, c_rates, width, label="context_cache", color="tab:blue")
    ax.set_xticks(x)
    ax.set_xticklabels([str(lv) for lv in levels])
    ax.set_xlabel("Packet loss (%)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 112)
    ax.set_title("Tier5 mitigation: loss cliff before/after (n=20/level/condition)\n"
                 "adaptive_timeout fully closes the cliff at 75% loss (70%->100%, Fisher p=0.020)", pad=12)
    ax.legend()
    _savefig(fig, out_dir, "tier5_loss_cliff_comparison.png")


def chart_loss75_detail(none, adt, cache, out_dir):
    """Zoomed detail at loss=75%: success rate + mean error/timeout/retry counts."""
    conditions = ["none", "adaptive_timeout", "context_cache"]
    dfs = {"none": none, "adaptive_timeout": adt, "context_cache": cache}
    subs = {c: dfs[c][dfs[c]["loss_pct"] == 75] for c in conditions}

    metrics = ["success_rate", "mean_error", "mean_timeout", "mean_retry"]
    labels = ["Success rate (%)", "Mean errors/trial (x10)", "Mean timeouts/trial (x10)", "Mean retries/trial (x10)"]
    data = {c: [
        subs[c]["success"].mean() * 100,
        subs[c]["total_error_count"].mean() * 10,
        subs[c]["timeout_count"].mean() * 10,
        subs[c]["retry_count"].mean() * 10,
    ] for c in conditions}

    x = np.arange(len(metrics))
    width = 0.27
    colors = {"none": "tab:gray", "adaptive_timeout": "tab:green", "context_cache": "tab:blue"}

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, c in enumerate(conditions):
        offset = (i - 1) * width
        bars = ax.bar(x + offset, data[c], width, label=c, color=colors[c])
        for bar, val in zip(bars, data[c]):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 1.5, f"{val:.1f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0, 115)
    ax.set_title("Detail at loss=75% (the only level where 'none' fails, n=20/condition)\n"
                 "error/timeout/retry counts scaled x10 to share the same axis as success rate", pad=12, fontsize=10)
    ax.legend()
    _savefig(fig, out_dir, "tier5_loss75_detail.png")


def chart_elapsed_tradeoff(none, adt, cache, out_dir):
    """Overall mean elapsed_seconds per condition -- shows the latency cost of adaptive_timeout."""
    conditions = ["none", "adaptive_timeout", "context_cache"]
    dfs = {"none": none, "adaptive_timeout": adt, "context_cache": cache}
    overall = [dfs[c]["elapsed_seconds"].mean() for c in conditions]
    at75 = [dfs[c][dfs[c]["loss_pct"] == 75]["elapsed_seconds"].mean() for c in conditions]

    x = np.arange(2)
    width = 0.27
    colors = ["tab:gray", "tab:green", "tab:blue"]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    for i, c in enumerate(conditions):
        vals = [overall[i], at75[i]]
        offset = (i - 1) * width
        bars = ax.bar(x + offset, vals, width, label=c, color=colors[i])
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 10, f"{val:.0f}s", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(["Overall (all 220 trials)", "At loss=75% only (n=20)"])
    ax.set_ylabel("Mean elapsed seconds / trial")
    ax.set_title("Latency cost of mitigation: adaptive_timeout trades time for reliability", pad=12)
    ax.legend()
    _savefig(fig, out_dir, "tier5_elapsed_tradeoff.png")


def print_summary(none, adt, cache):
    from scipy import stats

    print("\n=== Tier5 key numbers ===")
    for name, df in [("none", none), ("adaptive_timeout", adt), ("context_cache", cache)]:
        print(f"{name}: overall success={df['success'].mean()*100:.2f}% ({int(df['success'].sum())}/{len(df)}), "
              f"GT mean={df['ground_truth_score'].mean():.3f}, elapsed mean={df['elapsed_seconds'].mean():.1f}s")

    n75 = none[none["loss_pct"] == 75]["success"]
    a75 = adt[adt["loss_pct"] == 75]["success"]
    c75 = cache[cache["loss_pct"] == 75]["success"]
    print(f"\nloss=75% success: none={n75.mean()*100:.0f}%, adaptive={a75.mean()*100:.0f}%, cache={c75.mean()*100:.0f}%")

    def fisher(a, b, label):
        table = [[int(a.sum()), len(a) - int(a.sum())], [int(b.sum()), len(b) - int(b.sum())]]
        odds, p = stats.fisher_exact(table)
        print(f"  {label}: OR={odds:.3f} p={p:.4f}")

    fisher(n75, a75, "none vs adaptive_timeout @75%loss")
    fisher(n75, c75, "none vs context_cache @75%loss")
    fisher(none["success"], adt["success"], "none vs adaptive_timeout (overall)")
    fisher(none["success"], cache["success"], "none vs context_cache (overall)")


def main(none_path, adaptive_path, cache_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    none = pd.read_csv(none_path)
    adt = pd.read_csv(adaptive_path)
    cache = pd.read_csv(cache_path)

    print(f"Loaded none n={len(none)}, adaptive_timeout n={len(adt)}, context_cache n={len(cache)}")
    print("\nDrawing Tier5 charts...")
    chart_loss_cliff_comparison(none, adt, cache, out_dir)
    chart_loss75_detail(none, adt, cache, out_dir)
    chart_elapsed_tradeoff(none, adt, cache, out_dir)

    print_summary(none, adt, cache)
    print(f"\nAll Tier5 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--none", default="../data/tier5_none_master.csv")
    parser.add_argument("--adaptive", default="../data/tier5_adaptive_master.csv")
    parser.add_argument("--cache", default="../data/tier5_cache_master.csv")
    parser.add_argument("--out-dir", default="../charts/tier5")
    args = parser.parse_args()
    main(args.none, args.adaptive, args.cache, args.out_dir)
