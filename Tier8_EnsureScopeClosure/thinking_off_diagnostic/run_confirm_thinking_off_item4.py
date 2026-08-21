#!/usr/bin/env python3
"""
run_confirm_thinking_off_item4.py — Confirmatory re-run เฉพาะจุด
t8in_baseline + t8in_loss75 ของข้อ 4 (ingress/bidirectional) ด้วย thinking mode ปิด
================================================================================
ทำไมต้องมีสคริปต์นี้ — และทำไมต่างจากข้อ 1/2/3
--------------------------------------------------------------------------
ตรวจ log ของข้อ 4 จริง (`logs_tier8_ingress_No.4`) แยกตาม scenario พบสิ่งที่
ต่างจากข้อ 1/2/3 อย่างสิ้นเชิง: `t8in_loss75` (loss=75% ทั้งสองทิศทางผ่าน
ingress+IFB, mitigation="none") ได้ completion **0/20 (0%)** — ไม่ใช่ ceiling
effect (สูงผิดปกติ) เหมือนข้อ 1/2/3 แต่เป็น floor effect (ต่ำผิดปกติ/ล้มเหลว
หมด) ตรวจ error log แล้วพบว่าทั้ง 20 trials ล้มตั้งแต่ round แรก (rounds=1 ทุก
trial) ด้วย APIConnectionError (connection reset) เป็นหลัก (50 ครั้ง) มากกว่า
timeout ธรรมดา (10 ครั้ง) และแต่ละ trial ใช้เวลา 100-1800+ วินาทีกว่าจะยอมแพ้
ทั้งที่ล้มตั้งแต่ round แรก — สอดคล้องกับ median ช่วงห่างข้อความ 88.0 วินาที
(สัญญาณ thinking mode เปิดอยู่เหมือนข้อ 1/2/3)

สมมติฐานที่เป็นไปได้ (ยังไม่ยืนยัน — คือเหตุผลที่ต้องรันสคริปต์นี้)
--------------------------------------------------------------------------
thinking mode ทำให้แต่ละ LLM call เปิด connection ค้างไว้นานผิดปกติ (10-30+
เท่า) พอเจอ loss ทั้งสองทิศทางพร้อมกัน (effective loss สูงกว่า egress-only
มาก เพราะทั้ง request และ response ต้องรอดพ้น drop ทั้งคู่) ยิ่ง connection
เปิดค้างนานเท่าไหร่ ยิ่งมีโอกาสสูงที่จะโดน drop จนหลุดไปเลย (connection reset)
แทนที่จะแค่ช้า — ถ้าสมมติฐานนี้ถูก thinking-off ควรทำให้ completion กลับมา
ไม่ใช่ 0% แม้จะยังต่ำกว่า baseline มากเพราะ bidirectional loss ยังหนักอยู่จริง
**แต่ก็เป็นไปได้เช่นกันว่า 0/20 คือผลจริงของ bidirectional shaping ที่ compound
กันจนเกินจะรอด ไม่เกี่ยวกับ thinking mode เลย** — สคริปต์นี้ตอบคำถามนี้ตรงๆ

ทำไมต้องรัน baseline (t8in_baseline) ซ้ำด้วย ไม่ใช่แค่ loss75
--------------------------------------------------------------------------
run_tier8_ingress.py ตัวจริงมี falsification check สองจุดโดยเจตนา (ดู
docstring ของมันเอง): baseline ต้อง >= 85% ก่อนถึงจะตีความ positive control
(loss75) ได้ — ถ้ารัน loss75 อย่างเดียวโดยไม่มี baseline คู่กันภายใต้
thinking-off เดียวกัน จะไม่รู้ว่า 0/20 (ถ้ายังเกิดซ้ำ) เป็นเพราะ loss75 จริง
หรือเป็นเพราะ IFB/ingress path เองมีปัญหาอะไรที่ไม่เกี่ยวกับ loss เลย

ขอบเขต: t8in_baseline + t8in_loss75 (ไม่รัน bw50/delay1000 ซ้ำ เพราะทั้งสอง
เป็น null result เดิมที่ไม่ใช่จุดที่ผิดปกติ) x 4 tasks x 5 repeats = 40 trials

ข้อกำหนดสภาพแวดล้อม: เหมือน run_tier8_ingress.py ทุกประการ ต้องรัน
`sudo modprobe ifb numifbs=0` บน host ก่อน

การใช้งาน
---------
    python3 smoke_test_thinking_off.py                          # ทดสอบ wiring ก่อนเสมอ
    python3 run_confirm_thinking_off_item4.py --probe-only
    python3 run_confirm_thinking_off_item4.py --dry-run
    python3 run_confirm_thinking_off_item4.py --resume
"""
import argparse
import glob
import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # thinking_off_diagnostic/
_TIER8_DIR = os.path.dirname(_THIS_DIR)  # Tier8_EnsureScopeClosure/
_PROJECT_ROOT = os.path.dirname(_TIER8_DIR)  # โฟลเดอร์โปรเจกต์
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TIER8_DIR)
sys.path.insert(0, _THIS_DIR)  # insert ท้ายสุดเพื่อให้อยู่ตำแหน่ง 0 จริง

import psutil  # noqa: E402
from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402

REPEATS = 5
CPU_GATE_THRESHOLD_PCT = 70.0
CPU_GATE_MAX_WAIT_S = 120
CPU_GATE_POLL_S = 5

TEST_SCENARIOS = [
    {
        "name": "t8in_confirm_baseline", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "falsification check (thinking-off): IFB path เองต้องไม่ทำให้ completion ตก",
        "role": "falsification_baseline",
    },
    {
        "name": "t8in_confirm_loss75", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 75,
        "bandwidth_kbit": None,
        "note": "diagnostic confirmatory re-run ของ t8in_loss75 เดิม (0/20 ตอน thinking-on) "
                "ด้วย thinking mode ปิด",
        "role": "positive_control",
    },
]


def _wait_for_low_cpu(threshold=CPU_GATE_THRESHOLD_PCT, max_wait_s=CPU_GATE_MAX_WAIT_S,
                      poll_s=CPU_GATE_POLL_S):
    waited = 0.0
    readings = []
    cpu = psutil.cpu_percent(interval=1.0)
    readings.append(cpu)
    while cpu > threshold and waited < max_wait_s:
        time.sleep(poll_s)
        waited += poll_s
        cpu = psutil.cpu_percent(interval=1.0)
        readings.append(cpu)
    return {"waited_seconds": waited, "final_cpu_percent": cpu, "readings": readings,
            "gate_passed": cpu <= threshold}


def _trial_key(scenario, task_name, repeat_index):
    return f"thinking_off_confirm_item4__{scenario['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    gate = _wait_for_low_cpu()
    print(f"  [{scenario['name']}] task={task_name} run={run_index} "
          f"-> loss={scenario['loss_pct']}% dir={net.direction} "
          f"(cpu_gate: waited={gate['waited_seconds']:.0f}s final_cpu={gate['final_cpu_percent']:.0f}%)")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)
    logger.data["cpu_gate"] = gate

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"], jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"], bandwidth_kbit=scenario.get("bandwidth_kbit"),
    )
    logger.data.setdefault("network_commands", []).append({"action": "apply", "result": apply_result})
    logger.data["impairment_direction"] = net.direction

    if apply_result.get("returncode") not in (0, None):
        logger.log_error(error_type="invalid_trial",
                         detail=f"network apply failed: {apply_result.get('stderr','')[:200]}")
        logger.log_outcome(success=False, rounds=0, rejections=0,
                           elapsed_seconds=time.time() - logger.start_time)
        print("    -> INVALID TRIAL: network apply failed")
    else:
        try:
            result = multi_agent_module.run_multi_agent_task(
                task_prompt, logger=logger, task_name=task_name,
                strict_reviewer=False, mitigation="none", network_condition=scenario,
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


def _print_verdict(log_dir):
    counts = {s["name"]: {"success": 0, "total": 0} for s in TEST_SCENARIOS}
    for path in glob.glob(os.path.join(log_dir, "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        name = d.get("network_condition", {}).get("name")
        if name not in counts:
            continue
        counts[name]["total"] += 1
        if (d.get("outcome") or {}).get("success"):
            counts[name]["success"] += 1

    print("\n" + "=" * 70)
    print("สรุปผล confirmatory re-run (ข้อ 4, thinking-off)")
    print("=" * 70)
    for s in TEST_SCENARIOS:
        c = counts[s["name"]]
        rate = f"{c['success']}/{c['total']}" if c["total"] else "0/0"
        print(f"  {s['name']:24s} role={s['role']:16s} {rate}")

    baseline = counts["t8in_confirm_baseline"]
    loss75 = counts["t8in_confirm_loss75"]
    print("-" * 70)
    print("เทียบกับผลเดิม (thinking-on): t8in_baseline เดิม = 20/20, "
          "t8in_loss75 เดิม = 0/20")
    if baseline["total"] and loss75["total"]:
        baseline_rate = baseline["success"] / baseline["total"]
        loss75_rate = loss75["success"] / loss75["total"]
        print(f"ผลรอบนี้ (thinking-off): baseline={baseline_rate:.0%} loss75={loss75_rate:.0%}")
        if baseline_rate >= 0.85 and loss75_rate > 0:
            print("-> loss75 ฟื้นจาก 0% แปลว่า thinking mode มีส่วนจริงในการทำให้ connection "
                  "หลุดหมดที่ loss75 เดิม (สมควรพิจารณารันข้อ 4 ใหม่ทั้งชุดด้วย thinking-off)")
        elif baseline_rate >= 0.85 and loss75_rate == 0:
            print("-> loss75 ยังคง 0% แม้ thinking ปิดแล้ว แปลว่า bidirectional loss 75% "
                  "ทั้งสองทิศทางเป็นสาเหตุจริง ไม่เกี่ยวกับ thinking mode — เป็นผลลัพธ์ที่ valid "
                  "เอาไปเขียนลงเปเปอร์ได้ตรงๆ (compounded effective loss เกินกว่าจะรอด)")
        else:
            print("-> baseline เองก็ต่ำกว่า 85% ห้ามตีความ loss75 เลย ตาม falsification check "
                  "เดิม — ต้องตรวจ IFB/checksum offload/CPU gate ก่อน ไม่ใช่ตีความว่าเป็นเรื่อง thinking mode")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--ifb-dev", default="ifb0")
    ap.add_argument("--log-dir", default=os.path.join(
        _THIS_DIR, "logs_tier8_diagnostic_thinking_off_confirm_item4"))
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--skip-checksum-offload-fix", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    total = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    print("run_confirm_thinking_off_item4.py — diagnostic confirmatory re-run "
          "(ข้อ 4, t8in_baseline + t8in_loss75 เท่านั้น)")
    for s in TEST_SCENARIOS:
        print(f"    - {s['name']:24s} ({s['role']}) {s['note']}")
    print(f"  {len(TEST_SCENARIOS)} scenarios x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  log dir: {args.log_dir}")

    if args.dry_run and not args.probe_only:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log, "
              "ยังไม่ probe ingress support (ไม่แตะระบบจริงเลย)")
        return

    net = NetworkController(iface=args.iface, direction="both", ifb_dev=args.ifb_dev)

    probe = net.probe_ingress_support()
    print(f"\ningress+IFB support: {probe['supported']}  ({probe['reason']})")
    if args.probe_only:
        for c in probe["checks"]:
            r = c["result"]
            print(f"   - {c['check']:28s} rc={r['returncode']}  {r.get('stderr','').strip()[:80]}")
        return
    if not probe["supported"]:
        raise SystemExit(
            "\nหยุดก่อนรัน: environment ยังไม่รองรับ ingress shaping\n"
            f"  เหตุผล: {probe['reason']}\n"
            "  วิธีแก้: รันบน host ก่อน -> sudo modprobe ifb numifbs=0 แล้วสั่ง --probe-only ซ้ำ"
        )

    if not args.skip_checksum_offload_fix:
        r = net.disable_checksum_offload()
        status = "สำเร็จ" if r["returncode"] == 0 else f"ไม่สำเร็จ (best-effort, ไม่ fatal): {r.get('stderr','')[:150]}"
        print(f"ปิด NIC checksum offload: {status}")

    import multi_agent_thinking_off  # noqa: E402  (side effect: patch multi_agent)
    import multi_agent as multi_agent_module  # noqa: E402

    checkpoint = load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = "diagnostic_thinking_off_confirm_item4"
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
    _print_verdict(args.log_dir)


if __name__ == "__main__":
    main()
