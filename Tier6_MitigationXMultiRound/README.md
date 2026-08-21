# Tier 6 — Mitigation × Multi-Round (optional stretch experiment)

**สถานะ:** ✅ รันเสร็จแล้ว — 120/120 trials, 0 ไฟล์เสีย — เป็น **optional stretch** experiment เพิ่มจาก 5 Tier หลัก (ดู `Paper/NetImpact.md/Archive_Legacy/NetImpact_10_AINTEC2026_Readiness_Assessment.md` สำหรับบริบท timeline เดิมที่ทำให้ถูกจัดเป็น optional) — ผลจริงอยู่ที่หัวข้อ "ผลที่ได้" ด้านล่าง และรายละเอียดเต็มที่
`Paper/NetImpact.md/Current/NetImpact_06_Tier6_Pending_Experiment.md` (ชื่อไฟล์ยังใช้คำว่า
"Pending" เพื่อความคงที่ของลิงก์อ้างอิงในเอกสารอื่น — เนื้อหาข้างในเป็นผลจริงที่รันจบแล้ว ไม่ใช่แผนที่ยังไม่ได้รัน)

## เป้าหมาย

เชื่อม 2 finding ที่แข็งแรงที่สุดของโปรเจกต์เข้าด้วยกัน:

1. **Tier2 finding:** เมื่อใช้ hard tasks + `strict_reviewer=True` (บังคับคุยหลายรอบ) success rate โดยรวมตกจาก ~100% เหลือ 83.75% และ **`moderate_delay` (delay=300ms) คือ scenario ที่แย่ที่สุด (75%)** — แย่กว่า baseline (95%), high_loss (85%) และ combined_bad (80%) เสียอีก แสดงว่า delay สะสมผลข้ามรอบสนทนาได้ ทั้งที่ main-effect เดิม (single-pass) ไม่เห็นผลของ delay เลย
2. **Tier5 finding:** `adaptive_timeout` แก้ปัญหา loss cliff ได้จริงมีนัยสำคัญ (70%→100% ที่ loss=75%, Fisher p=0.020) แต่ทดสอบบนแกน loss แบบ single-pass (`strict_reviewer=False`) เท่านั้น

**คำถามของ Tier6:** mitigation ที่พิสูจน์แล้วว่าช่วยแกน loss (single-pass) จะช่วยปัญหา "delay สะสมข้ามรอบสนทนา multi-round" ของ Tier2 ได้ด้วยหรือไม่ — เป็นคำถามที่ไม่มี Tier ไหนก่อนหน้าเคยตอบ เพราะไม่เคยมีการเรียก `strict_reviewer=True` และ `mitigation=<...>` พร้อมกันมาก่อน

ถ้าพิสูจน์ได้ว่าช่วย: paper จะมี narrative แบบ "พบปัญหา A (loss cliff) → แก้ได้ → พบปัญหา B ที่ต่างมิติ (multi-round delay) → mitigation เดิมช่วยได้ด้วย (generalizes)" ซึ่งแข็งแรงกว่า "แก้ได้แค่ปัญหาเดียว" มาก ถ้าไม่ช่วย: ก็ยังเป็นผลลัพธ์ที่มีประโยชน์ (ระบุขอบเขตของ mitigation ชัดเจนขึ้น เขียนเป็น limitation/future work ได้)

## ทำไมใช้ scope แค่นี้ (ไม่ใช่ full factorial)

ทดสอบเฉพาะ 2 scenario ที่จำเป็น: `baseline` (control — มี strict_reviewer แต่ไม่มี network impairment เพื่อแยกผลของ "reviewer เข้มงวด" ออกจากผลของ "delay") กับ `moderate_delay` (จุดที่ Tier2 พบว่าแย่สุด, delay=300ms) — ไม่รวม `high_loss`/`combined_bad` ของ Tier2 เพราะเป้าหมายเฉพาะเจาะจงคือ moderate_delay ตามที่วิเคราะห์ไว้ข้างต้น ถ้ามีเวลาเหลือทีหลังขยายได้ง่าย (แค่เพิ่ม scenario เข้า `TEST_SCENARIOS` ใน `run_tier6_mitigation_multiround.py`)

## ⚠️ ขั้นตอนก่อนรัน

```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # สำรองไฟล์เดิมไว้เสมอ
cp "Tier6_MitigationXMultiRound/multi_agent.py" multi_agent.py
```

ไฟล์นี้เป็นสำเนา 1:1 ของ `Tier5_Mitigation/multi_agent.py` (logic เหมือนกันทุกบรรทัด ไม่ได้แก้อะไร) — เก็บสำเนาไว้ในโฟลเดอร์นี้ด้วยเพื่อให้ Tier6 self-contained ตามธรรมเนียมเดียวกับทุก Tier ก่อนหน้า รองรับ `strict_reviewer` (จาก Tier2) และ `mitigation`/`network_condition` (จาก Tier5) **พร้อมกัน** โดย default ทั้งคู่ยังเป็นค่าเดิม (`strict_reviewer=False`, `mitigation="none"`) เสมอ ถ้าไม่ส่งพารามิเตอร์ พฤติกรรมเหมือนต้นฉบับ 100% (ยืนยันด้วย `tests/test_baseline_regression.py` ที่มีอยู่แล้ว)

`run_tier6_mitigation_multiround.py` มี guard เช็คอัตโนมัติว่า `multi_agent.py` ที่ root รองรับทั้ง `strict_reviewer`, `mitigation`, `network_condition` จริง — ถ้า cp ผิดไฟล์ (เช่น cp `Tier2_แกนใหม่/multi_agent.py` ที่ไม่มี `mitigation`) จะ error พร้อมคำแนะนำทันที ไม่รันไปแล้วได้ผลผิดแบบเงียบๆ

## วิธีรัน

```bash
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --dry-run

# รันทีละเงื่อนไข (แนะนำ — ใช้ --resume ได้ทุกครั้งถ้าหลุดกลางคัน):
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition none --resume             # control (strict_reviewer=True, mitigation ปิด)
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition adaptive_timeout --resume  # Mitigation A
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition context_cache --resume     # Mitigation B

# หรือรันรวดเดียวทั้ง 3 เงื่อนไข (120 trials รวม)
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition all --resume
```

จำนวน trial: 2 scenarios (`t6_baseline`, `t6_moderate_delay`) × 2 hard tasks (`coding_task_hard`, `planning_decision_hard`, ยืมมาจาก Tier2 ตรงๆ ไม่ duplicate นิยาม) × 10 repeats (เท่า Tier2 เพื่อเทียบ n ตรงกัน) = **40 trials ต่อเงื่อนไข** × 3 เงื่อนไข = **120 trials รวม**

log แยกเป็น `logs_tier6_none/`, `logs_tier6_adaptive_timeout/`, `logs_tier6_context_cache/` — สิ่งที่ต้องเทียบหลังรันเสร็จ:

- success rate ที่ `t6_moderate_delay` โดยเฉพาะ (none vs adaptive_timeout vs context_cache) — นี่คือคำถามหลัก
- success rate ที่ `t6_baseline` ควรใกล้เคียงกันทั้ง 3 เงื่อนไข (ถ้าต่างกันมาก แปลว่า mitigation มีผลข้างเคียงกับกรณีไม่มีปัญหาเลยด้วย ต้องระวัง)
- reviewer_rejections เฉลี่ยต่อ trial ที่ `t6_moderate_delay` (ลดลงหรือไม่หลัง mitigation)
- elapsed_seconds เฉลี่ย (ต้นทุนเวลาที่แลกมา เหมือนที่ Tier5 พบว่า adaptive_timeout ทำให้ช้าขึ้น)

**หมายเหตุ code (สืบทอดจาก Tier5):** field `mitigation` ใน `multi_agent.py` ถูกคำนวณและใส่ใน return dict แต่ **ไม่ถูกบันทึกลง JSON log จริง** (`logger.log_outcome()` ไม่รับพารามิเตอร์นี้) — ไม่กระทบผลการวิเคราะห์เพราะ Tier6 แยกโฟลเดอร์ log ต่อเงื่อนไขอยู่แล้ว (`logs_tier6_<condition>/`) และ field `network_condition.experiment_phase` (`tier6_mitigation_multiround__<condition>`) ระบุเงื่อนไขถูกต้อง 100% เมื่อ parse log — เหมือนที่ Tier5 เจอและสรุปไว้แล้ว

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `multi_agent.py` | สำเนา 1:1 ของ `Tier5_Mitigation/multi_agent.py` — **แทนที่** root เดิม รองรับ `strict_reviewer` (Tier2) + `mitigation` A/B (Tier5) พร้อมกัน |
| `run_tier6_mitigation_multiround.py` | รัน before/after comparison ที่ scenario `t6_baseline`/`t6_moderate_delay` ด้วย hard tasks ของ Tier2 + `strict_reviewer=True` เสมอ |

ไม่มีไฟล์ task/scenario ของตัวเอง — ยืม `TIER2_HARD_TASKS`/`TIER2_HARD_TASK_GROUND_TRUTH` จาก `Tier2_แกนใหม่/tier2_tasks_multiround.py` ตรงๆ (import ข้ามโฟลเดอร์ ดู `sys.path` setup ต้นไฟล์ `run_tier6_mitigation_multiround.py`)

## การทดสอบ (offline, ไม่ต้องมี Ollama/GPU/tc จริง)

```bash
python3 -m pytest tests_extended/test_tier6_mitigation_multiround.py -v
python3 -m pytest tests_extended/ -v   # full suite รวมทุก Tier
```

ครอบคลุม: `multi_agent.py` ของ Tier6 รองรับ `strict_reviewer`+`mitigation`+`network_condition` พร้อมกันจริง (ไม่ใช่แค่มี parameter แต่ต้องส่งผลจริงตอนเรียกพร้อมกัน — เช่น reviewer ใช้ strict message ถูกต้อง **และ** timeout ถูกขยายตาม network_condition ถูกต้อง ในการเรียกครั้งเดียวกัน), guard เช็ค version ทำงานถูกต้อง (error ชัดเจนถ้า multi_agent.py ไม่รองรับ), `TEST_SCENARIOS` ตรงกับค่าของ Tier2 เป๊ะ, runner script import ได้ไม่ error

## ผลที่ได้

✅ รันเสร็จแล้ว — 120/120 trials, 0 ไฟล์เสีย

**Completion counts (n=20/เงื่อนไข/scenario):**

| เงื่อนไข | `t6_baseline` | `t6_moderate_delay` | รวม |
|---|---|---|---|
| `none` (control) | 14/20 | 16/20 | 30/40 |
| `adaptive_timeout` | 17/20 | 19/20 | 36/40 |
| `context_cache` | 18/20 | 17/20 | 35/40 |

**ไม่มีคู่เปรียบเทียบไหนถึงนัยสำคัญทางสถิติ** (Fisher's exact test, p > 0.05 ทั้ง 6 คู่ — ใกล้นัยสำคัญที่สุดคือ p = 0.139)

**ข้อค้นพบสำคัญที่สุดของ Tier นี้ไม่ใช่ตัวเลขข้างบน แต่คือการตรวจสอบ falsification ล้มเหลว**: ที่ scenario `t6_baseline` (ไม่มี network impairment เลย) สูตร adaptive-timeout คำนวณค่าเพิ่มเป็นศูนย์เสมอ (code path เดียวกับ control ทุกประการใน 20/20 trials) และ context-caching branch เกิดเพียง 1/20 trials — แต่ completion ยังต่างกันถึง 14/20, 17/20, 18/20 (ต่างกัน 15-20 percentage points) ระหว่าง arm ที่ไม่มีมาตรการทำงานอยู่เลย นี่คือหลักฐานว่าความผันแปรระหว่าง run-block ในระดับนี้เกิดขึ้นได้เองแม้ไม่มีการรักษาใดๆ ทำงาน จึงไม่สามารถแยกผลของ mitigation จริงออกจากความผันแปรนี้ได้ในดีไซน์นี้ — control arm เองก็ไม่ reproduce ลำดับผลเดิมของ Tier2 ด้วย (baseline 14/20 เทียบ moderate_delay 16/20 — สลับทิศทางจาก Tier2 เดิมที่ baseline 19/20 > moderate_delay 15/20)

**สรุปสำหรับเปเปอร์**: การทดลองนี้ไม่พบว่า mitigation ที่พิสูจน์แล้วว่าช่วยแกน loss (Tier5) ส่งผลข้ามไปช่วยปัญหา multi-round delay (Tier2) ได้ แต่ไม่ใช่เพราะพิสูจน์แล้วว่าไม่ช่วย — เป็นเพราะดีไซน์นี้ (n=20/arm, ไม่สลับลำดับ) ไม่สามารถแยกผลของ mitigation ออกจากความผันแปรระหว่าง block ได้เลย รายละเอียดสถิติ/การตีความ/ข้อจำกัดเต็มรูปแบบอยู่ที่
`Paper/NetImpact.md/Current/NetImpact_06_Tier6_Pending_Experiment.md`
