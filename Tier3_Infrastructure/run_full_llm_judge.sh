#!/usr/bin/env bash
# run_full_llm_judge.sh — รัน LLM-judge บน log ทั้งหมดที่มีอยู่แล้ว (ไม่ apply network,
# ไม่รัน agent ใหม่ — ประเมินซ้ำจาก final answer ที่บันทึกไว้แล้วเท่านั้น)
#
# แก้ปัญหาที่พบ: ทุก 1,544 trials เดิมถูกประเมินด้วย mode="heuristic" (keyword
# matching) เท่านั้น ไม่เคยรัน mode="llm"/"both" เลยแม้โค้ดจะรองรับ (ยืนยันจาก
# grep "posthoc_evaluation" ใน logs_three_day/ ได้ 0 ไฟล์) — นี่คือหนึ่งใน
# blocking gap สำหรับ AINTEC2026 ตาม
# Paper/NetImpact.md/Archive_Legacy/NetImpact_10_AINTEC2026_Readiness_Assessment.md
# (ไฟล์ย้ายมาจาก Docs/ แล้ว)
#
# วิธีใช้:
#   ต้องแทนที่ experiment/evaluator.py (ไม่ใช่ root evaluator.py!) ด้วยเวอร์ชัน
#   Tier3 ก่อน (ไม่บังคับสำหรับสคริปต์นี้จริงๆ เพราะ evaluate_logs.py เรียก
#   _llm_evaluate ตรงๆ ซึ่งจะใช้ AGENT_MODEL_NAME เป็น judge เหมือนเดิมถ้าไม่ตั้ง
#   JUDGE_MODEL_NAME — แต่แนะนำให้แทนที่เพื่อให้ตั้ง JUDGE_MODEL_NAME แยกจาก agent
#   ได้ และจำเป็นสำหรับ run_dual_judge_sample.py ในขั้นถัดไป)
#
#   cd NetImpact
#   cp experiment/evaluator.py experiment/evaluator.py.backup_original
#   cp "Tier3_โครงสร้างพื้นฐาน/evaluator.py" experiment/evaluator.py
#
#   # รันจริงกับทุก log (1,544 ไฟล์ ใช้เวลานานมาก ประมาณหลายชั่วโมง เพราะเรียก
#   # LLM ต่อไฟล์ 1 ครั้ง):
#   bash "Tier3_โครงสร้างพื้นฐาน/run_full_llm_judge.sh" logs_three_day
#
#   # ทดสอบก่อนด้วย dry-run:
#   bash "Tier3_โครงสร้างพื้นฐาน/run_full_llm_judge.sh" logs_three_day --dry-run
#
# ผลลัพธ์: เขียนกลับเข้าไปใน field "posthoc_evaluation" ของทุกไฟล์ log เดิมโดยตรง
# (in-place, atomic write ผ่าน .tmp + os.replace อยู่แล้วใน evaluate_logs.py เดิม)
# แนะนำ backup โฟลเดอร์ log ก่อนรันจริงเสมอ: cp -r logs_three_day logs_three_day.backup

set -euo pipefail

LOG_DIR="${1:-logs_three_day}"
shift || true
EXTRA_ARGS="$@"

echo "=== Tier3: Full LLM-Judge Re-evaluation ==="
echo "log dir: $LOG_DIR"
echo "JUDGE_MODEL_NAME=${JUDGE_MODEL_NAME:-<ไม่ตั้ง, จะ fallback ไปใช้ MODEL_NAME เดียวกับ agent>}"
echo ""
echo "แนะนำ backup ก่อนรันจริง: cp -r \"$LOG_DIR\" \"${LOG_DIR}.backup\""
echo ""

python3 experiment/evaluate_logs.py --log-dir "$LOG_DIR" --mode both --all --strategy stratified $EXTRA_ARGS
