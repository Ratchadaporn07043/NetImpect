#!/usr/bin/env python3
"""
Tier 9, ขั้นตอนที่ 2 — เปรียบเทียบ mitigation เต็มรูปแบบที่ critical loss ใหม่
========================================================================
คำถามที่สคริปต์นี้ตอบ
----------------------
เดียวกับที่ Tier 8 ข้อ 2 ตั้งใจตอบ (timeout scaling ที่ช่วย completion มาจาก
"ปรับตามสภาพเครือข่าย" จริง หรือแค่ "ให้เวลามากขึ้นเฉยๆ") แต่ที่ **critical loss
ใหม่ของสภาพแวดล้อมปัจจุบัน** (ไม่ใช่ 75% เดิมที่พิสูจน์แล้วว่าไม่ล้มเหลวอีกต่อไป
เพราะ inference เร็วขึ้นเอง ~2 เท่าตั้งแต่ Tier 5) — ค่า `--critical-loss-pct`
ต้องมาจากผลของ `run_tier9_exploratory_scan.py` (ขั้นตอนที่ 1) เท่านั้น ไม่มีค่า
default เพราะการเดาค่านี้เองไม่มีความหมายอะไร ต้องมาจากข้อมูลจริง

รันทั้ง 3 arms ในบล็อกเดียวกัน (none -> adaptive_timeout -> fixed_long_timeout
ตามลำดับ ในการเรียกสคริปต์ครั้งเดียวกัน) เพื่อตัด run-block confound ออกทั้งหมด
— ทั้ง 3 arms อยู่ในสภาพแวดล้อม/ช่วงเวลาเดียวกันเป๊ะ ไม่มี cross-tier/cross-time
confound แบบที่ทำให้ผลของ Tier 8 เทียบกับ Tier 5 ไม่ได้ตรงๆ อีกต่อไป

FIXED_LONG_TIMEOUT คำนวณอัตโนมัติจากสูตรเดียวกับ adaptive (BASE_LLM_TIMEOUT +
int(critical_loss * 3)) ผ่านฟังก์ชัน `multi_agent._adaptive_timeout_seconds()`
ตัวจริงโดยตรง (ไม่ reimplement สูตรซ้ำที่นี่ กันไม่ให้ค่าคลาดเคลื่อนจากกัน) แล้ว
override `multi_agent.FIXED_LONG_TIMEOUT` หลัง import ทันที — รับประกันว่า
fixed arm กับ adaptive arm ได้ timeout เท่ากันเป๊ะที่ critical loss ใหม่ (เงื่อนไข
เดียวที่ทำให้เปรียบเทียบสอง arm นี้ตัด confound เรื่อง "เวลา" ออกได้)

Falsification check ในตัว (ก่อนเชื่อผล adaptive/fixed ต้องผ่านก่อน)
--------------------------------------------------------------------
ถ้า `none` arm ที่ critical loss ใหม่นี้ยังได้ completion > 85% (คือยังไม่
ล้มเหลวจริง) แปลว่าจุดที่เลือกมาจาก exploratory scan (n เล็ก) อาจจะสุ่มพลาด
หรือยังไม่ใช่จุดวิกฤตจริง — สคริปต์จะเตือนทันทีตอนจบการรัน และห้ามตีความ
adaptive/fixed ต่อจนกว่าจะแก้ไข (สแกนซ้ำที่ระดับสูงกว่านี้)

Pre-flight self-test
---------------------
เหมือน run_tier9_exploratory_scan.py ทุกประการ — เรียก OllamaNativeThinkOffClient
ตรงๆ ก่อนรันจริงเสมอ

การใช้งาน
---------
    # 1. ทดสอบ offline ก่อนเสมอ
    cd Tier9_CriticalThresholdRecalibration && python3 -m pytest tests_tier9/ -q

    # 2. ดูแผนการรันโดยไม่แตะอะไรจริง (ต้องระบุ critical loss จาก scan ขั้นตอนที่ 1)
    python3 run_tier9_critical_comparison.py --critical-loss-pct 90 --dry-run

    # 3. รันจริง
    python3 run_tier9_critical_comparison.py --critical-loss-pct 90 --resume
"""
import argparse
import glob
import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # Tier9_CriticalThresholdRecalibration/
# Tier 9 standalone เต็มรูปแบบ — ดูคำอธิบายเดียวกับ run_tier9_exploratory_scan.py
sys.path.insert(0, _THIS_DIR)

from tier9_controller import NetworkController  # noqa: E402
from tier9_logger import ExperimentLogger  # noqa: E402
from tier9_checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from tier9_tasks import TASKS  # noqa: E402
from ollama_native_client import OllamaNativeThinkOffClient  # noqa: E402

REPEATS = 5  # x 4 tasks = 20 trials/arm เท่ากับทุกจุดอื่นในเปเปอร์
CONDITIONS_IN_ORDER = ["none", "adaptive_timeout", "fixed_long_timeout"]
FALSIFICATION_THRESHOLD = 0.85  # เกณฑ์เดียวกับ exploratory scan/ข้อ 4 เดิม


def _self_test_native_client_fast_and_thinking_off():
    print("[self-test] ตรวจว่า native client เร็วจริงและไม่มี thinking mode ปนก่อนรันจริง...")
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
            "— thinking mode อาจยังเปิดอยู่ ห้ามรันต่อจนกว่าจะแก้ได้"
        )
    if not content:
        raise SystemExit("\n[SELF-TEST FAILED] content ว่างเปล่า — ตรวจว่า Ollama รันอยู่จริง")
    print(f"  ผ่าน: {elapsed:.2f}s, content={content!r}, ไม่มี reasoning/thinking field")


def build_scenario(critical_loss_pct, condition):
    return {
        "name": f"t9_critical_loss{critical_loss_pct}",
        "scenario_type": "critical_threshold_comparison",
        "delay_ms": 0,
        "requested_delay_ms": 0,
        "jitter_ms": 0,
        "loss_pct": critical_loss_pct,
        "bandwidth_kbit": None,
        "note": f"Tier 9 critical comparison ที่ loss={critical_loss_pct}% "
                f"(critical threshold ใหม่ของสภาพแวดล้อมปัจจุบัน) mitigation={condition}",
        "experiment_phase": f"tier9_critical_comparison__{condition}",
    }


def _trial_key(condition, scenario, task_name, repeat_index):
    return f"{condition}__{scenario['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir,
                     condition, multi_agent_module):
    print(f"  [{scenario['name']}] cond={condition} task={task_name} run={run_index} "
          f"-> loss={scenario['loss_pct']}%")

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
                strict_reviewer=False, mitigation=condition, network_condition=scenario,
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"timeout_used={result.get('timeout_seconds')} elapsed={result['elapsed_seconds']}s")
        except Exception as exc:  # noqa: BLE001
            logger.log_error(error_type="fatal_error", detail=str(exc)[:300])
            logger.log_outcome(success=False, rounds=0, rejections=0,
                               elapsed_seconds=time.time() - logger.start_time)
            print(f"    -> FATAL ERROR: {exc}")

    clear_result = net.clear()
    logger.data.setdefault("network_commands", []).append({"action": "clear", "result": clear_result})
    return logger.save()


def run_condition(net, condition, tasks, log_dir, resume, multi_agent_module, critical_loss_pct):
    print(f"\n######## condition = {condition}  ->  {log_dir} ########")
    checkpoint = load_checkpoint(log_dir) if resume else None
    scenario_base = build_scenario(critical_loss_pct, condition)

    for repeat_index in range(1, REPEATS + 1):
        scenario = dict(scenario_base)
        for task_name, task_prompt in tasks.items():
            key = _trial_key(condition, scenario, task_name, repeat_index)
            if should_skip(resume, checkpoint, key):
                print(f"  [SKIP] {key}")
                continue
            log_file = run_single_trial(net, scenario, task_name, task_prompt,
                                        repeat_index, log_dir, condition, multi_agent_module)
            if checkpoint is not None:
                mark_completed(log_dir, checkpoint, key, log_file)


def _completion_rate(log_dir, scenario_name):
    s, t = 0, 0
    for path in glob.glob(os.path.join(log_dir, "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if (d.get("network_condition") or {}).get("name") != scenario_name:
            continue
        t += 1
        if (d.get("outcome") or {}).get("success"):
            s += 1
    return s, t


def _print_final_verdict(log_dir_prefix, critical_loss_pct):
    scenario_name = f"t9_critical_loss{critical_loss_pct}"
    print("\n" + "=" * 70)
    print(f"สรุปผล Tier 9 critical comparison ที่ loss={critical_loss_pct}%")
    print("=" * 70)

    rates = {}
    for condition in CONDITIONS_IN_ORDER:
        s, t = _completion_rate(f"{log_dir_prefix}_{condition}", scenario_name)
        rates[condition] = (s, t)
        rate_str = f"{s}/{t} ({100*s/t:.0f}%)" if t else "0/0"
        print(f"  {condition:20s}: {rate_str}")

    none_s, none_t = rates["none"]
    print("-" * 70)
    if none_t == 0:
        print("[ไม่มีข้อมูล none arm — รันไม่ครบ ยังสรุปอะไรไม่ได้]")
        print("=" * 70)
        return

    none_rate = none_s / none_t
    if none_rate > FALSIFICATION_THRESHOLD:
        print(f"⚠️  FALSIFICATION CHECK ไม่ผ่าน: none arm ได้ {none_rate:.0%} "
              f"(> {FALSIFICATION_THRESHOLD:.0%}) ที่ loss={critical_loss_pct}% — "
              "จุดนี้ยังไม่ใช่ critical threshold จริง (exploratory scan อาจสุ่มพลาด "
              "เพราะ n เล็ก) **ห้ามตีความ adaptive_timeout/fixed_long_timeout ต่อ** "
              "จนกว่าจะสแกนหาจุดที่สูงกว่านี้แล้วรันใหม่")
        print("=" * 70)
        return

    print(f"✅ Falsification check ผ่าน: none arm ล้มเหลวจริง ({none_rate:.0%}) ที่จุดนี้ "
          "— ตีความ adaptive_timeout/fixed_long_timeout ต่อได้")
    print()

    adaptive_s, adaptive_t = rates["adaptive_timeout"]
    fixed_s, fixed_t = rates["fixed_long_timeout"]
    if adaptive_t and fixed_t:
        adaptive_rate = adaptive_s / adaptive_t
        fixed_rate = fixed_s / fixed_t
        print("วิธีอ่านผล:")
        if abs(fixed_rate - adaptive_rate) <= 0.05:
            print(f"  fixed ({fixed_rate:.0%}) ≈ adaptive ({adaptive_rate:.0%}), ทั้งคู่สูงกว่า "
                  f"control ({none_rate:.0%}) -> สิ่งที่ช่วยคือ 'เวลา' ไม่ใช่ condition-awareness")
        elif fixed_rate < adaptive_rate - 0.05:
            print(f"  fixed ({fixed_rate:.0%}) < adaptive ({adaptive_rate:.0%}) ชัดเจน "
                  "-> condition-awareness ช่วยจริง")
        elif abs(fixed_rate - none_rate) <= 0.05:
            print(f"  fixed ({fixed_rate:.0%}) ≈ control ({none_rate:.0%}) -> ผิดคาด "
                  "ตรวจว่า FIXED_LONG_TIMEOUT ถูกส่งถึง llm_config จริงก่อนตีความ "
                  "(ดู log field 'timeout_seconds' ในแต่ละ trial)")
        else:
            print(f"  fixed={fixed_rate:.0%} adaptive={adaptive_rate:.0%} control={none_rate:.0%} "
                  "-> รูปแบบไม่ตรงกับ 3 กรณีข้างต้นเป๊ะ ให้พิจารณาเป็นรายกรณี "
                  "(อาจต้องดู Fisher's exact test/CI เพิ่มเพราะ n=20 ต่อ arm อาจมี noise)")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--critical-loss-pct", type=int, required=True,
                    help="ค่า loss %% ที่พบจาก run_tier9_exploratory_scan.py (ขั้นตอนที่ 1) "
                         "ไม่มีค่า default โดยเจตนา")
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir-prefix", default=os.path.join(_THIS_DIR, "logs_tier9_critical_comparison"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-self-test", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    per_condition = len(tasks) * REPEATS
    total = per_condition * len(CONDITIONS_IN_ORDER)

    print("Tier 9, ขั้นตอนที่ 2 — critical comparison (none vs adaptive_timeout vs fixed_long_timeout)")
    print(f"  critical loss = {args.critical_loss_pct}%")
    print(f"  {len(tasks)} tasks x {REPEATS} repeats = {per_condition} trials/arm")
    for c in CONDITIONS_IN_ORDER:
        print(f"    - {c}: {per_condition} trials -> {args.log_dir_prefix}_{c}/")
    print(f"  รวม = {total} trials")
    print(f"  ประมาณเวลา: ~{total * 2 / 60:.1f}-{total * 4 / 60:.1f} ชั่วโมง (thinking-off "
          f"เร็วกว่า Tier 8 เดิมมาก แต่ loss สูงยังทำให้บาง trial ใช้ retry/เวลานานได้)")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log, ยังไม่ self-test")
        return

    if not args.skip_self_test:
        _self_test_native_client_fast_and_thinking_off()

    import multi_agent as multi_agent_module  # noqa: E402  (Tier 9 เอง)

    if "fixed_long_timeout" not in multi_agent_module.VALID_MITIGATIONS:
        raise SystemExit("multi_agent.py ที่โหลดมาไม่รองรับ 'fixed_long_timeout' — ตรวจ sys.path")

    # คำนวณ FIXED_LONG_TIMEOUT จากสูตร adaptive ตัวจริงของโมดูล ไม่ reimplement
    # ซ้ำที่นี่ — รับประกันว่า fixed arm กับ adaptive arm ได้ timeout เท่ากันเป๊ะ
    # ที่ critical loss ใหม่นี้ (เงื่อนไขที่ทำให้เทียบสอง arm นี้ตัด confound
    # เรื่อง 'เวลา' ออกได้ เหมือนที่ Tier 8 ออกแบบไว้ที่ loss=75% เดิม)
    critical_condition = {"delay_ms": 0, "loss_pct": args.critical_loss_pct, "jitter_ms": 0}
    computed_fixed_timeout = multi_agent_module._adaptive_timeout_seconds(critical_condition)
    multi_agent_module.FIXED_LONG_TIMEOUT = computed_fixed_timeout
    print(f"  FIXED_LONG_TIMEOUT (คำนวณจาก adaptive formula ที่ loss={args.critical_loss_pct}%) "
          f"= {computed_fixed_timeout}s")
    assert multi_agent_module._adaptive_timeout_seconds(critical_condition) == multi_agent_module.FIXED_LONG_TIMEOUT

    net = NetworkController(iface=args.iface, direction="egress")
    start = time.time()
    for condition in CONDITIONS_IN_ORDER:
        run_condition(net, condition, tasks, f"{args.log_dir_prefix}_{condition}",
                      args.resume, multi_agent_module, args.critical_loss_pct)
    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    _print_final_verdict(args.log_dir_prefix, args.critical_loss_pct)


if __name__ == "__main__":
    main()
