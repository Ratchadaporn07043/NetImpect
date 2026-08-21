#!/usr/bin/env python3
"""
Tier 8, ข้อ 5 — jitter-floor matched control (delay=50ms คงที่, jitter=0)
================================================================================
คำถามที่การทดลองนี้ตอบ
----------------------
sigconf.tex (`sec:modelservingpath`) ระบุไว้ว่า: เพราะ netem ต้องมี delay > 0
ถึงจะใส่ jitter ได้ ทุกระดับ jitter ที่ไม่ใช่ศูนย์ในชุดข้อมูลเดิมจึงถูกบวก delay
พื้นฐาน 50ms เข้าไปด้วยเสมอ (`_netem_delay_for()` ใน `experiment/scenarios.py`)
ขณะที่ระดับ jitter=0 เอง ใช้ delay=0 จริง (ไม่มี floor) ทำให้แกน jitter เดิม
เปรียบเทียบ "ไม่มี impairment เลย" กับ "delay 50ms + jitter" ไม่ใช่ "delay 50ms"
กับ "delay 50ms + jitter" ที่ตัดผลของ floor ออกไปแล้ว — จึงแยกผลของ floor เองกับ
ผลของ jitter เองไม่ออก

ตรวจยืนยันก่อนเขียนสคริปต์นี้ (Tier 8 ข้อ 5): ไม่มี scenario ไหนในทั้งโปรเจกต์
(`experiment/scenarios.py`, ทุก Tier ก่อนหน้า) เคยทดสอบ delay=50ms คงที่ +
jitter=0 แยกเป็นจุดของตัวเอง — ทุก main-effect jitter scenario เรียกผ่าน
`_netem_delay_for(0, jitter_ms)` เสมอ (requested_delay_ms=0 คงที่) scenario นี้
จึงเป็นจุดใหม่จริง ไม่ซ้ำของเดิม

การออกแบบ
----------
scenario เดียว: delay_ms=50 (ตรงกับ MIN_DELAY_FOR_JITTER_MS ใน
experiment/scenarios.py), jitter_ms=0, loss_pct=0, bandwidth=None — รันด้วย
direction="egress" (ค่าเริ่มต้น) เพื่อให้เทียบตรงกับตาราง Table 2
(`tab:nondetection`) ในเปเปอร์ได้แบบไม่มีตัวแปรที่สองเปลี่ยนไปด้วย

4 tasks x 5 repeats = 20 trials (n=20 เท่ากับทุกจุดเดี่ยวอื่นในเปเปอร์)

วิธีอ่านผล
-----------
เทียบ completion ของจุดนี้ (delay=50, jitter=0) กับ 2 จุดที่มีอยู่แล้ว:
  - configured จริงที่ jitter=0 เดิม (delay=0, jitter=0, จาก main-effect เดิม) 20/20
  - configured ที่ jitter=100ms (delay=50 floor + jitter=100) จาก precision
    remeasurement เดิม 19/20 (Table 2 แถว jitter)
ถ้าจุดใหม่นี้ (delay=50, jitter=0) ก็ยัง ~20/20 เหมือน delay=0 เดิม แปลว่า floor
เองไม่ใช่ตัวขับ completion ที่สังเกตได้ที่ jitter=100ms — สนับสนุนการอ่านผลเดิมว่า
jitter axis ไม่ถูกกระทบจาก floor ในแง่ completion (แม้ methodology จะยังไม่ใช่
matched control ที่สมบูรณ์แบบในแง่อื่น เช่น elapsed time)

การใช้งาน
---------
    python3 Tier8_EnsureScopeClosure/run_tier8_jitter_floor.py --dry-run
    python3 Tier8_EnsureScopeClosure/run_tier8_jitter_floor.py --resume
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # ต้อง insert หลัง _PROJECT_ROOT เพื่อให้ _THIS_DIR อยู่ตำแหน่ง 0 จริง

from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from experiment.scenarios import MIN_DELAY_FOR_JITTER_MS  # noqa: E402  (=50, ค่าเดียวกับที่ project ใช้จริง)
from experiment.tasks import TASKS  # noqa: E402

REPEATS = 5

JITTER_FLOOR_SCENARIO = {
    "name": "t8_jitter_floor_control",
    "scenario_type": "matched_control",
    "main_effect_axis": "jitter_floor_control",
    "delay_ms": MIN_DELAY_FOR_JITTER_MS,
    "requested_delay_ms": 0,  # เหมือนกับทุกจุดอื่นบนแกน jitter: "ขอ" delay=0 แต่ต้องปัดขึ้นเพราะ floor
    "jitter_ms": 0,
    "loss_pct": 0,
    "bandwidth_kbit": None,
    "note": (
        f"matched control: delay={MIN_DELAY_FOR_JITTER_MS}ms คงที่ (ค่า floor เดียวกับที่ทุกระดับ "
        "jitter>0 ได้รับ) แต่ jitter=0 เพื่อแยกผลของ floor เองออกจากผลของ jitter เอง"
    ),
}


def _trial_key(task_name, repeat_index):
    return f"{JITTER_FLOOR_SCENARIO['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    print(f"  [{JITTER_FLOOR_SCENARIO['name']}] task={task_name} run={run_index} "
          f"-> delay={JITTER_FLOOR_SCENARIO['delay_ms']}ms jitter=0")

    logger = ExperimentLogger(scenario=JITTER_FLOOR_SCENARIO, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=JITTER_FLOOR_SCENARIO["delay_ms"],
        jitter_ms=JITTER_FLOOR_SCENARIO["jitter_ms"],
        loss_pct=JITTER_FLOOR_SCENARIO["loss_pct"],
        bandwidth_kbit=JITTER_FLOOR_SCENARIO.get("bandwidth_kbit"),
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
                strict_reviewer=False, mitigation="none", network_condition=JITTER_FLOOR_SCENARIO,
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir", default=os.path.join(_THIS_DIR, "logs_tier8_jitter_floor"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    total = len(tasks) * REPEATS
    print("Tier 8, ข้อ 5 — jitter-floor matched control")
    print(f"  1 scenario (delay={JITTER_FLOOR_SCENARIO['delay_ms']}ms, jitter=0) "
          f"x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  ประมาณเวลา ~{total * 60 / 3600:.2f} ชั่วโมง")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log")
        return

    import multi_agent as multi_agent_module  # noqa: E402

    net = NetworkController(iface=args.iface, direction="egress")
    checkpoint = load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, REPEATS + 1):
        for task_name, task_prompt in tasks.items():
            key = _trial_key(task_name, repeat_index)
            if should_skip(args.resume, checkpoint, key):
                print(f"  [SKIP] {key}")
                continue
            log_file = run_single_trial(net, task_name, task_prompt, repeat_index,
                                        args.log_dir, multi_agent_module)
            if checkpoint is not None:
                mark_completed(args.log_dir, checkpoint, key, log_file)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    print("ขั้นตอนถัดไป: เทียบ completion ของจุดนี้กับ jitter=0 เดิม (delay=0) และ "
          "jitter=100ms เดิม (Table 2 ในเปเปอร์)")


if __name__ == "__main__":
    main()
