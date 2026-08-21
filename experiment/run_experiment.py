"""
Experiment Runner
===================
รัน 2 ชุดการทดลอง:
  1. factorial 2x2x2 แบบ tournament พบกันหมด
  2. combined delay x packet loss x jitter แบบพบกันหมดทุก combination

วิธีรัน (จากใน container):
    python3 experiment/run_experiment.py                         # tournament + combined full run
    python3 experiment/run_experiment.py --quick                  # test สั้นมาก
    python3 experiment/run_experiment.py --pilot                  # pilot subset
    python3 experiment/run_experiment.py --three-day --dry-run
    python3 experiment/run_experiment.py --three-day --resume     # bounded design + resume checkpoint
    python3 experiment/run_experiment.py --tournament-only
    python3 experiment/run_experiment.py --combined-only
"""
import argparse
import json
import os
import sys
import time

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiment.controller import NetworkController
from experiment.scenarios import (
    BASELINE_SCENARIO,
    COMBINED_SCENARIOS,
    MAIN_EFFECT_SCENARIOS,
    PILOT_COMBINED_SCENARIOS,
    PILOT_MATCHES,
    PILOT_REPEATS,
    REPEATS_PER_SCENARIO,
    THREE_DAY_BASELINE_REPEATS,
    THREE_DAY_COMBINED_REPEATS,
    THREE_DAY_COMBINED_SCENARIOS,
    THREE_DAY_MAIN_EFFECT_REPEATS,
    THREE_DAY_TOURNAMENT_REPEATS,
    TOURNAMENT_MATCHES,
)
from experiment.tasks import TASKS
from logger import ExperimentLogger


def _network_result_problems(action: str, result: dict):
    """คืนรายการปัญหาจากผล apply()/clear() รวม sub-result ที่สำคัญ"""
    if result is None:
        return []

    problems = []
    if result.get("returncode") not in (0, None):
        problems.append(f"{action}: returncode={result.get('returncode')} stderr={result.get('stderr', '')[:200]}")

    clear_before = result.get("clear_before_apply")
    if clear_before and clear_before.get("returncode") not in (0, None):
        problems.append(
            f"{action}_clear_before: returncode={clear_before.get('returncode')} "
            f"stderr={clear_before.get('stderr', '')[:200]}"
        )

    tbf = result.get("tbf")
    if tbf and tbf.get("returncode") not in (0, None):
        problems.append(f"{action}_tbf: returncode={tbf.get('returncode')} stderr={tbf.get('stderr', '')[:200]}")

    return problems


def _log_network_result(logger: ExperimentLogger, action: str, result: dict):
    """ตรวจ returncode ของ NetworkController.apply()/clear()"""
    for detail in _network_result_problems(action, result):
        logger.log_error(error_type=f"network_{action}_failed", detail=detail)


def _with_phase(base_scenario: dict, phase: str) -> dict:
    """เพิ่ม phase metadata ลงใน scenario โดยไม่แก้ dict ต้นฉบับ"""
    scenario = dict(base_scenario)
    scenario["experiment_phase"] = phase
    return scenario


def _scenario_for_match(base_scenario: dict, match: dict, side: str, phase: str = "tournament") -> dict:
    """เพิ่ม metadata ของ tournament ลงใน scenario โดยไม่แก้ dict ต้นฉบับ"""
    opponent_key = "scenario_b" if side == "A" else "scenario_a"
    scenario = _with_phase(base_scenario, phase)
    scenario["tournament"] = {
        "match_id": match["match_id"],
        "round_index": match["round_index"],
        "pair_index": match["pair_index"],
        "side": side,
        "opponent": match[opponent_key]["name"],
        "pair": match["scenario_names"],
    }
    return scenario


def _advance_progress(progress_bar):
    if progress_bar is not None:
        progress_bar.update(1)


def _open_progress(total_trials: int, desc: str):
    if tqdm is None:
        return None
    return tqdm(total=total_trials, desc=desc, unit="trial")


def _checkpoint_path(log_dir: str) -> str:
    return os.path.join(log_dir, "_checkpoint", "checkpoint.json")


def _trial_key(phase: str, scenario: dict, task_name: str, run_index: int) -> str:
    tournament = scenario.get("tournament") or {}
    match_id = tournament.get("match_id", "no_match")
    side = tournament.get("side", "no_side")
    return "::".join([
        phase or scenario.get("experiment_phase", "unknown_phase"),
        str(match_id),
        str(side),
        scenario["name"],
        task_name,
        f"run{run_index}",
    ])


def _scan_completed_logs(log_dir: str) -> dict:
    completed = {}
    if not os.path.isdir(log_dir):
        return completed

    for filename in os.listdir(log_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(log_dir, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        network_condition = record.get("network_condition") or {}
        outcome = record.get("outcome")
        trial_key = network_condition.get("trial_key")
        if trial_key and outcome:
            completed[trial_key] = {
                "log_file": path,
                "completed_at": record.get("saved_at"),
                "source": "log_scan",
            }
    return completed


def _load_checkpoint(log_dir: str) -> dict:
    path = _checkpoint_path(log_dir)
    checkpoint = {
        "version": 1,
        "log_dir": os.path.abspath(log_dir),
        "completed": {},
    }

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                checkpoint.update(loaded)
                checkpoint.setdefault("completed", {})
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: อ่าน checkpoint ไม่สำเร็จ จะ scan log แทน: {exc}")

    scanned = _scan_completed_logs(log_dir)
    checkpoint["completed"].update(scanned)
    return checkpoint


def _save_checkpoint(log_dir: str, checkpoint: dict):
    path = _checkpoint_path(log_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    checkpoint["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def _mark_completed(log_dir: str, checkpoint: dict, trial_key: str, log_file: str):
    checkpoint.setdefault("completed", {})[trial_key] = {
        "log_file": log_file,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "checkpoint",
    }
    _save_checkpoint(log_dir, checkpoint)


def _should_skip_trial(resume: bool, checkpoint: dict, trial_key: str) -> bool:
    return resume and checkpoint is not None and trial_key in checkpoint.get("completed", {})


def run_single_trial(net: NetworkController, scenario: dict, task_name: str,
                      task_prompt: str, run_index: int, log_dir: str = "logs"):
    """รัน 1 scenario"""

    bandwidth_kbit = scenario.get("bandwidth_kbit")
    tournament = scenario.get("tournament", {})
    phase = scenario.get("experiment_phase")
    phase_label = f" phase={phase}" if phase else ""
    match_label = ""
    if tournament:
        match_label = (f" match={tournament['match_id']} side={tournament['side']} "
                       f"vs={tournament['opponent']}")

    requested_delay = scenario.get("requested_delay_ms", scenario["delay_ms"])
    note = f" note={scenario['note']}" if scenario.get("note") else ""
    print(f"  [{scenario['name']}]{phase_label}{match_label} task={task_name} run={run_index} "
          f"-> requested_delay={requested_delay}ms applied_delay={scenario['delay_ms']}ms "
          f"jitter={scenario['jitter_ms']}ms loss={scenario['loss_pct']}%"
          + (f" bandwidth={bandwidth_kbit}kbit" if bandwidth_kbit else "")
          + note)

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                               run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=bandwidth_kbit,
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
            from multi_agent import run_multi_agent_task

            result = run_multi_agent_task(task_prompt, logger=logger, task_name=task_name)
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"rejections={result['rejections']} reviewer_score={result.get('quality_score')} "
                  f"ground_truth_score={result.get('ground_truth_score')} "
                  f"ground_truth_passed={result.get('ground_truth_passed')} "
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


def _run_match(net: NetworkController, match: dict, tasks: dict, repeat_index: int,
               log_dir: str, trial_state: dict, total_trials: int, phase: str = "tournament",
               progress_bar=None, checkpoint: dict = None, resume: bool = False):
    print(f"\n--- Tournament Match {match['match_id']} | Round {match['round_index']} "
          f"Pair {match['pair_index']}: {match['scenario_a']['name']} vs {match['scenario_b']['name']} ---")

    for side, scenario_key in (("A", "scenario_a"), ("B", "scenario_b")):
        scenario = _scenario_for_match(match[scenario_key], match, side, phase=phase)
        for task_name, task_prompt in tasks.items():
            trial_state["count"] += 1
            trial_key = _trial_key(phase, scenario, task_name, repeat_index)
            print(f"\n=== Trial {trial_state['count']}/{total_trials} ===")
            if _should_skip_trial(resume, checkpoint, trial_key):
                print(f"  [SKIP] completed checkpoint: {trial_key}")
                _advance_progress(progress_bar)
                continue
            trial_scenario = dict(scenario)
            trial_scenario["trial_key"] = trial_key
            log_file = run_single_trial(net, trial_scenario, task_name, task_prompt, repeat_index, log_dir)
            if checkpoint is not None:
                _mark_completed(log_dir, checkpoint, trial_key, log_file)
            _advance_progress(progress_bar)


def _run_scenario(net: NetworkController, scenario: dict, tasks: dict, repeat_index: int,
                  log_dir: str, trial_state: dict, total_trials: int, phase: str,
                  progress_bar=None, checkpoint: dict = None, resume: bool = False):
    scenario = _with_phase(scenario, phase)
    print(f"\n--- {phase} Scenario: {scenario['name']} ---")
    for task_name, task_prompt in tasks.items():
        trial_state["count"] += 1
        trial_key = _trial_key(phase, scenario, task_name, repeat_index)
        print(f"\n=== Trial {trial_state['count']}/{total_trials} ===")
        if _should_skip_trial(resume, checkpoint, trial_key):
            print(f"  [SKIP] completed checkpoint: {trial_key}")
            _advance_progress(progress_bar)
            continue
        trial_scenario = dict(scenario)
        trial_scenario["trial_key"] = trial_key
        log_file = run_single_trial(net, trial_scenario, task_name, task_prompt, repeat_index, log_dir)
        if checkpoint is not None:
            _mark_completed(log_dir, checkpoint, trial_key, log_file)
        _advance_progress(progress_bar)


def _estimate_hours(total_trials: int, seconds_per_trial: float = 145.8) -> float:
    """ประมาณเวลาจากค่าเฉลี่ย pilot เดิม"""
    return total_trials * seconds_per_trial / 3600


def _print_dry_run_summary(total_trials: int):
    est_hours = _estimate_hours(total_trials)
    print(f"ประมาณเวลา ≈ {est_hours:.1f} ชั่วโมง ({est_hours / 24:.2f} วัน) จากค่าเฉลี่ย 145.8 วินาที/trial")
    print("DRY RUN เท่านั้น: ยังไม่ apply network, ยังไม่เรียก LLM, ยังไม่เขียน log")


def _run_three_day_plan(net: NetworkController, tasks: dict, log_dir: str,
                        dry_run: bool = False, resume: bool = False):
    """
    แผนรันภายในเวลาประมาณ 3 วัน โดยยังครอบคลุมคำถามหลักมากที่สุด:
      1. tournament เดิมครบทุกคู่ 1 repeat
      2. main effects ครบทุกระดับ 5 repeats
      3. combined stratified sample 100 จุด 1 repeat
      4. baseline 20 repeats
    """
    phases = [
        {
            "name": "three_day_tournament",
            "kind": "matches",
            "items": TOURNAMENT_MATCHES,
            "repeats": THREE_DAY_TOURNAMENT_REPEATS,
        },
        {
            "name": "three_day_main_effect",
            "kind": "scenarios",
            "items": MAIN_EFFECT_SCENARIOS,
            "repeats": THREE_DAY_MAIN_EFFECT_REPEATS,
        },
        {
            "name": "three_day_combined_sample",
            "kind": "scenarios",
            "items": THREE_DAY_COMBINED_SCENARIOS,
            "repeats": THREE_DAY_COMBINED_REPEATS,
        },
        {
            "name": "three_day_baseline_extra",
            "kind": "scenarios",
            "items": [BASELINE_SCENARIO],
            "repeats": THREE_DAY_BASELINE_REPEATS,
        },
    ]

    total_trials = 0
    for phase in phases:
        item_count = len(phase["items"])
        scenario_multiplier = 2 if phase["kind"] == "matches" else 1
        total_trials += item_count * scenario_multiplier * len(tasks) * phase["repeats"]

    print("เริ่ม three-day bounded design:")
    for phase in phases:
        item_count = len(phase["items"])
        scenario_multiplier = 2 if phase["kind"] == "matches" else 1
        phase_trials = item_count * scenario_multiplier * len(tasks) * phase["repeats"]
        print(f"  - {phase['name']}: {phase_trials} trials")
    print(f"รวมทั้งหมด {total_trials} trials")
    if dry_run:
        _print_dry_run_summary(total_trials)
        return

    trial_state = {"count": 0}
    start = time.time()
    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        completed_count = len(checkpoint.get("completed", {}))
        print(f"เปิด resume mode: พบ completed trials เดิม {completed_count} รายการ")

    progress_bar = _open_progress(total_trials, "three-day")
    try:
        for phase in phases:
            print(f"\n######## Phase: {phase['name']} ########")
            for repeat_index in range(1, phase["repeats"] + 1):
                print(f"\n######## Repeat {repeat_index}/{phase['repeats']} ########")
                if phase["kind"] == "matches":
                    for match in phase["items"]:
                        _run_match(
                            net, match, tasks, repeat_index, log_dir, trial_state, total_trials,
                            phase=phase["name"], progress_bar=progress_bar,
                            checkpoint=checkpoint, resume=resume,
                        )
                else:
                    for scenario in phase["items"]:
                        _run_scenario(
                            net, scenario, tasks, repeat_index, log_dir, trial_state, total_trials,
                            phase=phase["name"], progress_bar=progress_bar,
                            checkpoint=checkpoint, resume=resume,
                        )
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น three-day plan ทั้งหมด {trial_state['count']} trials ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")
    if resume:
        print(f"checkpoint อยู่ที่: {os.path.abspath(_checkpoint_path(log_dir))}")


def main(quick: bool = False, pilot: bool = False, three_day: bool = False,
         iface: str = "eth0", log_dir: str = "logs",
         tournament_only: bool = False, combined_only: bool = False,
         dry_run: bool = False, resume: bool = False):
    net = NetworkController(iface=iface)

    if three_day:
        tasks = TASKS
        _run_three_day_plan(net, tasks, log_dir, dry_run=dry_run, resume=resume)
        return

    if quick:
        matches = TOURNAMENT_MATCHES[:1]
        combined_scenarios = COMBINED_SCENARIOS[:1]
        tasks = {"coding_task": TASKS["coding_task"]}
        repeats = 1
    elif pilot:
        matches = PILOT_MATCHES
        combined_scenarios = PILOT_COMBINED_SCENARIOS
        tasks = {"coding_task": TASKS["coding_task"],
                 "research_summary": TASKS["research_summary"]}
        repeats = PILOT_REPEATS
    else:
        matches = TOURNAMENT_MATCHES
        combined_scenarios = COMBINED_SCENARIOS
        tasks = TASKS
        repeats = REPEATS_PER_SCENARIO

    if tournament_only:
        combined_scenarios = []
    if combined_only:
        matches = []

    tournament_trials = len(matches) * 2 * len(tasks) * repeats
    combined_trials = len(combined_scenarios) * len(tasks) * repeats
    total_trials = tournament_trials + combined_trials

    print(f"เริ่ม experiment: tournament={len(matches)} matches ({tournament_trials} trials), "
          f"combined={len(combined_scenarios)} scenarios ({combined_trials} trials), "
          f"tasks={len(tasks)}, repeats={repeats}, total={total_trials} trials")
    if dry_run:
        _print_dry_run_summary(total_trials)
        return

    trial_state = {"count": 0}
    start = time.time()
    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        completed_count = len(checkpoint.get("completed", {}))
        print(f"เปิด resume mode: พบ completed trials เดิม {completed_count} รายการ")

    progress_bar = _open_progress(total_trials, "experiment")
    try:
        for repeat_index in range(1, repeats + 1):
            print(f"\n######## Repeat {repeat_index}/{repeats} ########")

            for match in matches:
                _run_match(
                    net, match, tasks, repeat_index, log_dir, trial_state, total_trials,
                    progress_bar=progress_bar, checkpoint=checkpoint, resume=resume,
                )

            for scenario in combined_scenarios:
                _run_scenario(
                    net, scenario, tasks, repeat_index, log_dir, trial_state, total_trials,
                    phase="combined_full", progress_bar=progress_bar,
                    checkpoint=checkpoint, resume=resume,
                )
    finally:
        if progress_bar is not None:
            progress_bar.close()

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้นทั้งหมด {trial_state['count']} trials ใช้เวลารวม {elapsed/60:.1f} นาที")
    print(f"log files อยู่ที่: {os.path.abspath(log_dir)}")
    if resume:
        print(f"checkpoint อยู่ที่: {os.path.abspath(_checkpoint_path(log_dir))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="โหมดทดสอบเร็ว: 1 tournament match + 1 combined scenario, 1 task, 1 repeat")
    parser.add_argument("--pilot", action="store_true",
                        help="โหมด pilot: tournament round แรก + combined subset, 2 tasks, 5 repeats")
    parser.add_argument("--three-day", action="store_true",
                        help="รัน bounded design ให้จบประมาณ 3 วัน โดยครอบคลุมผลหลักและ interaction สำคัญ")
    parser.add_argument("--tournament-only", action="store_true", help="รันเฉพาะ factorial tournament")
    parser.add_argument("--combined-only", action="store_true", help="รันเฉพาะ combined scenarios")
    parser.add_argument("--dry-run", action="store_true", help="เช็กแผน จำนวน trial และเวลาประมาณ โดยไม่รันจริง")
    parser.add_argument("--resume", action="store_true",
                        help="รันต่อจาก checkpoint/log เดิม โดยข้าม trial ที่เสร็จแล้ว")
    parser.add_argument("--iface", default="eth0", help="network interface ที่จะ apply tc/netem")
    parser.add_argument("--log-dir", default="logs", help="โฟลเดอร์เก็บไฟล์ log")
    args = parser.parse_args()

    selected_modes = [args.quick, args.pilot, args.three_day]
    if sum(1 for selected in selected_modes if selected) > 1:
        parser.error("ใช้ --quick, --pilot, --three-day พร้อมกันไม่ได้ เลือกอย่างใดอย่างหนึ่ง")
    if args.tournament_only and args.combined_only:
        parser.error("ใช้ --tournament-only กับ --combined-only พร้อมกันไม่ได้")

    main(
        quick=args.quick,
        pilot=args.pilot,
        three_day=args.three_day,
        iface=args.iface,
        log_dir=args.log_dir,
        tournament_only=args.tournament_only,
        combined_only=args.combined_only,
        dry_run=args.dry_run,
        resume=args.resume,
    )
