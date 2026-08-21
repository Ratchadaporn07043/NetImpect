"""
generate_charts_tier6.py -- charts for Tier6 mitigation x multi-round results
================================================================================
Reads tier6_none_master.csv, tier6_adaptive_master.csv, tier6_cache_master.csv
(produced by Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py,
2 scenarios [t6_baseline, t6_moderate_delay] x 2 hard tasks x 10 repeats x 3
mitigation conditions, strict_reviewer=True throughout). Draws 3 charts:
success rate by scenario x condition, a mechanism-detail view at moderate_delay
(rounds/rejections/errors), and an elapsed-time view with the one known outlier
trial explicitly excluded from the headline number and disclosed on the chart.
Saved as .png in charts/tier6/.

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 parse_logs.py --log-dir "../../Tier6_MitigationXMultiRound/logs_tier6_none" --out ../data/tier6_none_master.csv
    python3 parse_logs.py --log-dir "../../Tier6_MitigationXMultiRound/logs_tier6_adaptive_timeout" --out ../data/tier6_adaptive_master.csv
    python3 parse_logs.py --log-dir "../../Tier6_MitigationXMultiRound/logs_tier6_context_cache" --out ../data/tier6_cache_master.csv
    python3 generate_charts_tier6.py --none ../data/tier6_none_master.csv \
        --adaptive ../data/tier6_adaptive_master.csv \
        --cache ../data/tier6_cache_master.csv --out-dir ../charts/tier6
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

# One trial (context_cache, t6_baseline, run7, planning_decision_hard) logged
# elapsed_seconds=33266 (~9.2 hours) against every other trial's <=3476s -- a
# clear single-trial infrastructure anomaly (0 errors, 0 timeouts, success=True,
# rounds=3, i.e. a normal-looking completion that was simply stalled externally),
# not a real mechanism cost. Excluded from elapsed-time headline figures only,
# and disclosed explicitly on the chart. Never excluded from success-rate figures.
KNOWN_ELAPSED_OUTLIER_SECONDS = 30000


def _savefig(fig, out_dir, filename):
    path = os.path.join(out_dir, filename)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> saved: {path}")


def chart_success_by_scenario(none, adt, cache, out_dir):
    """Success rate per scenario x condition -- the core Tier6 comparison."""
    scenarios = ["t6_baseline", "t6_moderate_delay"]
    conditions = [("none", none, "tab:gray"), ("adaptive_timeout", adt, "tab:green"), ("context_cache", cache, "tab:blue")]

    x = np.arange(len(scenarios))
    width = 0.27

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, (name, df, color) in enumerate(conditions):
        rates = [df[df["scenario_name"] == s]["success"].mean() * 100 for s in scenarios]
        ns = [df[df["scenario_name"] == s]["success"].size for s in scenarios]
        offset = (i - 1) * width
        bars = ax.bar(x + offset, rates, width, label=name, color=color)
        for bar, val, n in zip(bars, rates, ns):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 2, f"{val:.0f}%",
                    ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(["t6_baseline\n(no impairment)", "t6_moderate_delay\n(300ms delay)"])
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 115)
    ax.set_title("Tier6: strict-reviewer multi-round success by scenario x mitigation (n=20/scenario/condition)\n"
                 "directionally positive for both mitigations at both scenarios -- neither reaches significance (Fisher p>0.05, all four comparisons)",
                 pad=12, fontsize=9.5)
    ax.legend()
    _savefig(fig, out_dir, "tier6_success_by_scenario.png")


def chart_mechanism_at_moderate_delay(none, adt, cache, out_dir):
    """Mechanism detail at t6_moderate_delay: rounds / reviewer_rejections / errors, by condition."""
    conditions = ["none", "adaptive_timeout", "context_cache"]
    dfs = {"none": none, "adaptive_timeout": adt, "context_cache": cache}
    subs = {c: dfs[c][dfs[c]["scenario_name"] == "t6_moderate_delay"] for c in conditions}

    metrics = ["rounds", "reviewer_rejections", "total_error_count", "timeout_count"]
    labels = ["Mean rounds", "Mean reviewer\nrejections/trial", "Mean errors/trial", "Mean timeouts/trial (x5)"]
    data = {c: [
        subs[c]["rounds"].mean(),
        subs[c]["reviewer_rejections"].mean(),
        subs[c]["total_error_count"].mean(),
        subs[c]["timeout_count"].mean() * 5,
    ] for c in conditions}

    x = np.arange(len(metrics))
    width = 0.27
    colors = {"none": "tab:gray", "adaptive_timeout": "tab:green", "context_cache": "tab:blue"}

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, c in enumerate(conditions):
        offset = (i - 1) * width
        bars = ax.bar(x + offset, data[c], width, label=c, color=colors[c])
        for bar, val in zip(bars, data[c]):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.05, f"{val:.2f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_title("Mechanism at t6_moderate_delay (n=20/condition): rounds/rejections/errors all fall with mitigation\n"
                 "timeout count scaled x5 to share the same axis", pad=12, fontsize=10)
    ax.legend()
    _savefig(fig, out_dir, "tier6_mechanism_moderate_delay.png")


def chart_elapsed_tradeoff(none, adt, cache, out_dir):
    """Mean elapsed_seconds per condition, overall -- one known outlier trial excluded and disclosed."""
    conditions = ["none", "adaptive_timeout", "context_cache"]
    dfs_raw = {"none": none, "adaptive_timeout": adt, "context_cache": cache}
    n_excluded = {}
    dfs = {}
    for c, df in dfs_raw.items():
        mask = df["elapsed_seconds"] < KNOWN_ELAPSED_OUTLIER_SECONDS
        n_excluded[c] = int((~mask).sum())
        dfs[c] = df[mask]

    means = [dfs[c]["elapsed_seconds"].mean() for c in conditions]
    medians = [dfs[c]["elapsed_seconds"].median() for c in conditions]

    x = np.arange(len(conditions))
    width = 0.35
    colors = ["tab:gray", "tab:green", "tab:blue"]

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    bars1 = ax.bar(x - width / 2, means, width, label="Mean elapsed (s)", color=colors)
    bars2 = ax.bar(x + width / 2, medians, width, label="Median elapsed (s)", color=colors, alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(conditions)
    ax.set_ylabel("Elapsed seconds per trial")
    excl_note = ", ".join(f"{c}: excluded {n}" for c, n in n_excluded.items() if n > 0)
    title = "Tier6: elapsed-time cost per condition (all 40 trials/condition)"
    if excl_note:
        title += f"\n(one known infrastructure-stall outlier >{KNOWN_ELAPSED_OUTLIER_SECONDS}s excluded from this figure -- {excl_note})"
    ax.set_title(title, pad=12, fontsize=9.5)
    for bar, val in zip(bars1, means):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 10, f"{val:.0f}s", ha="center", fontsize=8)
    for bar, val in zip(bars2, medians):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 10, f"{val:.0f}s", ha="center", fontsize=8)
    ax.legend()
    _savefig(fig, out_dir, "tier6_elapsed_tradeoff.png")


def print_summary(none, adt, cache):
    from scipy import stats

    print("\n=== Tier6 key numbers ===")
    for name, df in [("none", none), ("adaptive_timeout", adt), ("context_cache", cache)]:
        print(f"{name}: overall success={df['success'].mean()*100:.2f}% ({int(df['success'].sum())}/{len(df)})")
        g = df.groupby("scenario_name")["success"].agg(["mean", "count"])
        print(g)

    def fisher(a, b, label):
        table = [[int(a.sum()), len(a) - int(a.sum())], [int(b.sum()), len(b) - int(b.sum())]]
        odds, p = stats.fisher_exact(table)
        print(f"  {label}: OR={odds:.3f} p={p:.4f}")

    print("\n-- significance tests --")
    none_md = none[none.scenario_name == "t6_moderate_delay"]["success"]
    adt_md = adt[adt.scenario_name == "t6_moderate_delay"]["success"]
    cache_md = cache[cache.scenario_name == "t6_moderate_delay"]["success"]
    fisher(none_md, adt_md, "none vs adaptive_timeout @moderate_delay")
    fisher(none_md, cache_md, "none vs context_cache @moderate_delay")
    none_bl = none[none.scenario_name == "t6_baseline"]["success"]
    adt_bl = adt[adt.scenario_name == "t6_baseline"]["success"]
    cache_bl = cache[cache.scenario_name == "t6_baseline"]["success"]
    fisher(none_bl, adt_bl, "none vs adaptive_timeout @baseline")
    fisher(none_bl, cache_bl, "none vs context_cache @baseline")


def main(none_path, adaptive_path, cache_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    none = pd.read_csv(none_path)
    adt = pd.read_csv(adaptive_path)
    cache = pd.read_csv(cache_path)
    for df in (none, adt, cache):
        df["success"] = df["success"].astype(bool)

    print(f"Loaded none n={len(none)}, adaptive_timeout n={len(adt)}, context_cache n={len(cache)}")
    print("\nDrawing Tier6 charts...")
    chart_success_by_scenario(none, adt, cache, out_dir)
    chart_mechanism_at_moderate_delay(none, adt, cache, out_dir)
    chart_elapsed_tradeoff(none, adt, cache, out_dir)

    print_summary(none, adt, cache)
    print(f"\nAll Tier6 charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--none", default="../data/tier6_none_master.csv")
    parser.add_argument("--adaptive", default="../data/tier6_adaptive_master.csv")
    parser.add_argument("--cache", default="../data/tier6_cache_master.csv")
    parser.add_argument("--out-dir", default="../charts/tier6")
    args = parser.parse_args()
    main(args.none, args.adaptive, args.cache, args.out_dir)
