#!/usr/bin/env bash
# ============================================================================
# confirm_thinking_mode.sh — ยืนยันสมมติฐาน "thinking mode" ว่าเป็นสาเหตุจริง
# ของ elapsed_seconds ที่พุ่งขึ้นใน Tier 8 หรือไม่ ก่อนแก้อะไรใน multi_agent.py
# ============================================================================
# รันบน HOST เดียวกับที่รัน diagnose_environment_drift.sh (ที่ Ollama อยู่)
# ทดสอบ 3 แบบเทียบกัน ไม่แตะ multi_agent.py/experiment code เลย:
#   A) prompt เปล่า (ให้ Ollama ตัดสินใจเองว่าจะ think หรือไม่ — คือสภาพที่
#      multi_agent.py ใช้อยู่ตอนนี้ทุกประการ)
#   B) prompt + "/no_think" ต่อท้าย (ปิด reasoning mode ตามคอนเวนชันของ Qwen3)
#   C) ลองส่ง "think": false ผ่าน API โดยตรง (เผื่อ Ollama เวอร์ชันนี้รองรับ
#      parameter นี้ที่ระดับ request แทนที่จะต้องพึ่ง prompt suffix)
#
# ใช้เวลารวมไม่เกิน 2-3 นาที (6 request สั้นๆ) เทียบง่ายๆ ว่าปิด thinking ได้
# จริงไหม และช่วยเวลาลงเท่าไหร่ ก่อนตัดสินใจว่าจะแก้โค้ด experiment จริงหรือไม่
# ============================================================================
set -uo pipefail

PROMPT_BASE="Reply with exactly one word: OK"
N=3

_run_case() {
    local label="$1"
    local body="$2"
    echo "--- $label ---"
    for i in $(seq 1 "$N"); do
        START=$(date +%s.%N)
        RESP=$(curl -s http://localhost:11434/api/generate -d "$body")
        END=$(date +%s.%N)
        ELAPSED=$(python3 -c "print(f'{$END - $START:.2f}')")
        HAS_THINKING=$(echo "$RESP" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    t = d.get('thinking')
    print('มี thinking field (' + str(len(t)) + ' ตัวอักษร)' if t else 'ไม่มี thinking field')
except Exception as e:
    print('parse ไม่ได้:', e)
")
        echo "  รอบที่ $i: ${ELAPSED}s  -  $HAS_THINKING"
    done
    echo ""
}

echo "======================================================================"
echo "A) prompt ปกติ (เหมือนที่ multi_agent.py ใช้อยู่ตอนนี้ ไม่ได้สั่งอะไรเพิ่ม)"
echo "======================================================================"
_run_case "A: prompt เปล่า" "{\"model\": \"qwen3:8b\", \"prompt\": \"$PROMPT_BASE\", \"stream\": false}"

echo "======================================================================"
echo "B) prompt + /no_think ต่อท้าย (ปิด reasoning ตามคอนเวนชันของ Qwen3)"
echo "======================================================================"
_run_case "B: /no_think suffix" "{\"model\": \"qwen3:8b\", \"prompt\": \"$PROMPT_BASE /no_think\", \"stream\": false}"

echo "======================================================================"
echo "C) ลองส่ง think:false ตรงๆ ผ่าน API (เผื่อเวอร์ชันนี้รองรับ)"
echo "======================================================================"
_run_case "C: think:false param" "{\"model\": \"qwen3:8b\", \"prompt\": \"$PROMPT_BASE\", \"think\": false, \"stream\": false}"

echo "======================================================================"
echo "สรุปวิธีอ่านผล"
echo "======================================================================"
cat << 'EOF'
- ถ้า A ช้า (~8-23s เหมือนที่เจอใน diagnose_environment_drift.sh) แต่ B หรือ C
  เร็วขึ้นชัดเจน (เหลือ 1-3s) และไม่มี thinking field แล้ว -> ยืนยันสมมติฐาน
  ชัดเจนว่า thinking mode คือสาเหตุหลักของ elapsed_seconds ที่พุ่งขึ้นใน Tier 8
- ถ้าได้ผลนี้ ขั้นต่อไปคือแก้ multi_agent.py ให้ต่อ "/no_think" ท้าย
  system_message ของทุก agent (Planner/Worker/Reviewer) แล้วรันทดสอบเทียบ
  เล็กๆ (เช่น 20 trial ที่ 75% loss, arm "none") ดูว่า completion กลับไปใกล้
  เคียงผลเดิมของ Tier 5 (14/20) หรือไม่ — ถ้าใช่ แปลว่าปิด thinking mode ทำให้
  ระบบกลับไปมีพฤติกรรมใกล้เคียงชุดข้อมูลเดิม ควรพิจารณาว่าจะรัน Tier 8 ทั้งชุด
  ซ้ำแบบปิด thinking หรือรายงานทั้งสองสภาพ (thinking-on / thinking-off) แยกกัน
- ถ้า B/C ไม่ต่างจาก A เลย -> สมมติฐาน thinking mode ตกไป ต้องหาสาเหตุอื่นต่อ
  (เช่น กลับไปดู GPU/Vulkan fallback จากข้อ 8 ของการวินิจฉัยรอบก่อน)
EOF
