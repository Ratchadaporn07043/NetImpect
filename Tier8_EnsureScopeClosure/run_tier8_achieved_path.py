#!/usr/bin/env python3
"""
Tier 8, Item 1 - Achieved-path measurement at four representative paper points.
========================================================================================
Question addressed by this experiment
----------------------
The original 5,300 trials recorded only configured impairment values from tc/netem
and the tc return code; they never measured the achieved path. This experiment
`sec:modelservingpath` และ `sec:scopelimitations`: "a return code verifies
installation, not behavior" / "the highest priority addition here") การทดลองนี้
ปิดช่องว่างนั้น "ที่จุดเดิมที่เปเปอร์อ้างอิงอยู่แล้ว" แทนที่จะรันใหม่ทั้ง 5,300
trial (ซึ่งไม่จำเป็นและใช้เวลาเกินจำเป็นมาก) โดยแนบการวัด achieved 4 อย่างเข้า
alongside each trial:

  1. `tc -s qdisc` counters before and after each trial, measuring kernel drops and overlimits.
  2. ICMP RTT probes to the Ollama host before and after each trial, measuring achieved delay.
  3. TCP retransmission counter จาก /proc/net/snmp ก่อน/หลัง trial — สัญญาณ
     ทางอ้อมของ loss/congestion ที่เกิดขึ้นจริงระดับ transport
  4. background throughput probe ด้วย curl ไปยัง Ollama endpoint ก่อน/หลัง
     trial — วัด throughput จริงที่ทำได้บน path เดียวกัน อิสระจาก LLM call เอง

4 จุดที่เลือก (ตรงกับที่ sigconf.tex อ้างอิงอยู่แล้วในทุกที่ที่พูดถึง
configured-vs-achieved)
-------------------------------------------------------------------------------
  - t8ap_baseline    ไม่มี impairment เลย     — ค่าอ้างอิง (achieved ควรใกล้ 0)
  - t8ap_loss75      loss 75% (configured)    — จุดวิกฤตของแกน loss (Section 5.1)
  - t8ap_delay3000   delay 3,000ms (configured) — จุดสูงสุดที่เคยทดสอบบนแกน delay (Section 5.2)
  - t8ap_bw50        bandwidth 50kbit/s (configured) — จุดต่ำสุดที่เคยทดสอบบนแกน bandwidth (Section 5.2)

4 tasks x 5 repeats x 4 จุด = 80 trials (n=20 ต่อจุด เท่ากับจุดเดี่ยวอื่นในเปเปอร์)

การใช้งาน
---------
    python3 Tier8_EnsureScopeClosure/run_tier8_achieved_path.py --dry-run
    python3 Tier8_EnsureScopeClosure/run_tier8_achieved_path.py --resume
"""
import argparse
import os
import re
import sys
import time
from urllib.parse import urlparse

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # ต้อง insert หลัง _PROJECT_ROOT เพื่อให้ _THIS_DIR อยู่ตำแหน่ง 0 จริง

from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402

REPEATS = 5
PING_COUNT = 5

TEST_SCENARIOS = [
    {
        "name": "t8ap_baseline", "scenario_type": "achieved_path_check",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "ค่าอ้างอิง ไม่มี impairment — achieved ควรใกล้ configured (คือใกล้ 0)",
    },
    {
        "name": "t8ap_loss75", "scenario_type": "achieved_path_check",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 75,
        "bandwidth_kbit": None,
        "note": "จุดวิกฤตของแกน loss (sigconf.tex sec:lossresults) — วัด achieved loss จริง",
    },
    {
        "name": "t8ap_delay3000", "scenario_type": "achieved_path_check",
        "delay_ms": 3000, "requested_delay_ms": 3000, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": None,
        "note": "จุดสูงสุดของแกน delay (sigconf.tex sec:nondetection) — วัด achieved RTT จริง",
    },
    {
        "name": "t8ap_bw50", "scenario_type": "achieved_path_check",
        "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0,
        "bandwidth_kbit": 50,
        "note": "จุดต่ำสุดของแกน bandwidth (sigconf.tex sec:nondetection) — วัด achieved throughput จริง",
    },
]


def _ollama_host():
    """ดึง hostname จาก OLLAMA_BASE_URL สำหรับ ping (ค่าเริ่มต้นเดียวกับที่
    multi_agent.py ใช้เชื่อมต่อโมเดลจริง — วัด achieved path บนเส้นทางเดียวกันเป๊ะ)"""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    parsed = urlparse(base_url)
    return parsed.hostname or "host.docker.internal"


def _ollama_probe_url():
    """URL สำหรับ background throughput probe — ใช้ endpoint list-models ของ
    Ollama (`/api/tags`) เพราะเบาและตอบจริงโดยไม่ต้องรอ inference"""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/api/tags"


def _trial_key(scenario, task_name, repeat_index):
    return f"{scenario['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, scenario, task_name, task_prompt, run_index, log_dir,
                     multi_agent_module, ollama_host, probe_url):
    print(f"  [{scenario['name']}] task={task_name} run={run_index} -> "
          f"delay={scenario['delay_ms']}ms loss={scenario['loss_pct']}% "
          f"bw={scenario.get('bandwidth_kbit')}")

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
        clear_result = net.clear()
        logger.data.setdefault("network_commands", []).append({"action": "clear", "result": clear_result})
        return logger.save()

    # --- ข้อ 1: achieved-path "before" snapshot (หลัง apply, ก่อนเรียก LLM) ---
    before = net.snapshot_achieved()
    before["rtt_probe"] = net.measure_rtt_ms(ollama_host, count=PING_COUNT)
    before["throughput_probe"] = net.background_transfer_probe(probe_url)

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

    # --- ข้อ 1: achieved-path "after" snapshot (ก่อน clear) ---
    after = net.snapshot_achieved()
    after["rtt_probe"] = net.measure_rtt_ms(ollama_host, count=PING_COUNT)
    after["throughput_probe"] = net.background_transfer_probe(probe_url)

    logger.log_achieved({"before": before, "after": after})

    clear_result = net.clear()
    logger.data.setdefault("network_commands", []).append({"action": "clear", "result": clear_result})
    return logger.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="eth0")
    ap.add_argument("--log-dir", default=os.path.join(_THIS_DIR, "logs_tier8_achieved_path"))
    ap.add_argument("--ollama-host", default=None,
                    help="host สำหรับ ping (ค่าเริ่มต้น: ดึงจาก OLLAMA_BASE_URL)")
    ap.add_argument("--probe-url", default=None,
                    help="URL สำหรับ background throughput probe (ค่าเริ่มต้น: {OLLAMA}/api/tags)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    ollama_host = args.ollama_host or _ollama_host()
    probe_url = args.probe_url or _ollama_probe_url()

    tasks = TASKS
    total = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    print("Tier 8, ข้อ 1 — achieved-path measurement (4 จุดตัวแทน)")
    print(f"  ping target  : {ollama_host}")
    print(f"  throughput probe url: {probe_url}")
    for s in TEST_SCENARIOS:
        print(f"    - {s['name']:16s} {s['note']}")
    print(f"  {len(TEST_SCENARIOS)} scenarios x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  ประมาณเวลา ~{total * 90 / 3600:.2f} ชั่วโมง (รวมเวลา ping/curl probe เพิ่มจากเดิมเล็กน้อย)")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่วัด achieved path, ยังไม่เขียน log")
        return

    # self-test แบบเบา: ตรวจว่า ping/curl ใช้งานได้ในสภาพแวดล้อมนี้ก่อนเริ่ม
    # (ผลลัพธ์ error ที่ parse ได้ยังปล่อยให้รันต่อ แค่เตือนไว้ก่อน)
    scratch_net = NetworkController(iface=args.iface, direction="egress")
    rtt_test = scratch_net.measure_rtt_ms(ollama_host, count=1, timeout=10.0)
    if "avg_ms" not in rtt_test:
        print(f"[คำเตือน] ping ไปยัง {ollama_host} ยังไม่สำเร็จตอน self-test: {rtt_test}")
        print("          ตรวจว่า container มีสิทธิ์ ping จริง (บาง environment ปิด ICMP ไว้)")
    else:
        print(f"[self-test] ping {ollama_host} สำเร็จ, avg={rtt_test['avg_ms']}ms")

    throughput_test = scratch_net.background_transfer_probe(probe_url, timeout=10.0)
    if "achieved_kbit_s" not in throughput_test:
        print(f"[คำเตือน] curl ไปยัง {probe_url} ยังไม่สำเร็จตอน self-test: {throughput_test}")
        print("          ตรวจว่า Ollama กำลังรันอยู่จริงและ OLLAMA_BASE_URL ถูกต้อง")
    else:
        print(f"[self-test] curl {probe_url} สำเร็จ, "
              f"{throughput_test['bytes']} bytes ใน {throughput_test['seconds']}s")

    import multi_agent as multi_agent_module  # noqa: E402

    net = NetworkController(iface=args.iface, direction="egress")
    checkpoint = load_checkpoint(args.log_dir) if args.resume else None
    start = time.time()

    for repeat_index in range(1, REPEATS + 1):
        for base_scenario in TEST_SCENARIOS:
            scenario = dict(base_scenario)
            scenario["experiment_phase"] = "tier8_achieved_path"
            for task_name, task_prompt in tasks.items():
                key = _trial_key(scenario, task_name, repeat_index)
                if should_skip(args.resume, checkpoint, key):
                    print(f"  [SKIP] {key}")
                    continue
                log_file = run_single_trial(net, scenario, task_name, task_prompt, repeat_index,
                                            args.log_dir, multi_agent_module, ollama_host, probe_url)
                if checkpoint is not None:
                    mark_completed(args.log_dir, checkpoint, key, log_file)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    print("ขั้นตอนถัดไป: เทียบ configured vs achieved ต่อจุด — เช่น loss_pct=75 (configured) "
          "กับ dropped/sent_pkts ที่วัดได้จริงจาก qdisc counters (achieved), "
          "และ delay_ms=3000 (configured) กับ rtt avg_ms จริงจาก ping")


if __name__ == "__main__":
    main()
