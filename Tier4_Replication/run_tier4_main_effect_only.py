"""
run_tier4_main_effect_only.py — รัน main-effect ซ้ำด้วยโมเดลอื่น (multi-model replication)
====================================================================================================
เป้าหมาย: ผลการทดลองเดิมทั้งหมดใช้ Qwen3:8b ตัวเดียว — reviewer AINTEC จะถามว่า
"finding นี้เป็น general pattern ของ multi-agent LLM system หรือเป็นแค่ quirk
เฉพาะของโมเดลนี้" การรันซ้ำด้วยโมเดลอื่น (ขนาดใกล้เคียงกัน) บนแกน main-effect
เดิม (delay/loss/jitter) คือหลักฐานที่ตรงจุดที่สุดสำหรับคำถามนี้

ไม่แก้ experiment/scenarios.py หรือ run_experiment.py เลย — สคริปต์นี้ import
MAIN_EFFECT_SCENARIOS ตรงๆ จากของเดิม แล้วรันผ่าน _run_scenario (ฟังก์ชันเดิม)
ตัวแปรที่เปลี่ยนคือ MODEL_NAME (env var ที่ multi_agent.py อ่านตอน import)

⚠️ สำคัญ: MODEL_NAME ต้องตั้งก่อนรันสคริปต์ (เป็น env var ระดับ process เพราะ
multi_agent.py อ่านค่านี้ตอน import module) — ตั้งผ่าน env var ตรงๆ เวลาเรียก
ไม่ใช่ --arg ของสคริปต์นี้ (กัน bug: ถ้าตั้งผ่าน argparse แล้วค่อย os.environ
หลัง multi_agent ถูก import ไปแล้วจะไม่มีผลอะไรเลย)

วิธีรัน:
    ollama pull llama3.1:8b     # เตรียมโมเดลที่สองไว้ก่อน (ต้องมีขนาดใกล้เคียง 8b)

    MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --dry-run
    MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --resume

log จะถูกเขียนไปที่ logs_tier4_<MODEL_NAME แปลง / เป็น _>/ โดยอัตโนมัติ
(เช่น MODEL_NAME=llama3.1:8b -> logs_tier4_llama3.1_8b/) เพื่อไม่ให้ผลของแต่ละ
โมเดลไปปนกัน และเทียบกับ logs_three_day/ เดิม (ซึ่งถือเป็นผลของ qwen3:8b) ได้ตรงไปตรงมา
"""
import argparse
import os
import re
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.controller import NetworkController  # noqa: E402
from experiment.run_experiment import (  # noqa: E402
    _run_scenario,
    _load_checkpoint,
    _open_progress,
    _print_dry_run_summary,
)
from experiment.scenarios import MAIN_EFFECT_SCENARIOS, THREE_DAY_MAIN_EFFECT_REPEATS  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402


def _safe_model_dirname(model_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", model_name)


def main(iface: str, log_dir: str, dry_run: bool, resume: bool, repeats: int):
    model_name = os.environ.get("MODEL_NAME", "qwen3:8b")
    print(f"=== Tier 4: Main-Effect Replication ด้วย MODEL_NAME={model_name} ===")
    if model_name == "qwen3:8b":
        print("  [คำเตือน] MODEL_NAME ยังเป็น qwen3:8b (default เดิม) — ถ้าต้องการ replicate "
              "ด้วยโมเดลอื่น ต้องตั้ง env var MODEL_NAME ก่อนรันสคริปต์นี้ เช่น:\n"
              "    MODEL_NAME=llama3.1:8b python3 run_tier4_main_effect_only.py")

    tasks = TASKS
    total_trials = len(MAIN_EFFECT_SCENARIOS) * len(tasks) * repeats
    print(f"  main-effect scenarios: {len(MAIN_EFFECT_SCENARIOS)} x {len(tasks)} tasks x "
          f"{repeats} repeats = {total_trials} trials")

    if dry_run:
        _print_dry_run_summary(total_trials)
        return

    net = NetworkController(iface=iface)
    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        print(f"เปิด resume mode: พบ completed trials เดิม {len(checkpoint.get('completed', {}))} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, f"tier4_{model_name}")
    start = time.time()
    phase = f"tier4_main_effect_replicate__{_safe_model_dirname(model_name)}"
    try:
        for repeat_index in range(1, repeats + 1):
            print(f"\n######## Repeat {repeat_index}/{repeats} ########")
            for scenario in MAIN_EFFECT_SCENARIOS:
                _run_scenario(
                    net, scenario, tasks, repeat_index, log_dir, trial_state, total_trials,
                    phase=phase, progress_bar=progress_bar,
                    checkpoint=checkpoint, resume=resume,
                )
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier4 main-effect replication ({model_name}) ทั้งหมด "
          f"{trial_state['count']} trials ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier4: rerun main-effect scenarios with a different MODEL_NAME (multi-model replication)"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--repeats", type=int, default=THREE_DAY_MAIN_EFFECT_REPEATS,
                         help=f"จำนวน repeat ต่อ scenario (default={THREE_DAY_MAIN_EFFECT_REPEATS} เท่ากับของเดิม)")
    parser.add_argument("--log-dir", default=None,
                         help="default: logs_tier4_<model_name> (สร้างอัตโนมัติจาก MODEL_NAME env var)")
    args = parser.parse_args()

    log_dir = args.log_dir
    if log_dir is None:
        model_name = os.environ.get("MODEL_NAME", "qwen3:8b")
        log_dir = f"logs_tier4_{_safe_model_dirname(model_name)}"

    main(iface=args.iface, log_dir=log_dir, dry_run=args.dry_run, resume=args.resume,
         repeats=args.repeats)
