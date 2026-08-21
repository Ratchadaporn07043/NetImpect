#!/usr/bin/env python3
"""
Tier 7B — Bidirectional (ingress + egress) impairment subset
=============================================================
Question addressed by this experiment
--------------------------------------
All previous experiments attached qdisc to the interface `root`, which controls
**egress เท่านั้น** จึงหน่วง/ทิ้ง/จำกัดแบนด์วิดท์เฉพาะ inference request และ
TCP ACK ขาออก ส่วน response body จากโมเดล — ซึ่งมักใหญ่กว่า request มาก —
เดินทางเข้ามาโดยไม่ถูก shape เลย

This means the two null results in the project have a hidden condition:

  * bandwidth cap ลงไปถึง 50 kbit/s ไม่กระทบ completion
        -> แต่ cap นั้นจำกัดเฉพาะ payload ฝั่งที่เล็กกว่า
  * delay สูงถึง 3,000 ms ไม่กระทบ completion
        -> แต่ delay นั้นบวกเฉพาะแพ็กเก็ตขาออก ไม่ได้บวกกับ response ที่ stream กลับมา

การทดลองนี้รัน 4 จุดตัวแทนด้วย `direction="both"` (redirect ingress ไป IFB
แล้ว shape ที่นั่นด้วยค่าเดียวกับ egress) เพื่อตอบว่า null ทั้งสองรอดจาก
symmetric shaping ไหม

Selected points (80 trials, approximately 8 hours)
--------------------------------------------------
  1. t7in_baseline        ไม่มี impairment  — ยืนยันว่า IFB path เองไม่ทำให้พัง
  2. t7in_bw50            bandwidth 50 kbit/s  — จุดที่ egress-only ให้ null
  3. t7in_delay1000       delay 1,000 ms       — จุดที่ egress-only ให้ null
  4. t7in_loss75          loss 75%             — positive control: ต้องเห็น
                                                  degradation เหมือน egress-only
                                                  ถ้าไม่เห็น แปลว่าการตั้งค่า
                                                  ingress ไม่ทำงานจริง

Points 1 and 4 are falsification checks for the experiment itself. If either point
ผิดคาด ห้ามตีความจุดที่ 2 และ 3 เลย

Environment requirements (checked automatically before running)
----------------------------------------------------------------
  * kernel module ifb ต้องโหลดบน **host** ก่อน:  sudo modprobe ifb numifbs=0
  * container ต้องมี NET_ADMIN (docker-compose ของโปรเจกต์มีให้แล้ว)
  * container ต้องมี iproute2 (`ip`)
The script always calls probe_ingress_support() first and stops immediately with
ถ้าไม่ผ่าน — ดีกว่าไปพบตอนตี 3 ว่ารันทั้งคืนแล้วไม่ได้ impair ingress จริง

Usage
-----
    python3 Tier7_ScopeClosure/run_tier7_ingress.py --probe-only
    python3 Tier7_ScopeClosure/run_tier7_ingress.py --dry-run
    python3 Tier7_ScopeClosure/run_tier7_ingress.py --resume
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

REPEATS = 5

TEST_SCENARIOS = [
    {
        "name": "t7in_baseline", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "falsification check: IFB path เองต้องไม่ทำให้ completion ตก",
    },
    {
        "name": "t7in_bw50", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": 50,
        "note": "จุดที่ egress-only ให้ null — ทดสอบว่า null รอด symmetric shaping ไหม",
    },
    {
        "name": "t7in_delay1000", "scenario_type": "ingress_subset",
        "delay_ms": 1000, "requested_delay_ms": 1000, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "จุดที่ egress-only ให้ null — ทดสอบว่า null รอด symmetric shaping ไหม",
    },
    {
        "name": "t7in_loss75", "scenario_type": "ingress_subset",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 75,
        "bandwidth_kbit": None,
        "note": "positive control: ต้องเห็น degradation ถ้าการตั้งค่าทำงานจริง",
    },
]


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


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    print(f"  [{scenario['name']}] task={task_name} run={run_index} "
          f"-> delay={scenario['delay_ms']}ms loss={scenario['loss_pct']}% "
          f"bw={scenario.get('bandwidth_kbit')} dir={net.direction}")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=scenario.get("bandwidth_kbit"),
    )
    # Store every tc command in the log, including the ingress branch, so that
    # bidirectional shaping can be verified later without relying on the folder name.
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--ifb-dev", default="ifb0")
    ap.add_argument("--log-dir", default="Tier7_ScopeClosure/logs_tier7_ingress")
    ap.add_argument("--probe-only", action="store_true",
                    help="ตรวจว่า environment รองรับ ingress+IFB ไหม แล้วออก")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    net = NetworkController(iface=args.iface, direction="both", ifb_dev=args.ifb_dev)

    probe = net.probe_ingress_support()
    print(f"ingress+IFB support: {probe['supported']}  ({probe['reason']})")
    if args.probe_only:
        for c in probe["checks"]:
            r = c["result"]
            print(f"   - {c['check']:24s} rc={r['returncode']}  {r.get('stderr','').strip()[:80]}")
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

    tasks = TASKS
    total = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    print(f"\nTier 7B — bidirectional impairment subset")
    print(f"  {len(TEST_SCENARIOS)} scenarios x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    for s in TEST_SCENARIOS:
        print(f"    - {s['name']:16s} {s['note']}")
    print(f"  ประมาณเวลา ~{(60 * 200 + 20 * 900) / 3600:.1f} ชั่วโมง")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log")
        return

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import multi_agent as multi_agent_module  # noqa: E402

    checkpoint = _load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = "tier7_ingress__both"
            for task_name, task_prompt in tasks.items():
                key = f"{scenario['name']}__{task_name}__run{repeat_index}"
                if args.resume and checkpoint is not None and key in checkpoint.get("completed", {}):
                    print(f"  [SKIP] {key}")
                    continue
                log_file = run_single_trial(net, scenario, task_name, task_prompt,
                                            repeat_index, args.log_dir, multi_agent_module)
                if checkpoint is not None:
                    checkpoint.setdefault("completed", {})[key] = {
                        "log_file": log_file,
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                    _save_checkpoint(args.log_dir, checkpoint)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    print("อย่าลืม: เทียบผลกับ egress-only เดิมที่จุดเดียวกัน "
          "(bandwidth 50 kbit/s, delay 1000 ms, loss 75%) ก่อนสรุปอะไร")


if __name__ == "__main__":
    main()
