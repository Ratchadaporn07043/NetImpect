"""
run_dual_judge_sample.py — เปรียบเทียบ LLM-judge 2 โมเดล บน sample เดียวกัน
================================================================================
วัด inter-rater agreement ระหว่าง judge model 2 ตัว (เช่น qwen3:8b vs llama3.1:8b)
เพื่อยืนยันว่า ground-truth score ที่ได้ไม่ได้ขึ้นกับ "โมเดลไหนมาตัดสิน" มากเกินไป
(ถ้า agreement ต่ำ แปลว่า LLM-judge ยังไม่น่าเชื่อถือพอจะใช้เป็น ground truth หลัก)

⚠️ Read-only ต่อไฟล์ log เดิม — สคริปต์นี้ "ไม่เขียนกลับ" เข้าไปใน log JSON เดิม
เลย (ต่างจาก evaluate_logs.py ที่เขียน posthoc_evaluation กลับเข้าไฟล์) ผลลัพธ์
การเปรียบเทียบจะถูกเขียนเป็นไฟล์ CSV/JSON แยกต่างหาก

วิธีใช้:
    python3 "Tier3_โครงสร้างพื้นฐาน/run_dual_judge_sample.py" \\
        --log-dir logs_three_day --sample 200 \\
        --judge-a qwen3:8b --judge-b llama3.1:8b \\
        --out dual_judge_report

ต้องมี Ollama serve ทั้งสองโมเดลพร้อมใช้งาน (ollama pull llama3.1:8b ก่อนถ้ายังไม่มี)
"""
import argparse
import csv
import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.evaluate_logs import _eligible_records, _select_records  # noqa: E402
from experiment.evaluator import _llm_evaluate, _heuristic_evaluate  # noqa: E402


def _cohens_kappa_binary(labels_a, labels_b):
    """Cohen's kappa สำหรับ label 2 ค่า (True/False) — คำนวณเองแบบ pure Python
    ไม่พึ่ง sklearn เพื่อลด dependency"""
    n = len(labels_a)
    if n == 0:
        return None
    agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agree / n

    a_true = sum(1 for a in labels_a if a) / n
    b_true = sum(1 for b in labels_b if b) / n
    pe = (a_true * b_true) + ((1 - a_true) * (1 - b_true))

    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def _quadratic_weighted_kappa(scores_a, scores_b, min_score=1, max_score=5):
    """Quadratic weighted kappa สำหรับ score 1-5 (ordinal) — pure Python"""
    n = len(scores_a)
    if n == 0:
        return None
    levels = list(range(min_score, max_score + 1))
    k = len(levels)

    observed = [[0] * k for _ in range(k)]
    for a, b in zip(scores_a, scores_b):
        if a is None or b is None:
            continue
        observed[a - min_score][b - min_score] += 1

    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    total = sum(hist_a)
    if total == 0:
        return None

    numerator, denominator = 0.0, 0.0
    for i in range(k):
        for j in range(k):
            weight = ((i - j) ** 2) / ((k - 1) ** 2)
            expected = (hist_a[i] * hist_b[j]) / total
            numerator += weight * observed[i][j]
            denominator += weight * expected

    if denominator == 0:
        return 1.0
    return 1 - (numerator / denominator)


def _pearson_r(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None
    xs2 = [p[0] for p in pairs]
    ys2 = [p[1] for p in pairs]
    mean_x = sum(xs2) / n
    mean_y = sum(ys2) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x in xs2)
    var_y = sum((y - mean_y) ** 2 for y in ys2)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x ** 0.5 * var_y ** 0.5)


def main(log_dir, sample, judge_a, judge_b, out_prefix, seed):
    rows, broken = _eligible_records(log_dir, force=True)  # force=True: อ่านทุก record รวมที่มี posthoc แล้ว (read-only ไม่กระทบ)
    selected = _select_records(rows, sample=sample, strategy="stratified", seed=seed)
    print(f"eligible logs: {len(rows)} | selected for dual-judge: {len(selected)} | broken: {len(broken)}")

    results = []
    start = time.time()
    for idx, row in enumerate(selected, start=1):
        record = row["record"]
        task_name = row["task_name"]
        task_prompt = record.get("task_prompt") or f"Benchmark task: {task_name}"
        final_answer = row["final_answer"]

        print(f"[{idx}/{len(selected)}] {task_name} | {row['scenario_name']}")
        eval_a = _llm_evaluate(task_name, task_prompt, final_answer, judge_model_name=judge_a)
        eval_b = _llm_evaluate(task_name, task_prompt, final_answer, judge_model_name=judge_b)
        heuristic = _heuristic_evaluate(task_name, task_prompt, final_answer)

        results.append({
            "log_file": os.path.basename(row["path"]),
            "task_name": task_name,
            "phase": row["phase"],
            "scenario_name": row["scenario_name"],
            "heuristic_score": heuristic.get("score"),
            "heuristic_passed": heuristic.get("passed"),
            "judge_a_model": judge_a,
            "judge_a_score": eval_a.get("score"),
            "judge_a_passed": eval_a.get("passed"),
            "judge_b_model": judge_b,
            "judge_b_score": eval_b.get("score"),
            "judge_b_passed": eval_b.get("passed"),
        })
        print(f"    -> heuristic={heuristic.get('score')} "
              f"{judge_a}={eval_a.get('score')} {judge_b}={eval_b.get('score')}")

    elapsed = time.time() - start

    # --- สรุป agreement metrics ---
    passed_a = [r["judge_a_passed"] for r in results if r["judge_a_passed"] is not None
                and r["judge_b_passed"] is not None]
    passed_b = [r["judge_b_passed"] for r in results if r["judge_a_passed"] is not None
                and r["judge_b_passed"] is not None]
    scores_a = [r["judge_a_score"] for r in results]
    scores_b = [r["judge_b_score"] for r in results]

    kappa_binary = _cohens_kappa_binary(passed_a, passed_b)
    kappa_weighted = _quadratic_weighted_kappa(scores_a, scores_b)
    pearson = _pearson_r(scores_a, scores_b)
    exact_agreement = (
        sum(1 for a, b in zip(scores_a, scores_b) if a == b and a is not None) / len(scores_a)
        if scores_a else None
    )

    summary = {
        "n_samples": len(results),
        "judge_a_model": judge_a,
        "judge_b_model": judge_b,
        "cohens_kappa_pass_fail": round(kappa_binary, 4) if kappa_binary is not None else None,
        "quadratic_weighted_kappa_score": round(kappa_weighted, 4) if kappa_weighted is not None else None,
        "pearson_r_score": round(pearson, 4) if pearson is not None else None,
        "exact_score_agreement_rate": round(exact_agreement, 4) if exact_agreement is not None else None,
        "elapsed_seconds": round(elapsed, 1),
        "interpretation": (
            "kappa < 0.20 = slight, 0.21-0.40 = fair, 0.41-0.60 = moderate, "
            "0.61-0.80 = substantial, 0.81-1.00 = almost perfect (Landis & Koch 1977)"
        ),
    }

    csv_path = f"{out_prefix}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else [])
        writer.writeheader()
        writer.writerows(results)

    json_path = f"{out_prefix}_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== Dual-Judge Agreement Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nรายละเอียดต่อ trial: {csv_path}")
    print(f"สรุป: {json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier3: compare two LLM judge models on a sample of existing logs")
    parser.add_argument("--log-dir", default="logs_three_day")
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--judge-a", default="qwen3:8b", help="โมเดลตัวแรก (แนะนำเป็นตัวเดียวกับ agent เพื่อวัด self-eval bias)")
    parser.add_argument("--judge-b", default="llama3.1:8b", help="โมเดลตัวที่สอง (ต้องต่างจาก agent model)")
    parser.add_argument("--out", default="dual_judge_report", help="prefix ของไฟล์ output (.csv และ _summary.json)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    main(log_dir=args.log_dir, sample=args.sample, judge_a=args.judge_a, judge_b=args.judge_b,
         out_prefix=args.out, seed=args.seed)
