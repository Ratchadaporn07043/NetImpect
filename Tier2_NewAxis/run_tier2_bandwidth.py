"""
run_tier2_bandwidth.py — ตัวรัน Tier 2 ส่วน Bandwidth Axis
================================================================
ใช้ multi_agent.py "ต้นฉบับเดิม" ที่ root โปรเจกต์ (ไม่ต้องแทนที่ด้วย
Tier2/multi_agent.py) เพราะ bandwidth ไม่เกี่ยวกับ Reviewer prompt เลย —
network layer (tc/tbf) รองรับ bandwidth_kbit อยู่แล้วใน controller.py เดิม

วิธีติดตั้ง/วางไฟล์: เหมือน Tier1 — คัดลอกโฟลเดอร์ Tier2_แกนใหม่/ ทั้งโฟลเดอร์
ไปวางไว้ที่ root ของโปรเจกต์ NetImpact (ระดับเดียวกับ multi_agent.py, experiment/)

วิธีรัน:
    cd NetImpact
    python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --dry-run
    python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --part main_effect --resume
    python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --part x_loss --resume
    python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --part all --resume

log เขียนไปที่ logs_tier2_bandwidth/ (แยกจากทุก log dir อื่น)
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
# สำคัญ: ต้องแทรก _THIS_DIR ก่อน แล้วค่อยแทรก _PROJECT_ROOT ทีหลัง เพื่อให้
# _PROJECT_ROOT ไปอยู่ที่ index 0 (priority สูงสุด) — โฟลเดอร์นี้ (Tier2_แกนใหม่/)
# มีไฟล์ multi_agent.py ของตัวเองอยู่ด้วย ถ้า _THIS_DIR มี priority สูงกว่า
# _PROJECT_ROOT แล้ว "import multi_agent" จะไปเจอไฟล์ในโฟลเดอร์นี้เสมอ
# แทนที่จะเป็นไฟล์ที่ root โปรเจกต์จริง (ตามที่ผู้ใช้ cp ไว้ตามคำแนะนำ)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.controller import NetworkController  # noqa: E402
from experiment.run_experiment import (  # noqa: E402
    _run_scenario,
    _load_checkpoint,
    _open_progress,
    _print_dry_run_summary,
)
from experiment.tasks import TASKS  # noqa: E402

from tier2_scenarios_bandwidth import (  # noqa: E402
    TIER2_BANDWIDTH_MAIN_EFFECT_SCENARIOS,
    TIER2_BANDWIDTH_X_LOSS_SCENARIOS,
    REPEATS_PER_BANDWIDTH_LEVEL,
    REPEATS_PER_BANDWIDTH_X_LOSS,
)

PARTS = {
    "main_effect": {
        "scenarios": TIER2_BANDWIDTH_MAIN_EFFECT_SCENARIOS,
        "phase": "tier2_bandwidth_main_effect",
        "repeats": REPEATS_PER_BANDWIDTH_LEVEL,
    },
    "x_loss": {
        "scenarios": TIER2_BANDWIDTH_X_LOSS_SCENARIOS,
        "phase": "tier2_bandwidth_x_loss",
        "repeats": REPEATS_PER_BANDWIDTH_X_LOSS,
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

    print("=== Tier 2: Bandwidth Axis ===")
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
        print(f"เปิด resume mode: พบ completed trials เดิม {len(checkpoint.get('completed', {}))} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, "tier2_bandwidth")
    start = time.time()
    try:
        for part_name in part_names:
            spec = PARTS[part_name]
            print(f"\n######## Part: {part_name} ########")
            for repeat_index in range(1, spec["repeats"] + 1):
                print(f"\n######## Repeat {repeat_index}/{spec['repeats']} ########")
                for scenario in spec["scenarios"]:
                    _run_scenario(
                        net, scenario, tasks, repeat_index, log_dir, trial_state, total_trials,
                        phase=spec["phase"], progress_bar=progress_bar,
                        checkpoint=checkpoint, resume=resume,
                    )
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier2 bandwidth ({part}) ทั้งหมด {trial_state['count']} trials "
          f"ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier2: Bandwidth axis (main-effect + bandwidth x loss)")
    parser.add_argument("--part", choices=list(PARTS.keys()) + ["all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--log-dir", default="logs_tier2_bandwidth")
    args = parser.parse_args()

    main(part=args.part, iface=args.iface, log_dir=args.log_dir,
         dry_run=args.dry_run, resume=args.resume)
