"""
run_tier2_multiround.py — ตัวรัน Tier 2 ส่วน Multi-Round Tasks + Strict Reviewer
======================================================================================
⚠️ ก่อนรันสคริปต์นี้ ต้อง "แทนที่" multi_agent.py ที่ root โปรเจกต์ด้วย
   Tier2_แกนใหม่/multi_agent.py ก่อน (สำรองไฟล์เดิมไว้ด้วย!):

    cd NetImpact
    cp multi_agent.py multi_agent.py.backup_original
    cp "Tier2_แกนใหม่/multi_agent.py" multi_agent.py

   ไฟล์ที่แทนที่รองรับพารามิเตอร์ strict_reviewer=True/False โดย default=False
   จึงไม่กระทบ experiment เดิม/Tier1 ที่เรียก run_multi_agent_task() แบบไม่ส่ง
   พารามิเตอร์นี้เลย — พฤติกรรมเหมือนเดิมทุกประการ

สคริปต์นี้:
  1. เช็คก่อนว่า multi_agent.py ที่ import ได้รองรับ strict_reviewer จริง
     (กัน user ลืมขั้นตอนด้านบน) — ถ้าไม่รองรับจะ error พร้อมคำแนะนำ
  2. merge TIER2_HARD_TASK_GROUND_TRUTH เข้ากับ experiment.tasks.TASK_GROUND_TRUTH
     (in-place update ของ dict เดิม) เพื่อให้ evaluator.py ประเมิน hard task ได้
     โดยไม่ต้องแก้ evaluator.py/tasks.py เลย
  3. รัน hard tasks (coding_task_hard, planning_decision_hard) x scenario ตัวแทน
     (baseline / moderate delay / high loss / combined-bad) x strict_reviewer=True
     เขียน log ไปที่ logs_tier2_multiround/ (ใหม่ทั้งหมด แยกจาก log dir อื่น)

วิธีรัน:
    python3 "Tier2_แกนใหม่/run_tier2_multiround.py" --dry-run
    python3 "Tier2_แกนใหม่/run_tier2_multiround.py" --resume
"""
import argparse
import inspect
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
# สำคัญ: ต้องแทรก _THIS_DIR ก่อน แล้วค่อยแทรก _PROJECT_ROOT ทีหลัง เพื่อให้
# _PROJECT_ROOT ไปอยู่ที่ index 0 (priority สูงสุด) — โฟลเดอร์นี้ (Tier2_แกนใหม่/)
# มีไฟล์ multi_agent.py ของตัวเองอยู่ด้วย ถ้า _THIS_DIR มี priority สูงกว่า
# _PROJECT_ROOT แล้ว _verify_multi_agent_supports_strict_reviewer() ด้านล่างจะ
# import multi_agent.py ของโฟลเดอร์นี้เสมอ (guard เช็คไม่ได้จริงว่า root ถูก
# cp ตามคำแนะนำหรือยัง)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.controller import NetworkController  # noqa: E402
from experiment.run_experiment import (  # noqa: E402
    _network_result_problems,
    _log_network_result,
    _load_checkpoint,
    _mark_completed,
    _should_skip_trial,
    _trial_key,
    _open_progress,
    _print_dry_run_summary,
    _with_phase,
)
from logger import ExperimentLogger  # noqa: E402
import experiment.tasks as experiment_tasks  # noqa: E402

from tier2_tasks_multiround import TIER2_HARD_TASKS, TIER2_HARD_TASK_GROUND_TRUTH  # noqa: E402

REPEATS = 10  # ต่อ scenario ต่อ task (มากกว่า main-effect ปกติเล็กน้อย เพราะ REVISE
              # มี randomness สูง อยากได้ตัวอย่างพอสำหรับดู distribution ของ rounds)

# scenario ตัวแทน (ไม่ full factorial เพราะเป้าหมายคือดู "อัตราการเกิด multi-round"
# ไม่ใช่ผลของ network ต่อ multi-round โดยตรง — ถ้าอยากขยายเพิ่มทำได้ทีหลัง)
TEST_SCENARIOS = [
    {"name": "t2mr_baseline", "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0, "note": ""},
    {"name": "t2mr_moderate_delay", "delay_ms": 300, "requested_delay_ms": 300, "jitter_ms": 0, "loss_pct": 0, "note": ""},
    {"name": "t2mr_high_loss", "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 30, "note": ""},
    {"name": "t2mr_combined_bad", "delay_ms": 500, "requested_delay_ms": 500, "jitter_ms": 30, "loss_pct": 20, "note": ""},
]


def _verify_multi_agent_supports_strict_reviewer():
    import multi_agent  # import เดียวกับที่ project จริงจะใช้ (root ของ project)
    sig = inspect.signature(multi_agent.run_multi_agent_task)
    if "strict_reviewer" not in sig.parameters:
        raise RuntimeError(
            "multi_agent.py ที่ root โปรเจกต์ยังไม่รองรับ strict_reviewer= \n"
            "กรุณาแทนที่ไฟล์ก่อน (ดูคำแนะนำที่ต้นไฟล์นี้):\n"
            "  cp multi_agent.py multi_agent.py.backup_original\n"
            '  cp "Tier2_แกนใหม่/multi_agent.py" multi_agent.py'
        )
    return multi_agent


def _merge_hard_task_ground_truth():
    experiment_tasks.TASK_GROUND_TRUTH.update(TIER2_HARD_TASK_GROUND_TRUTH)


def run_single_trial_strict(net: NetworkController, scenario: dict, task_name: str,
                             task_prompt: str, run_index: int, log_dir: str, multi_agent_module):
    """เหมือน run_experiment.run_single_trial() ทุกประการ ยกเว้นเรียก
    run_multi_agent_task(..., strict_reviewer=True) แทน"""
    print(f"  [{scenario['name']}] task={task_name} run={run_index} "
          f"-> delay={scenario['delay_ms']}ms jitter={scenario['jitter_ms']}ms "
          f"loss={scenario['loss_pct']}% (strict_reviewer=True)")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                               run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=scenario.get("bandwidth_kbit"),
    )
    _log_network_result(logger, action="apply", result=apply_result)

    apply_problems = _network_result_problems("apply", apply_result)
    if apply_problems:
        logger.log_error(error_type="invalid_trial", detail="network apply failed; skipped LLM run")
        elapsed = time.time() - logger.start_time
        logger.log_outcome(success=False, rounds=0, rejections=0, elapsed_seconds=elapsed)
        print("    -> INVALID TRIAL: network apply failed, skipped LLM run")
    else:
        try:
            result = multi_agent_module.run_multi_agent_task(
                task_prompt, logger=logger, task_name=task_name, strict_reviewer=True
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"rejections={result['rejections']} reviewer_score={result.get('quality_score')} "
                  f"ground_truth_score={result.get('ground_truth_score')} "
                  f"elapsed={result['elapsed_seconds']}s")
        except Exception as e:
            logger.log_error(error_type="fatal_error", detail=str(e)[:300])
            elapsed = time.time() - logger.start_time
            logger.log_outcome(success=False, rounds=0, rejections=0, elapsed_seconds=elapsed)
            print(f"    -> FATAL ERROR: {e}")

    clear_result = net.clear()
    _log_network_result(logger, action="clear", result=clear_result)

    filepath = logger.save()
    print(f"    -> log saved: {filepath}")
    return filepath


def main(iface: str, log_dir: str, dry_run: bool, resume: bool):
    total_trials = len(TEST_SCENARIOS) * len(TIER2_HARD_TASKS) * REPEATS
    print("=== Tier 2: Multi-Round Tasks + Strict Reviewer ===")
    print(f"  {len(TEST_SCENARIOS)} scenarios x {len(TIER2_HARD_TASKS)} hard tasks x {REPEATS} repeats "
          f"= {total_trials} trials")

    if dry_run:
        _print_dry_run_summary(total_trials)
        return

    multi_agent_module = _verify_multi_agent_supports_strict_reviewer()
    _merge_hard_task_ground_truth()

    net = NetworkController(iface=iface)
    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        print(f"เปิด resume mode: พบ completed trials เดิม {len(checkpoint.get('completed', {}))} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, "tier2_multiround")
    start = time.time()
    phase = "tier2_multiround"
    try:
        for repeat_index in range(1, REPEATS + 1):
            print(f"\n######## Repeat {repeat_index}/{REPEATS} ########")
            for base_scenario in TEST_SCENARIOS:
                scenario = _with_phase(base_scenario, phase)
                for task_name, task_prompt in TIER2_HARD_TASKS.items():
                    trial_state["count"] += 1
                    trial_key = _trial_key(phase, scenario, task_name, repeat_index)
                    print(f"\n=== Trial {trial_state['count']}/{total_trials} ===")
                    if _should_skip_trial(resume, checkpoint, trial_key):
                        print(f"  [SKIP] completed checkpoint: {trial_key}")
                        if progress_bar is not None:
                            progress_bar.update(1)
                        continue
                    trial_scenario = dict(scenario)
                    trial_scenario["trial_key"] = trial_key
                    log_file = run_single_trial_strict(
                        net, trial_scenario, task_name, task_prompt, repeat_index, log_dir,
                        multi_agent_module,
                    )
                    if checkpoint is not None:
                        _mark_completed(log_dir, checkpoint, trial_key, log_file)
                    if progress_bar is not None:
                        progress_bar.update(1)
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier2 multiround ทั้งหมด {trial_state['count']} trials "
          f"ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier2: Multi-round hard tasks + strict reviewer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--log-dir", default="logs_tier2_multiround")
    args = parser.parse_args()

    main(iface=args.iface, log_dir=args.log_dir, dry_run=args.dry_run, resume=args.resume)
