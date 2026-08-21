#!/usr/bin/env python3
"""
run_confirm_thinking_off.py — Confirmatory re-run เพื่อยืนยัน/หักล้าง
สมมติฐาน "thinking mode คือสาเหตุของ ceiling effect ใน Tier 8 ข้อ 2/3"
================================================================================
คำถามที่การรันนี้ตอบ
--------------------
Tier 8 ข้อ 2/3 พบว่า completion rate สูงผิดปกติ (ใกล้ 100% ทุก mitigation
รวมถึง mitigation="none" ที่ควรจะ fail บ่อยเหมือน Tier 5 เดิม ซึ่งได้ 14/20
ที่ loss=75%) การวินิจฉัยก่อนหน้านี้ (ดู diagnosis_output.txt,
thinking_output.txt, openai_endpoint_output.txt, native_api_output.txt ใน
โฟลเดอร์นี้) พบว่า Ollama เวอร์ชันปัจจุบัน (0.32.5) เปิด "thinking" mode
เป็นค่าเริ่มต้นให้ qwen3:8b ทำให้แต่ละ LLM call ช้าลง 10-30+ เท่า ซึ่งอาจ
เปลี่ยน timing dynamics ของทั้งระบบจนบัง failure mode เดิมที่เคยเห็นใน Tier 5

การรันนี้ทดสอบตรงๆ ว่า: ถ้าปิด thinking mode แล้ว (ผ่าน
multi_agent_thinking_off.py ที่คุย Ollama ผ่าน native /api/chat +
"think": false) completion rate ที่ loss=75%, mitigation="none" จะกลับไป
ใกล้เคียงผลเดิมของ Tier 5 (14/20, ~70%) หรือไม่ ต่างจาก Tier 8 ข้อ 2 เดิม
(ที่ thinking ยังเปิดอยู่) ที่ได้ ceiling effect เกือบ 100%

ขอบเขต (ตั้งใจให้เล็ก — นี่คือการทดสอบวินิจฉัย ไม่ใช่ผลที่จะใช้ลงเปเปอร์)
-----------------------------------------------------------------------
loss=75% (จุดเดียว จุดวิกฤตที่สุดที่ Tier 5/8 ต่างกันชัดที่สุด) x 4 tasks x
5 repeats = 20 trials, mitigation="none" เท่านั้น ตรงกับ n=20 ต่อจุดเดียวกับ
ทุกจุดอื่นในเปเปอร์ ใช้เวลาประมาณ 20 trials x ~1-2 นาที/trial (ถ้า thinking
ปิดจริง) = ~20-40 นาที (เร็วกว่า Tier 8 ข้อ 2 เดิมที่ใช้หลายชั่วโมงมาก
เพราะแต่ละ trial ไม่ต้องรอ thinking mode ที่ทำให้ช้า)

⚠️ นี่คือการรันวินิจฉัย (diagnostic run) ไม่ใช่ Tier8 item ที่ 6 อย่างเป็นทางการ
-----------------------------------------------------------------------------
ผลลัพธ์จากสคริปต์นี้ใช้เพื่อ "ตัดสินใจ" ว่าควรรันข้อ 2/3 ใหม่ทั้งชุดด้วย
thinking-off หรือไม่ ไม่ใช่ผลที่เอาไปแทนที่ข้อ 2/3 เดิมโดยตรง (n=20 เล็ก
เกินไปสำหรับการอ้างสรุปในเปเปอร์ ต้องดูร่วมกับ log ทั้งหมดและตัดสินใจร่วมกับ
ผู้ใช้ก่อนว่าจะรันเพิ่มแค่ไหน)

การใช้งาน
---------
    # 1. รัน smoke test ก่อนเสมอ (ยืนยันว่า client ทำงานถูกต้องก่อน)
    python3 smoke_test_thinking_off.py

    # 2. ทดสอบ dry-run (ไม่แตะ Ollama/tc จริง)
    python3 run_confirm_thinking_off.py --dry-run

    # 3. รันจริง
    python3 run_confirm_thinking_off.py --resume
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # thinking_off_diagnostic/
_TIER8_DIR = os.path.dirname(_THIS_DIR)  # Tier8_EnsureScopeClosure/ (controller/logger/multi_agent อยู่ที่นี่)
_PROJECT_ROOT = os.path.dirname(_TIER8_DIR)  # โฟลเดอร์โปรเจกต์ (experiment/ อยู่ที่นี่)

# ลำดับสำคัญ: _THIS_DIR ต้องอยู่ตำแหน่ง 0 (สำหรับ ollama_native_client.py/
# multi_agent_thinking_off.py ที่อยู่โฟลเดอร์เดียวกัน) ตามด้วย _TIER8_DIR
# (สำหรับ controller/logger/checkpoint_utils/multi_agent แบบ Tier8-local)
# ตามด้วย _PROJECT_ROOT (สำหรับ experiment/tasks.py) — insert ย้อนลำดับเพื่อให้
# ตัวที่ insert ทีหลังสุดอยู่ index 0 จริง
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TIER8_DIR)
sys.path.insert(0, _THIS_DIR)

from controller import NetworkController  # noqa: E402  (Tier8 local)
from logger import ExperimentLogger  # noqa: E402  (Tier8 local)
from checkpoint_utils import (  # noqa: E402
    load_checkpoint, save_checkpoint, mark_completed, should_skip,
)
from experiment.tasks import TASKS  # noqa: E402  (shared module, unchanged)

LOSS_PCT = 75
REPEATS = 5
CONDITION = "none"


def _self_test_logger_agent_param():
    """เหมือนกับ self-test ใน run_tier8_fixed_timeout.py ทุกประการ — ป้องกัน
    บั๊กเดียวกับที่ทำให้ Tier 7 (7A) ใช้ไม่ได้ไม่ให้เกิดซ้ำ"""
    scratch = ExperimentLogger(
        scenario={"name": "__self_test__"}, task_name="__self_test__",
        run_index=0, log_dir=os.path.join(_THIS_DIR, "_selftest_tmp_thinking_off"),
    )
    try:
        scratch.log_timeout(detail="self-test", agent="Worker")
        assert scratch.data["errors"][0]["agent"] == "Worker"
    except TypeError as exc:
        raise SystemExit(
            f"\n[SELF-TEST FAILED] logger.py ไม่รองรับ agent= พารามิเตอร์จริง — error: {exc}"
        )
    finally:
        import shutil
        shutil.rmtree(os.path.join(_THIS_DIR, "_selftest_tmp_thinking_off"), ignore_errors=True)
    print("[self-test] logger.py รองรับ agent= พารามิเตอร์ถูกต้อง ผ่าน")


def build_scenario():
    return {
        "name": f"t8_confirm_loss{LOSS_PCT}",
        "scenario_type": "main_effect",
        "main_effect_axis": "loss",
        "delay_ms": 0,
        "requested_delay_ms": 0,
        "jitter_ms": 0,
        "loss_pct": LOSS_PCT,
        "bandwidth_kbit": None,
        "note": "diagnostic confirmatory re-run: thinking mode ปิดผ่าน "
                "native /api/chat + think:false (ดู multi_agent_thinking_off.py)",
        "experiment_phase": "diagnostic_thinking_off_confirm",
    }


def _trial_key(scenario, task_name, repeat_index):
    return f"thinking_off_confirm__{scenario['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    print(f"  [{scenario['name']}] task={task_name} run={run_index} -> loss={scenario['loss_pct']}%")

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
                mitigation=CONDITION,
                network_condition=scenario,
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
    ap.add_argument("--log-dir", default=os.path.join(
        _THIS_DIR, "logs_tier8_diagnostic_thinking_off_confirm"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-self-test", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    scenario = build_scenario()
    total = len(tasks) * REPEATS

    print("run_confirm_thinking_off.py — diagnostic confirmatory re-run")
    print(f"  loss={LOSS_PCT}% x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  mitigation={CONDITION!r} (เหมือน Tier 8 ข้อ 2/3 ที่ arm นี้ 'ควร' fail "
          f"บ่อยถ้า timing dynamics เหมือน Tier 5)")
    print(f"  log dir: {args.log_dir}")
    print(f"  ประมาณเวลา: ~20-40 นาที ถ้า thinking mode ปิดสำเร็จจริง "
          f"(เทียบกับหลายชั่วโมงถ้ายังเปิดอยู่)")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log, ยังไม่ self-test")
        return

    if not args.skip_self_test:
        _self_test_logger_agent_param()

    import multi_agent_thinking_off  # noqa: E402  (side effect: patch multi_agent)
    import multi_agent as multi_agent_module  # noqa: E402  (module เดียวกับที่ถูก patch)

    if "none" not in multi_agent_module.VALID_MITIGATIONS:
        raise SystemExit("multi_agent.py ที่โหลดมาไม่รองรับ mitigation='none' — ตรวจ sys.path")

    net = NetworkController(iface=args.iface, direction="egress")
    checkpoint = load_checkpoint(args.log_dir) if args.resume else None

    start = time.time()
    for repeat_index in range(1, REPEATS + 1):
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
    print(f"ผลลัพธ์อยู่ที่: {args.log_dir}")
    print("ขั้นตอนถัดไป: เทียบ completion rate (จำนวน success=True จาก 20 trials) "
          "กับ Tier 5 เดิม (14/20 ที่ loss=75%, mitigation=none) และ Tier 8 ข้อ 2 "
          "เดิม (ที่ thinking ยังเปิดอยู่) ก่อนตัดสินใจว่าจะรันข้อ 2/3 ใหม่ทั้งชุด")


if __name__ == "__main__":
    main()
