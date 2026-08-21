"""
run_tier1.py — ตัวรัน Tier 1 (เจาะจุดในแกนที่มีอยู่แล้ว)
================================================================
ไม่แก้ไขไฟล์ต้นฉบับของโปรเจกต์เลย (scenarios.py, run_experiment.py, multi_agent.py
, logger.py, controller.py, evaluator.py, tasks.py ทั้งหมดเหมือนเดิม 100%)
ใช้ฟังก์ชันเดิมทั้งหมดจาก experiment/run_experiment.py (run_single_trial, checkpoint
ฯลฯ) เพื่อให้พฤติกรรมการรันจริง (LLM call, logging, network apply) เหมือนกับ
three-day experiment เดิมทุกประการ — ต่างกันแค่ "scenario ไหนถูกเลือกมารัน"

วิธีติดตั้ง/วางไฟล์:
  1. คัดลอกโฟลเดอร์นี้ทั้งโฟลเดอร์ไปวางไว้ "ข้างใน" root ของโปรเจกต์ NetImpact จริง
     (ตำแหน่งเดียวกับที่มีไฟล์ multi_agent.py, logger.py, และโฟลเดอร์ experiment/)
     เช่น:
         NetImpact/
           multi_agent.py
           logger.py
           experiment/
           Tier1_เจาะจุดในแกนที่มีอยู่/   <-- เอาโฟลเดอร์นี้มาวางตรงนี้
             tier1_scenarios.py
             run_tier1.py
  2. รันจากภายใน container เดียวกับที่รัน run_experiment.py เดิม (มี Ollama/tc/netem พร้อม)
     cd NetImpact
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --dry-run
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --part loss_cliff
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --part delay_recheck
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --part delay_extended
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --part jitter_extended
     python3 Tier1_เจาะจุดในแกนที่มีอยู่/run_tier1.py --part all --resume

  หมายเหตุ: ถ้าจะรันจาก path อื่น ให้ตั้ง env var NETIMPACT_PROJECT_ROOT ชี้ไปที่ root
  ของโปรเจกต์ก่อน เช่น:
     NETIMPACT_PROJECT_ROOT=/root/NetImpact python3 run_tier1.py --part all

log จะถูกเขียนไปที่ logs_tier1/ (แยกจาก logs_three_day/ เดิมโดยสิ้นเชิง ไม่มีทางชนกัน)
checkpoint แยกเป็นของตัวเอง (logs_tier1/_checkpoint/checkpoint.json) รองรับ --resume
เหมือน run_experiment.py เดิม
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from experiment.controller import NetworkController  # noqa: E402
from experiment.run_experiment import (  # noqa: E402
    _run_scenario,
    _load_checkpoint,
    _open_progress,
    _print_dry_run_summary,
)
from experiment.tasks import TASKS  # noqa: E402

from tier1_scenarios import (  # noqa: E402
    TIER1_LOSS_CLIFF_SCENARIOS,
    TIER1_DELAY_EXTENDED_SCENARIOS,
    TIER1_JITTER_EXTENDED_SCENARIOS,
    TIER1_DELAY_250_RECHECK_SCENARIO,
    REPEATS_PER_NEW_LEVEL,
    DELAY_250_RECHECK_START_RUN_INDEX,
    DELAY_250_RECHECK_REPEATS,
)


PARTS = {
    "loss_cliff": {
        "scenarios": TIER1_LOSS_CLIFF_SCENARIOS,
        "phase": "tier1_loss_cliff",
        "repeats": REPEATS_PER_NEW_LEVEL,
        "start_run_index": 1,
    },
    "delay_extended": {
        "scenarios": TIER1_DELAY_EXTENDED_SCENARIOS,
        "phase": "tier1_delay_extended",
        "repeats": REPEATS_PER_NEW_LEVEL,
        "start_run_index": 1,
    },
    "jitter_extended": {
        "scenarios": TIER1_JITTER_EXTENDED_SCENARIOS,
        "phase": "tier1_jitter_extended",
        "repeats": REPEATS_PER_NEW_LEVEL,
        "start_run_index": 1,
    },
    "delay_recheck": {
        "scenarios": [TIER1_DELAY_250_RECHECK_SCENARIO],
        "phase": "tier1_delay_recheck",
        "repeats": DELAY_250_RECHECK_REPEATS,
        "start_run_index": DELAY_250_RECHECK_START_RUN_INDEX,
    },
}


def _selected_parts(part_arg: str):
    if part_arg == "all":
        return list(PARTS.keys())
    return [part_arg]


def _count_trials(part_names, tasks):
    total = 0
    for part_name in part_names:
        spec = PARTS[part_name]
        total += len(spec["scenarios"]) * len(tasks) * spec["repeats"]
    return total


def main(part: str, iface: str, log_dir: str, dry_run: bool, resume: bool):
    tasks = TASKS
    part_names = _selected_parts(part)
    total_trials = _count_trials(part_names, tasks)

    print("=== Tier 1: เจาะจุดในแกนที่มีอยู่แล้ว ===")
    for part_name in part_names:
        spec = PARTS[part_name]
        n = len(spec["scenarios"]) * len(tasks) * spec["repeats"]
        print(f"  - {part_name}: {len(spec['scenarios'])} scenarios x {len(tasks)} tasks "
              f"x {spec['repeats']} repeats = {n} trials")
    print(f"รวมทั้งหมด {total_trials} trials")

    if dry_run:
        _print_dry_run_summary(total_trials)
        return

    net = NetworkController(iface=iface)
    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        completed_count = len(checkpoint.get("completed", {}))
        print(f"เปิด resume mode: พบ completed trials เดิม {completed_count} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, "tier1")
    start = time.time()
    try:
        for part_name in part_names:
            spec = PARTS[part_name]
            print(f"\n######## Part: {part_name} ########")
            for repeat_offset in range(spec["repeats"]):
                run_index = spec["start_run_index"] + repeat_offset
                print(f"\n######## Repeat run_index={run_index} "
                      f"({repeat_offset + 1}/{spec['repeats']}) ########")
                for scenario in spec["scenarios"]:
                    _run_scenario(
                        net, scenario, tasks, run_index, log_dir, trial_state, total_trials,
                        phase=spec["phase"], progress_bar=progress_bar,
                        checkpoint=checkpoint, resume=resume,
                    )
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier1 ({part}) ทั้งหมด {trial_state['count']} trials "
          f"ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier1: เจาะจุดในแกนที่มีอยู่แล้ว (loss cliff / delay extended / jitter extended / delay=250 recheck)")
    parser.add_argument("--part", choices=list(PARTS.keys()) + ["all"], default="all",
                         help="เลือกรันเฉพาะบางส่วน หรือ 'all' รันทุกส่วน (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="เช็คแผนจำนวน trial และเวลาประมาณ โดยไม่รันจริง")
    parser.add_argument("--resume", action="store_true", help="รันต่อจาก checkpoint เดิม โดยข้าม trial ที่เสร็จแล้ว")
    parser.add_argument("--iface", default="eth0", help="network interface ที่จะ apply tc/netem")
    parser.add_argument("--log-dir", default="logs_tier1", help="โฟลเดอร์เก็บ log ของ Tier1 (แยกจาก logs_three_day/)")
    args = parser.parse_args()

    main(part=args.part, iface=args.iface, log_dir=args.log_dir,
         dry_run=args.dry_run, resume=args.resume)
