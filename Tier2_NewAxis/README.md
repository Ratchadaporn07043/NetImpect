# Tier 2 — แกนใหม่ (Bandwidth + Multi-Round Tasks)

**เป้าหมาย:** เปิดแกนการทดลองที่โค้ดรองรับอยู่แล้วแต่ไม่เคยถูกใช้ (bandwidth) และแก้ปัญหา "แทบทุก trial จบใน 1 รอบ" ที่พบในชุดข้อมูลเดิม

## ส่วนที่ 1: Bandwidth Axis (`run_tier2_bandwidth.py`)

**ไม่แก้โค้ดต้นฉบับเลย** — `NetworkController.apply()` รองรับ `bandwidth_kbit` อยู่แล้ว (tc + tbf) เพียงแต่ไม่เคยมี scenario ไหนส่งค่านี้เข้ามา

- `main_effect`: bandwidth เดี่ยวๆ 6 ระดับ (2000/1000/500/250/100/50 kbit) × 4 tasks × 5 repeats = **120 trials**
- `x_loss`: bandwidth ต่ำ (500/100) × loss กลาง-สูง (10/30/50%) × 4 tasks × 3 repeats = **72 trials**
- รวม **192 trials** ≈ 7.8 ชั่วโมง

```bash
python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --dry-run
python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --part all --resume
```

## ส่วนที่ 2: Multi-Round Tasks + Strict Reviewer (`run_tier2_multiround.py`)

**ปัญหาที่แก้:** จากการวิเคราะห์เชิงลึก (`Paper/NetImpact.md/Archive_Legacy/NetImpact_12_InDepth_Experiment_Results.md`) พบว่าเกือบทุก trial ใน dataset เดิมจบใน attempt เดียว (Reviewer พูด APPROVED รอบแรก) เพราะ task เดิมง่ายเกินไปสำหรับ Qwen3:8b — ทำให้แทบไม่มีข้อมูลว่า network ที่แย่ไปรบกวน "บทสนทนาหลายรอบ" อย่างไรบ้าง

**วิธีแก้ 2 ทาง (ใช้พร้อมกัน):**
1. Task ที่ยากขึ้น (`tier2_tasks_multiround.py`): `coding_task_hard` (ต้อง parse log พร้อม edge case 4 อย่าง), `planning_decision_hard` (ต้องให้คะแนน 5 มิติ + เลือก 2/5 + วิเคราะห์ trade-off)
2. Reviewer เข้มงวดขึ้น (`multi_agent.py` เวอร์ชันนี้, พารามิเตอร์ `strict_reviewer=True`): บังคับเช็ค rubric ทีละข้อ ห้าม APPROVED ถ้ายังขาดข้อไหน

**⚠️ ขั้นตอนสำคัญก่อนรัน `run_tier2_multiround.py`:**
```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # สำรองไฟล์เดิมไว้ก่อนเสมอ
cp "Tier2_แกนใหม่/multi_agent.py" multi_agent.py    # แทนที่ด้วยเวอร์ชันรองรับ strict_reviewer
```

ไฟล์ที่แทนที่มี `strict_reviewer: bool = False` เป็นค่า default เสมอ — ถ้าไม่ส่งพารามิเตอร์นี้ (เหมือนที่ `run_tier1.py`/`run_experiment.py` เดิมเรียก) พฤติกรรมจะ**เหมือนต้นฉบับ 100%** จึงปลอดภัยที่จะแทนที่ไฟล์นี้แล้วยังรัน Tier1 หรือ three-day เดิมต่อได้ตามปกติ (ผ่านการทดสอบใน `tests_extended/test_baseline_regression.py`)

```bash
python3 "Tier2_แกนใหม่/run_tier2_multiround.py" --dry-run
python3 "Tier2_แกนใหม่/run_tier2_multiround.py" --resume
```

4 scenario ตัวแทน (baseline / moderate delay / high loss / combined-bad) × 2 hard tasks × 10 repeats = **80 trials** ≈ 3.2 ชั่วโมง (อาจนานกว่านี้เพราะ REVISE ทำให้คุยหลายรอบ)

## ⚠️ หมายเหตุสำคัญ: environment variable ที่ใช้จริงตอนรัน (ต่างจาก Tier อื่น)

การรันจริงทั้ง 2 ส่วน (bandwidth 192 trials + multiround 80 trials รวม 272 trials) ใช้ `LLM_TIMEOUT=600` (ไม่ใช่ default 120 วินาทีที่ Tier1/Tier3/Tier4/Tier5/Tier6 ใช้กันหมด) — ค่านี้**ไม่ถูกบันทึกลง JSON log เลย** (`logger.py` ไม่มี field เก็บค่า config นี้) จึงบันทึกไว้ในเอกสารนี้แทนเพื่อ reproducibility และกันถูกถามเรื่อง hyperparameter ตอน submit AINTEC2026

```bash
LLM_TIMEOUT=600 python3 "Tier2_แกนใหม่/run_tier2_bandwidth.py" --part all --resume
LLM_TIMEOUT=600 python3 "Tier2_แกนใหม่/run_tier2_multiround.py" --resume
```

**ผลต่อการตีความ:**
- **Multi-round finding (moderate_delay 75%) ไม่ได้รับผลกระทบเชิงลบ** — timeout ที่กว้างกว่านี้ (600s) ควรจะช่วยลด "timeout ปลอม" ได้มากกว่า 120s ปกติเสียอีก ถ้ายังเจอ success rate ตกที่ moderate_delay ทั้งที่ timeout ไม่ใช่คอขวดแล้ว ยิ่งยืนยันว่าสาเหตุจริงคือ reviewer rejection สะสมข้ามรอบสนทนา ไม่ใช่ timeout artifact
- **Bandwidth finding ("ไม่มีผลเลย") ควรอ่านโดยมี caveat นี้ประกอบ** — bandwidth ต่ำมาก (50 kbit/s) ถ้าใช้ timeout เข้มกว่านี้ (120s ปกติ) อาจเจอ timeout จริงที่ถูกบดบังไปด้วย timeout=600 ก็ได้ ไม่ควรสรุปแบบ absolute ว่า bandwidth ไม่มีผลเลยในทุกเงื่อนไข timeout
- **Tier6 (`Tier6_MitigationXMultiRound/`) ที่ทดสอบ mitigation บน moderate_delay scenario นี้ต่อ ต้องรันด้วย `LLM_TIMEOUT=600` เช่นกัน** เพื่อให้ "none" condition เทียบกับตัวเลข 75% เดิมได้ตรงๆ (ดูหมายเหตุใน `Tier6_MitigationXMultiRound/README.md`)

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `tier2_scenarios_bandwidth.py` | นิยาม scenario แกน bandwidth (ใหม่ล้วน) |
| `tier2_tasks_multiround.py` | นิยาม hard task 2 อัน + ground-truth rubric |
| `multi_agent.py` | **แทนที่** ไฟล์ root เดิม — เพิ่ม `strict_reviewer` param (default=False = เหมือนเดิม) |
| `run_tier2_bandwidth.py` | รัน bandwidth axis (ใช้ multi_agent.py เดิมได้เลย ไม่ต้องแทนที่) |
| `run_tier2_multiround.py` | รัน hard tasks + strict reviewer (ต้องแทนที่ multi_agent.py ก่อน) |

log: `logs_tier2_bandwidth/` และ `logs_tier2_multiround/` (แยกจากทุกอันอื่น)

## สถานะการรัน

✅ รันเสร็จแล้ว — 192+80=272/272 trials, 0 ไฟล์เสีย

ผลการวิเคราะห์แบบละเอียด (bandwidth null result เต็มช่วง, และ multi-round reversal ที่ delay กลายเป็นปัจจัยแย่ที่สุด) พร้อมสถิติและการตีความเต็มรูปแบบ รวมไว้ใน
`Paper/NetImpact.md/Current/NetImpact_02_Tier1_Tier2_Measurement_Axes.md` แล้ว — ไฟล์นี้เก็บไว้เฉพาะวิธีรันโค้ดและสถานะการรันเท่านั้น
กราฟดิบอยู่ที่ `Analysis_เบื้องต้น/charts/tier2/`
