#!/usr/bin/env python3
"""
Tier 8, Item 5 - Jitter-Floor Matched Control (fixed delay=50ms, jitter=0)
================================================================================
Question addressed by this experiment
----------------------
sigconf.tex (`sec:modelservingpath`) notes that netem requires delay > 0 before
jitter can be applied. Every nonzero jitter level in the original dataset therefore
received a 50ms base delay through `_netem_delay_for()` in `experiment/scenarios.py`.
The jitter=0 level used delay=0, so the original axis compared no impairment with
delay 50ms plus jitter rather than comparing matched 50ms delay conditions. The
floor effect and jitter effect could therefore not be separated.

Before writing this script, we verified that no scenario in the project had tested
fixed delay=50ms with jitter=0 as its own point. Every prior main-effect jitter
scenario called `_netem_delay_for(0, jitter_ms)`, so this is a genuinely new control.

Design
----------
One scenario uses delay_ms=50 (matching MIN_DELAY_FOR_JITTER_MS), jitter_ms=0,
loss_pct=0, and bandwidth=None. It uses the default direction="egress" so it can
be compared directly with Table 2 (`tab:nondetection`) without another variable changing.

4 tasks x 5 repeats = 20 trials (n=20, matching the other single-point experiments)

How to interpret the result
-----------
Compare completion at delay=50, jitter=0 with two existing points: the original
jitter=0 configuration (delay=0, 20/20) and the original jitter=100ms configuration
(50ms floor plus jitter, 19/20). If the new control remains approximately 20/20,
the floor itself is not driving completion at jitter=100ms. This supports the original
interpretation, although elapsed time and other measures are not perfectly matched.

Usage
---------
    python3 Tier8_EnsureScopeClosure/run_tier8_jitter_floor.py --dry-run
    python3 Tier8_EnsureScopeClosure/run_tier8_jitter_floor.py --resume
"""
import argparse
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)  # Insert after _PROJECT_ROOT so this directory has priority.

from controller import NetworkController  # noqa: E402
from logger import ExperimentLogger  # noqa: E402
from checkpoint_utils import load_checkpoint, mark_completed, should_skip  # noqa: E402
from experiment.scenarios import MIN_DELAY_FOR_JITTER_MS  # noqa: E402  (the project's actual 50ms floor)
from experiment.tasks import TASKS  # noqa: E402

REPEATS = 5

JITTER_FLOOR_SCENARIO = {
    "name": "t8_jitter_floor_control",
    "scenario_type": "matched_control",
    "main_effect_axis": "jitter_floor_control",
    "delay_ms": MIN_DELAY_FOR_JITTER_MS,
    "requested_delay_ms": 0,  # All jitter points request delay=0, then apply the floor.
    "jitter_ms": 0,
    "loss_pct": 0,
    "bandwidth_kbit": None,
    "note": (
        f"matched control: fixed delay={MIN_DELAY_FOR_JITTER_MS}ms (the floor applied to all "
        "jitter>0 levels), with jitter=0 to isolate the floor from jitter itself"
    ),
}


def _trial_key(task_name, repeat_index):
    return f"{JITTER_FLOOR_SCENARIO['name']}__{task_name}__run{repeat_index}"


def run_single_trial(net, task_name, task_prompt, run_index, log_dir, multi_agent_module):
    print(f"  [{JITTER_FLOOR_SCENARIO['name']}] task={task_name} run={run_index} "
          f"-> delay={JITTER_FLOOR_SCENARIO['delay_ms']}ms jitter=0")

    logger = ExperimentLogger(scenario=JITTER_FLOOR_SCENARIO, task_name=task_name,
                              run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=JITTER_FLOOR_SCENARIO["delay_ms"],
        jitter_ms=JITTER_FLOOR_SCENARIO["jitter_ms"],
        loss_pct=JITTER_FLOOR_SCENARIO["loss_pct"],
        bandwidth_kbit=JITTER_FLOOR_SCENARIO.get("bandwidth_kbit"),
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
                strict_reviewer=False, mitigation="none", network_condition=JITTER_FLOOR_SCENARIO,
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
    ap.add_argument("--log-dir", default=os.path.join(_THIS_DIR, "logs_tier8_jitter_floor"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    tasks = TASKS
    total = len(tasks) * REPEATS
    print("Tier 8, Item 5 - jitter-floor matched control")
    print(f"  1 scenario (delay={JITTER_FLOOR_SCENARIO['delay_ms']}ms, jitter=0) "
          f"x {len(tasks)} tasks x {REPEATS} repeats = {total} trials")
    print(f"  Estimated time: ~{total * 60 / 3600:.2f} hours")

    if args.dry_run:
        print("\nDRY RUN: no network impairment, LLM call, or log write will occur")
        return

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
                                        args.log_dir, multi_agent_module)
            if checkpoint is not None:
                mark_completed(args.log_dir, checkpoint, key, log_file)

    print(f"\nCompleted in {(time.time() - start) / 60:.1f} minutes")
    print("Next step: compare completion with the original jitter=0 (delay=0) and "
          "jitter=100ms points in Table 2")


if __name__ == "__main__":
    main()
