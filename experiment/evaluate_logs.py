"""
Post-hoc Ground Truth Evaluator
===============================
อ่าน log JSON ที่รันเสร็จแล้ว แล้วประเมิน final answer ซ้ำด้วย ground-truth evaluator
โดยไม่ apply network, ไม่รัน Planner/Worker/Reviewer ใหม่

ตัวอย่าง:
    python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode llm --sample 200
    python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode both --sample 200 --strategy stratified
    python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode llm --all
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiment.evaluator import _heuristic_evaluate, _llm_evaluate


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path, data):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _iter_log_files(log_dir):
    for name in sorted(os.listdir(log_dir)):
        if name.endswith(".json"):
            path = os.path.join(log_dir, name)
            if os.path.isfile(path):
                yield path


def _final_worker_answer(record):
    final_answer = ""
    for msg in record.get("messages", []):
        if msg.get("from") == "Worker":
            final_answer = msg.get("content") or ""
    return final_answer


def _eligible_records(log_dir, force=False):
    rows = []
    broken = []
    for path in _iter_log_files(log_dir):
        try:
            record = _load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            broken.append((path, str(exc)))
            continue

        if not record.get("outcome"):
            broken.append((path, "missing outcome"))
            continue
        if record.get("posthoc_evaluation") and not force:
            continue

        final_answer = _final_worker_answer(record)
        if not final_answer:
            broken.append((path, "missing final Worker answer"))
            continue

        scenario = record.get("network_condition", {}) or {}
        rows.append({
            "path": path,
            "record": record,
            "task_name": record.get("task_name"),
            "phase": scenario.get("experiment_phase", "unknown"),
            "scenario_name": scenario.get("name", "unknown"),
            "final_answer": final_answer,
        })
    return rows, broken


def _select_records(rows, sample=None, strategy="stratified", seed=42):
    if sample is None or sample >= len(rows):
        return rows

    rng = random.Random(seed)
    if strategy == "random":
        selected = list(rows)
        rng.shuffle(selected)
        return selected[:sample]

    if strategy == "first":
        return rows[:sample]

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["phase"], row["task_name"])].append(row)

    groups = list(grouped.values())
    for group in groups:
        rng.shuffle(group)

    selected = []
    cursor = 0
    while len(selected) < sample and groups:
        group = groups[cursor % len(groups)]
        if group:
            selected.append(group.pop())
        groups = [g for g in groups if g]
        cursor += 1
    return selected


def _evaluate(mode, task_name, task_prompt, final_answer):
    heuristic = _heuristic_evaluate(task_name, task_prompt, final_answer)
    if mode == "heuristic":
        return heuristic
    if mode == "llm":
        result = _llm_evaluate(task_name, task_prompt, final_answer)
        result["heuristic_reference"] = heuristic
        return result

    result = _llm_evaluate(task_name, task_prompt, final_answer)
    result["mode"] = "both"
    result["heuristic_reference"] = heuristic
    return result


def main(log_dir, mode="llm", sample=None, all_records=False, strategy="stratified", seed=42,
         force=False, dry_run=False):
    rows, broken = _eligible_records(log_dir, force=force)
    if all_records:
        sample = None
    selected = _select_records(rows, sample=sample, strategy=strategy, seed=seed)

    print(f"อ่าน log จาก: {os.path.abspath(log_dir)}")
    print(f"eligible logs: {len(rows)} | selected: {len(selected)} | skipped/broken: {len(broken)}")
    if broken:
        print("ตัวอย่าง skipped/broken:")
        for path, reason in broken[:5]:
            print(f"  - {os.path.basename(path)}: {reason}")

    if dry_run:
        print("DRY RUN เท่านั้น: ยังไม่เรียก LLM และยังไม่เขียนไฟล์")
        return

    start = time.time()
    for idx, row in enumerate(selected, start=1):
        record = row["record"]
        task_name = row["task_name"]
        task_prompt = record.get("task_prompt") or ""
        if not task_prompt:
            # task prompt เดิมไม่ได้ถูกเก็บใน log รุ่นแรก จึงใช้ task_name + final answer เป็นบริบทขั้นต่ำ
            task_prompt = f"Benchmark task: {task_name}"

        print(f"[{idx}/{len(selected)}] {task_name} | {row['phase']} | {row['scenario_name']}")
        evaluation = _evaluate(mode, task_name, task_prompt, row["final_answer"])
        evaluation["posthoc"] = True
        evaluation["evaluated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        record["posthoc_evaluation"] = evaluation
        record.setdefault("outcome", {})["posthoc_ground_truth_score"] = evaluation.get("score")
        record.setdefault("outcome", {})["posthoc_ground_truth_passed"] = evaluation.get("passed")
        record.setdefault("outcome", {})["posthoc_ground_truth_mode"] = evaluation.get("mode")
        _atomic_write_json(row["path"], record)

        print(
            f"    -> score={evaluation.get('score')} passed={evaluation.get('passed')} "
            f"mode={evaluation.get('mode')} elapsed={evaluation.get('elapsed_seconds')}s"
        )

    elapsed = time.time() - start
    print(f"เสร็จแล้ว: evaluated {len(selected)} logs ใช้เวลา {elapsed/60:.1f} นาที")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs_three_day", help="โฟลเดอร์ log JSON จาก experiment")
    parser.add_argument("--mode", choices=["heuristic", "llm", "both"], default="llm",
                        help="โหมดประเมินย้อนหลัง")
    parser.add_argument("--sample", type=int, default=200,
                        help="จำนวน log ที่สุ่มมาตรวจ; ใช้ --all ถ้าจะตรวจทั้งหมด")
    parser.add_argument("--all", action="store_true", help="ตรวจทุก log ที่ยังไม่มี posthoc_evaluation")
    parser.add_argument("--strategy", choices=["stratified", "random", "first"], default="stratified",
                        help="วิธีเลือก sample")
    parser.add_argument("--seed", type=int, default=42, help="random seed สำหรับเลือก sample")
    parser.add_argument("--force", action="store_true", help="ตรวจซ้ำแม้ log นั้นมี posthoc_evaluation แล้ว")
    parser.add_argument("--dry-run", action="store_true", help="ดูจำนวน log ที่จะตรวจ โดยไม่เรียก LLM/ไม่เขียนไฟล์")
    args = parser.parse_args()

    main(
        log_dir=args.log_dir,
        mode=args.mode,
        sample=args.sample,
        all_records=args.all,
        strategy=args.strategy,
        seed=args.seed,
        force=args.force,
        dry_run=args.dry_run,
    )
