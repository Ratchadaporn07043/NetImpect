# Tier 4 — Replication (Multi-Model + Temporal)

**เป้าหมาย:** ตอบคำถามที่ reviewer จะถามแน่นอน 2 ข้อ — "ผลนี้ generalize ข้ามโมเดลไหม" และ "ผลนี้เสถียร/ทำซ้ำได้ไหม (reproducibility)"

ไม่แก้ไฟล์ต้นฉบับใดๆ เลยทั้ง 2 ส่วน (purely additive — เรียกโค้ดเดิมด้วย parameter/log-dir ต่างไปเท่านั้น)

## ส่วนที่ 1: Multi-Model Replication (`run_tier4_main_effect_only.py`)

รัน main-effect axis เดิม (delay/loss/jitter, 5 repeats/level เท่าของเดิม) ซ้ำด้วยโมเดลอื่น เพื่อดูว่า pattern ที่พบ (เช่น degradation region ของ loss ที่ ~50-75%) เป็นเรื่องทั่วไปของ multi-agent LLM หรือเฉพาะ Qwen3:8b

```bash
ollama pull llama3.1:8b   # เตรียมโมเดลเทียบขนาด (8B เหมือนกัน เพื่อ control ตัวแปร "ขนาดโมเดล")

MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --dry-run
MODEL_NAME=llama3.1:8b python3 "Tier4_Replication/run_tier4_main_effect_only.py" --resume
```

**⚠️ ต้องตั้ง `MODEL_NAME` เป็น env var ก่อนเรียก python3** (ไม่ใช่ `--model` flag) เพราะ `multi_agent.py` อ่านค่านี้ตอน import module ครั้งเดียว

Scenarios: 42 main-effect levels (21 delay + 11 loss + 10 jitter) × 4 tasks × 5 repeats = **840 trials/โมเดล** ≈ 34.0 ชั่วโมง/โมเดล (ยืนยันด้วย `--dry-run` จริง) — log แยกอัตโนมัติเป็น `logs_tier4_<model_name>/` เทียบกับ `logs_three_day/` เดิม (=qwen3:8b) ได้ตรงไปตรงมา

## ส่วนที่ 2: Temporal Full Replication (`run_tier4_temporal_replicate.sh`)

รัน three-day plan **ทั้งชุดซ้ำ** (tournament + main-effect + combined + baseline, 1,544 trials เท่าเดิม) ในช่วงเวลาอื่น เพื่อตรวจว่าความแปรปรวนที่เห็นมาจาก network condition จริง ไม่ใช่ noise จากเครื่อง/เวลา/LLM sampling

```bash
bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --dry-run
bash "Tier4_Replication/run_tier4_temporal_replicate.sh"
bash "Tier4_Replication/run_tier4_temporal_replicate.sh" --resume
```

เขียนไป `logs_three_day_replicate2/` — ใช้ `experiment/run_experiment.py --three-day` เดิมตรงๆ แค่เปลี่ยน `--log-dir` เท่านั้น (**1,544 trials ≈ 62.5 ชั่วโมง ≈ 2.6 วัน** เท่าของเดิม — งบเวลาหนักสุดใน 5 tier)

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `run_tier4_main_effect_only.py` | รัน main-effect axis ซ้ำด้วย `MODEL_NAME` อื่น |
| `run_tier4_temporal_replicate.sh` | รัน three-day plan ทั้งชุดซ้ำในช่วงเวลาอื่น |

## สถานะการรัน

✅ รันเสร็จแล้ว — 1,544+840=2,384/2,384 trials, 0 ไฟล์เสีย

ผลการวิเคราะห์แบบละเอียด (temporal replication ยืนยันผลหลักทั้งหมด, และข้อจำกัดใหม่ที่ heuristic evaluator ไม่ transfer ข้ามโมเดล) พร้อมสถิติและการตีความเต็มรูปแบบ รวมไว้ใน
`Paper/NetImpact.md/Current/NetImpact_04_Tier4_Replication.md` แล้ว — ไฟล์นี้เก็บไว้เฉพาะวิธีรันโค้ดและสถานะการรันเท่านั้น
กราฟดิบอยู่ที่ `Analysis_เบื้องต้น/charts/tier4/`
