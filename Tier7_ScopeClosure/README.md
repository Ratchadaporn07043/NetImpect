# Tier 7 — Scope Closure

**สถานะ (อัปเดตล่าสุด — เช็คจาก raw logs จริง ณ ปัจจุบัน):** 🔴 7A รันแล้ว 60/60 trials แต่
**ผลใช้ไม่ได้** — พบบั๊กจริงตอนตรวจ raw logs (ดู "⚠️ บั๊กที่พบใน 7A" ด้านล่าง ก่อนอ่านหรืออ้างอิงผลใดๆ)
· 🔴 7B **รันจบแล้วจริง 80/80 trials แต่ผลใช้ไม่ได้เช่นกัน** — ไม่ผ่าน falsification check ของตัวเอง
(baseline completion แค่ 70% ไม่ใช่ ~100% ตามที่ควรจะเป็น — ดู "⚠️ ผลจาก 7B" ด้านล่าง ก่อนอ่านหรือ
อ้างอิงผลใดๆ) · 7C เสร็จแล้วสำหรับข้อมูลย้อนหลัง แต่โค้ด logging ใหม่มีบั๊กเดียวกับ
7A ต้องแก้ก่อนใช้กับ run ใหม่

## ⚠️ บั๊กที่พบใน 7A — ต้องแก้ก่อนอ่านผลหรือรันซ้ำ

ทุก trial ที่ fail ทั้ง 8 ตัวใน `logs_tier7_fixed_fixed_long_timeout/` fail ด้วย error เดียวกัน:

```
ExperimentLogger.log_timeout() got an unexpected keyword argument 'agent'
ExperimentLogger.log_error() got an unexpected keyword argument 'agent'
```

สาเหตุ: `multi_agent.py` ในโฟลเดอร์นี้เรียก `logger.log_timeout(..., agent=blamed_agent)` และ
`logger.log_error(..., agent=blamed_agent)` ตามที่ตั้งใจไว้ใน 7C แต่ `logger.py` ที่ project root
(ไฟล์ที่ `run_tier7_fixed_timeout.py` import จริงตอนรัน — ตรวจ `sys.path` แล้วยืนยัน) **ไม่มีพารามิเตอร์
`agent` เลย** ทั้งที่ตารางด้านล่าง (หัวข้อ 7C) เขียนไว้ว่าเพิ่มแล้ว การเพิ่มพารามิเตอร์ที่ root
`logger.py` ไม่ได้ถูกทำจริง

ผลที่ตามมาร้ายแรงกว่าที่ดูตอนแรก: `logger.log_timeout(...)`/`log_error(...)` ถูกเรียก **นอก**
try/except ของ attempt นั้นใน `run_multi_agent_task` — เมื่อมันโยน `TypeError` เอง exception จะหลุดขึ้นไป
ถึง `try/except` ชั้นนอกสุดใน `run_single_trial` (ของ `run_tier7_fixed_timeout.py`) ทันที กลายเป็น
`fatal_error`, `success=false`, `rounds=0` **โดยไม่มีการ retry เลยแม้แต่ครั้งเดียว** ทั้งที่
`MAX_RETRIES=2` ควรให้โอกาสอีก 2 ครั้ง

**สรุป:** ทุก trial ที่เจอ error/timeout จริงในการรันนี้ fail ทันทีเพราะโค้ดที่ควรบันทึกและ retry
พังก่อน ไม่ใช่เพราะโมเดล/เครือข่ายไม่ฟื้นตัวภายใน retry budget ตัวเลข 20/20, 19/20, 13/20 ที่ 65/70/75%
loss **จึงเทียบกับ control หรือ adaptive arm เดิมไม่ได้เลย** — ไม่ใช่ apples-to-apples เพราะ arm นี้
retry ไม่ทำงาน ในขณะที่ control/adaptive ของ Tier 5 retry ทำงานปกติ

**ก่อนรันซ้ำ:** ต้องเพิ่มพารามิเตอร์ `agent=None` ให้ `log_error`/`log_timeout`/`log_retry` ที่ root
`logger.py` จริงๆ (ไม่ใช่แค่เขียนในเอกสารว่าเพิ่มแล้ว) แล้วรัน `pytest` ยืนยันก่อน แล้วจึงรัน
`run_tier7_fixed_timeout.py --resume` ใหม่ทั้งหมด (ลบ checkpoint เดิมทิ้งก่อน มิฉะนั้นจะ skip trial ที่
"เสร็จ" ไปแล้วทั้งที่ผลใช้ไม่ได้)

เอกสารฉบับเต็มของสิ่งที่พบ: `Paper/NetImpact.md/Current/NetImpact_18_Implementation_Verification_Addendum.md` §10D และ `Paper/NetImpact.md/Current/NetImpact_20_Tier7_Scope_Closure.md`

---

## ⚠️ ผลจาก 7B — รันจบแล้ว 80/80 trials แต่ไม่ผ่าน falsification check ของตัวเอง

`run_tier7_ingress.py` รันจบครบทั้ง 80 trials จริง (4 scenario × 4 task type × 5 run) และทุก trial
ยืนยันแล้วว่า field `impairment_direction` = `"both"` ครบทั้ง 80/80 — แปลว่า IFB/bidirectional shaping
ถูก wire เข้าจริง ไม่ใช่แค่ชื่อโฟลเดอร์ ตรงตามที่ README เดิมเขียนไว้ว่าให้ตรวจ

**แต่ตัวเลขที่ได้ไม่ผ่านเงื่อนไขที่ README ข้อ "4 จุดที่เลือก และเหตุผล" ตั้งไว้เอง**
("จุด 1 และ 4 คือการตรวจสอบตัวการทดลองเอง ถ้าสองจุดนี้ผิดคาด ห้ามตีความจุด 2 และ 3 เลย"):

| scenario | บทบาท | completion ที่วัดได้ | ควรเป็น |
|---|---|---|---|
| `t7in_baseline` (ไม่มี impairment) | falsification check | **14/20 (70%)** | ~100% |
| `t7in_bw50` | จุดที่ egress-only เคยให้ null | 10/20 (50%) | — |
| `t7in_delay1000` | จุดที่ egress-only เคยให้ null | 7/20 (35%) | — |
| `t7in_loss75` (positive control) | ต้องเห็น degradation | 0/20 (0%) | ต่ำกว่า baseline ชัดเจน |

baseline ควรได้ใกล้ 100% เพราะไม่มี impairment ใดๆ เลย แต่ได้แค่ 70% — ตรวจ error log ของ trial ที่ fail
แล้วพบว่าเป็น `OpenAI API call timed out` จริง (ไม่ใช่ `TypeError`/บั๊ก logging แบบ 7A) เกิดที่ Worker หลัง
retry 2 ครั้งแล้วยังไม่ผ่าน — **ไม่ใช่บั๊กโค้ดแบบ 7A แต่เป็นสัญญาณว่าตัว IFB/bidirectional redirect เอง
(หรือสภาพแวดล้อมตอนรัน) ทำให้เกิด timeout จริงแม้ไม่มี impairment ใดๆ ถูก configure เลย**

**สรุป: ตาม logic ที่ README ข้อนี้กำหนดไว้เอง ห้ามตีความตัวเลข `t7in_bw50` และ `t7in_delay1000`
ว่าเป็นผลจาก bidirectional shaping** เพราะ baseline (จุดควบคุม) เองก็ fail ไปแล้ว 30% ทั้งที่ไม่มี
impairment เลย ตัวเลข 50%/35% ที่เห็นอาจมาจาก IFB overhead/instability ปนอยู่ ไม่ใช่จากค่า bandwidth/delay
ที่ตั้งไว้ล้วนๆ — 7B จึง**ยังไม่ปิดช่องโหว่ egress-only ได้จริง** เหมือนที่ตั้งใจไว้ ต้องหาสาเหตุที่ทำให้
baseline fail ก่อน (สงสัย IFB redirect overhead / เครื่องที่รันตอนนั้นไม่เสถียร) แล้วรันใหม่ให้ baseline
ผ่านก่อนถึงจะตีความจุดอื่นได้

---

Tier นี้ปิดช่องโหว่เชิงระเบียบวิธี 3 จุดที่การตรวจสอบ implementation พบ และเป็นจุดที่ reviewer
สาย networking มีโอกาสถามสูงที่สุด รายละเอียดเต็มของแต่ละช่องโหว่อยู่ที่
`Paper/NetImpact.md/Current/NetImpact_18_Implementation_Verification_Addendum.md`

| ส่วน | ปิดช่องโหว่อะไร | trials | เวลาโดยประมาณ | สถานะ |
|---|---|---|---|---|
| **7A** `run_tier7_fixed_timeout.py` | condition-awareness ยังไม่ถูกแยกออกจาก "แค่ให้เวลามากขึ้น" | 60 | ~9 ชม. | 🔴 รันจบแล้ว แต่ผลใช้ไม่ได้ (บั๊ก logging) |
| **7B** `run_tier7_ingress.py` | impairment เป็น egress-only มาตลอด | 80 | ~8 ชม. | 🔴 รันจบแล้ว แต่ผลใช้ไม่ได้ (falsification check ไม่ผ่าน) |
| **7C** *(ไม่ต้องรัน)* | timeout ไม่มี agent attribution | 0 | เสร็จแล้ว | ✅ ใช้ได้ |

---

## ก่อนรันอะไรก็ตาม

```bash
# 1. โมเดลต้องพร้อม
ollama serve
ollama pull qwen3:8b

# 2. เข้า container
cd docker && docker compose up -d --build && docker compose exec agent-lab bash

# 3. เทสต์ offline ต้องผ่านครบก่อน (ไม่แตะ Ollama/tc เลย)
python3 -m pytest tests_extended/ -q
```

---

## 7A — fixed-long-timeout arm

### คำถามที่ตอบ

Tier 5 พบว่า condition-aware timeout scaling เพิ่ม observed completion ที่ 75% configured loss
จาก **14/20 เป็น 20/20** (Fisher's exact test, p = 0.0202; risk difference +30.0 pp, 95% CI +7.7
ถึง +51.9) แต่ไม่เคยเทียบกับ timeout ยาวคงที่ จึงแยกไม่ออกว่าสิ่งที่ช่วยคือ

- **(ก)** การปรับ timeout ตามสภาพเครือข่าย — *condition-awareness*
- **(ข)** แค่การให้เวลามากขึ้นเฉยๆ — *more time*

arm นี้ตั้ง `timeout = 345 s` คงที่ทุก scenario ซึ่งคือค่าที่สูตร adaptive คืนพอดีที่จุดวิกฤต
(`120 + int(75 × 3) = 345`) ทั้งสอง arm จึงได้เวลาเท่ากันเป๊ะที่ loss=75% และต่างกันเฉพาะที่
ระดับ loss อื่น

**การอ่านผล:**

| ผลที่ loss=75% | แปลว่า |
|---|---|
| fixed ≈ adaptive (ทั้งคู่สูงกว่า control) | สิ่งที่ช่วยคือ **(ข)** เวลา — ต้องเขียนใหม่ว่า "a longer timeout budget increased completion" และตัดคำว่า condition-aware ออกจาก contribution |
| fixed < adaptive ชัดเจน | สิ่งที่ช่วยคือ **(ก)** condition-awareness จริง — contribution เดิมแข็งขึ้นมาก |
| fixed ≈ control | ผิดคาด ตรวจว่า `FIXED_LONG_TIMEOUT` ถูกส่งถึง `llm_config` จริงไหมก่อนตีความ |

### รัน

```bash
python3 Tier7_ScopeClosure/run_tier7_fixed_timeout.py --dry-run     # ตรวจก่อน
python3 Tier7_ScopeClosure/run_tier7_fixed_timeout.py --resume      # รันจริง ~9 ชม.
```

**ตัวเลือกที่ตัด confound ได้จริง (แต่ใช้เวลา ~28 ชม.):**

```bash
python3 Tier7_ScopeClosure/run_tier7_fixed_timeout.py --resume --include-reference-arms
```

รัน `none` / `adaptive_timeout` / `fixed_long_timeout` ใหม่ทั้งหมดในบล็อกเดียวกัน ทำให้ทั้งสาม arm
อยู่ในช่วงเวลาเดียวกัน → **ตัด run-block confound ออกได้** ซึ่งเป็นข้อจำกัดที่ Tier 5 มีอยู่และ
ถูกบันทึกไว้ใน threats-to-validity แล้ว ถ้ามีเวลาคืนเดียวว่างพอ อันนี้คุ้มกว่ามาก

> ⚠️ ถ้ารันแบบสั้น (60 trials) การเทียบกับ Tier 5 จะยังมี run-block confound ปนอยู่ ต้องเขียนใน
> Methods ตามจริง ห้ามเทียบตรงๆ แล้วสรุปเป็นเหตุเป็นผล

---

## 7B — bidirectional (ingress + egress) subset

> ✅ **สคริปต์นี้รันจบไปแล้ว** (80/80 trials, log อยู่ที่ `logs_tier7_7B_ingress/`) **แต่ผลใช้ไม่ได้**
> เพราะไม่ผ่าน falsification check ของตัวเอง — อ่านรายละเอียดที่หัวข้อ "⚠️ ผลจาก 7B" ด้านบนก่อน
> ถ้าจะรันใหม่ให้ลบ checkpoint เดิมทิ้งก่อน (`logs_tier7_7B_ingress/_checkpoint/`) มิฉะนั้นจะ skip
> trial ที่ "เสร็จ" ไปแล้วทั้งที่ผลใช้ไม่ได้ เหมือนที่เกิดกับ 7A

### คำถามที่ตอบ

qdisc ที่ `root` ควบคุม **egress เท่านั้น** ดังนั้น null result 2 ข้อของโปรเจกต์มีเงื่อนไขแฝง:

- bandwidth cap 50 kbit/s ไม่กระทบ completion → แต่ cap เฉพาะ **request ที่เล็ก** ส่วน response
  ที่ใหญ่กว่ามากเข้ามาโดยไม่ถูก shape
- delay 3,000 ms ไม่กระทบ completion → แต่บวกเฉพาะแพ็กเก็ตขาออก ไม่ได้บวกกับ response ที่ stream กลับ

arm นี้ redirect ingress ไป IFB แล้ว shape ด้วยค่าเดียวกับ egress

### 4 จุดที่เลือก และเหตุผล

| scenario | ค่า | บทบาท |
|---|---|---|
| `t7in_baseline` | ไม่มี impairment | **falsification check** — IFB path เองต้องไม่ทำให้ completion ตก |
| `t7in_bw50` | bandwidth 50 kbit/s | จุดที่ egress-only ให้ null |
| `t7in_delay1000` | delay 1,000 ms | จุดที่ egress-only ให้ null |
| `t7in_loss75` | loss 75% | **positive control** — ต้องเห็น degradation ถ้า setup ทำงานจริง |

> จุด 1 และ 4 คือการตรวจสอบตัวการทดลองเอง **ถ้าสองจุดนี้ผิดคาด ห้ามตีความจุด 2 และ 3 เลย**

### ข้อกำหนดของสภาพแวดล้อม

ต้องโหลด kernel module `ifb` **บน host** ก่อน (container โหลดเองไม่ได้แม้มี NET_ADMIN):

```bash
sudo modprobe ifb numifbs=0
```

### รัน (ซ้ำ — เพราะรอบแรกผลใช้ไม่ได้)

```bash
python3 Tier7_ScopeClosure/run_tier7_ingress.py --probe-only   # ตรวจว่าสภาพแวดล้อมพร้อม
python3 Tier7_ScopeClosure/run_tier7_ingress.py --dry-run
python3 Tier7_ScopeClosure/run_tier7_ingress.py --resume       # ~8 ชม.
```

สคริปต์เรียก `probe_ingress_support()` ก่อนเสมอและหยุดทันทีพร้อมบอกวิธีแก้ถ้าไม่ผ่าน — ออกแบบมา
เพื่อไม่ให้ไปพบตอนตี 3 ว่ารันทั้งคืนแล้ว ingress ไม่ได้ถูก shape จริง

ทุก trial บันทึกคำสั่ง `tc` ทั้งหมด (รวมสาขา ingress) และ field `impairment_direction` ลงไฟล์ log
จึงตรวจย้อนหลังได้ว่า trial นั้นถูก shape สองทางจริง ไม่ต้องเชื่อชื่อโฟลเดอร์

### ถ้ารันไม่ได้

ให้รายงานในเปเปอร์ตามจริงว่าเป็นการวัดแบบ **egress-only** และเก็บ bidirectional shaping ไว้เป็น
future work — **ห้ามอ้างว่าทำแล้ว** ถ้อยคำที่ต้องใช้อยู่ใน File 18 §1.3

---

## 7C — agent attribution (เสร็จแล้ว ไม่ต้องรัน)

เดิม error log ไม่มี field บอกว่า LLM call ของ agent ตัวไหน timeout ทำให้คำอธิบายผลลบของ context
caching เป็นเพียงสมมติฐาน

**ทำไปแล้ว 2 อย่าง:**

1. **`logger.py`** รับพารามิเตอร์ `agent` ใน `log_error` / `log_timeout` / `log_retry` แล้ว
   (backward compatible — เรียกแบบเดิมได้ ได้ `agent=None`) และ `Tier7_ScopeClosure/multi_agent.py`
   อนุมาน agent จาก transcript แล้วส่งเข้า logger — run ใหม่ทุกครั้งจะมีข้อมูลนี้ติดมาเอง

2. **กู้ย้อนหลังจาก log เดิมสำเร็จแล้ว** โดยไม่ต้องรันใหม่:

   ```bash
   cd Analysis_เบื้องต้น/scripts
   python3 recover_timeout_attribution.py \
       --log-dir ../../Tier5_Mitigation/logs_tier5_none \
       --log-dir ../../Tier5_Mitigation/logs_tier5_context_cache \
       --log-dir ../../Tier5_Mitigation/logs_tier5_adaptive_timeout \
       --csv ../data/timeout_attribution.csv
   ```

   **ผลจาก 660 trials, 38 timeout events:** Worker 19 (50.0%) · Reviewer 18 (47.4%) · Planner 1 (2.6%)

### แต่ตัวเลขนี้ต้องอ่านให้ถูก

Planner ได้ 2.6% **ไม่ใช่เพราะ Planner เร็วหรือทน** แต่เพราะ `planner.initiate_chat()` ทำให้ข้อความ
แรกที่ติดป้ายว่า Planner คือ **seed message ที่เป็นตัว prompt เอง ไม่ใช่ผลลัพธ์จากโมเดล** จากนั้น
round-robin ไป Worker ทันที → ใน **95.8%** ของ trial ที่ตรวจ **Planner ไม่ได้เรียก LLM เลยสักครั้ง**
1 trial ที่สำเร็จมี **2 LLM call** ไม่ใช่ 3

ผลต่อเนื่อง: `cached_plan` ที่ context caching เก็บไว้คือตัว prompt เดิม ไม่ใช่แผน ดังนั้น context
caching **ไม่ได้ตัด LLM call ออกเลย** — นี่คือเหตุผลจริงที่ผลออกมาไม่มีนัยสำคัญ ไม่ใช่ "timeout ไป
กระจุกที่ Worker/Reviewer" ตามที่เคยเขียนไว้

**พฤติกรรมนี้คงไว้ตามเดิมโดยเจตนา** เพื่อให้ Tier 7 เทียบกับข้อมูลเดิม 5,300 trials ได้ และรายงาน
ระบบตามที่เป็นจริงในเปเปอร์ แทนการเปลี่ยนระบบกลางคันแล้วต้องรันใหม่ทั้งหมด

---

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `multi_agent.py` | สำเนาสะสมของ Tier5/Tier6 + `fixed_long_timeout` + agent attribution |
| `run_tier7_fixed_timeout.py` | 7A |
| `run_tier7_ingress.py` | 7B |
| `README.md` | ไฟล์นี้ |

โค้ดที่แก้นอกโฟลเดอร์นี้ (additive ทั้งหมด ไม่กระทบพฤติกรรมเดิม):

- `logger.py` — เพิ่มพารามิเตอร์ `agent`
- `experiment/controller.py` — เพิ่ม `direction="both"` + `probe_ingress_support()` (ค่าเริ่มต้นยังเป็น `egress`)
- `Analysis_เบื้องต้น/scripts/recover_timeout_attribution.py` — สคริปต์กู้ย้อนหลัง

## หลังรันเสร็จ

```bash
cd Analysis_เบื้องต้น/scripts
python3 parse_logs.py --log-dir "../../Tier7_ScopeClosure/logs_tier7_fixed_fixed_long_timeout" \
                      --out ../data/tier7_fixed_master.csv
python3 parse_logs.py --log-dir "../../Tier7_ScopeClosure/logs_tier7_7B_ingress" \
                      --out ../data/tier7_ingress_master.csv
```

> หมายเหตุ: path ของ log 7B คือ `logs_tier7_7B_ingress/` (ไม่ใช่ `logs_tier7_ingress/` ตามที่เคยเขียนไว้
> เดิม — แก้ path ในคำสั่งด้านบนแล้ว)

แล้วอัปเดต `Paper/NetImpact.md/Current/NetImpact_18_...` §11 (ตารางสถิติที่มีอำนาจสูงสุด) และ
`NetImpact_05_...` §5.1 ให้ตรงกับผลจริง — **อย่าลืมว่า claim strength ถูกล็อคไว้แล้วใน File 17/18
ผลใหม่ต้องเขียนตามกฎเดิม ไม่ใช่ตั้งกฎใหม่ให้เข้ากับผล**

**สถานะล่าสุดของ 7A/7B (อัปเดตแล้ว — ตรวจสอบกับ `Paper/` แล้วว่าตรงกัน):** ทั้ง 7A (60/60, บั๊ก logging)
และ 7B (80/80, ไม่ผ่าน falsification check — baseline 70% แทนที่จะเป็น ~100%) รันจบแล้วทั้งคู่แต่ใช้ไม่ได้
ตามที่อธิบายไว้ในหัวข้อด้านบน — `NetImpact_20_Tier7_Scope_Closure.md` เขียนสถานะทั้งคู่ถูกต้องแล้วว่า
"executed, invalid" (ไม่ใช่ "code prepared, not executed" อีกต่อไป) ไม่มีอะไรค้างให้แก้ในจุดนี้ ทั้งสอง
ช่องว่างถูกปิดสำเร็จในภายหลังโดย Tier 9 (สำหรับ 7A ที่ระดับ loss 80% ของสภาพแวดล้อมช่วงหลัง) และ Tier 8
item 4 (สำหรับ 7B — ดู `Docs/NetImpact_Summary_All_Tiers.md` หัวข้อ Tier 7)
