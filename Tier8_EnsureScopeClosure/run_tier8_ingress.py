#!/usr/bin/env python3
"""
Tier 8, ข้อ 4 — bidirectional (ingress + egress) subset ผ่าน IFB
========================================================================
คำถามที่การทดลองนี้ตอบ
----------------------
ทุกการทดลองในโปรเจกต์นี้ (5,300 trials เดิม) ผูก qdisc ไว้ที่ root ของ
interface ซึ่งควบคุม egress (ขาออก) เท่านั้น ดังนั้น null result สองข้อของ
โปรเจกต์มีเงื่อนไขแฝง:
  - bandwidth cap 50 kbit/s ไม่กระทบ completion -> แต่ cap เฉพาะ request ที่เล็ก
    ส่วน response ที่ใหญ่กว่ามากเข้ามาโดยไม่ถูก shape
  - delay สูงถึง 3,000 ms ไม่กระทบ completion -> แต่บวกเฉพาะแพ็กเก็ตขาออก
arm นี้ redirect ingress ไป IFB แล้ว shape ด้วยค่าเดียวกับ egress เพื่อตอบว่า
null ทั้งสองรอด symmetric shaping ไหม

⚠️ สำคัญ: ความพยายามครั้งก่อนหน้าไม่ผ่าน falsification check ของตัวเอง
--------------------------------------------------------------------------
มีความพยายามรันชุดนี้มาก่อนหน้านี้แล้วครั้งหนึ่ง และ baseline (ไม่มี impairment)
กับ positive control (75% loss) ไม่ได้ผลลัพธ์ตามที่คาด (baseline ล้มเหลวสูงกว่า
ที่ควรจะเป็นมาก) — ตรวจพบสัญญาณสองอย่างที่อาจอธิบายได้:
  1. trial ที่ fail จำนวนมากจบด้วย CPU 100% และเวลาที่ใช้กระจุกตัวแคบมาก
     ไม่ว่าจะมี impairment หรือไม่ -> สงสัยว่าเป็น host/CPU resource contention
     ไม่ใช่ผลจาก network shaping
  2. รูปแบบนี้เป็นที่รู้จักกันดีว่าเกิดจาก NIC checksum offload ที่ยังเปิดอยู่
     ทำให้ packet ที่ผ่าน tc mirred redirect ไปยัง IFB มี checksum ไม่ตรงกับที่
     kernel คาดหวัง แล้วถูกดรอปโดยไม่เกี่ยวกับ netem loss ที่ตั้งไว้เลย
สคริปต์นี้จึงเพิ่ม 2 อย่างที่ความพยายามก่อนหน้าไม่มี เพื่อลดความเสี่ยงที่จะเจอ
ปัญหาเดิมซ้ำ:
  - ปิด checksum offload บน NIC ก่อนเริ่ม (best-effort, ผ่าน ethtool)
  - resource gate: เช็ค CPU load ก่อนเริ่มแต่ละ trial ถ้าสูงเกิน threshold
    จะรอแล้วเช็คซ้ำก่อนรันจริง กันไม่ให้ trial เริ่มขณะเครื่องกำลังโหลดหนักจาก
    งานอื่น

4 จุดที่เลือก และเหตุผล (เหมือนเดิม)
-------------------------------------
  1. t8in_baseline    ไม่มี impairment      -> falsification check: IFB path
                                               เองต้องไม่ทำให้ completion ตก
  2. t8in_bw50        bandwidth 50 kbit/s   -> จุดที่ egress-only ให้ null
  3. t8in_delay1000   delay 1,000 ms        -> จุดที่ egress-only ให้ null
  4. t8in_loss75      loss 75%              -> positive control: ต้องเห็น
                                               degradation ถ้าการตั้งค่าทำงานจริง

**จุด 1 และ 4 คือการตรวจสอบตัวการทดลองเอง ถ้าสองจุดนี้ผิดคาด ห้ามตีความจุด 2
และ 3 เลย** — สคริปต์นี้พิมพ์คำตัดสิน PASS/FAIL ของทั้งสอง falsification check
ให้อัตโนมัติตอนจบการรัน ไม่ต้องไปนั่งอ่าน log เองเพื่อรู้ว่าเชื่อผลได้ไหม

ข้อกำหนดของสภาพแวดล้อม
------------------------
ต้องโหลด kernel module `ifb` บน **host** ก่อน (container โหลดเองไม่ได้แม้มี
NET_ADMIN):
    sudo modprobe ifb numifbs=0
สคริปต์เรียก probe_ingress_support() ก่อนเสมอและหยุดทันทีถ้าไม่ผ่าน

การใช้งาน
---------
    python3 Tier8_EnsureScopeClosure/run_tier8_ingress.py --probe-only
    python3 Tier8_EnsureScopeClosure/run_tier8_ingress.py --dry-run
    python3 Tier8_EnsureScopeClosure/run_tier8_ingress.py --resume
"""
import argparse
import glob
import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # ต้อง insert หลัง _PROJECT_ROOT เพื่อให้ _THIS_DIR อยู่ตำแหน่ง 0 จริง

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
        "name": "t8in_baseline", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "falsification check: IFB path เองต้องไม่ทำให้ completion ตก",
        "role": "falsification_baseline",
    },
    {
        "name": "t8in_bw50", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": 50,
        "note": "จุดที่ egress-only ให้ null — ทดสอบว่า null รอด symmetric shaping ไหม",
        "role": "test_point",
    },
    {
        "name": "t8in_delay1000", "scenario_type": "ingress_subset",
        "delay_ms": 1000, "requested_delay_ms": 1000, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "จุดที่ egress-only ให้ null — ทดสอบว่า null รอด symmetric shaping ไหม",
        "role": "test_point",
    },
    {
        "name": "t8in_loss75", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 75,
        "bandwidth_kbit": None,
        "note": "positive control: ต้องเห็น degradation ถ้าการตั้งค่าทำงานจริง",
        "role": "positive_control",
    },
]


def _wait_for_low_cpu(threshold=CPU_GATE_THRESHOLD_PCT, max_wait_s=CPU_GATE_MAX_WAIT_S,
                      poll_s=CPU_GATE_POLL_S):
    """resource gate: เช็ค CPU load ก่อนเริ่ม trial ถ้าสูงเกิน threshold ต่อเนื่อง
    จะรอ (สูงสุด max_wait_s) ก่อนรันจริง — กันไม่ให้ trial ปนกับ host contention
    ที่ไม่เกี่ยวกับ network condition ที่กำลังทดสอบ คืน dict สรุปว่ารอไปเท่าไหร่
    และ CPU ตอนสุดท้ายเท่าไหร่ (บันทึกลง log เพื่อความโปร่งใส)"""
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


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    gate = _wait_for_low_cpu()
    print(f"  [{scenario['name']}] task={task_name} run={run_index} "
          f"-> delay={scenario['delay_ms']}ms loss={scenario['loss_pct']}% "
          f"bw={scenario.get('bandwidth_kbit')} dir={net.direction} "
          f"(cpu_gate: waited={gate['waited_seconds']:.0f}s final_cpu={gate['final_cpu_percent']:.0f}%)")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)
    logger.data["cpu_gate"] = gate

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=scenario.get("bandwidth_kbit"),
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


def _trial_key(scenario, task_name, repeat_index):
    return f"{scenario['name']}__{task_name}__run{repeat_index}"


def _print_falsification_verdict(log_dir):
    """อ่าน log ที่เพิ่งรันเสร็จกลับมาทันที สรุป completion ต่อ scenario แล้ว
    ตัดสิน PASS/FAIL ของ falsification check สองจุด (baseline, positive control)
    แบบอัตโนมัติ ไม่ต้องให้คนมานั่งนับเอง"""
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
    print("สรุปผลและคำตัดสิน falsification check (ข้อ 4)")
    print("=" * 70)
    for s in TEST_SCENARIOS:
        c = counts[s["name"]]
        print(f"  {s['name']:20s} role={s['role']:22s} {c['success']}/{c['total']}")

    baseline = counts["t8in_baseline"]
    loss75 = counts["t8in_loss75"]

    baseline_ok = baseline["total"] > 0 and (baseline["success"] / baseline["total"]) >= 0.85
    loss75_degrades = (
        loss75["total"] > 0 and baseline["total"] > 0
        and (loss75["success"] / loss75["total"]) < (baseline["success"] / baseline["total"])
    )

    print("-" * 70)
    print(f"  Falsification check 1 (baseline ต้องไม่ตก, เกณฑ์ >= 85%): "
          f"{'PASS' if baseline_ok else 'FAIL'}")
    print(f"  Falsification check 2 (positive control ต้องแสดง degradation กว่า baseline): "
          f"{'PASS' if loss75_degrades else 'FAIL'}")
    print("-" * 70)
    if baseline_ok and loss75_degrades:
        print("  ทั้งสอง PASS -> ตีความผลของ t8in_bw50 และ t8in_delay1000 ได้")
    else:
        print("  อย่างน้อยหนึ่งจุด FAIL -> ห้ามตีความ t8in_bw50/t8in_delay1000 ตามกฎที่ตั้งไว้")
        print("  ตรวจ resource_snapshots (cpu_percent) และ cpu_gate ในแต่ละ log ก่อน "
              "ว่าเป็น host contention หรือปัญหาอื่นที่ไม่เกี่ยวกับ network shaping")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--ifb-dev", default="ifb0")
    ap.add_argument("--log-dir", default=os.path.join(_THIS_DIR, "logs_tier8_ingress"))
    ap.add_argument("--probe-only", action="store_true",
                    help="ตรวจว่า environment รองรับ ingress+IFB ไหม แล้วออก")
    ap.add_argument("--skip-checksum-offload-fix", action="store_true",
                    help="ข้ามการปิด NIC checksum offload (ไม่แนะนำ)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    total = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    print(f"Tier 8, ข้อ 4 — bidirectional impairment subset")
    print(f"  {len(TEST_SCENARIOS)} scenarios x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    for s in TEST_SCENARIOS:
        print(f"    - {s['name']:16s} ({s['role']}) {s['note']}")
    print(f"  ประมาณเวลา ~{(60 * 200 + 20 * 900) / 3600:.1f} ชั่วโมง (ไม่รวมเวลารอ cpu gate)")

    # ตรวจ --dry-run "ก่อน" เรียก probe_ingress_support()/disable_checksum_offload()
    # โดยเจตนา — สองฟังก์ชันนั้นมีผลข้างเคียงจริง (สร้าง ifb device, ใส่ qdisc,
    # แก้ NIC offload) --dry-run ต้องไม่แตะระบบจริงเลยแม้แต่นิดเดียว ต่างจาก
    # --probe-only ที่ตั้งใจให้ตรวจ (และมีผลข้างเคียงที่ idempotent/ปลอดภัย) ได้
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
            "  วิธีแก้ที่พบบ่อยที่สุด: รันบน host ก่อน  ->  sudo modprobe ifb numifbs=0\n"
            "  แล้วสั่ง --probe-only ซ้ำเพื่อยืนยัน\n"
            "  ถ้าแก้ไม่ได้ ให้รายงานในเปเปอร์ตามจริงว่าเป็นการวัดแบบ egress-only\n"
            "  และเก็บ bidirectional shaping ไว้เป็น future work — ห้ามอ้างว่าทำแล้ว"
        )

    if not args.skip_checksum_offload_fix:
        r = net.disable_checksum_offload()
        status = "สำเร็จ" if r["returncode"] == 0 else f"ไม่สำเร็จ (best-effort, ไม่ fatal): {r.get('stderr','')[:150]}"
        print(f"ปิด NIC checksum offload: {status}")
    else:
        print("ข้ามการปิด checksum offload ตาม --skip-checksum-offload-fix")

    import multi_agent as multi_agent_module  # noqa: E402

    checkpoint = load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = "tier8_ingress__both"
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
    _print_falsification_verdict(args.log_dir)


if __name__ == "__main__":
    main()
