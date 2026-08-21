#!/usr/bin/env python3
"""
run_confirm_thinking_off_item1.py — Confirmatory re-run เฉพาะจุด t8ap_loss75
ของข้อ 1 (achieved_path) ด้วย thinking mode ปิด
================================================================================
ทำไมต้องมีสคริปต์นี้แยกจาก run_confirm_thinking_off.py (ข้อ 2/3)
--------------------------------------------------------------------------
ตรวจ log ของข้อ 1 จริง (`logs_tier8_achieved_path_No.1`) แยกตาม scenario แล้ว
พบว่า scenario `t8ap_loss75` (loss=75%, mitigation="none" — เงื่อนไขเดียวกับที่
ข้อ 2 ผิดปกติเป๊ะ) ได้ completion **20/20 (100%)** เหมือนกับข้อ 2/3 (ควรจะได้
ใกล้ 14/20 ตาม Tier 5 เดิม) และ median ช่วงห่างระหว่างข้อความ = 91.6 วินาที
(สัญญาณเดียวกับ thinking mode เปิดอยู่ — เทียบ <2s ถ้าปิดจริง) ส่วนอีก 3
scenario ของข้อ 1 (baseline/delay3000/bw50) ไม่มี packet loss เลย จึงไม่ใช่แบบ
ที่ thinking-mode latency จะไปดัน completion ให้ผิดปกติได้ ไม่ต้องรันซ้ำ

**สิ่งที่ยังไม่กระทบ:** เป้าหมายหลักของข้อ 1 คือวัด achieved (qdisc counters/
RTT/throughput จริง) เทียบกับ configured ซึ่งเป็นการวัดระดับเครือข่ายอิสระจาก
ว่า LLM ตอบช้าแค่ไหน — สคริปต์นี้จึงยังคงวัด achieved-path เหมือนเดิมทุกประการ
(ใช้ controller methods เดิม) เพื่อเทียบว่าค่าที่วัดได้ยังสมเหตุสมผลหรือไม่
ภายใต้ thinking-off ด้วย ไม่ใช่แค่เช็ค completion rate อย่างเดียว

ขอบเขต: t8ap_loss75 เท่านั้น (ไม่รันซ้ำ baseline/delay3000/bw50) x 4 tasks x
5 repeats = 20 trials — ตรงกับ n=20 ที่ Tier 5 ใช้ เทียบตรงได้

การใช้งาน
---------
    python3 smoke_test_thinking_off.py            # ทดสอบ wiring ก่อนเสมอ
    python3 run_confirm_thinking_off_item1.py --dry-run
    python3 run_confirm_thinking_off_item1.py --resume
"""
import argparse
import os
import sys
import time
from urllib.parse import urlparse

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # thinking_off_diagnostic/
_TIER8_DIR = os.path.dirname(_THIS_DIR)  # Tier8_EnsureScopeClosure/
_PROJECT_ROOT = os.path.dirname(_TIER8_DIR)  # โฟลเดอร์โปรเจกต์
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TIER8_DIR)
sys.path.insert(0, _THIS_DIR)  # insert ท้ายสุดเพื่อให้อยู่ตำแหน่ง 0 จริง

from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402

REPEATS = 5
PING_COUNT = 5

SCENARIO = {
    "name": "t8ap_confirm_loss75", "scenario_type": "achieved_path_check",
    "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 75,
    "bandwidth_kbit": None,
    "note": "diagnostic confirmatory re-run ของ t8ap_loss75 เดิม (ข้อ 1) "
            "ด้วย thinking mode ปิด (native /api/chat + think:false)",
    "experiment_phase": "diagnostic_thinking_off_confirm_item1",
}


def _ollama_host():
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    return urlparse(base_url).hostname or "host.docker.internal"


def _ollama_probe_url():
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/api/tags"


def _trial_key(task_name, repeat_index):
    return f"thinking_off_confirm_item1__{SCENARIO['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, task_name, task_prompt, run_index, log_dir, multi_agent_module,
                     ollama_host, probe_url):
    print(f"  [{SCENARIO['name']}] task={task_name} run={run_index} -> loss={SCENARIO['loss_pct']}%")

    logger = ExperimentLogger(scenario=SCENARIO, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=SCENARIO["delay_ms"], jitter_ms=SCENARIO["jitter_ms"],
        loss_pct=SCENARIO["loss_pct"], bandwidth_kbit=SCENARIO.get("bandwidth_kbit"),
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

    before = net.snapshot_achieved()
    before["rtt_probe"] = net.measure_rtt_ms(ollama_host, count=PING_COUNT)
    before["throughput_probe"] = net.background_transfer_probe(probe_url)

    try:
        result = multi_agent_module.run_multi_agent_task(
            task_prompt, logger=logger, task_name=task_name,
            strict_reviewer=False, mitigation="none", network_condition=SCENARIO,
        )
        print(f"    -> success={result['success']} rounds={result['rounds']} "
              f"elapsed={result['elapsed_seconds']}s")
    except Exception as exc:  # noqa: BLE001
        logger.log_error(error_type="fatal_error", detail=str(exc)[:300])
        logger.log_outcome(success=False, rounds=0, rejections=0,
                           elapsed_seconds=time.time() - logger.start_time)
        print(f"    -> FATAL ERROR: {exc}")

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
    ap.add_argument("--log-dir", default=os.path.join(
        _THIS_DIR, "logs_tier8_diagnostic_thinking_off_confirm_item1"))
    ap.add_argument("--ollama-host", default=None)
    ap.add_argument("--probe-url", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    ollama_host = args.ollama_host or _ollama_host()
    probe_url = args.probe_url or _ollama_probe_url()
    tasks = TASKS
    total = len(tasks) * REPEATS

    print("run_confirm_thinking_off_item1.py — diagnostic confirmatory re-run (ข้อ 1, t8ap_loss75 เท่านั้น)")
    print(f"  loss=75% x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  log dir: {args.log_dir}")
    print(f"  ประมาณเวลา: ~20-40 นาที ถ้า thinking mode ปิดสำเร็จจริง")

    if args.dry_run:
        print("\nDRY RUN: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่วัด achieved path, ยังไม่เขียน log")
        return

    import multi_agent_thinking_off  # noqa: E402  (side effect: patch multi_agent)
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
                                        args.log_dir, multi_agent_module, ollama_host, probe_url)
            if checkpoint is not None:
                mark_completed(args.log_dir, checkpoint, key, log_file)

    print(f"\nเสร็จสิ้น ใช้เวลารวม {(time.time() - start) / 60:.1f} นาที")
    print(f"ผลลัพธ์อยู่ที่: {args.log_dir}")
    print("ขั้นตอนถัดไป: เทียบ completion rate กับ t8ap_loss75 เดิม (20/20, thinking-on) "
          "และ Tier 5 เดิม (14/20) — และเทียบ achieved loss ที่วัดได้ (qdisc counters) "
          "ว่ายังใกล้เคียง 75% configured เหมือนเดิมไหมภายใต้ thinking-off")


if __name__ == "__main__":
    main()
