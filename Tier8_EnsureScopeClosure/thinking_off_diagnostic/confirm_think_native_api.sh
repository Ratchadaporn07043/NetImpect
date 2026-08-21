#!/usr/bin/env bash
# ============================================================================
# confirm_think_native_api.sh — หาทางปิด thinking mode ที่ใช้ได้จริง
# เนื่องจาก "think": false ใช้ไม่ได้ผ่าน /v1/chat/completions (ทดสอบไปแล้ว)
# สคริปต์นี้ทดสอบอีก 3 ทาง:
#   D) /v1/chat/completions + "/no_think" ต่อท้ายข้อความ (ไม่ใช่ field แยก) —
#      อาจได้ผลต่างจากตอนทดสอบผ่าน /api/generate เพราะ endpoint นี้ apply
#      chat template จริง (ที่ /no_think อาจถูกออกแบบมาให้ทำงานตรงนี้)
#   E) native /api/chat (ไม่ผ่าน OpenAI-compat layer) ปกติ — วัด baseline
#   F) native /api/chat + "think": false — endpoint เดียวกับ E แต่ปิด thinking
# ============================================================================
set -uo pipefail

_run_case() {
    local label="$1"; local url="$2"; local body="$3"
    echo "--- $label ---"
    for i in 1 2 3; do
        START=$(date +%s.%N)
        RESP=$(curl -s "$url" -H "Content-Type: application/json" -d "$body")
        END=$(date +%s.%N)
        ELAPSED=$(python3 -c "print(f'{$END - $START:.2f}')")
        HAS_REASONING=$(echo "$RESP" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    msg = d.get('message', {}) or (d.get('choices',[{}])[0].get('message', {}) if d.get('choices') else {})
    r = msg.get('thinking') or msg.get('reasoning')
    print('มี reasoning/thinking (' + str(len(r)) + ' ตัวอักษร)' if r else 'ไม่มี reasoning/thinking')
except Exception as e:
    print('parse ไม่ได้:', str(e)[:100])
"
        )
        echo "  รอบที่ $i: ${ELAPSED}s  -  $HAS_REASONING"
    done
    echo ""
}

echo "======================================================================"
echo "D) /v1/chat/completions + \"/no_think\" ต่อท้ายข้อความ (ผ่าน chat template จริง)"
echo "======================================================================"
_run_case "D: /no_think ในข้อความ" "http://localhost:11434/v1/chat/completions" '{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "Reply with exactly one word: OK /no_think"}],
  "temperature": 0.3
}'

echo "======================================================================"
echo "E) native /api/chat ปกติ (ไม่ผ่าน OpenAI-compat layer)"
echo "======================================================================"
_run_case "E: native /api/chat ปกติ" "http://localhost:11434/api/chat" '{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
  "stream": false
}'

echo "======================================================================"
echo "F) native /api/chat + \"think\": false"
echo "======================================================================"
_run_case "F: native /api/chat + think:false" "http://localhost:11434/api/chat" '{
  "model": "qwen3:8b",
  "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
  "think": false,
  "stream": false
}'

echo "======================================================================"
echo "สรุปวิธีอ่านผล"
echo "======================================================================"
cat << 'EOF'
- ถ้า D เร็วขึ้นชัดเจน (<2s, ไม่มี reasoning) -> ปิด thinking ได้ง่ายที่สุดแค่
  ต่อ "/no_think" ท้าย task_prompt ใน multi_agent.py เอง ไม่ต้องแก้อะไรมาก
- ถ้า D ยังช้าเหมือนเดิม แต่ F เร็วขึ้นชัดเจน (<2s, ไม่มี reasoning) -> ต้อง
  เลี่ยง AutoGen's OpenAI client wrapper ไปเรียก /api/chat โดยตรงแทน (ต้อง
  เขียน custom model client ให้ AutoGen ใช้ - งานใหญ่กว่า แต่ทำได้)
- ถ้าทั้ง D และ F ยังช้าเหมือนเดิมหมด -> รุ่น Ollama/โมเดลนี้ไม่ยอมปิด thinking
  ทางไหนเลยที่ทดสอบมา ต้องพิจารณาเปลี่ยนกลยุทธ์ (เช่น ใช้โมเดลอื่น หรือยอมรับ
  thinking mode เป็นส่วนหนึ่งของระบบใหม่ แล้วเพิ่ม BASE_LLM_TIMEOUT/MAX_ROUNDS
  ให้เหมาะสมแทน)
EOF
