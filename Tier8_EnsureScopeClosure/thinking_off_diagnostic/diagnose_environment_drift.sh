#!/usr/bin/env bash
# ============================================================================
# diagnose_environment_drift.sh — วินิจฉัยว่าอะไรเปลี่ยนไประหว่าง Tier 5/7 เดิม
# กับ Tier 8 ที่เพิ่งรัน (บนเครื่องเดียวกัน) เพื่อหาสาเหตุของ ceiling effect
# ============================================================================
# รันบน HOST (นอก container agent-lab) เพราะ Ollama ทำงานอยู่บน host ตาม
# docker-compose.yml เดิมของโปรเจกต์ (OLLAMA_BASE_URL ชี้ไปที่
# host.docker.internal) — ถ้ารันใน container จะไม่เจอ ollama binary/โมเดลจริง
#
# ใช้งาน:
#   chmod +x diagnose_environment_drift.sh
#   ./diagnose_environment_drift.sh | tee diagnosis_output.txt
# ============================================================================
set -uo pipefail  # ไม่ใส่ -e เพราะบางคำสั่งไม่มีในระบบนี้แล้วอยากให้รันต่อ ไม่หยุด

_section() { echo ""; echo "================================================================"; echo "  $1"; echo "================================================================"; }

_section "1. Ollama version ปัจจุบัน"
ollama --version 2>&1 || echo "ollama command ไม่พบ — ตรวจว่ารันบน host จริงหรือยัง"

_section "2. รายละเอียดโมเดล qwen3:8b ปัจจุบัน (quantization, parameter, template)"
ollama show qwen3:8b 2>&1

_section "3. รายการโมเดลทั้งหมด + ขนาด/วันที่"
ollama list 2>&1

_section "4. mtime ของ ollama binary (วันที่ติดตั้ง/อัปเดตล่าสุด)"
OLLAMA_BIN=$(command -v ollama 2>/dev/null)
echo "binary path: ${OLLAMA_BIN:-ไม่พบ}"
[ -n "$OLLAMA_BIN" ] && stat "$OLLAMA_BIN" 2>&1

_section "5. mtime ของไฟล์โมเดล qwen3:8b จริง (blob files ใต้ ~/.ollama/models)"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS:-$HOME/.ollama/models}"
echo "ใช้ path: $OLLAMA_MODELS_DIR (เปลี่ยนได้ผ่าน env var OLLAMA_MODELS ถ้าตั้งไว้ต่างจากปกติ)"
MANIFEST=$(find "$OLLAMA_MODELS_DIR/manifests" -ipath "*qwen3*" 2>/dev/null | grep -i "8b" | head -1)
if [ -n "$MANIFEST" ]; then
    echo "manifest: $MANIFEST"
    stat "$MANIFEST" 2>&1
    echo "--- blob files ที่ manifest นี้อ้างถึง (ตัวโมเดลจริง) ---"
    grep -o '"digest"[[:space:]]*:[[:space:]]*"[^"]*"' "$MANIFEST" 2>/dev/null | sed -E 's/.*"(sha256:[^"]*)".*/\1/;s/sha256://' | while read -r digest; do
        blob="$OLLAMA_MODELS_DIR/blobs/sha256-$digest"
        [ -f "$blob" ] && stat "$blob" 2>&1
    done
else
    echo "ไม่พบ manifest ของ qwen3:8b ที่ path มาตรฐาน — ตรวจ OLLAMA_MODELS env var เอง"
fi

_section "6. ประวัติ start/restart/update ของ Ollama service (systemd, ถ้าใช้)"
journalctl -u ollama --since "2026-07-15" --until "now" 2>/dev/null | grep -iE "start|restart|version|updat|listen" | tail -40 \
    || echo "journalctl ไม่มี หรือไม่ได้รันเป็น systemd service"

_section "7. ประวัติ apt/dpkg ที่เกี่ยวกับ ollama/nvidia/cuda (เผื่อมีการอัปเดตระบบ)"
if [ -f /var/log/apt/history.log ]; then
    grep -iB2 -A2 "ollama\|nvidia\|cuda" /var/log/apt/history.log 2>/dev/null | tail -80
else
    echo "ไม่พบ /var/log/apt/history.log"
fi

_section "8. GPU/driver (เช็คว่า inference ใช้ GPU จริง หรือ fallback เป็น CPU อยู่)"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi 2>&1
else
    echo "ไม่พบ nvidia-smi — ถ้าเดิมมี GPU แล้วหายไป (driver พัง/ไม่ได้โหลด) นี่คือสาเหตุที่อธิบาย"
    echo "elapsed_seconds ที่สูงขึ้นมากได้ตรงๆ (inference fallback ไปเป็น CPU)"
fi

_section "9. micro-benchmark: เวลา inference ดิบ (ไม่ผ่าน multi-agent framework เลย)"
echo "ยิง request ตรงไปที่ Ollama /api/generate 3 ครั้ง วัดเวลาที่ใช้จริงต่อครั้ง"
echo "(prompt สั้นๆ คงที่ เพื่อเทียบ organic latency ของเครื่อง ณ ตอนนี้)"
for i in 1 2 3; do
    START=$(date +%s.%N)
    curl -s http://localhost:11434/api/generate -d '{
        "model": "qwen3:8b",
        "prompt": "Reply with exactly one word: OK",
        "stream": false
    }' -o /tmp/ollama_bench_out.json 2>&1
    END=$(date +%s.%N)
    ELAPSED=$(echo "$END - $START" | bc 2>/dev/null || python3 -c "print($END - $START)")
    echo "  รอบที่ $i: ${ELAPSED}s"
done
echo "--- response ตัวอย่างล่าสุด ---"
cat /tmp/ollama_bench_out.json 2>/dev/null | head -c 500
echo ""

_section "10. ช่วงเวลาที่รันจริงของแต่ละ Tier (อ้างอิงจาก log timestamps จริง)"
cat << 'DATES'
  Tier5 (none, ผลเดิม 14/20 ที่ 75% loss): 2026-07-22 15:38 - 2026-07-23 01:53
  Tier7 (fixed_long_timeout):              2026-07-27 08:26 - 2026-07-27 15:38
  Tier8 (fixed_none):                      2026-07-31 06:37 - 2026-07-31 13:34
  Tier8 (randomized_mitigation none):      2026-08-02 08:09 - 2026-08-04 02:50
  ---
  ถ้า mtime ในข้อ 4/5 อยู่ในช่วง 2026-07-23 ถึง 2026-07-31 (ระหว่าง Tier5 กับ
  Tier8) แปลว่ามีการอัปเดต ollama/โมเดลเกิดขึ้นจริงในช่วงเวลาที่เกี่ยวข้อง —
  นั่นคือคำตอบของ ceiling effect โดยไม่ต้องรันทดลองเพิ่มเลย
DATES

_section "เสร็จสิ้น"
echo "ส่งผลลัพธ์ทั้งหมดนี้กลับมาดูได้เลย จะช่วยตีความว่าจุดไหนเป็นสาเหตุที่เป็นไปได้มากที่สุด"
