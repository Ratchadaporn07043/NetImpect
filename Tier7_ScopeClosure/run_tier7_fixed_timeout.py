#!/usr/bin/env python3
"""
Tier 7A — Fixed-long-timeout arm
=================================
Question addressed by this experiment
--------------------------------------
Tier 5 พบว่า condition-aware timeout scaling เพิ่ม observed completion ที่ 75%
configured loss จาก 14/20 เป็น 20/20 (Fisher's exact test, p = 0.0202; risk
difference +30.0 pp, 95% CI +7.7 ถึง +51.9) — แต่ **ไม่เคยเทียบกับ timeout ยาว
fixed timeout**, so it cannot determine whether the improvement comes from

    (ก) การปรับ timeout ตามสภาพเครือข่ายที่รู้อยู่แล้ว  (condition-awareness)
    (ข) แค่การให้เวลามากขึ้นเฉยๆ                        (more time)

arm นี้แยกสองอย่างนั้นออกจากกัน โดยตั้ง timeout คงที่ 345 วินาที (= ค่าที่สูตร
adaptive คืนที่จุดวิกฤต loss=75%: 120 + int(75*3)) กับ **ทุก** scenario ดังนั้น
arm นี้กับ adaptive arm ได้เวลาเท่ากันเป๊ะที่ loss=75% และต่างกันเฉพาะที่ระดับ
loss อื่น — ถ้าผลที่ 75% เท่ากัน แปลว่าสิ่งที่ช่วยคือ (ข) ไม่ใช่ (ก)

Scope (selected to finish in approximately 9 hours)
----------------------------------------------------
configured loss 65 / 70 / 75%  ×  4 tasks  ×  5 repeats  =  60 trials
ครอบคลุม degradation region ทั้งช่วง และ n=20 ต่อระดับ เท่ากับ Tier 5 เป๊ะ
จึงเทียบกับ arm `none` และ `adaptive_timeout` เดิมได้โดยตรง

⚠️ ข้อจำกัดที่ต้องเขียนลง Methods
---------------------------------
arm นี้รันเป็นบล็อกของตัวเอง คนละช่วงเวลากับ Tier 5 ดังนั้น **condition ยัง
confounded กับ run block อยู่** เหมือนเดิม การเปรียบเทียบกับ Tier 5 จึงมีทั้ง
ความต่างของ treatment และความต่างของช่วงเวลารันปนกัน — ถ้ามีเวลาพอ ควรรัน
`--include-reference-arms` เพื่อรัน none/adaptive ซ้ำในบล็อกเดียวกันนี้ด้วย
(180 trials, ~27 ชม.) ซึ่งจะตัด confound นั้นออกได้จริง

Usage
-----
    # Check that everything is ready without running the experiment.
    python3 Tier7_ScopeClosure/run_tier7_fixed_timeout.py --dry-run

    # Run the experiment. Keeping --resume enabled is recommended.
    python3 Tier7_ScopeClosure/run_tier7_fixed_timeout.py --resume
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiment.controller import NetworkController  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402
from logger import ExperimentLogger  # noqa: E402

LOSS_LEVELS_PCT = [65, 70, 75]
REPEATS = 5
DEFAULT_CONDITION = "fixed_long_timeout"
REFERENCE_ARMS = ["none", "adaptive_timeout"]


def build_scenarios():
    """scenario ชุดเดียวกับแกน loss ของ Tier 5 เพียงแต่เลือกเฉพาะ 3 ระดับ"""
    return [
        {
            "name": f"t7_loss{loss}",
            "scenario_type": "main_effect",
            "main_effect_axis": "loss",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss,
            "bandwidth_kbit": None,
            "note": "",
        }
        for loss in LOSS_LEVELS_PCT
    ]


TEST_SCENARIOS = build_scenarios()


# ----------------------------------------------------------------------
# Checkpoint format shared with the other tiers.
# ----------------------------------------------------------------------
def _checkpoint_path(log_dir):
    return os.path.join(log_dir, "_checkpoint", "checkpoint.json")


def _load_checkpoint(log_dir):
    path = _checkpoint_path(log_dir)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    return {"completed": {}}


def _save_checkpoint(log_dir, checkpoint):
    path = _checkpoint_path(log_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(checkpoint, fh, ensure_ascii=False, indent=2)


def _trial_key(condition, scenario, task_name, repeat_index):
    return f"{condition}__{scenario['name']}__{task_name}__run{repeat_index}"


# ----------------------------------------------------------------------
def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir,
                     condition, multi_agent_module):
    print(f"  [{scenario['name']}] cond={condition} task={task_name} run={run_index} "
          f"-> loss={scenario['loss_pct']}%")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

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
                strict_reviewer=False,
                mitigation=condition,
                network_condition=scenario,
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"timeout_used={result.get('timeout_seconds')} "
                  f"elapsed={result['elapsed_seconds']}s")
        except Exception as exc:  # noqa: BLE001
            logger.log_error(error_type="fatal_error", detail=str(exc)[:300])
            logger.log_outcome(success=False, rounds=0, rejections=0,
                               elapsed_seconds=time.time() - logger.start_time)
            print(f"    -> FATAL ERROR: {exc}")

    clear_result = net.clear()
    logger.data.setdefault("network_commands", []).append({"action": "clear", "result": clear_result})
    return logger.save()


def run_condition(net, condition, tasks, log_dir, resume, multi_agent_module):
    print(f"\n######## condition = {condition}  ->  {log_dir} ########")
    checkpoint = _load_checkpoint(log_dir) if resume else None

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = f"tier7_fixed_timeout__{condition}"
            for task_name, task_prompt in tasks.items():
                key = _trial_key(condition, scenario, task_name, repeat_index)
                if resume and checkpoint is not None and key in checkpoint.get("completed", {}):
                    print(f"  [SKIP] {key}")
                    continue
                log_file = run_single_trial(net, scenario, task_name, task_prompt,
                                            repeat_index, log_dir, condition, multi_agent_module)
                if checkpoint is not None:
                    checkpoint.setdefault("completed", {})[key] = {
                        "log_file": log_file,
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                    _save_checkpoint(log_dir, checkpoint)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir-prefix", default="Tier7_ScopeClosure/logs_tier7_fixed")
    ap.add_argument("--include-reference-arms", action="store_true",
                    help="รัน none/adaptive_timeout ซ้ำในบล็อกเดียวกัน เพื่อตัด run-block confound")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    conditions = [DEFAULT_CONDITION]
    if args.include_reference_arms:
        conditions = REFERENCE_ARMS + [DEFAULT_CONDITION]

    tasks = TASKS
    per_condition = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    total = per_condition * len(conditions)

    print("Tier 7A — fixed-long-timeout arm")
    print(f"  {len(TEST_SCENARIOS)} loss levels {LOSS_LEVELS_PCT} x {len(tasks)} tasks "
          f"x {REPEATS} repeats = {per_condition} trials/condition")
    for c in conditions:
        print(f"    - {c}: {per_condition} trials -> {args.log_dir_prefix}_{c}/")
    print(f"  total = {total} trials")
    print(f"  ประมาณเวลา ~{(40 * 400 + 20 * 900) * len(conditions) / 3600:.1f} ชั่วโมง")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log")
        return

    # โหลด multi_agent ของ Tier7 (ต้องมี fixed_long_timeout)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import multi_agent as multi_agent_module  # noqa: E402

    if "fixed_long_timeout" not in multi_agent_module.VALID_MITIGATIONS:
        raise SystemExit(
            "multi_agent.py ที่โหลดมาไม่รองรับ 'fixed_long_timeout' — "
            "ตรวจว่ากำลังใช้ Tier7_ScopeClosure/multi_agent.py ไม่ใช่ไฟล์ของ tier ก่อนหน้า"
        )
    print(f"  FIXED_LONG_TIMEOUT = {multi_agent_module.FIXED_LONG_TIMEOUT} s")

    net = NetworkController(iface=args.iface, direction="egress")
    start = time.time()
    for condition in conditions:
        run_condition(net, condition, tasks, f"{args.log_dir_prefix}_{condition}",
                      args.resume, multi_agent_module)
    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")


if __name__ == "__main__":
    main()
