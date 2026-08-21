# thinking_off_diagnostic — checklist สั้นๆ ว่าต้องทำอะไรต่อ

โฟลเดอร์นี้แยกออกมาจาก `Tier8_EnsureScopeClosure/` เพื่อไม่ให้ปนกับ 5 ข้อหลัก
ที่รันจบไปแล้ว (อยู่ที่ `../results_completed/`) — **ทุกอย่างในนี้รันจบแล้ว**
(smoke test + ทั้ง 3 confirmatory script, รวม 80 diagnostic trials) ผลสรุปคือ
thinking mode ไม่ใช่สาเหตุของความผิดปกติที่พบในข้อ 1/2/3/4 — ดูตัวเลขจริงในหัวข้อ
"หลังรันครบ 3 สคริปต์แล้วทำอะไรต่อ" ด้านล่าง

## ทำไมต้องมีโฟลเดอร์นี้

วิเคราะห์ผลจาก 5 ข้อหลักแล้วพบว่า Ollama เปิด "thinking mode" อยู่ตลอดการรัน
ทำให้แต่ละ LLM call ช้าลง 10-30+ เท่า และทำให้บาง scenario ที่ loss=75% ในข้อ
1/2/3/4 ได้ผลผิดเพี้ยน (ข้อ 1/2/3 ได้ completion สูงผิดปกติ, ข้อ 4 ได้ต่ำผิดปกติ
จนเหลือ 0%) โฟลเดอร์นี้มีทั้งหลักฐานการวินิจฉัย + โค้ดตัวแก้ + สคริปต์ทดสอบยืนยัน

## สถานะไฟล์ในนี้ (ทำไปแล้ว vs ยังไม่ได้ทำ)

**✅ ทำไปแล้ว (แค่ตรวจวินิจฉัย ไม่ใช่ trial การทดลองจริง):**
- `diagnosis_output.txt` — เช็คเวอร์ชัน Ollama/model ว่าเหมือนตอนรัน Tier 1-7 ไหม
- `thinking_output.txt`, `openai_endpoint_output.txt`, `native_api_output.txt` —
  ทดสอบยืนยันว่าวิธีไหนปิด thinking mode ได้จริง (สรุป: ต้องใช้ native
  `/api/chat` + `think:false` เท่านั้น)
- `ollama_native_client.py`, `multi_agent_thinking_off.py` — เขียนโค้ดแก้เสร็จ
  แล้ว ทดสอบ wiring ด้วย fake server จำลองแล้วว่าถูกต้อง (ไม่ใช่การรันจริงกับ
  Ollama ยังต้องทดสอบกับของจริงอีกที ดูขั้นตอนที่ 0 ด้านล่าง)

**✅ รันจบแล้วทั้งหมด:**
- `smoke_test_thinking_off.py` — ผ่านทั้ง 2 stage
- `run_confirm_thinking_off.py` — 20/20 trials (ข้อ 2/3)
- `run_confirm_thinking_off_item1.py` — 20/20 trials (ข้อ 1)
- `run_confirm_thinking_off_item4.py` — 40/40 trials (ข้อ 4)

## ลำดับที่รันจริง (เก็บไว้อ้างอิง ไม่ต้องรันซ้ำ)

### ขั้นตอนที่ 0 — smoke test

```bash
python3 smoke_test_thinking_off.py
```

✅ ผ่านทั้ง 2 stage

### ขั้นตอนที่ 1 — ข้อ 2/3 (20 trials)

```bash
python3 run_confirm_thinking_off.py --dry-run
python3 run_confirm_thinking_off.py --resume
```

### ขั้นตอนที่ 2 — ข้อ 1 (20 trials)

```bash
python3 run_confirm_thinking_off_item1.py --dry-run
python3 run_confirm_thinking_off_item1.py --resume
```

### ขั้นตอนที่ 3 — ข้อ 4 (40 trials, ต้อง `sudo modprobe ifb numifbs=0` บน host ก่อน)

```bash
sudo modprobe ifb numifbs=0        # รันบน host เท่านั้น ไม่ใช่ใน container
python3 run_confirm_thinking_off_item4.py --probe-only
python3 run_confirm_thinking_off_item4.py --dry-run
python3 run_confirm_thinking_off_item4.py --resume
```

### ข้อ 5 — ไม่ได้รันซ้ำ (ตัดสินใจแต่แรกว่าไม่จำเป็น)

เงื่อนไขของข้อ 5 ไม่มี packet loss เลย (delay=50ms คงที่) จึงไม่ใช่แบบที่
thinking-mode latency จะไปดัน completion ให้ผิดปกติได้ และผลเดิมก็ตรงกับ
baseline ที่มีอยู่แล้ว

## ผลที่ได้ (รันจบแล้ว)

เทียบ completion rate ที่ได้จาก log ใหม่ (`logs_tier8_diagnostic_thinking_off_confirm*/`
ในโฟลเดอร์นี้ — 20+20+40 = 80 trials) กับตัวเลขเดิม:

| จุดที่เทียบ | Tier 5 เดิม | thinking-on (เดิม) | thinking-off (ผลจริง) |
|---|---|---|---|
| ข้อ 2/3 (loss=75%, none) | 14/20 | ~100% | 20/20 |
| ข้อ 1 (`t8ap_loss75`) | 14/20 | 20/20 | 18/20 |
| ข้อ 4 (`t8in_baseline` / `t8in_loss75`) | — | 20/20 / 0/20 | 100% / 0/20 |

**ไม่มีจุดไหนขยับเข้าใกล้คอลัมน์ Tier 5 เดิมเลย** — แปลว่า thinking mode **ไม่ใช่**
สาเหตุหลักของ ceiling/floor effect ที่พบในข้อ 1/2/3/4 สาเหตุจริงที่พบภายหลัง (ผ่านการเทียบ
elapsed time โดยตรง ไม่ใช่จากการรันชุดนี้) คือความเร็ว inference ของสภาพแวดล้อมปัจจุบัน
เร็วขึ้นราว 2 เท่าเทียบกับตอน Tier 5 รัน — รายละเอียดเต็มอยู่ที่
`Paper/NetImpact.md/Current/NetImpact_21_Tier8_Ensure_Scope_Closure.md` §6 ผลจาก 3
สคริปต์นี้เป็นการวินิจฉัย (n=20-40 ต่อสคริปต์) ใช้เพื่อตัดสินใจเท่านั้น ไม่ใช่ผลที่แทนที่
ข้อ 1/2/3/4 เดิมโดยตรง — การหาจุดวิกฤตใหม่ของสภาพแวดล้อมปัจจุบันดำเนินต่อที่
`Tier9_CriticalThresholdRecalibration/` (พบว่าอยู่ที่ 80%)

รายละเอียดเชิงลึกทั้งหมด (สาเหตุ/หลักฐาน/สมมติฐาน) อยู่ที่
`../README.md` หัวข้อ "ส่วนเสริม (diagnostic)"
