#!/usr/bin/env python3
"""
Tier 8, ข้อ 2 — fixed-long-timeout arm (แก้บั๊กที่ทำให้ 7A ของ Tier 7 ใช้ไม่ได้)
====================================================================================
คำถามที่การทดลองนี้ตอบ
----------------------
Tier 5 พบว่า condition-aware timeout scaling เพิ่ม completion ที่ 75% configured
loss จาก 14/20 เป็น 20/20 (Fisher's exact test, p = 0.0202) แต่ไม่เคยเทียบกับ
timeout ยาวคงที่ จึงแยกไม่ได้ว่าสิ่งที่ช่วยคือ

    (ก) การปรับ timeout ตามสภาพเครือข่าย (condition-awareness)
    (ข) แค่การให้เวลามากขึ้นเฉยๆ (more time)

arm นี้ตั้ง timeout คงที่ 345 วินาที (= ค่าที่สูตร adaptive คืนที่จุดวิกฤต
loss=75%: 120 + int(75*3)) กับทุก scenario ดังนั้น arm นี้กับ adaptive arm ได้
เวลาเท่ากันเป๊ะที่ loss=75% และต่างกันเฉพาะที่ระดับ loss อื่น

ทำไมต้องรันใหม่ (ไม่ใช้ผลเดิมจาก Tier7_ScopeClosure/logs_tier7_fixed_fixed_long_timeout/)
--------------------------------------------------------------------------------------
ทุก trial ที่ fail ในการรันครั้งก่อนพังด้วย
    ExperimentLogger.log_timeout() got an unexpected keyword argument 'agent'
เพราะ logger.py ที่ root โปรเจกต์ตอนนั้นไม่มีพารามิเตอร์ `agent` ทำให้ retry
ทั้งหมดถูกตัดทิ้ง (ดู Paper/NetImpact.md/Current/NetImpact_20_Tier7_Scope_Closure.md
§3.1 สำหรับรายละเอียดเต็ม) Tier 8 นี้ใช้ logger.py ใหม่ที่ตรวจสอบแล้วว่ามี
พารามิเตอร์นี้จริง (ดู self-test ก่อนรันจริงด้านล่าง) และแยกโฟลเดอร์ทั้งหมดออกจาก
Tier 7 เพื่อไม่ให้ปนกับผลที่ใช้ไม่ได้ของเดิม

ขอบเขต (เลือกไว้ให้จบใน ~9 ชั่วโมงต่อ arm)
------------------------------------------
configured loss 65 / 70 / 75%  ×  4 tasks  ×  5 repeats  =  60 trials ต่อ arm
n=20 ต่อระดับ เท่ากับทุกจุดอื่นในเปเปอร์ จึงเทียบกับ arm อื่นได้ตรงๆ

⚠️ ข้อจำกัดที่ต้องเขียนลง Methods เสมอ
---------------------------------------
ถ้ารันแค่ arm เดียว (--resume ธรรมดา, 60 trials) จะยังเทียบกับ Tier 5
(control/adaptive เดิม) ไม่ได้แบบตัด run-block confound ออก เพราะรันคนละ
ช่วงเวลา — แนะนำให้ใช้ --include-reference-arms เสมอถ้าเวลาเอื้ออำนวย (รัน
none/adaptive_timeout ซ้ำในบล็อกเดียวกัน 180 trials รวม ~27 ชม.) ซึ่งตัด
confound นั้นออกได้จริง และเป็นสิ่งเดียวที่ทำให้ผลลัพธ์ของข้อ 2 นี้ "เทียบตรง"
ได้อย่างสมบูรณ์

การใช้งาน
---------
    # 1. ทดสอบ offline ก่อนเสมอ (ไม่แตะ Ollama/tc จริง)
    cd Tier8_EnsureScopeClosure && python3 -m pytest tests_tier8/ -q

    # 2. ตรวจว่าทุกอย่างพร้อม ไม่รันจริง
    python3 Tier8_EnsureScopeClosure/run_tier8_fixed_timeout.py --dry-run

    # 3. รันจริง (แนะนำให้เปิด --resume ไว้เสมอ เผื่อเครื่องดับกลางทาง)
    python3 Tier8_EnsureScopeClosure/run_tier8_fixed_timeout.py --resume --include-reference-arms
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# Tier8 code (controller/logger/multi_agent) ต้องถูก import "ก่อน" project root
# เสมอ เพื่อไม่ให้ Python เผลอไปเจอ experiment/controller.py หรือ logger.py ที่
# root ก่อน (ทั้งสองไฟล์นั้นไม่มีความสามารถที่ Tier8 ต้องใช้)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # ต้อง insert หลัง _PROJECT_ROOT เพื่อให้ _THIS_DIR อยู่ตำแหน่ง 0 จริง

from controller import NetworkController  # noqa: E402  (Tier8 local)
from logger import ExperimentLogger  # noqa: E402  (Tier8 local)
from checkpoint_utils import (  # noqa: E402
    load_checkpoint, save_checkpoint, mark_completed, should_skip,
)
from experiment.tasks import TASKS  # noqa: E402  (unchanged shared module)

LOSS_LEVELS_PCT = [65, 70, 75]
REPEATS = 5
DEFAULT_CONDITION = "fixed_long_timeout"
REFERENCE_ARMS = ["none", "adaptive_timeout"]


def _self_test_logger_agent_param():
    """ตรวจก่อนเริ่มรันจริงว่า logger.py ตัวนี้รองรับ agent= จริง — ป้องกันการ
    พังแบบเดียวกับ 7A ของ Tier 7 ไม่ให้เกิดซ้ำ (ที่นั่นบั๊กถูกพบหลังรันจบไปแล้ว
    60 trials เท่านั้น) เรียกจริงด้วย object ทิ้ง ไม่เขียนไฟล์ log ถาวร"""
    scratch = ExperimentLogger(
        scenario={"name": "__self_test__"}, task_name="__self_test__",
        run_index=0, log_dir=os.path.join(_THIS_DIR, "_selftest_tmp"),
    )
    try:
        scratch.log_timeout(detail="self-test", agent="Worker")
        scratch.log_error(error_type="self_test", detail="self-test", agent="Reviewer")
        scratch.log_retry(reason="self-test", agent="Planner")
        assert scratch.data["errors"][0]["agent"] == "Worker"
        assert scratch.data["errors"][1]["agent"] == "Reviewer"
        assert scratch.data["errors"][2]["agent"] == "Planner"
    except TypeError as exc:
        raise SystemExit(
            "\n[SELF-TEST FAILED] logger.py ไม่รองรับ agent= พารามิเตอร์จริง — "
            f"error: {exc}\n"
            "นี่คือบั๊กเดียวกับที่ทำให้ Tier 7 (7A) ใช้ไม่ได้ ห้ามรันต่อ ตรวจ "
            "Tier8_EnsureScopeClosure/logger.py ก่อน"
        )
    finally:
        import shutil
        shutil.rmtree(os.path.join(_THIS_DIR, "_selftest_tmp"), ignore_errors=True)
    print("[self-test] logger.py รองรับ agent= พารามิเตอร์ถูกต้อง ผ่าน")


def build_scenarios():
    """scenario ชุดเดียวกับแกน loss ของ Tier 5 เพียงแต่เลือกเฉพาะ 3 ระดับวิกฤต"""
    return [
        {
            "name": f"t8_loss{loss}",
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


def _trial_key(condition, scenario, task_name, repeat_index):
    return f"{condition}__{scenario['name']}__{task_name}__run{repeat_index}"


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
    checkpoint = load_checkpoint(log_dir) if resume else None

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = f"tier8_fixed_timeout__{condition}"
            for task_name, task_prompt in tasks.items():
                key = _trial_key(condition, scenario, task_name, repeat_index)
                if should_skip(resume, checkpoint, key):
                    print(f"  [SKIP] {key}")
                    continue
                log_file = run_single_trial(net, scenario, task_name, task_prompt,
                                            repeat_index, log_dir, condition, multi_agent_module)
                if checkpoint is not None:
                    mark_completed(log_dir, checkpoint, key, log_file)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir-prefix", default=os.path.join(_THIS_DIR, "logs_tier8_fixed"))
    ap.add_argument("--include-reference-arms", action="store_true",
                    help="รัน none/adaptive_timeout ซ้ำในบล็อกเดียวกัน เพื่อตัด run-block confound (แนะนำ)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-self-test", action="store_true",
                    help="ข้าม self-test ของ logger.py (ไม่แนะนำ — ใช้เฉพาะ debug)")
    args = ap.parse_args()

    conditions = [DEFAULT_CONDITION]
    if args.include_reference_arms:
        conditions = REFERENCE_ARMS + [DEFAULT_CONDITION]

    tasks = TASKS
    per_condition = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    total = per_condition * len(conditions)

    print("Tier 8, ข้อ 2 — fixed-long-timeout arm")
    print(f"  {len(TEST_SCENARIOS)} loss levels {LOSS_LEVELS_PCT} x {len(tasks)} tasks "
          f"x {REPEATS} repeats = {per_condition} trials/condition")
    for c in conditions:
        print(f"    - {c}: {per_condition} trials -> {args.log_dir_prefix}_{c}/")
    print(f"  total = {total} trials")
    print(f"  ประมาณเวลา ~{(40 * 400 + 20 * 900) * len(conditions) / 3600:.1f} ชั่วโมง")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log, ยังไม่ self-test")
        return

    if not args.skip_self_test:
        _self_test_logger_agent_param()

    import multi_agent as multi_agent_module  # noqa: E402  (Tier8 local, บน sys.path แล้ว)

    if "fixed_long_timeout" not in multi_agent_module.VALID_MITIGATIONS:
        raise SystemExit(
            "multi_agent.py ที่โหลดมาไม่รองรับ 'fixed_long_timeout' — ตรวจว่ากำลังใช้ "
            "Tier8_EnsureScopeClosure/multi_agent.py จริง (sys.path ต้องมี Tier8_EnsureScopeClosure "
            "อยู่ก่อน project root)"
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
