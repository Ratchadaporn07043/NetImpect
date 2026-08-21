"""
Pilot Experiment Analyzer (ฉบับขยาย)
=======================================
อ่านไฟล์ log JSON ทั้งหมดใน logs/ แล้วตรวจครบ 8 ประเด็นที่ต้องรู้ก่อนตัดสินใจ
รันเต็มระบบ ไม่ใช่แค่ mean/SD อย่างเดียว:

  A. Mean / SD ต่อ scenario + เช็คจำนวน repeat พอไหม (Coefficient of Variation)
  B. ระบบ crash / error ระหว่างทางไหม (fatal_error, ไฟล์ที่ไม่มี outcome)
  C. เวลาจริงต่อ trial -> ประมาณเวลารวมถ้ารันเต็มระบบ (ใช้เลขจริงจาก scenarios.py/tasks.py)
  D. quality_score parse ได้จริงกี่ % (Reviewer ตอบตามฟอร์แมตที่ตั้งไว้ไหม)
  E. Resource (RAM) มีแนวโน้ม leak ไหมเมื่อรันต่อเนื่อง
  F. Retry/Timeout เกิดใน baseline (no impairment) ด้วยไหม -> สัญญาณปัญหาจากระบบเอง ไม่ใช่ network
  G. ทิศทางผลลัพธ์สมเหตุสมผลไหม (baseline ควรเร็วสุด, severe scenario ควรช้าสุด)
  H. ข้อจำกัด: การ apply/clear tc netem ถูกต้องจริงไหม -> อธิบายว่าเช็คจาก JSON log ไม่ได้
     โดยตรง ต้องดู console output ตอนรัน (หรือเพิ่ม logging ใน controller.py ทีหลัง)

วิธีรัน (จากใน container หลังรัน --pilot เสร็จแล้ว):
    python3 experiment/analyze_pilot.py
    python3 experiment/analyze_pilot.py --log-dir logs
    python3 experiment/analyze_pilot.py --csv summary.csv
"""
import argparse
import glob
import json
import os
import sys
import statistics as stats
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# metric ที่จะดึงมาคำนวณ mean/SD (ต้องตรงกับ key ใน logger.py -> data["outcome"])
NUMERIC_METRICS = [
    "elapsed_seconds",
    "total_tokens",
    "quality_score",
    "retry_count",
    "timeout_count",
    "total_error_count",
]


# ============================================================
# โหลดข้อมูล
# ============================================================
def load_all_records(log_dir: str):
    """
    อ่านทุกไฟล์ .json ใน log_dir คืนค่า:
      - valid: list ของ dict ข้อมูลเต็ม (มี outcome ครบ) พร้อม filepath
      - broken: list ของ (filepath, เหตุผล) ที่อ่านไม่ได้ หรือไม่มี outcome (รันไม่จบจริง)
    เก็บข้อมูลแบบเต็ม (ไม่ใช่แค่ outcome) เพราะ section อื่นต้องใช้
    messages / errors / resource_snapshots ด้วย
    """
    valid, broken = [], []
    for filepath in sorted(glob.glob(os.path.join(log_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            broken.append((filepath, f"อ่านไฟล์ไม่ได้: {e}"))
            continue

        if data.get("outcome") is None:
            broken.append((filepath, "ไม่มี outcome (รันไม่จบ/ไฟล์เขียนไม่สมบูรณ์)"))
            continue

        data["_filepath"] = filepath
        valid.append(data)
    return valid, broken


# ============================================================
# A. Mean / SD + CV check 
# ============================================================
def summarize(valid_records):
    grouped = defaultdict(list)
    for data in valid_records:
        name = data.get("network_condition", {}).get("name", "unknown")
        grouped[name].append(data["outcome"])

    summary = {}
    for name, outcomes in grouped.items():
        n_total = len(outcomes)
        success_count = sum(1 for o in outcomes if o.get("success"))
        entry = {"n_total": n_total, "success_rate": round(success_count / n_total, 3) if n_total else None}

        for metric in NUMERIC_METRICS:
            values = [o[metric] for o in outcomes if o.get(metric) is not None]
            if len(values) == 0:
                entry[metric] = {"mean": None, "sd": None, "n": 0}
            elif len(values) == 1:
                entry[metric] = {"mean": round(values[0], 3), "sd": None, "n": 1}
            else:
                entry[metric] = {
                    "mean": round(stats.mean(values), 3),
                    "sd": round(stats.stdev(values), 3),
                    "n": len(values),
                }
        summary[name] = entry
    return summary


def print_summary_table(summary: dict):
    print("\n" + "=" * 60)
    print("A. สรุป Mean / SD ต่อ Scenario")
    print("=" * 60)
    for name, entry in summary.items():
        print(f"\n=== Scenario: {name} (n={entry['n_total']}, success_rate={entry['success_rate']}) ===")
        header = f"{'metric':<20}{'mean':>12}{'sd':>12}{'n':>6}"
        print(header)
        print("-" * len(header))
        for metric in NUMERIC_METRICS:
            m = entry[metric]
            mean_str = f"{m['mean']:.2f}" if m["mean"] is not None else "-"
            sd_str = f"{m['sd']:.2f}" if m["sd"] is not None else "-"
            print(f"{metric:<20}{mean_str:>12}{sd_str:>12}{m['n']:>6}")


def check_variance_warning(summary: dict, cv_threshold: float = 0.3):
    print("\n" + "-" * 60)
    print("ตรวจสอบว่าจำนวน repeat พอไหม (Coefficient of Variation = SD/mean)")
    print("-" * 60)
    any_warning = False
    for name, entry in summary.items():
        for metric in ("elapsed_seconds", "total_tokens"):
            m = entry[metric]
            if m["mean"] is None or m["sd"] is None or m["mean"] == 0:
                continue
            cv = m["sd"] / m["mean"]
            flag = "⚠️ สูง — ควรเพิ่ม repeats" if cv > cv_threshold else "✅ โอเค"
            if cv > cv_threshold:
                any_warning = True
            print(f"  [{name}] {metric}: CV = {cv:.2%}  {flag}")

    if any_warning:
        print(f"\n⚠️ พบ scenario ที่ CV > {cv_threshold:.0%} — แนะนำเพิ่ม REPEATS_PER_SCENARIO "
              f"เป็น 15-20 ก่อนรันเต็ม")
    else:
        print(f"\n✅ ทุก scenario มี CV <= {cv_threshold:.0%} — จำนวน repeat น่าจะเพียงพอสำหรับรันเต็ม")
    return any_warning


# ============================================================
# B. ระบบ crash / error ระหว่างทางไหม
# ============================================================
def check_crashes_and_errors(valid_records, broken_records):
    print("\n" + "=" * 60)
    print("B. เช็คว่าระบบ crash / error ระหว่างทางไหม")
    print("=" * 60)

    if broken_records:
        print(f"⚠️ พบ {len(broken_records)} ไฟล์ที่รันไม่จบ/อ่านไม่ได้:")
        for filepath, reason in broken_records:
            print(f"    - {os.path.basename(filepath)}: {reason}")
    else:
        print("✅ ไม่มีไฟล์ log ที่หายไปหรืออ่านไม่ได้ — ทุก trial เขียน log จบสมบูรณ์")

    # นับ fatal_error / error รวมต่อ scenario
    fatal_by_scenario = defaultdict(int)
    total_errors_by_scenario = defaultdict(int)
    for data in valid_records:
        name = data.get("network_condition", {}).get("name", "unknown")
        errors = data.get("errors", [])
        fatal_count = sum(1 for e in errors if e.get("error_type") == "fatal_error")
        fatal_by_scenario[name] += fatal_count
        total_errors_by_scenario[name] += data["outcome"].get("total_error_count", 0)

    any_fatal = any(v > 0 for v in fatal_by_scenario.values())
    if any_fatal:
        print("\n⚠️ พบ fatal_error ในบาง scenario (task ล่มจน retry ครบแล้วยังไม่จบ):")
        for name, count in fatal_by_scenario.items():
            if count > 0:
                print(f"    - {name}: fatal_error {count} ครั้ง")
        print("   -> ควรดู detail ของ error ใน field 'errors' ของไฟล์ log ที่เกี่ยวข้อง "
              "ก่อนรันเต็ม เพราะถ้าเกิดถี่ ผลรันเต็มจะมี success=False ปนเยอะโดยไม่เกี่ยวกับ "
              "คุณภาพงานจริง")
    else:
        print("\n✅ ไม่พบ fatal_error เลยในทุก trial ของ pilot")

    return {"broken_count": len(broken_records), "any_fatal": any_fatal,
            "total_errors_by_scenario": dict(total_errors_by_scenario)}


# ============================================================
# C. เวลาจริงต่อ trial -> ประมาณเวลารวมถ้ารันเต็มระบบ
# ============================================================
def check_timing_and_estimate_full_run(valid_records, full_scenarios_count=None,
                                        full_tasks_count=None, full_repeats=None):
    print("\n" + "=" * 60)
    print("C. เวลาจริงต่อ trial และประมาณเวลารวมถ้ารันเต็มระบบ")
    print("=" * 60)

    elapsed_by_scenario = defaultdict(list)
    for data in valid_records:
        name = data.get("network_condition", {}).get("name", "unknown")
        elapsed = data["outcome"].get("elapsed_seconds")
        if elapsed is not None:
            elapsed_by_scenario[name].append(elapsed)

    all_elapsed = [e for values in elapsed_by_scenario.values() for e in values]
    if not all_elapsed:
        print("⚠️ ไม่มีข้อมูล elapsed_seconds เลย ข้าม section นี้")
        return

    for name, values in elapsed_by_scenario.items():
        mean_e = stats.mean(values)
        print(f"  [{name}] elapsed เฉลี่ย = {mean_e:.1f} วิ (n={len(values)}, "
              f"min={min(values):.1f}, max={max(values):.1f})")

    overall_mean = stats.mean(all_elapsed)
    print(f"\n  ค่าเฉลี่ยรวมทุก scenario ใน pilot: {overall_mean:.1f} วิ/trial")

    # ลองพยายาม import ตัวเลขจริงจาก scenarios.py/tasks.py เพื่อประมาณเวลารันเต็ม
    if full_scenarios_count and full_tasks_count and full_repeats:
        full_total_trials = full_scenarios_count * full_tasks_count * full_repeats
        est_seconds = overall_mean * full_total_trials
        est_hours = est_seconds / 3600
        print(f"\n  ถ้ารันเต็ม: {full_scenarios_count} scenario-runs x {full_tasks_count} tasks "
              f"x {full_repeats} repeats = {full_total_trials} trials")
        print(f"  ประมาณเวลารวม ≈ {est_hours:.1f} ชั่วโมง "
              f"(ใช้ค่าเฉลี่ยจาก pilot คูณตรงๆ — เป็นการประมาณคร่าวๆ เพราะเวลาในแต่ละ "
              f"tournament match/combined scenario อาจแกว่งตาม task, model inference และ network condition)")
    else:
        print("\n  (ไม่ได้ระบุจำนวน scenario/task/repeat ของรันเต็ม จึงไม่ประมาณเวลารวมให้)")


# ============================================================
# D. quality_score parse ได้จริงกี่ %
# ============================================================
def check_quality_score_parse_rate(valid_records):
    print("\n" + "=" * 60)
    print("D. quality_score parse ได้จริงกี่ % (Reviewer ตอบตามฟอร์แมตไหม)")
    print("=" * 60)

    by_scenario = defaultdict(lambda: {"total": 0, "parsed": 0})
    for data in valid_records:
        name = data.get("network_condition", {}).get("name", "unknown")
        by_scenario[name]["total"] += 1
        if data["outcome"].get("quality_score") is not None:
            by_scenario[name]["parsed"] += 1

    any_low = False
    for name, counts in by_scenario.items():
        rate = counts["parsed"] / counts["total"] if counts["total"] else 0
        flag = "⚠️ ต่ำ" if rate < 0.9 else "✅ โอเค"
        if rate < 0.9:
            any_low = True
        print(f"  [{name}] parse ได้ {counts['parsed']}/{counts['total']} ({rate:.0%})  {flag}")

    if any_low:
        print("\n⚠️ บาง scenario parse quality_score ไม่ได้เกิน 10% ของ trial — ควรตรวจ "
              "system prompt ของ Reviewer agent ใน multi_agent.py ว่าบังคับฟอร์แมต "
              "'SCORE: X' ชัดเจนพอหรือยัง ก่อนรันเต็ม (ไม่งั้นข้อมูล quality_score "
              "จะหายไปเยอะตอนวิเคราะห์ผลจริง)")
    else:
        print("\n✅ quality_score parse ได้เกิน 90% ในทุก scenario — รูปแบบคำตอบของ "
              "Reviewer เชื่อถือได้")


# ============================================================
# E. Resource (RAM) มีแนวโน้ม leak ไหม
# ============================================================
def check_resource_leak(valid_records):
    print("\n" + "=" * 60)
    print("E. เช็คแนวโน้ม RAM leak เมื่อรันต่อเนื่องหลาย trial")
    print("=" * 60)

    # รวม resource_snapshots จากทุกไฟล์ เรียงตาม timestamp จริง
    all_snapshots = []
    for data in valid_records:
        all_snapshots.extend(data.get("resource_snapshots", []))
    all_snapshots.sort(key=lambda s: s["timestamp"])

    if len(all_snapshots) < 4:
        print("⚠️ มี resource snapshot น้อยเกินไป ข้าม section นี้")
        return

    ram_values = [s["ram_used_mb"] for s in all_snapshots]
    half = len(ram_values) // 2
    first_half_mean = stats.mean(ram_values[:half])
    second_half_mean = stats.mean(ram_values[half:])
    diff_pct = (second_half_mean - first_half_mean) / first_half_mean * 100 if first_half_mean else 0

    print(f"  RAM used เฉลี่ยครึ่งแรกของ pilot : {first_half_mean:.1f} MB")
    print(f"  RAM used เฉลี่ยครึ่งหลังของ pilot: {second_half_mean:.1f} MB")
    print(f"  เปลี่ยนแปลง: {diff_pct:+.1f}%")

    if diff_pct > 15:
        print("\n⚠️ RAM เพิ่มขึ้นเกิน 15% ระหว่างครึ่งแรกกับครึ่งหลังของ pilot — "
              "สัญญาณว่าอาจมี memory leak (จาก Ollama หรือ multi-agent library) "
              "ถ้ารัน full tournament ต่อเนื่องนานหลายชั่วโมง เสี่ยง container ล่มเพราะ "
              "RAM เต็มกลางทาง ควรตรวจก่อนรันเต็ม")
    else:
        print("\n✅ RAM ไม่มีแนวโน้มเพิ่มขึ้นผิดปกติ ดูปลอดภัยสำหรับรันต่อเนื่องยาวๆ")


# ============================================================
# F. Retry/Timeout เกิดใน baseline ด้วยไหม (สัญญาณปัญหาจากระบบเอง)
# ============================================================
def _is_baseline_record(data, baseline_name: str = "baseline"):
    scenario = data.get("network_condition", {})
    if scenario.get("name") == baseline_name:
        return True
    requested_delay = scenario.get("requested_delay_ms", scenario.get("delay_ms", 0))
    return requested_delay == 0 and scenario.get("jitter_ms", 0) == 0 and scenario.get("loss_pct", 0) == 0


def check_baseline_stability(valid_records, baseline_name: str = "baseline"):
    print("\n" + "=" * 60)
    print(f"F. Retry/Timeout เกิดใน '{baseline_name}' (ไม่มี network impairment) ด้วยไหม")
    print("=" * 60)

    baseline_records = [d for d in valid_records if _is_baseline_record(d, baseline_name)]

    if not baseline_records:
        print(f"⚠️ ไม่พบ scenario ชื่อ '{baseline_name}' ใน log — ข้าม section นี้")
        return

    total_retry = sum(d["outcome"].get("retry_count", 0) for d in baseline_records)
    total_timeout = sum(d["outcome"].get("timeout_count", 0) for d in baseline_records)
    n = len(baseline_records)

    print(f"  จำนวน trial ของ baseline: {n}")
    print(f"  รวม retry_count: {total_retry}  |  รวม timeout_count: {total_timeout}")

    if total_retry > 0 or total_timeout > 0:
        print(f"\n⚠️ baseline ไม่มี network impairment เลย แต่ยังเกิด retry/timeout "
              f"— แปลว่าปัญหาไม่ได้มาจาก network อย่างเดียว อาจมาจากตัวระบบเอง "
              f"(Ollama โหลดช้า, GPU ไม่พอ, MODEL_NAME ตอบช้า ฯลฯ) ถ้าไม่แก้ก่อนรันเต็ม "
              f"ข้อมูล retry/timeout จะปนกันระหว่าง 'network effect' กับ 'system instability' "
              f"แยกไม่ออกตอนวิเคราะห์ผล")
    else:
        print(f"\n✅ baseline ไม่มี retry/timeout เลย — ระบบพื้นฐานเสถียรดี "
              f"retry/timeout ที่เจอใน scenario อื่นน่าจะมาจาก network impairment จริงๆ")


# ============================================================
# G. ทิศทางผลลัพธ์สมเหตุสมผลไหม (sanity check)
# ============================================================
def check_result_direction_sanity(summary: dict, baseline_name: str = "baseline"):
    print("\n" + "=" * 60)
    print("G. ทิศทางผลลัพธ์สมเหตุสมผลไหม (sanity check)")
    print("=" * 60)

    baseline_key = baseline_name if baseline_name in summary else None
    if baseline_key is None:
        for candidate in ("combined_d0000_loss0_j000", "factorial_baseline", "main_delay_d0000"):
            if candidate in summary:
                baseline_key = candidate
                break

    if baseline_key is None or summary[baseline_key]["elapsed_seconds"]["mean"] is None:
        print(f"⚠️ ไม่มีข้อมูล baseline ที่สมบูรณ์พอ ข้าม section นี้")
        return

    baseline = summary[baseline_key]["elapsed_seconds"]
    baseline_mean = baseline["mean"]
    baseline_sd = baseline["sd"] or 0

    print(f"  baseline elapsed เฉลี่ย = {baseline_mean:.1f} วิ, SD = {baseline_sd:.1f} วิ")

    any_strong_warning = False

    for name, entry in summary.items():
        if name == baseline_key:
            continue

        m = entry["elapsed_seconds"]
        mean_e = m["mean"]
        sd_e = m["sd"] or 0

        if mean_e is None:
            continue

        diff = mean_e - baseline_mean
        diff_pct = (diff / baseline_mean) * 100 if baseline_mean else 0

        # tolerance ใช้ baseline SD เป็นกันชน เพราะ LLM inference แกว่งสูงมาก
        within_noise = abs(diff) <= baseline_sd

        if diff >= 0:
            print(
                f"  ✅ [{name}] mean={mean_e:.1f}s, SD={sd_e:.1f}s, "
                f"diff={diff:+.1f}s ({diff_pct:+.1f}%) — ช้ากว่า baseline"
            )
        elif within_noise:
            print(
                f"  ⚠️ [{name}] mean={mean_e:.1f}s, SD={sd_e:.1f}s, "
                f"diff={diff:+.1f}s ({diff_pct:+.1f}%) — เร็วกว่า baseline "
                f"แต่ยังอยู่ในช่วงความแปรปรวนของ baseline จึงยังสรุปทิศทางไม่ได้"
            )
        else:
            any_strong_warning = True
            print(
                f"  ❌ [{name}] mean={mean_e:.1f}s, SD={sd_e:.1f}s, "
                f"diff={diff:+.1f}s ({diff_pct:+.1f}%) — เร็วกว่า baseline "
                f"เกินช่วงความแปรปรวน ควรตรวจ design/task เพิ่ม"
            )

    if any_strong_warning:
        print(
            "\n⚠️ Section G ยังไม่ผ่านแบบเข้มงวด: ไม่ควรสรุปว่า network impairment "
            "ทำให้ช้าลงจาก elapsed_seconds เพียงอย่างเดียว ควรเพิ่ม task ที่มีหลายรอบสนทนา "
            "หรือเพิ่มระดับ impairment ให้ผลของ network เด่นกว่า LLM inference noise"
        )
    else:
        print(
            "\n✅ Section G ไม่พบความผิดปกติรุนแรงเมื่อพิจารณา SD ของ baseline แล้ว "
            "แต่ควรรายงานว่า elapsed_seconds มี noise สูงจาก LLM inference"
        )

# ============================================================
# H. apply()/clear() ของ tc netem ถูกต้องจริงไหม
# ============================================================
def check_network_apply_clear(valid_records):
    print("\n" + "=" * 60)
    print("H. เช็คว่า apply()/clear() ของ tc netem สำเร็จจริงไหม")
    print("=" * 60)

    apply_fail_by_scenario = defaultdict(list)
    clear_fail_by_scenario = defaultdict(list)

    for data in valid_records:
        name = data.get("network_condition", {}).get("name", "unknown")
        for e in data.get("errors", []):
            if e.get("error_type") == "network_apply_failed":
                apply_fail_by_scenario[name].append(e.get("detail", ""))
            elif e.get("error_type") == "network_clear_failed":
                clear_fail_by_scenario[name].append(e.get("detail", ""))

    any_fail = bool(apply_fail_by_scenario) or bool(clear_fail_by_scenario)

    if not any_fail:
        print("✅ ไม่พบ network_apply_failed หรือ network_clear_failed เลยในทุก trial "
              "— คำสั่ง tc netem สำเร็จ (returncode=0) ทุกครั้งที่เรียก apply()/clear()")
    else:
        if apply_fail_by_scenario:
            print("\n⚠️ พบ apply() ล้มเหลว (returncode != 0) ใน scenario ต่อไปนี้:")
            for name, details in apply_fail_by_scenario.items():
                print(f"    - {name}: {len(details)} ครั้ง เช่น '{details[0][:150]}'")
        if clear_fail_by_scenario:
            print("\n⚠️ พบ clear() ล้มเหลว (returncode != 0) ใน scenario ต่อไปนี้:")
            for name, details in clear_fail_by_scenario.items():
                print(f"    - {name}: {len(details)} ครั้ง เช่น '{details[0][:150]}'")
            print("   -> ถ้า clear() ล้มเหลว rule เดิมอาจค้างข้ามไปปน scenario ถัดไป "
                  "(เป็น confound อันตราย) ควรตรวจสิทธิ์ NET_ADMIN ของ container "
                  "ก่อนรันเต็ม")

    return {"any_fail": any_fail}


def print_network_check_note_if_missing(valid_records):
    """
    ถ้า log เก่า (รันด้วย run_experiment.py เวอร์ชันก่อนแก้) ไม่มี error_type
    'network_apply_failed'/'network_clear_failed' เลยแม้แต่ entry เดียว ให้เตือนว่า
    อาจเป็นเพราะไฟล์ log มาจากโค้ดเวอร์ชันเก่าที่ยังไม่ log ค่านี้ ไม่ใช่เพราะไม่มีปัญหาจริง
    """
    error_types_seen = set()
    for data in valid_records:
        for e in data.get("errors", []):
            error_types_seen.add(e.get("error_type"))

    if "network_apply_failed" not in error_types_seen and "network_clear_failed" not in error_types_seen:
        # อาจจะ "ไม่มีปัญหาจริง" หรือ "log มาจากโค้ดเก่าที่ยัง log ไม่ครอบคลุม" ก็ได้
        # แจ้งให้รู้ตัวไว้เฉยๆ ไม่ต้องเป็น warning สีแดง เพราะเป็นเรื่องปกติถ้าไม่มีปัญหาจริง
        print("  หมายเหตุ: ไม่พบ error_type 'network_apply_failed'/'network_clear_failed' "
              "เลยใน log ชุดนี้ ถ้า log นี้รันด้วย run_experiment.py เวอร์ชันล่าสุด "
              "(ที่มี _log_network_result) แปลว่า tc ทำงานสำเร็จจริงทุกครั้ง แต่ถ้า log นี้ "
              "รันด้วยเวอร์ชันเก่ากว่านั้น ผลนี้จะไม่มีความหมาย เพราะโค้ดเก่ายังไม่เคย log "
              "ค่านี้ไว้เลย")


# ============================================================
# CSV export 
# ============================================================
def save_csv(summary: dict, csv_path: str):
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["scenario", "n_total", "success_rate"]
        for metric in NUMERIC_METRICS:
            header += [f"{metric}_mean", f"{metric}_sd", f"{metric}_n"]
        writer.writerow(header)
        for name, entry in summary.items():
            row = [name, entry["n_total"], entry["success_rate"]]
            for metric in NUMERIC_METRICS:
                m = entry[metric]
                row += [m["mean"], m["sd"], m["n"]]
            writer.writerow(row)
    print(f"\nบันทึกผลสรุปเป็น CSV แล้วที่: {os.path.abspath(csv_path)}")


# ============================================================
# main
# ============================================================
def main(log_dir: str = "logs", csv_path: str = None):
    print(f"กำลังอ่าน log จาก: {os.path.abspath(log_dir)}")
    valid_records, broken_records = load_all_records(log_dir)
    print(f"พบ {len(valid_records)} trial ที่มี outcome สมบูรณ์ "
          f"({len(broken_records)} ไฟล์รันไม่จบ/อ่านไม่ได้)")

    if not valid_records:
        print("ไม่พบข้อมูล outcome เลย ตรวจสอบว่ารัน experiment เสร็จแล้วหรือยัง "
              "และ --log-dir ชี้ถูกโฟลเดอร์ไหม")
        return

    # พยายาม import ตัวเลขจริงจาก scenarios.py/tasks.py เพื่อประมาณเวลารันเต็ม (section C)
    full_scenarios_count = full_tasks_count = full_repeats = None
    try:
        from scenarios import COMBINED_SCENARIOS, REPEATS_PER_SCENARIO, SCENARIOS, TOURNAMENT_MATCHES
        from tasks import TASKS
        # tournament 1 match มี 2 scenario-runs (side A และ side B), combined นับ 1 scenario-run ต่อ scenario
        full_scenarios_count = len(TOURNAMENT_MATCHES) * 2 + len(COMBINED_SCENARIOS)
        if full_scenarios_count == 0:
            full_scenarios_count = len(SCENARIOS)
        full_tasks_count = len(TASKS)
        full_repeats = REPEATS_PER_SCENARIO
    except ImportError:
        pass  # ไม่ import ได้ก็ข้ามการประมาณเวลารันเต็มไป (section C จะแจ้งเอง)

    summary = summarize(valid_records)

    print_summary_table(summary)                                  # A
    check_variance_warning(summary)                                # A (CV)
    check_crashes_and_errors(valid_records, broken_records)        # B
    check_timing_and_estimate_full_run(                            # C
        valid_records, full_scenarios_count, full_tasks_count, full_repeats)
    check_quality_score_parse_rate(valid_records)                  # D
    check_resource_leak(valid_records)                             # E
    check_baseline_stability(valid_records)                        # F
    check_result_direction_sanity(summary)                         # G
    check_network_apply_clear(valid_records)                       # H
    print_network_check_note_if_missing(valid_records)             # H (หมายเหตุเสริม)

    if csv_path:
        save_csv(summary, csv_path)

    print("\n" + "=" * 60)
    print("จบการตรวจสอบ pilot ครบทุกประเด็น (A-H)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs", help="โฟลเดอร์ที่เก็บไฟล์ log JSON")
    parser.add_argument("--csv", default=None, help="ถ้าระบุ จะเซฟผลสรุปเป็นไฟล์ CSV ด้วย")
    args = parser.parse_args()

    main(log_dir=args.log_dir, csv_path=args.csv)