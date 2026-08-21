#!/usr/bin/env bash
# run_tier4_temporal_replicate.sh — รัน three-day plan เดิมซ้ำทั้งชุด (temporal replication)
#
# เป้าหมาย: ผลเดิมทั้งหมดรันครั้งเดียว (1 repeat ต่อ tournament match/combined
# scenario) — ไม่มีทางแยกได้ว่าความแปรปรวนที่เห็นมาจาก "network condition"
# จริงๆ หรือมาจาก "ความไม่นิ่งของ LLM/เครื่อง/เวลาที่รัน" (เช่น โหลดเครื่องต่างกัน
# ระหว่างวัน, Ollama warm-up, ความแปรปรวนตามธรรมชาติของ sampling ที่ temperature>0)
# การรันซ้ำทั้งชุดในช่วงเวลาอื่น (temporal replicate) คือวิธีตรวจสอบที่ตรงจุดที่สุด
#
# ไม่แก้ run_experiment.py เลย — แค่เรียกด้วย --log-dir อื่น เพื่อไม่ให้ไปทับ
# logs_three_day/ เดิม
#
# วิธีใช้:
#   bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --dry-run
#   bash "Tier4_Replication/run_tier4_temporal_replicate.sh"
#   bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --resume   # รันต่อถ้าค้างกลางคัน
#
# แนะนำ: รันห่างจากรอบแรก (logs_three_day/) อย่างน้อยหลายวัน หรือคนละช่วงเวลา
# ของวัน เพื่อให้เป็น "temporal" replication จริงๆ ไม่ใช่รันติดกันทันที

set -euo pipefail

EXTRA_ARGS="$@"
LOG_DIR="logs_three_day_replicate2"

echo "=== Tier 4: Temporal Full Replication -> $LOG_DIR ==="
echo "(ใช้ scenario/repeats ชุดเดียวกับ three-day plan เดิมทุกประการ ผ่าน --three-day เดิม)"
echo ""

python3 experiment/run_experiment.py --three-day --log-dir "$LOG_DIR" $EXTRA_ARGS
