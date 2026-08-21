#!/usr/bin/env python3
"""
Recover timeout agent attribution from existing logs (retroactive)
==================================================================

WHY THIS EXISTS
---------------
`logger.log_error()` originally recorded only {timestamp, error_type, detail},
and the detail string for a timeout is the framework's generic message, which
does not say which agent's LLM call timed out. That gap is what made the
documented explanation for the context-caching negative result — "most timeouts
occur during Worker or Reviewer calls rather than Planner calls" — an
unverifiable hypothesis rather than a measurement.

It turns out the attribution IS recoverable from the logs that already exist,
because the message log records the real send timestamp and the sender name for
every message that was produced.

THE RECONSTRUCTION
------------------
The group chat uses round-robin speaker selection over [Planner, Worker,
Reviewer]. A message is logged only when an agent's turn produced output. A
timeout therefore leaves a *gap*: the agent whose turn it was produced nothing.

So the agent that timed out is the one whose turn follows the last message
logged before the error timestamp:

    last logged message from Planner   -> Worker timed out
    last logged message from Worker    -> Reviewer timed out
    last logged message from Reviewer  -> Planner timed out   (round 4+ only)

CAVEATS, STATED PLAINLY
-----------------------
1. This is an inference from ordering, not a recorded fact. It assumes
   round-robin held and that no message was dropped from the log.
2. Errors that precede any logged message cannot be attributed and are counted
   separately rather than silently assigned.
3. Retries restart the conversation; because the reconstruction only ever looks
   at the most recent message before the error, the attempt boundary does not
   need to be modelled explicitly.
4. Going forward, `logger.log_error(..., agent=...)` records this directly and
   this script becomes unnecessary for new runs.

USAGE
-----
    python3 recover_timeout_attribution.py --log-dir ../../Tier5_Mitigation/logs_tier5_none
    python3 recover_timeout_attribution.py --log-dir DIR1 --log-dir DIR2 --csv out.csv
"""
import argparse
import collections
import csv
import glob
import json
import os

ROUND_ROBIN_ORDER = ["Planner", "Worker", "Reviewer"]
UNATTRIBUTABLE = "(no preceding message)"


def next_speaker(last_speaker: str):
    """คืนชื่อ agent ที่ถึงคิวถัดจาก last_speaker ตามลำดับ round-robin"""
    if last_speaker not in ROUND_ROBIN_ORDER:
        return None
    idx = ROUND_ROBIN_ORDER.index(last_speaker)
    return ROUND_ROBIN_ORDER[(idx + 1) % len(ROUND_ROBIN_ORDER)]


def attribute_errors_in_trial(trial: dict, error_types=("timeout",)):
    """คืน list ของ (error_type, attributed_agent, was_recorded)

    was_recorded = True ถ้า log มี field `agent` อยู่แล้ว (run ใหม่)
    ในกรณีนั้นจะใช้ค่าที่บันทึกไว้จริง ไม่ใช้การอนุมาน
    """
    messages = sorted(trial.get("messages", []), key=lambda m: m.get("timestamp", 0))
    results = []

    for err in trial.get("errors", []):
        if err.get("error_type") not in error_types:
            continue

        recorded = err.get("agent")
        if recorded:
            results.append((err["error_type"], recorded, True))
            continue

        err_ts = err.get("timestamp", 0)
        prior = [m for m in messages if m.get("timestamp", 0) <= err_ts]
        if not prior:
            results.append((err["error_type"], UNATTRIBUTABLE, False))
            continue

        inferred = next_speaker(prior[-1].get("from"))
        results.append((err["error_type"], inferred or UNATTRIBUTABLE, False))

    return results


def scan(log_dirs, error_types=("timeout",)):
    counts = collections.Counter()
    rows = []
    n_files = 0
    n_recorded = 0
    n_inferred = 0

    for log_dir in log_dirs:
        for path in sorted(glob.glob(os.path.join(log_dir, "*.json"))):
            try:
                with open(path, encoding="utf-8") as fh:
                    trial = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            n_files += 1
            for etype, agent, was_recorded in attribute_errors_in_trial(trial, error_types):
                counts[agent] += 1
                n_recorded += int(was_recorded)
                n_inferred += int(not was_recorded)
                rows.append({
                    "log_file": os.path.basename(path),
                    "log_dir": log_dir,
                    "task_name": trial.get("task_name"),
                    "scenario": (trial.get("network_condition") or {}).get("name"),
                    "loss_pct": (trial.get("network_condition") or {}).get("loss_pct"),
                    "error_type": etype,
                    "attributed_agent": agent,
                    "source": "recorded" if was_recorded else "inferred",
                })

    return counts, rows, n_files, n_recorded, n_inferred


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log-dir", action="append", required=True,
                    help="โฟลเดอร์ log (ระบุซ้ำได้หลายครั้ง)")
    ap.add_argument("--error-type", action="append", default=None,
                    help="ชนิด error ที่จะนับ (ค่าเริ่มต้น: timeout)")
    ap.add_argument("--csv", default=None, help="เขียนผลรายเหตุการณ์ลง CSV")
    args = ap.parse_args()

    error_types = tuple(args.error_type) if args.error_type else ("timeout",)
    counts, rows, n_files, n_recorded, n_inferred = scan(args.log_dir, error_types)
    total = sum(counts.values())

    print(f"scanned {n_files} trial logs across {len(args.log_dir)} directory(ies)")
    print(f"error types counted: {', '.join(error_types)}")
    print(f"events found: {total}  (recorded directly: {n_recorded}, inferred: {n_inferred})")
    if total == 0:
        print("no matching events")
        return

    print("\nattributed agent:")
    for agent in ROUND_ROBIN_ORDER + [UNATTRIBUTABLE]:
        if counts.get(agent):
            print(f"  {agent:24s} {counts[agent]:5d}   ({counts[agent] / total * 100:.1f}%)")

    worker_reviewer = counts.get("Worker", 0) + counts.get("Reviewer", 0)
    print(f"\nWorker+Reviewer combined: {worker_reviewer}/{total} "
          f"({worker_reviewer / total * 100:.1f}%)")
    print("Interpretation note: the Planner issues no LLM call on the dominant "
          "single-pass path (its logged message is the verbatim seed prompt), so a "
          "low Planner count reflects that structural fact and is not evidence about "
          "where inference cost concentrates among agents that do call the model.")

    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)) or ".", exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nper-event rows written to {args.csv}")


if __name__ == "__main__":
    main()
