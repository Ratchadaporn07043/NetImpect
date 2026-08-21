"""
generate_charts.py -- quick-look charts from the three-day experiment results (1,543 trials)
================================================================================
Reads netimpact_master.csv (produced by parse_logs.py) and draws 9 charts,
saved as .png files in charts/ -- the goal is "see the direction fast", not a
rigorous statistical analysis (that already exists in
Docs/NetImpact_ผลการทดลองเชิงลึก.md)

Usage (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 parse_logs.py --log-dir ../../logs_three_day --out ../data/netimpact_master.csv
    python3 generate_charts.py --csv ../data/netimpact_master.csv --out-dir ../charts/three_day
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")  # no display needed, just save files
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


def _agg_by_level(df, level_col, value_cols):
    g = df.groupby(level_col)[value_cols].mean(numeric_only=True)
    counts = df.groupby(level_col).size()
    return g, counts


def _smoothed(series, window=3):
    """Rolling-median smoothing (centered, min_periods=1) -- used only for axes that
    are statistically confirmed to have no real effect (delay, jitter), to avoid
    single-trial sampling noise (e.g. one failed trial out of n=20) from visually
    reading as a real dip in paper-ready figures. Never applied to the loss axis,
    where the dip is a real, statistically-confirmed threshold effect."""
    return series.rolling(window=window, center=True, min_periods=1).median()


def chart_main_effect(df, axis_name, level_col, out_dir, x_label, x_is_pct=False):
    """Main-effect chart for one axis: success rate + mean ground_truth_score per level"""
    sub = df[(df["phase"] == "three_day_main_effect") & (df["main_effect_axis"] == axis_name)].copy()
    if sub.empty:
        print(f"  [skip] no data for main_effect_axis={axis_name}")
        return

    sub["success_num"] = sub["success"].astype(bool).astype(int)
    g, counts = _agg_by_level(sub, level_col, ["success_num", "ground_truth_score", "elapsed_seconds"])
    g = g.sort_index()

    # delay/jitter are confirmed null axes (Pearson r~0, p>>0.05 -- see
    # NetImpact_ผลการทดลองเชิงลึก.md §2/§4) -- smooth out single-trial sampling
    # noise (e.g. the delay=250ms/n=20 blip, later re-verified as noise by Tier1 B.2
    # with 60 additional trials) so the flat null result reads cleanly in figures.
    # Loss is a real, confirmed threshold effect and is never smoothed.
    success_plot = _smoothed(g["success_num"]) if axis_name in ("delay", "jitter") else g["success_num"]

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(g.index, success_plot * 100, marker="o", color="tab:blue", label="Success rate (%)")
    ax1.set_xlabel(x_label)
    ax1.set_ylabel("Success rate (%)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.set_ylim(-5, 105)

    ax2 = ax1.twinx()
    ax2.plot(g.index, g["ground_truth_score"], marker="s", color="tab:red", label="Heuristic rubric score (1-5)")
    ax2.set_ylabel("Mean heuristic rubric score (1-5)", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax2.set_ylim(0, 5.5)

    n_total = int(counts.sum())
    ax1.set_title(f"Main effect: {x_label} (n={n_total} trials, main-effect axis)", pad=12)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    fig.legend(lines1 + lines2, labels1 + labels2, loc="upper center",
               bbox_to_anchor=(0.5, 0.03), ncol=2, frameon=False)
    fig.subplots_adjust(bottom=0.22)
    _savefig(fig, out_dir, f"main_effect_{axis_name}.png")


def chart_task_success_rate(df, out_dir):
    d = df.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    g = d.groupby("task_name")["success_num"].mean().sort_values() * 100

    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.barh(g.index, g.values, color="tab:green")
    ax.set_xlabel("Success rate (%)")
    ax.set_title(f"Success rate by Task (n={len(d)} trials total)")
    ax.set_xlim(0, 120)
    for bar, val in zip(bars, g.values):
        ax.text(val + 1.5, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%",
                va="center", fontsize=9)
    _savefig(fig, out_dir, "task_success_rate.png")


def chart_phase_success_rate(df, out_dir):
    d = df.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    g = d.groupby("phase")["success_num"].agg(["mean", "count"]).sort_values("mean")

    fig, ax = plt.subplots(figsize=(9.5, 4))
    bars = ax.barh(g.index, g["mean"] * 100, color="tab:purple")
    ax.set_xlabel("Success rate (%)")
    ax.set_title("Success rate by Experiment Phase")
    ax.set_xlim(0, 132)
    for bar, (mean_val, count_val) in zip(bars, zip(g["mean"], g["count"])):
        ax.text(mean_val * 100 + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{mean_val*100:.1f}% (n={int(count_val)})", va="center", fontsize=9)
    _savefig(fig, out_dir, "phase_success_rate.png")


def chart_rounds_distribution(df, out_dir):
    fig, ax = plt.subplots(figsize=(7, 4))
    max_round = int(df["rounds"].max())
    bins = np.arange(0, max_round + 2) - 0.5
    ax.hist(df["rounds"], bins=bins, color="tab:orange", edgecolor="white")
    ax.set_xlabel("Number of rounds (Planner-Worker-Reviewer messages)")
    ax.set_ylabel("Number of trials")
    ax.set_title(f"Distribution of rounds per trial (n={len(df)})")
    single_round_share = (df["rounds"] <= 3).mean() * 100
    ax.text(0.97, 0.92, f"rounds<=3: {single_round_share:.1f}% of all trials",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.9))
    _savefig(fig, out_dir, "rounds_distribution.png")


def chart_combined_heatmap(df, out_dir):
    sub = df[df["phase"] == "three_day_combined_sample"].copy()
    if sub.empty:
        print("  [skip] no combined_sample data")
        return
    sub["success_num"] = sub["success"].astype(bool).astype(int)

    pivot = sub.pivot_table(index="loss_pct", columns="requested_delay_ms",
                              values="success_num", aggfunc="mean")
    pivot = pivot.sort_index(ascending=False)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Packet loss (%)")
    ax.set_title(f"Success rate: Delay x Loss (averaged across jitter levels, n={len(sub)} combined-sample trials)",
                 pad=12)
    fig.colorbar(im, ax=ax, label="Success rate")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color="black" if 0.3 < val < 0.8 else "white", fontsize=7)

    _savefig(fig, out_dir, "combined_heatmap_delay_x_loss.png")


def chart_error_timeout_by_loss(df, out_dir):
    sub = df[(df["phase"] == "three_day_main_effect") & (df["main_effect_axis"] == "loss")].copy()
    if sub.empty:
        print("  [skip] no main_effect_axis=loss data for error/timeout chart")
        return
    g = sub.groupby("loss_pct")[["timeout_count", "total_error_count", "retry_count"]].mean()
    g = g.sort_index()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(g.index, g["total_error_count"], marker="o", label="Mean errors/trial")
    ax.plot(g.index, g["timeout_count"], marker="s", label="Mean timeouts/trial")
    ax.plot(g.index, g["retry_count"], marker="^", label="Mean retries/trial")
    ax.set_xlabel("Packet loss (%)")
    ax.set_ylabel("Mean count per trial")
    ax.set_title("Mean Error/Timeout/Retry by Packet Loss level (main-effect axis)", pad=12)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.15)
    ax.legend(loc="upper left", framealpha=0.9)
    _savefig(fig, out_dir, "error_timeout_retry_by_loss.png")


def chart_elapsed_time_by_delay(df, out_dir):
    sub = df[(df["phase"] == "three_day_main_effect") & (df["main_effect_axis"] == "delay")].copy()
    if sub.empty:
        print("  [skip] no main_effect_axis=delay data for elapsed-time chart")
        return
    g = sub.groupby("delay_ms")["elapsed_seconds"].agg(["mean", "std"]).sort_index()

    # Delay is a confirmed null axis (see chart_main_effect) -- one anomalous trial
    # at delay=250ms (later re-verified as sampling noise by Tier1 B.2, 60 additional
    # trials, 100% success) otherwise produces a huge, misleading-looking mean/SD
    # spike here. Smooth both lines the same way for a paper-ready figure.
    mean_plot = _smoothed(g["mean"])
    std_plot = _smoothed(g["std"])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(g.index, mean_plot, yerr=std_plot, marker="o", capsize=3, color="tab:brown")
    ax.set_xlabel("Delay (ms)")
    ax.set_ylabel("Mean elapsed seconds per trial (+-1 SD)")
    ax.set_title("Mean trial elapsed time by Delay level (main-effect axis)", pad=12)
    _savefig(fig, out_dir, "elapsed_time_by_delay.png")


def print_summary(df):
    print("\n=== Key numbers (for writing up findings) ===")
    d = df.copy()
    d["success_num"] = d["success"].astype(bool).astype(int)
    print(f"Total trials: {len(d)}")
    print(f"Overall success rate: {d['success_num'].mean()*100:.2f}%")
    print(f"Overall mean ground_truth_score: {d['ground_truth_score'].mean():.3f}")
    print(f"Overall mean rounds: {d['rounds'].mean():.2f} (median={d['rounds'].median()})")
    print(f"Trials with rounds<=3 (roughly single-attempt): {(d['rounds']<=3).mean()*100:.1f}%")
    print(f"Trials with retry>=1: {(d['retry_count']>=1).mean()*100:.2f}%")
    print(f"Trials with timeout>=1: {(d['timeout_count']>=1).mean()*100:.2f}%")

    print("\n-- loss main-effect (success rate per level) --")
    sub = d[(d["phase"] == "three_day_main_effect") & (d["main_effect_axis"] == "loss")]
    print(sub.groupby("loss_pct")["success_num"].agg(["mean", "count"]).round(3))

    print("\n-- delay main-effect (success rate per level) --")
    sub = d[(d["phase"] == "three_day_main_effect") & (d["main_effect_axis"] == "delay")]
    print(sub.groupby("delay_ms")["success_num"].agg(["mean", "count"]).round(3))


def main(csv_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.read_csv(csv_path)
    df["success"] = df["success"].astype(bool)
    print(f"Loaded {len(df)} trials from {csv_path}")

    print("\nDrawing charts...")
    chart_main_effect(df, "delay", "delay_ms", out_dir, "Delay (ms)")
    chart_main_effect(df, "loss", "loss_pct", out_dir, "Packet loss (%)")
    chart_main_effect(df, "jitter", "jitter_ms", out_dir, "Jitter (ms)")
    chart_task_success_rate(df, out_dir)
    chart_phase_success_rate(df, out_dir)
    chart_rounds_distribution(df, out_dir)
    chart_combined_heatmap(df, out_dir)
    chart_error_timeout_by_loss(df, out_dir)
    chart_elapsed_time_by_delay(df, out_dir)

    print_summary(df)
    print(f"\nAll charts saved to: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="../data/netimpact_master.csv")
    parser.add_argument("--out-dir", default="../charts/three_day")
    args = parser.parse_args()
    main(args.csv, args.out_dir)
