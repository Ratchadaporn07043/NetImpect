"""
parse_logs.py — แปลง log JSON ทั้งหมดใน logs_three_day/ ให้เป็นตาราง CSV เดียว
================================================================================
อ่านทุกไฟล์ .json ใน log dir (ยกเว้น _checkpoint/) ดึงเฉพาะฟิลด์ที่ใช้วิเคราะห์
บ่อยที่สุด (network condition, outcome, task, phase) ออกมาเป็นแถวเดียวต่อ 1 trial
แล้วบันทึกเป็น netimpact_master.csv

วิธีรัน (จากภายใน Analysis_เบื้องต้น/scripts/):
    python3 parse_logs.py --log-dir "../../logs_three_day" --out ../data/netimpact_master.csv
    python3 parse_logs.py --log-dir "../../Tier1_เจาะจุดในแกนที่มีอยู่/logs_tier1" --out ../data/tier1_master.csv

ไม่ต้องมี pandas/numpy ระหว่าง parse (ใช้แค่ json/csv มาตรฐาน) แต่
generate_charts.py ที่อ่านไฟล์ผลลัพธ์นี้ต่อ ต้องใช้ pandas/matplotlib
"""
import argparse
import csv
import json
import os


def _final_worker_answer_length(record):
    length = 0
    for msg in record.get("messages", []):
        if msg.get("from") == "Worker":
            length = len(msg.get("content") or "")
    return length


def _iter_log_files(log_dir):
    for name in sorted(os.listdir(log_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(log_dir, name)
        if os.path.isfile(path):
            yield path


def parse_logs(log_dir: str):
    rows = []
    broken = []
    for path in _iter_log_files(log_dir):
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            broken.append((path, str(exc)))
            continue

        nc = record.get("network_condition") or {}
        outcome = record.get("outcome") or {}
        evaluation = record.get("evaluation") or {}
        tournament = nc.get("tournament") or {}

        rows.append({
            "log_file": os.path.basename(path),
            "run_id": record.get("run_id"),
            "task_name": record.get("task_name"),
            "run_index": record.get("run_index"),
            "phase": nc.get("experiment_phase", "unknown"),
            "scenario_name": nc.get("name", "unknown"),
            "scenario_type": nc.get("scenario_type"),
            "delay_ms": nc.get("delay_ms"),
            "requested_delay_ms": nc.get("requested_delay_ms"),
            "jitter_ms": nc.get("jitter_ms"),
            "loss_pct": nc.get("loss_pct"),
            "bandwidth_kbit": nc.get("bandwidth_kbit"),
            "main_effect_axis": nc.get("main_effect_axis", ""),
            "match_id": tournament.get("match_id", ""),
            "side": tournament.get("side", ""),
            "success": outcome.get("success"),
            "rounds": outcome.get("rounds"),
            "reviewer_rejections": outcome.get("reviewer_rejections"),
            "elapsed_seconds": outcome.get("elapsed_seconds"),
            "total_tokens": outcome.get("total_tokens"),
            "quality_score": outcome.get("quality_score"),
            "ground_truth_score": outcome.get("ground_truth_score"),
            "ground_truth_passed": outcome.get("ground_truth_passed"),
            "retry_count": outcome.get("retry_count"),
            "timeout_count": outcome.get("timeout_count"),
            "total_error_count": outcome.get("total_error_count"),
            "eval_mode": evaluation.get("mode") if evaluation else "",
            "final_answer_length": _final_worker_answer_length(record),
            "n_messages": len(record.get("messages", [])),
        })

    return rows, broken


def main(log_dir, out_path):
    rows, broken = parse_logs(log_dir)
    print(f"อ่าน log จาก: {os.path.abspath(log_dir)}")
    print(f"parse สำเร็จ: {len(rows)} trials | parse ไม่ได้/broken: {len(broken)}")
    if broken:
        for path, reason in broken[:5]:
            print(f"  - {os.path.basename(path)}: {reason}")

    if not rows:
        print("ไม่มีข้อมูลให้เขียน หยุดทำงาน")
        return

    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"บันทึกแล้ว: {os.path.abspath(out_path)} ({len(rows)} แถว)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="../../logs_three_day", help="โฟลเดอร์ log JSON")
    parser.add_argument("--out", default="../data/netimpact_master.csv", help="ไฟล์ CSV ผลลัพธ์")
    args = parser.parse_args()
    main(args.log_dir, args.out)
