# Tier 9 — Critical Threshold Recalibration

**สถานะ:** ✅ รันเสร็จแล้วทั้ง 2 ขั้นตอน — 120/120 trials (60 exploratory scan + 60
critical comparison), 0 ไฟล์เสีย ผลสรุปอยู่ที่หัวข้อ "ผลที่ได้" ท้ายไฟล์นี้ รายละเอียด
เต็ม/สถิติ/wording ที่อนุมัติแล้วอยู่ที่
`Paper/NetImpact.md/Current/NetImpact_22_Tier9_Critical_Threshold_Recalibration.md`

โฟลเดอร์นี้ตอบคำถามที่ Tier 8 เปิดขึ้นมาแต่ตอบไม่ได้: mitigation="none" (arm
ควบคุม) ไม่ล้มเหลวเลยที่ loss=75% ในสภาพแวดล้อมปัจจุบัน (20/20 ทุกครั้ง ทั้ง
ตอน thinking mode เปิดและปิด) ทั้งที่ Tier 5 เดิมได้แค่ 14/20 ที่จุดเดียวกัน —
Tier 9 หา **critical loss threshold ใหม่** ของสภาพแวดล้อมปัจจุบัน แล้วรัน
เปรียบเทียบ mitigation strategies ที่จุดนั้นแทน เพื่อให้ได้ผลที่นำไปเขียนลง
เปเปอร์ได้จริง

---

## ที่มา (ทำไมต้องมี Tier 9 — สรุปจากการวินิจฉัยใน Tier 8)

การไล่หาสาเหตุใช้เวลาหลายรอบ สรุปเป็นลำดับได้ดังนี้:

1. **สมมติฐานแรก (ผิด บางส่วน)**: Ollama เปิด "thinking" mode เป็นค่าเริ่มต้น
   ให้ qwen3:8b ทำให้ทุก LLM call ช้าลง 10-30+ เท่า สงสัยว่าเป็นสาเหตุของ
   ceiling effect ที่ข้อ 1/2/3 ของ Tier 8
2. **ทดสอบจริง**: เขียน custom AutoGen client คุย Ollama ผ่าน native
   `/api/chat` + `"think": false` (endpoint เดียวที่ปิด thinking ได้จริง) แล้ว
   รัน confirmatory re-run จริงที่ loss=75%/mitigation=none — **ได้ 20/20 เท่า
   เดิม ไม่ขยับเลย** แปลว่า thinking mode ไม่ใช่สาเหตุของ ceiling effect (แต่
   เป็นปัญหาจริงเรื่อง latency ที่ยืนยันแล้วแยกต่างหาก)
3. **ตัด confound อื่นออกทีละอย่าง**: ตรวจโค้ด retry/timeout ของ Tier 5 เทียบ
   Tier 8 — เหมือนกันเป๊ะทุกตัวอักษร (`MAX_RETRIES=2`, `BASE_LLM_TIMEOUT=120`)
   ไม่ใช่สาเหตุ; ตรวจ achieved loss จริงจาก qdisc counters (ข้อ 1 เดิม) — ได้
   median 75.1% เกือบตรงกับ configured 75% เป๊ะ ไม่ใช่ว่า netem ไม่ทำงานจริง
4. **สาเหตุจริงที่พบ**: เทียบเฉพาะ trial ที่**สำเร็จตั้งแต่ครั้งแรก (ไม่มี
   retry)** ระหว่าง Tier 5 เดิมกับ thinking-off confirmatory run ที่ loss=75%
   เท่ากัน — **elapsed median ต่างกันเกือบ 2 เท่า** (Tier 5 เดิม 248s เทียบกับ
   127s ตอนนี้, msg-gap 86s เทียบกับ 45s) แม้ตัด thinking mode และ retry ออก
   หมดแล้ว การตอบกลับสำเร็จตอนนี้ยังเร็วกว่าเดิมเกือบ 2 เท่า — connection ที่
   สั้นลง = เสี่ยงโดน packet drop ระหว่างทางน้อยลง = รอดจาก 75% loss ได้บ่อยกว่า
5. **ยืนยันด้วยข้อมูลที่มีอยู่แล้ว**: ข้อ 3 เดิมของ Tier 8 (660 trials, 11
   ระดับ loss ตั้งแต่ 0-75%) พบว่า `none` arm ได้ ~100% **ทุกระดับ loss ที่เคย
   ทดสอบมาตลอดทั้งโปรเจกต์** — 75% คือ loss สูงสุดที่เคยทดสอบเลย ไม่เคยมีข้อมูล
   เกินนี้ จึงไม่รู้ว่าจุดวิกฤตใหม่อยู่ตรงไหน

**สรุป**: มี environment drift 2 ชั้นซ้อนกันระหว่างตอน Tier 5 รันกับตอนนี้ —
(ก) thinking mode เปิดขึ้นมา (แก้ได้ด้วย custom client, ดูข้อ 2) และ (ข)
inference โดยรวมเร็วขึ้นเอง ~2 เท่า (แก้ไม่ได้ด้วย client parameter — เป็นการ
เปลี่ยนแปลงของ software stack เอง อาจมาจาก Ollama เวอร์ชันใหม่/GPU-Vulkan ที่
เพิ่งเปิดใช้) Tier 9 จึงต้องหา critical threshold ใหม่แทนที่จะพยายามยัดค่า 75%
เดิมต่อไป

---

## ทำไมแยกเป็น Tier 9 ไม่อยู่ใต้ Tier 8

คำถามวิจัยของ Tier 9 ("critical threshold อยู่ตรงไหนในสภาพแวดล้อมปัจจุบัน")
เป็นคำถามใหม่ที่ไม่ได้อยู่ใน 5 ข้อเดิมของ Tier 8 เลย (Tier 8 = achieved-path
measurement, fixed-timeout arm, randomized order, ingress, jitter-floor) —
แยก tier ให้ชัดว่า **Tier 8 = จุดที่ค้นพบ scope gap + environment drift, Tier
9 = การ recalibrate และรันเปรียบเทียบใหม่ให้ถูกต้อง**

**Tier 9 เป็น standalone เต็มรูปแบบ ไม่ import จาก Tier 8 หรือ `experiment/`
ที่ root เลย**: `tier9_controller.py`, `tier9_logger.py`,
`tier9_checkpoint_utils.py`, `tier9_tasks.py`, `tier9_evaluator.py` เป็น
สำเนาของตัวเอง (คัดลอกมาจาก Tier 8's `controller.py`/`logger.py`/
`checkpoint_utils.py` และ root's `experiment/tasks.py`/`experiment/evaluator.py`
ซึ่งตรวจสอบ/เทสยืนยันความถูกต้องแล้ว — logic/โค้ดเหมือนต้นฉบับทุกบรรทัด ต่างกัน
แค่ 2 จุด: (1) `tier9_controller.py`/`tier9_logger.py` แก้ docstring header ให้
บอกที่มาว่าเป็นสำเนาของ Tier 9 (ไม่กระทบโค้ด) และ (2) `tier9_evaluator.py` แก้
import 1 บรรทัดให้ชี้มาที่ `tier9_tasks.py` แทน `experiment.tasks` — ส่วน
`tier9_checkpoint_utils.py`/`tier9_tasks.py` byte-identical ทุกตัวอักษรกับ
ต้นฉบับ ไม่แก้อะไรเลยแม้แต่ docstring) ตั้งชื่อ
ด้วย prefix `tier9_` เพื่อไม่ให้ชนกับไฟล์ชื่อเดียวกันใน Tier 8 หรือ root เวลา
เปิดหลาย tier พร้อมกัน — รัน/แก้ Tier 9 จบในโฟลเดอร์นี้โฟลเดอร์เดียว ไม่ต้อง
พึ่ง Tier 8 หรือ root อีกต่อไป

**โค้ดที่เป็นของ Tier 9 เอง (ไม่ใช่แค่ copy)**: `multi_agent.py` —
ใช้ `OllamaNativeThinkOffClient` เป็น client มาตรฐานตั้งแต่ต้น (ฝังในโค้ดจริง
ไม่ใช่ monkey-patch จากภายนอกแบบที่ Tier 8's `thinking_off_diagnostic/` ทำ)
เพราะ thinking-off คือสถานะจริงที่จะใช้รันเปเปอร์ต่อจากนี้ ไม่ใช่แค่เครื่องมือ
วินิจฉัยชั่วคราวอีกต่อไป

⚠️ **ข้อควรระวังสำคัญที่สุด**: การฝัง thinking-off เป็นค่าเริ่มต้นใน Tier 9
**ไม่ได้แก้ปัญหา ceiling effect** (นั่นพิสูจน์แล้วว่าไม่ใช่สาเหตุ) แต่รับประกัน
ว่า thinking mode จะไม่ปนเข้ามาเป็น confound เพิ่มอีกในผลของ Tier 9 เท่านั้น —
เป้าหมายที่แท้จริงของ Tier 9 คือหา critical loss ใหม่ (ขั้นตอนที่ 1) แล้วรัด
เปรียบเทียบที่จุดนั้น (ขั้นตอนที่ 2)

---

## เตรียมสภาพแวดล้อม

ใช้ container/host เดียวกับที่รัน Tier 8 (docker-compose เดิม, Ollama บน host
เดียวกัน) ไม่ต้องติดตั้งอะไรเพิ่ม — `requests` (ใช้โดย `ollama_native_client.py`)
มีอยู่แล้วใน `docker/requirements.txt` เดิม

```bash
cd "AINTEC Project/docker"
docker compose exec agent-lab bash
cd /workspace/Tier9_CriticalThresholdRecalibration

# ทดสอบ offline ก่อนเสมอ (ไม่แตะ Ollama/tc จริง)
python3 -m pytest tests_tier9/ -q
```

ต้องเห็น `... passed` ทั้งหมดก่อนรันจริง — ชุดเทสนี้ยืนยันว่า
`OllamaNativeThinkOffClient` ถูกผูกเข้ากับ Planner/Worker/Reviewer/
GroupChatManager ครบทุกตัวจริง (ไม่ใช่แค่เขียนโค้ดไว้เฉยๆ) และ retry/timeout/
agent-blame/mitigation dispatch logic ที่สืบทอดจาก Tier 8 ยังถูกต้องเป๊ะ

---

## ขั้นตอนที่ 1 — `run_tier9_exploratory_scan.py` (วันที่ 1-2)

หา critical loss threshold ใหม่ สแกน `mitigation="none"` ที่ loss สูงกว่า 75%
(default: 80/85/90/95/99%) ด้วย n เล็ก (default 12 trials/ระดับ = 3 repeats ×
4 tasks) เพื่อประหยัดเวลา — pre-flight self-test ตรวจ native client ก่อนเสมอ

```bash
python3 run_tier9_exploratory_scan.py --dry-run
python3 run_tier9_exploratory_scan.py --resume
```

ปรับช่วง/จำนวนรอบได้ตามเวลาที่มี:
```bash
python3 run_tier9_exploratory_scan.py --loss-levels 85,90,95,99 --repeats 2 --resume
```

60 trials (default), ประมาณ 3-5 ชม. ผลอยู่ที่ `logs_tier9_exploratory_scan/`
สคริปต์พิมพ์ตารางสรุป completion rate ต่อระดับ + แนะนำจุดวิกฤตที่เจอ (จุดแรกที่
completion ตก ≤ 85% — เกณฑ์เดียวกับ falsification check ของข้อ 4 เดิมใน Tier 8)

⚠️ **ผลจากขั้นตอนนี้ (n เล็ก) ใช้แค่หาว่าจุดไหนน่าจะเป็นจุดวิกฤตเท่านั้น ไม่ใช่
ตัวเลขที่เอาไปเขียนลงเปเปอร์ตรงๆ** ต้องไปขั้นตอนที่ 2 ก่อนถึงจะได้ n=20 ที่พอ
สำหรับอ้างอิงจริง

**ถ้าสแกนแล้วยังไม่เจอจุดวิกฤตเลยแม้ที่ 99%** สคริปต์จะแนะนำ 3 ทางเลือก
(ขยายช่วงสูงขึ้นอีก / ลองแกนอื่นร่วมกับ loss เช่น delay สูงมาก / ยอมรับเป็น
ข้อค้นพบเชิง methodology แทน) — ต้องตัดสินใจร่วมกันก่อนไปขั้นตอนที่ 2

---

## ขั้นตอนที่ 2 — `run_tier9_critical_comparison.py` (วันที่ 3-5)

เปรียบเทียบ `none` vs `adaptive_timeout` vs `fixed_long_timeout` เต็มรูปแบบ
(n=20/arm) ที่ critical loss ใหม่จากขั้นตอนที่ 1 รันทั้ง 3 arms ในบล็อกเดียวกัน
(การเรียกสคริปต์ครั้งเดียว) เพื่อตัด run-block confound

```bash
# --critical-loss-pct ต้องมาจากผลขั้นตอนที่ 1 เท่านั้น ไม่มีค่า default
# (ผลจริงจากขั้นตอนที่ 1: จุดวิกฤตคือ 80% — ดูหัวข้อ "ผลที่ได้" ท้ายไฟล์นี้)
python3 run_tier9_critical_comparison.py --critical-loss-pct 80 --dry-run
python3 run_tier9_critical_comparison.py --critical-loss-pct 80 --resume
```

60 trials (3 arms × 20), ผลอยู่ที่ `logs_tier9_critical_comparison_<condition>/`
สคริปต์คำนวณ `FIXED_LONG_TIMEOUT` อัตโนมัติจากสูตร adaptive ตัวจริง (ไม่พิมพ์
เลขคงที่ 345 แบบ Tier 8 อีกต่อไป เพราะ critical loss เปลี่ยนไปแล้ว) และมี
falsification check ในตัว: ถ้า `none` arm ที่จุดนี้ยังได้ completion > 85%
(คือยังไม่ล้มเหลวจริง) จะเตือนทันทีและห้ามตีความ adaptive/fixed ต่อ — ต้องกลับ
ไปสแกนหาจุดที่สูงกว่านี้แทน

**วิธีอ่านผลตอนจบ** (พิมพ์อัตโนมัติ, เกณฑ์เดียวกับข้อ 2 เดิมของ Tier 8):

| ผล | แปลว่า |
|---|---|
| fixed ≈ adaptive (ทั้งคู่สูงกว่า control) | สิ่งที่ช่วยคือเวลา ไม่ใช่ condition-awareness |
| fixed < adaptive ชัดเจน | condition-awareness ช่วยจริง |
| fixed ≈ control | ผิดคาด ตรวจว่า timeout ถูกส่งถึง llm_config จริงก่อนตีความ |

---

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `ollama_native_client.py` | custom AutoGen model client คุย Ollama ผ่าน native `/api/chat` + `think:false` — **client มาตรฐานของ Tier 9** ไม่ใช่ diagnostic patch |
| `multi_agent.py` | สำเนาจาก Tier 8 ปรับให้ใช้ native client เป็นค่าเริ่มต้นตั้งแต่ต้น (ดูคอมเมนต์ "TIER9 CHANGE" ในไฟล์) และ import `tier9_evaluator.py` (ไม่ใช่ `experiment/evaluator.py` ที่ root อีกต่อไป) |
| `tier9_controller.py` | สำเนา standalone ของ Tier 8's `controller.py` (logic/โค้ดเหมือนเป๊ะทุกบรรทัด ต่างแค่ docstring header ที่บอกที่มา) — ควบคุม netem/tc |
| `tier9_logger.py` | สำเนา standalone ของ Tier 8's `logger.py` (logic/โค้ดเหมือนเป๊ะทุกบรรทัด ต่างแค่ docstring header ที่บอกที่มา) — เขียน log ผลการทดลอง |
| `tier9_checkpoint_utils.py` | สำเนา standalone ของ Tier 8's `checkpoint_utils.py` (byte-identical ทุกตัวอักษร ไม่แก้แม้แต่ docstring) — รองรับ `--resume` |
| `tier9_tasks.py` | สำเนา standalone ของ root's `experiment/tasks.py` (byte-identical ทุกตัวอักษร ไม่แก้แม้แต่ docstring) — โจทย์ 4 งาน + ground truth |
| `tier9_evaluator.py` | สำเนาของ root's `experiment/evaluator.py` แก้ import บรรทัดเดียวให้ชี้ `tier9_tasks.py` แทน `experiment.tasks` |
| `run_tier9_exploratory_scan.py` | ขั้นตอนที่ 1 — หา critical loss threshold ใหม่ |
| `run_tier9_critical_comparison.py` | ขั้นตอนที่ 2 — เปรียบเทียบ mitigation เต็มรูปแบบที่จุดที่พบ |
| `tests_tier9/` | offline test suite (pytest, ไม่แตะ Ollama/tc จริงเลย) รวมเทสใหม่ยืนยันการผูก native client |

**Tier 9 เป็น standalone เต็มรูปแบบ**: ไม่ import จาก `Tier8_EnsureScopeClosure/`
หรือ `experiment/` ที่ root อีกต่อไป — ไฟล์ `tier9_*.py` ทั้ง 5 ตัวเป็นสำเนาของ
ตัวเอง แก้ไฟล์ใน Tier 8 หรือ root จะ**ไม่**มีผลกับ Tier 9 เลย (เจตนา — กันไม่ให้
งานเปเปอร์ที่กำลังจะจบพังเพราะมีคนแก้ Tier 8 ทีหลังโดยไม่ตั้งใจ) โฟลเดอร์นี้
โฟลเดอร์เดียวพอสำหรับรัน Tier 9 ทั้งหมด ไม่ต้องเปิด Tier 8 หรือ root ประกอบเลย

---

## ผลที่ได้

✅ รันเสร็จแล้วทั้ง 2 ขั้นตอน — 120/120 trials, 0 ไฟล์เสีย

**ขั้นตอนที่ 1 — Exploratory scan (n=12/ระดับ):**

| Configured loss | Completion |
|---|---|
| 80% | 3/12 (25%) |
| 85% | 1/12 (8%) |
| 90% | 0/12 (0%) |
| 95% | 0/12 (0%) |
| 99% | 0/12 (0%) |

**80% คือจุดวิกฤตที่นำไปเปรียบเทียบต่อในขั้นตอนที่ 2** (ไม่ใช่ "ช่วง 80-85%" — 85% เป็นเพียงจุด
หนึ่งใน scan ที่ยืนยันว่า completion ยังตกต่อเนื่องเมื่อ loss สูงขึ้น)

**ขั้นตอนที่ 2 — Critical comparison ที่ 80% loss (n=20/arm):**

| เงื่อนไข | Completion | เทียบ control |
|---|---|---|
| control (`none`) | 5/20 (25%) | — |
| adaptive_timeout | 1/20 (5%) | p = 0.182 (ไม่มีนัยสำคัญ) |
| fixed_long_timeout | 13/20 (65%) | **p = 0.0248** (มีนัยสำคัญ, two-sided Fisher's exact) |
| adaptive vs. fixed | — | **p < 0.001** |

**ข้อค้นพบหลัก: fixed timeout ที่ยาวคงที่ให้ผล completion ดีกว่า adaptive timeout scaling
อย่างมีนัยสำคัญ ที่จุดวิกฤตของสภาพแวดล้อมปัจจุบัน — เป็นลำดับผลลัพธ์ที่ตรงข้ามกับ Tier 5 เดิม**
(ที่ 75% loss ในช่วงเวลาเดิม adaptive_timeout ดีกว่า control อย่างมีนัยสำคัญ) สาเหตุส่วนหนึ่งที่พบ:
ที่ 80% loss ความล้มเหลวจำนวนมากเป็น connection-establishment failure (`ConnectionError`) ไม่ใช่
call ที่ช้าเกินจน timeout — `ConnectionError` เกิด 13 ครั้งใน control, 20 ครั้งใน adaptive_timeout
(มากที่สุด), 6 ครั้งใน fixed_long_timeout; ส่วน `timeout` event (นับแยกต่างหาก) เกิด 36 ครั้งใน
control, 39 ครั้งใน adaptive_timeout, 24 ครั้งใน fixed_long_timeout — ซึ่งเป็นรูปแบบความล้มเหลวที่
timeout ค่าไหนก็แก้ไม่ได้ (นอกจากนี้ยังมีบั๊กใน client wiring ของ Tier นี้เองที่ทำให้ทั้ง 3 arm ใช้
timeout จริงราว 120 วินาทีเท่ากันหมด แทนที่จะเป็นค่าที่ตั้งใจให้ต่างกัน — รายละเอียดที่
`NetImpact_22_...` §2)

**ข้อจำกัดบังคับที่ต้องติดไปด้วยเสมอ**: ทั้ง 3 arm รันเป็น 3 block ต่อเนื่องกัน ไม่ได้สลับลำดับ
(เหมือน Tier 5 เดิม) **ไม่ได้เขียนทับผลของ Tier 5**: ผล 75%-loss เดิมยังถูกต้องสำหรับช่วงเวลาที่วัด
— นี่คือหลักฐานล่าสุดที่ดีที่สุดสำหรับสภาพแวดล้อมปัจจุบัน ไม่ใช่ตัวแทนที่มาแทนผลเดิม รายละเอียด
สถิติ/การตีความ/wording ที่อนุมัติให้ใช้ในเปเปอร์เต็มรูปแบบอยู่ที่
`Paper/NetImpact.md/Current/NetImpact_22_Tier9_Critical_Threshold_Recalibration.md`
