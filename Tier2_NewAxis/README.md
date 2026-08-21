# Tier 2 - New Axes (Bandwidth + Multi-Round Tasks)

**Goal:** Activate the existing bandwidth support and address the original dataset problem in which almost every trial finished in one round.

## Part 1: Bandwidth Axis (`run_tier2_bandwidth.py`)

**No original code is modified.** `NetworkController.apply()` already supports `bandwidth_kbit` through tc and tbf; this tier adds scenarios that use it.

- `main_effect`: six bandwidth levels (2000/1000/500/250/100/50 kbit) x 4 tasks x 5 repeats = **120 trials**
- `x_loss`: low bandwidth (500/100) x 10/30/50% loss x 4 tasks x 3 repeats = **72 trials**
- Total: **192 trials**, approximately 7.8 hours.

```bash
python3 "Tier2_NewAxis/run_tier2_bandwidth.py" --dry-run
python3 "Tier2_NewAxis/run_tier2_bandwidth.py" --part all --resume
```

## Part 2: Multi-Round Tasks + Strict Reviewer (`run_tier2_multiround.py`)

**Problem addressed:** Deep analysis found that almost every original trial ended on the first attempt because the tasks were too easy for Qwen3:8b. The dataset therefore contained little evidence about how poor networks affect multi-round conversations.

**Two combined solutions:**
1. Harder tasks in `tier2_tasks_multiround.py`: `coding_task_hard` and `planning_decision_hard`.
2. A stricter Reviewer using `strict_reviewer=True`, which checks each rubric item and cannot approve incomplete work.

**⚠️ Required step before running `run_tier2_multiround.py`:**
```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # Always back up the original.
cp "Tier2_NewAxis/multi_agent.py" multi_agent.py    # Use the strict_reviewer version.
```

The replacement defaults to `strict_reviewer: bool = False`. Omitting the parameter preserves the original behavior, so Tier1 and the three-day experiment remain compatible. This is covered by `tests_extended/test_baseline_regression.py`.

```bash
python3 "Tier2_NewAxis/run_tier2_multiround.py" --dry-run
python3 "Tier2_NewAxis/run_tier2_multiround.py" --resume
```

Four representative scenarios (baseline / moderate delay / high loss / combined-bad) x 2 hard tasks x 10 repeats = **80 trials**, approximately 3.2 hours. REVISE responses may increase runtime.

## ⚠️ Runtime Environment Variable

Both parts use `LLM_TIMEOUT=600` (272 trials total), instead of the 120-second default used by Tier1, Tier3, Tier4, Tier5, and Tier6. This value is not stored in JSON logs, so it is documented here for reproducibility.

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
