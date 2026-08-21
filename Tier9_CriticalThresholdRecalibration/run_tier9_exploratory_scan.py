#!/usr/bin/env python3
"""
Tier 9, Step 1 - Exploratory scan for the new critical loss threshold.
========================================================================
Question addressed by this script
----------------------
Tier8 found that mitigation="none" (the control arm) did not fail at
loss=75% in the current environment (20/20 in every tested item, confirmed not to
be caused by thinking mode). The original item 3 (660 trials, 11 loss levels from
0-75%) also found approximately 100% completion for `none` at every tested level.
tested throughout the project (no data above 75% exists). Confirmed cause: overall
inference, excluding thinking, became approximately twice as fast than in Tier5.
Among first-try successes, median elapsed time was 248s in Tier5 versus 127s now,
shortening connections and reducing exposure to packet drops.

This script therefore searches for the **new critical point** by scanning
`mitigation="none"` above 75% with a small sample (12 trials per level by default).
Its result supplies `--critical-loss-pct` to `run_tier9_critical_comparison.py` (Step 2).

⚠️ Warning: this small-sample scan (n=8-12 per level) only locates a candidate
critical point. It is not paper-ready evidence; run run_tier9_critical_comparison.py
with n=20 per arm at the selected point for publishable estimates.

Pre-flight self-test
---------------------
Before each run, this script calls OllamaNativeThinkOffClient once to confirm that
thinking is disabled (elapsed < 5s, no
reasoning field) — ถ้าไม่ผ่านจะหยุดทันทีก่อนเสียเวลารันจริงหลายชั่วโมงไปเปล่าๆ
บนข้อมูลที่ปนเปื้อน thinking mode อีกครั้ง

Usage
---------
    # 1. Run offline checks first (no real Ollama/tc).
    cd Tier9_CriticalThresholdRecalibration && python3 -m pytest tests_tier9/ -q

    # 2. Preview the run without touching live services.
    python3 run_tier9_exploratory_scan.py --dry-run

    # 3. Run the experiment; adjust --loss-levels/--repeats as needed.
    python3 run_tier9_exploratory_scan.py --resume
"""
import argparse
import os
import sys
import time
from collections import defaultdict

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # Tier9_CriticalThresholdRecalibration/
# Tier9 is fully standalone and does not depend on Tier8 or root experiment files.
# Previously imported files are local tier9_* copies, avoiding name collisions and
# sys.path shadowing between tiers.
sys.path.insert(0, _THIS_DIR)

from tier9_controller import NetworkController  # noqa: E402
from tier9_logger import ExperimentLogger  # noqa: E402
from tier9_checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from tier9_tasks import TASKS  # noqa: E402
from ollama_native_client import OllamaNativeThinkOffClient  # noqa: E402

DEFAULT_LOSS_LEVELS = [80, 85, 90, 95, 99]
DEFAULT_REPEATS = 3  # x 4 tasks = 12 trials/ระดับ
CONDITION = "none"
CRITICAL_THRESHOLD_PCT = 0.85  # Same threshold as the original item 4 falsification check.


def _self_test_native_client_fast_and_thinking_off():
    """เหมือน smoke_test_thinking_off.py::stage1 ทุกประการ (warm-up แล้ววัดจริง)
    แต่ฝังไว้ในตัวสคริปต์รันจริงเลย เพื่อกันไม่ให้เผลอรันหลายชั่วโมงบนข้อมูลที่
    thinking mode แอบเปิดอยู่โดยไม่รู้ตัว"""
    print("[self-test] Verify that the native client is fast and thinking is disabled...")
    config = {"model": os.environ.get("MODEL_NAME", "qwen3:8b"),
             "base_url": os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
             "timeout": 180, "temperature": 0.3}
    client = OllamaNativeThinkOffClient(config)
    params = {"messages": [{"role": "user", "content": "Reply with exactly one word: OK"}], "n": 1}

    warmup_start = time.time()
    client.create(params)
    print(f"  warm-up เสร็จใน {time.time() - warmup_start:.2f}s (cold model load ถ้าเป็นครั้งแรก)")

    start = time.time()
    response = client.create(params)
    elapsed = time.time() - start
    content = response.choices[0].message.content

    if elapsed >= 5.0:
        raise SystemExit(
            f"\n[SELF-TEST FAILED] native client ช้าผิดคาด ({elapsed:.2f}s >= 5s) หลังอุ่นเครื่องแล้ว "
            "— thinking mode อาจยังเปิดอยู่ หรือ Ollama มีปัญหาอื่น ห้ามรันต่อจนกว่าจะแก้ได้ "
            "(ลอง raw curl ยืนยันตาม README.md ของ thinking_off_diagnostic ก่อน)"
        )
    if not content:
        raise SystemExit("\n[SELF-TEST FAILED] content ว่างเปล่า — ตรวจว่า Ollama รันอยู่จริง")
    print(f"  ผ่าน: {elapsed:.2f}s, content={content!r}, ไม่มี reasoning/thinking field")


def build_scenarios(loss_levels):
    return [
        {
            "name": f"t9_scan_loss{loss}",
            "scenario_type": "critical_threshold_scan",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss,
            "bandwidth_kbit": None,
            "note": f"exploratory scan หา critical threshold ใหม่ (loss={loss}%, "
                    f"mitigation=none, สภาพแวดล้อมปัจจุบัน thinking-off)",
            "experiment_phase": "tier9_exploratory_scan",
        }
        for loss in loss_levels
    ]


def _trial_key(scenario, task_name, repeat_index):
    return f"{scenario['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    print(f"  [{scenario['name']}] task={task_name} run={run_index} -> loss={scenario['loss_pct']}%")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"], jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"], bandwidth_kbit=scenario.get("bandwidth_kbit"),
    )
    logger.data.setdefault("network_commands", []).append({"action": "apply", "result": apply_result})

    if apply_result.get("returncode") not in (0, None):
        logger.log_error(error_type="invalid_trial", detail="network apply failed; skipped LLM run")
        logger.log_outcome(success=False, rounds=0, rejections=0,
                           elapsed_seconds=time.time() - logger.start_time)
        print("    -> INVALID TRIAL: network apply failed")
    else:
        try:
            result = multi_agent_module.run_multi_agent_task(
                task_prompt, logger=logger, task_name=task_name,
                strict_reviewer=False, mitigation=CONDITION, network_condition=scenario,
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"elapsed={result['elapsed_seconds']}s")
        except Exception as exc:  # noqa: BLE001
            logger.log_error(error_type="fatal_error", detail=str(exc)[:300])
            logger.log_outcome(success=False, rounds=0, rejections=0,
                               elapsed_seconds=time.time() - logger.start_time)
            print(f"    -> FATAL ERROR: {exc}")

    clear_result = net.clear()
    logger.data.setdefault("network_commands", []).append({"action": "clear", "result": clear_result})
    return logger.save()


def _print_scan_summary(log_dir, loss_levels):
    import glob
    import json

    counts = {f"t9_scan_loss{loss}": [0, 0] for loss in loss_levels}
    for path in glob.glob(os.path.join(log_dir, "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        name = (d.get("network_condition") or {}).get("name")
        if name not in counts:
            continue
        counts[name][1] += 1
        if (d.get("outcome") or {}).get("success"):
            counts[name][0] += 1

    print("\n" + "=" * 70)
    print("สรุปผล exploratory scan (mitigation=none, สภาพแวดล้อมปัจจุบัน)")
    print("=" * 70)
    candidate = None
    for loss in sorted(loss_levels):
        s, t = counts[f"t9_scan_loss{loss}"]
        rate = (s / t) if t else None
        rate_str = f"{s}/{t} ({100*rate:.0f}%)" if t else "0/0 (ยังไม่มีข้อมูล)"
        flag = ""
        if rate is not None and rate <= CRITICAL_THRESHOLD_PCT and candidate is None:
            candidate = loss
            flag = "  <-- จุดแรกที่เริ่มเห็น degradation ชัดเจน"
        print(f"  loss={loss}%: {rate_str}{flag}")

    print("-" * 70)
    if candidate is not None:
        print(f"แนะนำ: ใช้ loss={candidate}% เป็นจุดวิกฤตใหม่สำหรับ "
              f"run_tier9_critical_comparison.py --critical-loss-pct {candidate}")
        print(f"(เกณฑ์ที่ใช้เลือก: completion <= {CRITICAL_THRESHOLD_PCT:.0%} — เกณฑ์เดียวกับ "
              f"falsification check ของข้อ 4 เดิมใน Tier 8 เพื่อความสม่ำเสมอ)")
    else:
        print("ไม่พบจุดที่ completion ตกลงมา <= 85% เลยแม้แต่ระดับเดียวในช่วงที่ทดสอบ "
              f"({min(loss_levels)}-{max(loss_levels)}%) — ตัวเลือกที่ควรพิจารณาต่อ:")
        print("  1. ขยายช่วงการสแกนให้สูงขึ้นอีก (แต่ 99% ใกล้ทฤษฎีสูงสุดที่มีความหมายแล้ว "
              "netem ที่ loss=100% คือดรอปทุกแพ็กเก็ต ไม่มี trial ไหนสำเร็จได้เลยตามนิยาม)")
        print("  2. พิจารณาแกนอื่นที่ยังไม่เคยดัน limit ในสภาพแวดล้อมนี้ (เช่น delay สูงมากๆ "
              "ร่วมกับ loss, หรือ bandwidth ต่ำมากๆ ร่วมกับ loss) แทนแกน loss เดี่ยวๆ")
        print("  3. ยอมรับว่า arm ควบคุมของสภาพแวดล้อมปัจจุบันแข็งแกร่งกว่าที่คาดมาก และรายงาน "
              "เป็นข้อค้นพบเชิง methodology แทน (serving-stack drift ทำให้ threshold เดิมใช้ไม่ได้)")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir", default=os.path.join(_THIS_DIR, "logs_tier9_exploratory_scan"))
    ap.add_argument("--loss-levels", default=",".join(str(x) for x in DEFAULT_LOSS_LEVELS),
                    help="comma-separated loss percentages เช่น '80,85,90,95,99'")
    ap.add_argument("--repeats", type=int, default=DEFAULT_REPEATS,
                    help=f"จำนวนรอบต่อ task ต่อระดับ loss (default {DEFAULT_REPEATS} "
                         f"x 4 tasks = {DEFAULT_REPEATS*4} trials/ระดับ)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-self-test", action="store_true",
                    help="ข้าม pre-flight self-test ของ native client (ไม่แนะนำ — ใช้เฉพาะ debug)")
    args = ap.parse_args()

    loss_levels = [int(x.strip()) for x in args.loss_levels.split(",") if x.strip()]
    tasks = TASKS
    scenarios = build_scenarios(loss_levels)
    total = len(scenarios) * len(tasks) * args.repeats

    print("Tier 9, ขั้นตอนที่ 1 — exploratory scan หา critical loss threshold ใหม่")
    print(f"  loss levels: {loss_levels}")
    print(f"  {len(scenarios)} ระดับ x {len(tasks)} tasks x {args.repeats} repeats = {total} trials")
    print(f"  mitigation={CONDITION!r} เท่านั้น (arm ควบคุม — จุดประสงค์คือหาว่าจุดไหนเริ่มล้มเหลว)")
    print(f"  log dir: {args.log_dir}")
    print(f"  ประมาณเวลา: ~{total * 3 / 60:.1f}-{total * 5 / 60:.1f} ชั่วโมง "
          f"(ประมาณ 3-5 นาที/trial ที่ loss สูงมาก แม้ thinking ปิดแล้ว เพราะ retry/"
          f"connection error ยังเกิดได้ที่ loss ระดับนี้)")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log, ยังไม่ self-test")
        return

    if not args.skip_self_test:
        _self_test_native_client_fast_and_thinking_off()

    import multi_agent as multi_agent_module  # noqa: E402  (Tier 9 เอง, บน sys.path แล้ว)

    net = NetworkController(iface=args.iface, direction="egress")
    checkpoint = load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, args.repeats + 1):
        for scenario in scenarios:
            for task_name, task_prompt in tasks.items():
                key = _trial_key(scenario, task_name, repeat_index)
                if should_skip(args.resume, checkpoint, key):
                    print(f"  [SKIP] {key}")
                    continue
                log_file = run_single_trial(net, scenario, task_name, task_prompt,
                                            repeat_index, args.log_dir, multi_agent_module)
                if checkpoint is not None:
                    mark_completed(args.log_dir, checkpoint, key, log_file)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    _print_scan_summary(args.log_dir, loss_levels)


if __name__ == "__main__":
    main()
