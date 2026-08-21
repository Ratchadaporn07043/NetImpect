"""
Guideline Analyzer
==================
วิเคราะห์ log จาก three-day/full experiment เพื่อสร้าง practical deployment guideline:
  - safe / warning / failure zone
  - threshold รายแกน delay, packet loss, jitter จาก main-effect phase
  - combined interaction summary จาก combined sample/full combined
  - invalid trial / tc netem failure check

วิธีรัน:
    python3 experiment/analyze_guidelines.py --log-dir logs_three_day
    python3 experiment/analyze_guidelines.py --log-dir logs_three_day --csv guideline_summary.csv
"""
import argparse
import csv
import glob
import json
import os
import statistics as stats
from collections import defaultdict

SAFE_SUCCESS_RATE = 0.90
WARNING_SUCCESS_RATE = 0.80
SAFE_QUALITY_SCORE = 4.0
WARNING_QUALITY_SCORE = 3.0
WARNING_TIMEOUT_RATE = 0.10
FAILURE_TIMEOUT_RATE = 0.25
WARNING_RETRY_RATE = 0.50
FAILURE_RETRY_RATE = 1.00


def load_records(log_dir: str):
    valid, broken = [], []
    for filepath in sorted(glob.glob(os.path.join(log_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            broken.append((filepath, str(e)))
            continue

        if not data.get("outcome"):
            broken.append((filepath, "missing outcome"))
            continue

        scenario = data.get("network_condition", {})
        outcome = data.get("outcome", {})
        errors = data.get("errors", [])
        requested_delay = scenario.get("requested_delay_ms", scenario.get("delay_ms", 0))

        valid.append({
            "filepath": filepath,
            "task_name": data.get("task_name"),
            "run_index": data.get("run_index"),
            "scenario_name": scenario.get("name", "unknown"),
            "scenario_type": scenario.get("scenario_type", "unknown"),
            "phase": scenario.get("experiment_phase", "unknown"),
            "main_effect_axis": scenario.get("main_effect_axis"),
            "requested_delay_ms": requested_delay,
            "applied_delay_ms": scenario.get("delay_ms", 0),
            "loss_pct": scenario.get("loss_pct", 0),
            "jitter_ms": scenario.get("jitter_ms", 0),
            "success": bool(outcome.get("success")),
            "elapsed_seconds": outcome.get("elapsed_seconds"),
            "total_tokens": outcome.get("total_tokens"),
            "quality_score": outcome.get("quality_score"),
            "ground_truth_score": outcome.get("ground_truth_score"),
            "ground_truth_passed": outcome.get("ground_truth_passed"),
            "retry_count": outcome.get("retry_count", 0),
            "timeout_count": outcome.get("timeout_count", 0),
            "total_error_count": outcome.get("total_error_count", 0),
            "reviewer_rejections": outcome.get("reviewer_rejections", 0),
            "invalid_trial": any(e.get("error_type") == "invalid_trial" for e in errors),
            "network_apply_failed": any(e.get("error_type") == "network_apply_failed" for e in errors),
            "network_clear_failed": any(e.get("error_type") == "network_clear_failed" for e in errors),
        })
    return valid, broken


def _mean(values):
    values = [v for v in values if v is not None]
    return stats.mean(values) if values else None


def _sd(values):
    values = [v for v in values if v is not None]
    return stats.stdev(values) if len(values) >= 2 else None


def classify_zone(success_rate, quality_mean, timeout_rate, retry_mean, ground_truth_mean=None, ground_truth_pass_rate=None):
    quality_signal = ground_truth_mean if ground_truth_mean is not None else quality_mean

    if success_rate < WARNING_SUCCESS_RATE:
        return "failure"
    if ground_truth_pass_rate is not None and ground_truth_pass_rate < WARNING_SUCCESS_RATE:
        return "failure"
    if timeout_rate >= FAILURE_TIMEOUT_RATE or retry_mean >= FAILURE_RETRY_RATE:
        return "failure"
    if quality_signal is not None and quality_signal < WARNING_QUALITY_SCORE:
        return "failure"

    if success_rate < SAFE_SUCCESS_RATE:
        return "warning"
    if ground_truth_pass_rate is not None and ground_truth_pass_rate < SAFE_SUCCESS_RATE:
        return "warning"
    if timeout_rate >= WARNING_TIMEOUT_RATE or retry_mean >= WARNING_RETRY_RATE:
        return "warning"
    if quality_signal is not None and quality_signal < SAFE_QUALITY_SCORE:
        return "warning"

    return "safe"


def summarize_group(records, group_keys):
    grouped = defaultdict(list)
    for r in records:
        key = tuple(r[k] for k in group_keys)
        grouped[key].append(r)

    rows = []
    for key, items in sorted(grouped.items(), key=lambda kv: kv[0]):
        n = len(items)
        invalid = sum(1 for r in items if r["invalid_trial"] or r["network_apply_failed"])
        valid_items = [r for r in items if not r["invalid_trial"] and not r["network_apply_failed"]]
        denom = len(valid_items) or n
        success_rate = sum(1 for r in valid_items if r["success"]) / denom if denom else 0
        timeout_rate = sum(1 for r in valid_items if (r["timeout_count"] or 0) > 0) / denom if denom else 0
        quality_mean = _mean([r["quality_score"] for r in valid_items])
        ground_truth_mean = _mean([r["ground_truth_score"] for r in valid_items])
        gt_pass_values = [r["ground_truth_passed"] for r in valid_items if r["ground_truth_passed"] is not None]
        ground_truth_pass_rate = (sum(1 for v in gt_pass_values if v) / len(gt_pass_values)) if gt_pass_values else None
        retry_mean = _mean([r["retry_count"] for r in valid_items]) or 0
        elapsed_mean = _mean([r["elapsed_seconds"] for r in valid_items])
        tokens_mean = _mean([r["total_tokens"] for r in valid_items])
        rejection_mean = _mean([r["reviewer_rejections"] for r in valid_items]) or 0

        row = dict(zip(group_keys, key))
        row.update({
            "n_total": n,
            "n_valid": len(valid_items),
            "invalid_count": invalid,
            "success_rate": round(success_rate, 3),
            "quality_mean": round(quality_mean, 3) if quality_mean is not None else None,
            "ground_truth_mean": round(ground_truth_mean, 3) if ground_truth_mean is not None else None,
            "ground_truth_pass_rate": round(ground_truth_pass_rate, 3) if ground_truth_pass_rate is not None else None,
            "elapsed_mean": round(elapsed_mean, 3) if elapsed_mean is not None else None,
            "elapsed_sd": round(_sd([r["elapsed_seconds"] for r in valid_items]), 3) if _sd([r["elapsed_seconds"] for r in valid_items]) is not None else None,
            "tokens_mean": round(tokens_mean, 3) if tokens_mean is not None else None,
            "retry_mean": round(retry_mean, 3),
            "timeout_rate": round(timeout_rate, 3),
            "reviewer_rejection_mean": round(rejection_mean, 3),
            "zone": classify_zone(success_rate, quality_mean, timeout_rate, retry_mean, ground_truth_mean, ground_truth_pass_rate),
        })
        rows.append(row)
    return rows


def threshold_for_axis(axis_rows, value_key):
    ordered = sorted(axis_rows, key=lambda r: r[value_key])
    first_warning = next((r for r in ordered if r["zone"] in ("warning", "failure")), None)
    first_failure = next((r for r in ordered if r["zone"] == "failure"), None)
    max_safe = None
    for r in ordered:
        if r["zone"] == "safe":
            max_safe = r
    return max_safe, first_warning, first_failure


def print_thresholds(main_rows):
    print("\n" + "=" * 72)
    print("Threshold Summary: safe / warning / failure")
    print("=" * 72)

    axes = [
        ("delay", "requested_delay_ms", "ms"),
        ("loss", "loss_pct", "%"),
        ("jitter", "jitter_ms", "ms"),
    ]
    for axis, value_key, unit in axes:
        rows = [r for r in main_rows if r.get("main_effect_axis") == axis]
        if not rows:
            print(f"[{axis}] ไม่มีข้อมูล main-effect")
            continue
        max_safe, first_warning, first_failure = threshold_for_axis(rows, value_key)
        safe_text = f"<= {max_safe[value_key]}{unit}" if max_safe else "ไม่พบ safe zone"
        warn_text = f">= {first_warning[value_key]}{unit}" if first_warning else "ไม่พบ warning/failure ในช่วงที่ทดสอบ"
        fail_text = f">= {first_failure[value_key]}{unit}" if first_failure else "ไม่พบ failure ในช่วงที่ทดสอบ"
        print(f"[{axis}] safe: {safe_text} | warning starts: {warn_text} | failure starts: {fail_text}")


def print_phase_summary(records):
    print("\n" + "=" * 72)
    print("Phase Summary")
    print("=" * 72)
    rows = summarize_group(records, ["phase"])
    for r in rows:
        print(
            f"{r['phase']}: n={r['n_total']} valid={r['n_valid']} invalid={r['invalid_count']} "
            f"success={r['success_rate']:.1%} reviewer_quality={r['quality_mean']} "
            f"ground_truth={r['ground_truth_mean']} gt_pass={r['ground_truth_pass_rate']} "
            f"elapsed={r['elapsed_mean']}s zone={r['zone']}"
        )
    return rows


def print_combined_summary(combined_rows):
    print("\n" + "=" * 72)
    print("Combined Interaction Summary")
    print("=" * 72)
    if not combined_rows:
        print("ไม่มีข้อมูล combined sample/full combined")
        return

    zone_counts = defaultdict(int)
    for r in combined_rows:
        zone_counts[r["zone"]] += 1
    print("zone counts:", dict(sorted(zone_counts.items())))

    risky = [r for r in combined_rows if r["zone"] in ("warning", "failure")]
    risky = sorted(risky, key=lambda r: (r["zone"] != "failure", r["success_rate"], -(r["timeout_rate"] or 0)))
    for r in risky[:10]:
        print(
            f"{r['zone'].upper()}: delay={r['requested_delay_ms']}ms loss={r['loss_pct']}% "
            f"jitter={r['jitter_ms']}ms success={r['success_rate']:.1%} "
            f"reviewer_quality={r['quality_mean']} ground_truth={r['ground_truth_mean']} "
            f"gt_pass={r['ground_truth_pass_rate']} retry={r['retry_mean']} timeout={r['timeout_rate']:.1%}"
        )


def write_csv(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"บันทึก CSV: {os.path.abspath(path)}")


def main(log_dir: str, csv_prefix: str = None):
    records, broken = load_records(log_dir)
    print(f"อ่าน logs จาก: {os.path.abspath(log_dir)}")
    print(f"valid records: {len(records)} | broken/missing outcome: {len(broken)}")
    if broken:
        print("ตัวอย่าง broken logs:")
        for filepath, reason in broken[:5]:
            print(f"  - {os.path.basename(filepath)}: {reason}")

    if not records:
        return

    invalid = [r for r in records if r["invalid_trial"] or r["network_apply_failed"] or r["network_clear_failed"]]
    if invalid:
        print(f"\nพบ trial ที่มีปัญหา network/apply/clear: {len(invalid)} records")
        for r in invalid[:10]:
            print(f"  - {r['scenario_name']} task={r['task_name']} phase={r['phase']}")
    else:
        print("\nไม่พบ invalid/network failed trial")

    phase_rows = print_phase_summary(records)

    main_records = [r for r in records if r["phase"] == "three_day_main_effect" or r["scenario_type"] == "main_effect"]
    main_rows = summarize_group(main_records, ["main_effect_axis", "requested_delay_ms", "loss_pct", "jitter_ms"])
    print_thresholds(main_rows)

    combined_records = [
        r for r in records
        if r["phase"] in ("three_day_combined_sample", "combined_full") or r["scenario_type"] == "combined"
    ]
    combined_rows = summarize_group(combined_records, ["requested_delay_ms", "loss_pct", "jitter_ms"])
    print_combined_summary(combined_rows)

    task_rows = summarize_group(records, ["task_name"])
    print("\n" + "=" * 72)
    print("Task Sensitivity Summary")
    print("=" * 72)
    for r in task_rows:
        print(
            f"{r['task_name']}: success={r['success_rate']:.1%} reviewer_quality={r['quality_mean']} "
            f"ground_truth={r['ground_truth_mean']} gt_pass={r['ground_truth_pass_rate']} "
            f"elapsed={r['elapsed_mean']}s retry={r['retry_mean']} zone={r['zone']}"
        )

    if csv_prefix:
        write_csv(f"{csv_prefix}_phase.csv", phase_rows)
        write_csv(f"{csv_prefix}_main_effect.csv", main_rows)
        write_csv(f"{csv_prefix}_combined.csv", combined_rows)
        write_csv(f"{csv_prefix}_task.csv", task_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs_three_day", help="โฟลเดอร์ log JSON จาก experiment")
    parser.add_argument("--csv-prefix", default=None, help="prefix สำหรับ export CSV หลายไฟล์")
    args = parser.parse_args()
    main(args.log_dir, args.csv_prefix)
