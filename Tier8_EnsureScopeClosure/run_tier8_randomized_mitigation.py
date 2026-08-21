#!/usr/bin/env python3
"""
Tier 8, ข้อ 3 — mitigation comparison แบบสุ่ม/สลับลำดับ (interleaved) แทน consecutive block
================================================================================================
คำถามที่การทดลองนี้ตอบ
----------------------
ผลใน sigconf.tex (Section 5.5/`sec:mitigationresults`) รายงานว่า timeout scaling
เพิ่ม completion ที่ 75% configured loss จาก 14/20 (control) เป็น 20/20 — แต่
ทั้งสาม arm (none/adaptive_timeout/context_cache) ของ Tier 5 รันเป็น **บล็อก
ต่อเนื่อง** ทีละ arm ไม่ใช่สลับกัน (ดู `Tier5_Mitigation/run_tier5_mitigation_comparison.py`
บรรทัด `for condition in conditions: _run_condition(...)`) ทำให้ condition
confound กับ "ช่วงเวลาที่รัน" ตลอดทั้งบล็อก (host load, thermal state, model
server state, ฯลฯ — ดู sigconf.tex `sec:scopelimitations` ย่อหน้า 2) การทดลองนี้
รัน **ทั้ง 660 trial เดียวกันทุกประการ** (11 loss level x 4 task x 5 repeat x 3
condition) แต่ **สุ่มลำดับการรันข้าม condition** แทนที่จะรันเป็นบล็อก — ถ้าผล
ต่าง (14/20 vs 20/20 ที่ 75% loss) ยังปรากฏอยู่หลังตัด run-block confound ออก
แล้ว ก็ยกระดับจาก "hypothesis generating" เป็นข้อค้นพบที่อ้างได้จริง

การออกแบบ
----------
สร้าง trial spec ทั้ง 660 รายการ (condition x loss_pct x task x repeat) แล้วสุ่ม
ลำดับด้วย seed คงที่ที่ระบุไว้ชัดเจน (ดู RANDOM_SEED ด้านล่าง) บันทึกลำดับที่สุ่ม
ได้ทั้งหมดลง `<log-dir-prefix>_execution_order.json` ก่อนเริ่มรันจริง เพื่อให้ตรวจ
ย้อนหลังได้ว่าลำดับเวลาที่รันจริงกับ condition มีความสัมพันธ์กันหรือไม่ (ควรจะไม่มี
ถ้าสุ่มดีพอ) log แต่ละ trial ยังบันทึกแยกโฟลเดอร์ตาม condition เหมือนเดิม
(`logs_..._none/`, `logs_..._adaptive_timeout/`, `logs_..._context_cache/`) เพื่อ
ให้ parse_logs.py / สคริปต์วิเคราะห์เดิมใช้ต่อได้โดยไม่ต้องแก้

Checkpoint/resume ใช้ trial key เดียวกับ Tier5 (condition+scenario+task+repeat)
จึงทนต่อการรันสลับลำดับได้ปกติ ไม่ว่าจะหยุดกลางทางตรงไหนก็ resume ต่อจากจุดเดิมได้

ขอบเขต
-------
11 loss levels (0,1,5,10,15,20,25,30,40,50,75%) x 4 tasks x 5 repeats x 3
conditions = 660 trials รวม เท่ากับ Tier 5 เป๊ะ (n=20 ต่อ condition ต่อ loss
level เทียบตรงกับตารางเดิมได้)

การใช้งาน
---------
    python3 Tier8_EnsureScopeClosure/run_tier8_randomized_mitigation.py --dry-run
    python3 Tier8_EnsureScopeClosure/run_tier8_randomized_mitigation.py --resume
"""
import argparse
import json
import os
import random
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # ต้อง insert หลัง _PROJECT_ROOT เพื่อให้ _THIS_DIR อยู่ตำแหน่ง 0 จริง

from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import (  # noqa: E402
    load_checkpoint, save_checkpoint, mark_completed, should_skip,
)
from experiment.scenarios import PACKET_LOSS_LEVELS_PCT  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402

CONDITIONS = ["none", "adaptive_timeout", "context_cache"]
REPEATS = 5

# seed คงที่ ระบุไว้ตรงนี้อย่างเดียว ไม่สุ่มจาก time/os.urandom เพื่อให้ "ลำดับที่
# สุ่มได้" reproduce ซ้ำได้เป๊ะถ้าจำเป็นต้องตรวจสอบย้อนหลัง (เช่น สงสัยว่า
# random.shuffle ทำงานถูกต้องไหม) เปลี่ยนเลขนี้ได้ถ้าต้องการสุ่มชุดใหม่ แต่ต้อง
# บันทึกไว้ในรายงาน/README ว่าใช้ seed อะไรจริงตอนรัน
RANDOM_SEED = 20260101


def _loss_scenarios():
    scenarios = []
    for loss_pct in PACKET_LOSS_LEVELS_PCT:
        scenarios.append({
            "name": f"tier8_loss_loss{str(loss_pct).replace('.', 'p')}",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss_pct,
            "bandwidth_kbit": None,
            "note": "",
        })
    return scenarios


def _trial_key(condition, scenario, task_name, repeat_index):
    return f"{condition}__{scenario['name']}__{task_name}__run{repeat_index}"


def build_shuffled_trial_list(seed: int):
    """สร้าง trial spec ทั้ง 660 รายการ แล้วสุ่มลำดับ คืนค่า list ของ dict:
    {"condition", "scenario", "task_name", "task_prompt", "repeat_index"}"""
    scenarios = _loss_scenarios()
    tasks = TASKS

    trials = []
    for repeat_index in range(1, REPEATS + 1):
        for scenario in scenarios:
            for task_name, task_prompt in tasks.items():
                for condition in CONDITIONS:
                    trials.append({
                        "condition": condition,
                        "scenario": dict(scenario),
                        "task_name": task_name,
                        "task_prompt": task_prompt,
                        "repeat_index": repeat_index,
                    })

    rng = random.Random(seed)
    rng.shuffle(trials)
    return trials


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir,
                     condition, multi_agent_module, sequence_index):
    print(f"  [seq={sequence_index}] [{scenario['name']}] cond={condition} task={task_name} "
          f"run={run_index} -> loss={scenario['loss_pct']}%")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)
    logger.data["execution_sequence_index"] = sequence_index

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=scenario.get("bandwidth_kbit"),
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
                mitigation=condition, network_condition=scenario,
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
    ap.add_argument("--log-dir-prefix",
                    default=os.path.join(_THIS_DIR, "logs_tier8_randomized_mitigation"))
    ap.add_argument("--seed", type=int, default=RANDOM_SEED,
                    help="random seed สำหรับสุ่มลำดับ trial (ค่าเริ่มต้นตรึงไว้ตายตัวเพื่อ reproduce ได้)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    trials = build_shuffled_trial_list(args.seed)
    total = len(trials)
    per_condition = total // len(CONDITIONS)

    print("Tier 8, ข้อ 3 — mitigation comparison แบบสุ่มลำดับ (interleaved)")
    print(f"  seed = {args.seed}")
    print(f"  {len(PACKET_LOSS_LEVELS_PCT)} loss levels x {len(TASKS)} tasks x {REPEATS} repeats "
          f"x {len(CONDITIONS)} conditions = {total} trials รวม ({per_condition}/condition)")
    for c in CONDITIONS:
        print(f"    - {c}: log -> {args.log_dir_prefix}_{c}/")

    order_manifest_path = f"{args.log_dir_prefix}_execution_order.json"
    manifest = [
        {
            "sequence_index": i,
            "condition": t["condition"],
            "scenario_name": t["scenario"]["name"],
            "loss_pct": t["scenario"]["loss_pct"],
            "task_name": t["task_name"],
            "repeat_index": t["repeat_index"],
        }
        for i, t in enumerate(trials)
    ]
    os.makedirs(os.path.dirname(order_manifest_path) or ".", exist_ok=True)
    with open(order_manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"seed": args.seed, "total_trials": total, "order": manifest}, fh,
                  ensure_ascii=False, indent=2)
    print(f"  บันทึกลำดับการรันทั้งหมดไว้ที่: {order_manifest_path}")
    print(f"  ประมาณเวลา ~{total * 60 / 3600:.1f} ชั่วโมง (ประมาณคร่าวๆ 60s/trial เฉลี่ย)")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน trial log ใดๆ "
              "(แต่ไฟล์ execution_order.json ด้านบนถูกเขียนจริงแล้ว — เป็นไฟล์วางแผนล้วนๆ "
              "ไม่มีผลต่อระบบเครือข่าย/LLM เลย เขียนไว้ตั้งแต่ dry-run เพื่อให้ตรวจลำดับ "
              "ก่อนรันจริงได้)")
        return

    import multi_agent as multi_agent_module  # noqa: E402

    net = NetworkController(iface=args.iface, direction="egress")

    checkpoints = {c: (load_checkpoint(f"{args.log_dir_prefix}_{c}") if args.resume else None)
                   for c in CONDITIONS}

    start = time.time()
    for i, t in enumerate(trials):
        condition = t["condition"]
        log_dir = f"{args.log_dir_prefix}_{condition}"
        key = _trial_key(condition, t["scenario"], t["task_name"], t["repeat_index"])
        checkpoint = checkpoints[condition]
        if should_skip(args.resume, checkpoint, key):
            print(f"  [SKIP seq={i}] {key}")
            continue
        log_file = run_single_trial(net, t["scenario"], t["task_name"], t["task_prompt"],
                                    t["repeat_index"], log_dir, condition, multi_agent_module, i)
        if checkpoint is not None:
            mark_completed(log_dir, checkpoint, key, log_file)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    print("ขั้นตอนถัดไป: parse log ทั้ง 3 โฟลเดอร์แล้วเทียบ completion ที่ 75% loss "
          "ก่อน/หลังตัด run-block confound กับผลเดิมใน Tier5_Mitigation/")


if __name__ == "__main__":
    main()
