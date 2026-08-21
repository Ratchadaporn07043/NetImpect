#!/usr/bin/env bash
# ============================================================================
# confirm_think_via_openai_endpoint.sh — ยืนยันว่า "think": false ใช้ได้กับ
# endpoint แบบ OpenAI-compatible (/v1/chat/completions) ที่ multi_agent.py
# (ผ่าน AutoGen) เรียกจริง ไม่ใช่แค่ /api/generate ที่ทดสอบไปรอบก่อน
# ============================================================================
# รันบน HOST เดียวกัน (ที่ Ollama อยู่)
# ============================================================================
set -uo pipefail

_run_case() {
    local label="$1"; local body="$2"
    echo "--- $label ---"
    for i in 1 2 3; do
        START=$(date +%s.%N)
        RESP=$(curl -s http://localhost:11434/v1/chat/completions \
            -H "Content-Type: application/json" -d "$body")
        END=$(date +%s.%N)
        ELAPSED=$(python3 -c "print(f'{$END - $START:.2f}')")
        echo "  รอบที่ $i: ${ELAPSED}s"
        if [ "$i" = "1" ]; then
            echo "  response ตัวอย่าง: $(echo "$RESP" | head -c 400)"
        fi
    done
    echo ""
}

echo "======================================================================"
echo "A) /v1/chat/completions ปกติ (เหมือน multi_agent.py ใช้อยู่ตอนนี้ทุกประการ)"
echo "======================================================================"
_run_case "A: ปกติ" '{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
  "temperature": 0.3
}'

echo "======================================================================"
echo "B) /v1/chat/completions + \"think\": false ต่อท้าย body"
echo "======================================================================"
_run_case "B: think:false" '{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
  "temperature": 0.3,
  "think": false
}'

echo "======================================================================"
echo "สรุปวิธีอ่านผล"
echo "======================================================================"
cat << 'EOF'
- ถ้า B เร็วขึ้นชัดเจนเหมือนตอนทดสอบผ่าน /api/generate (เหลือ <2s) แปลว่า
  Ollama เวอร์ชันนี้รับ "think": false ผ่าน /v1/chat/completions ด้วย ->
  แก้ multi_agent.py ได้โดยเพิ่ม extra_body={"think": False} หรือใส่ key
  "think": False เข้าไปตรงๆ ใน config_list entry ของ _llm_config()
- ถ้า B ไม่ต่างจาก A เลย แปลว่า endpoint แบบ OpenAI-compatible ของ Ollama
  เวอร์ชันนี้ไม่ forward parameter นี้ให้ ต้องเปลี่ยนไปเรียก Ollama ผ่าน
  /api/chat หรือ /api/generate โดยตรงแทน AutoGen's OpenAI client wrapper
  (ใช้เวลาแก้มากกว่า ต้องเขียน custom client หรือ hook ใน pyautogen)
EOF
