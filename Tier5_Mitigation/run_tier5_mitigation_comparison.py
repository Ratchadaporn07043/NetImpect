"""
run_tier5_mitigation_comparison.py — เปรียบเทียบ before/after Mitigation A/B
================================================================================
⚠️ ก่อนรันสคริปต์นี้ ต้องแทนที่ multi_agent.py ที่ root โปรเจกต์ด้วย
   Tier5_Mitigation/multi_agent.py ก่อน (สำรองไฟล์เดิม/ของ Tier2 ไว้ด้วย):

    cd NetImpact
    cp multi_agent.py multi_agent.py.backup_original
    cp "Tier5_Mitigation/multi_agent.py" multi_agent.py

รันแกน loss main-effect เดิม (11 ระดับ: 0,1,5,10,15,20,25,30,40,50,75%) x 4 tasks
x 5 repeats = 220 trials ต่อเงื่อนไข x 3 เงื่อนไข (none / adaptive_timeout /
context_cache) = 660 trials รวม เพื่อเทียบ:
  - error/timeout rate ก่อน-หลัง Mitigation A (adaptive timeout)
  - จำนวน LLM call เฉลี่ยต่อ trial ก่อน-หลัง Mitigation B (context cache)
  - success rate / ground_truth_score เฉลี่ย ก่อน-หลังทั้งคู่

เลือก loss axis เพราะจาก NetImpact_ผลการทดลองเชิงลึก.md loss คือปัจจัยที่มี
ผลชัดเจนที่สุด (loss cliff ~50-75%) — ถ้า mitigation ช่วยได้จริง ควรเห็นผลชัด
ที่สุดตรงนี้

วิธีรัน:
    python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --dry-run
    python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition none --resume
    python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition adaptive_timeout --resume
    python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition context_cache --resume
    python3 "Tier5_Mitigation/run_tier5_mitigation_comparison.py" --condition all --resume
"""
import argparse
import inspect
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
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
from experiment.scenarios import PACKET_LOSS_LEVELS_PCT, THREE_DAY_MAIN_EFFECT_REPEATS  # noqa: E402
from experiment.tasks import TASKS  # noqa: E402
from logger import ExperimentLogger  # noqa: E402

CONDITIONS = ["none", "adaptive_timeout", "context_cache"]
REPEATS = THREE_DAY_MAIN_EFFECT_REPEATS  # 5 เท่าของเดิม เพื่อเทียบตรงกับ main-effect เดิมได้


def _loss_scenarios():
    scenarios = []
    for loss_pct in PACKET_LOSS_LEVELS_PCT:
        scenarios.append({
            "name": f"tier5_loss_loss{str(loss_pct).replace('.', 'p')}",
            "delay_ms": 0,
            "requested_delay_ms": 0,
            "jitter_ms": 0,
            "loss_pct": loss_pct,
            "note": "",
        })
    return scenarios


def _verify_multi_agent_supports_mitigation():
    import multi_agent
    sig = inspect.signature(multi_agent.run_multi_agent_task)
    if "mitigation" not in sig.parameters or "network_condition" not in sig.parameters:
        raise RuntimeError(
            "multi_agent.py ที่ root โปรเจกต์ยังไม่รองรับ mitigation=/network_condition= \n"
            "กรุณาแทนที่ไฟล์ก่อน (ดูคำแนะนำที่ต้นไฟล์นี้):\n"
            "  cp multi_agent.py multi_agent.py.backup_original\n"
            '  cp "Tier5_Mitigation/multi_agent.py" multi_agent.py'
        )
    return multi_agent


def run_single_trial_mitigation(net: NetworkController, scenario: dict, task_name: str,
                                 task_prompt: str, run_index: int, log_dir: str,
                                 mitigation: str, multi_agent_module):
    print(f"  [{scenario['name']}] task={task_name} run={run_index} mitigation={mitigation} "
          f"-> loss={scenario['loss_pct']}%")

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
                task_prompt, logger=logger, task_name=task_name,
                mitigation=mitigation, network_condition=scenario,
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"rejections={result['rejections']} ground_truth_score={result.get('ground_truth_score')} "
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


def _run_condition(net, condition, tasks, log_dir, resume, multi_agent_module):
    scenarios = _loss_scenarios()
    total_trials = len(scenarios) * len(tasks) * REPEATS
    print(f"\n######## Condition: mitigation={condition} ({total_trials} trials) ########")

    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        print(f"เปิด resume mode: พบ completed trials เดิม {len(checkpoint.get('completed', {}))} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, f"tier5_{condition}")
    phase = f"tier5_mitigation__{condition}"
    try:
        for repeat_index in range(1, REPEATS + 1):
            for base_scenario in scenarios:
                scenario = _with_phase(base_scenario, phase)
                for task_name, task_prompt in tasks.items():
                    trial_state["count"] += 1
                    trial_key = _trial_key(phase, scenario, task_name, repeat_index)
                    if _should_skip_trial(resume, checkpoint, trial_key):
                        print(f"  [SKIP] completed checkpoint: {trial_key}")
                        if progress_bar is not None:
                            progress_bar.update(1)
                        continue
                    trial_scenario = dict(scenario)
                    trial_scenario["trial_key"] = trial_key
                    log_file = run_single_trial_mitigation(
                        net, trial_scenario, task_name, task_prompt, repeat_index, log_dir,
                        condition, multi_agent_module,
                    )
                    if checkpoint is not None:
                        _mark_completed(log_dir, checkpoint, trial_key, log_file)
                    if progress_bar is not None:
                        progress_bar.update(1)
    finally:
        if progress_bar is not None:
            progress_bar.close()


def main(condition_arg: str, iface: str, log_dir_prefix: str, dry_run: bool, resume: bool):
    conditions = CONDITIONS if condition_arg == "all" else [condition_arg]
    tasks = TASKS
    scenarios = _loss_scenarios()
    per_condition_trials = len(scenarios) * len(tasks) * REPEATS

    print("=== Tier 5: Mitigation Before/After Comparison (loss axis) ===")
    for c in conditions:
        print(f"  - mitigation={c}: {per_condition_trials} trials -> {log_dir_prefix}_{c}/")
    print(f"รวม {per_condition_trials * len(conditions)} trials")

    if dry_run:
        _print_dry_run_summary(per_condition_trials * len(conditions))
        return

    multi_agent_module = _verify_multi_agent_supports_mitigation()
    net = NetworkController(iface=iface)
    start = time.time()

    for condition in conditions:
        log_dir = f"{log_dir_prefix}_{condition}"
        _run_condition(net, condition, tasks, log_dir, resume, multi_agent_module)

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier5 mitigation comparison ทั้งหมด ใช้เวลารวม {elapsed/60:.1f} นาที")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier5: before/after mitigation comparison on loss axis")
    parser.add_argument("--condition", choices=CONDITIONS + ["all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--log-dir-prefix", default="logs_tier5")
    args = parser.parse_args()

    main(condition_arg=args.condition, iface=args.iface, log_dir_prefix=args.log_dir_prefix,
         dry_run=args.dry_run, resume=args.resume)
