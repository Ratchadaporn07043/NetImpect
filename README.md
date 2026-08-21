# NetImpact

ทดลองผลกระทบของ network impairment ต่อระบบ Multi-Agent (Planner -> Worker -> Reviewer)
โดยใช้ Docker + `tc netem` เพื่อ inject delay/loss/jitter แล้วเก็บผลเป็น JSON log สำหรับวิเคราะห์เชิงสถิติ

## สิ่งที่โปรเจกต์นี้ทำ

- รัน multi-agent workflow บนโมเดลผ่าน Ollama (OpenAI-compatible API)
- จำลองสภาพ network หลายรูปแบบ (factorial, combined, three-day bounded design)
- เก็บ telemetry ราย trial เช่น success, rounds, retries, timeout, quality score, token, elapsed time
- วิเคราะห์ผลหลังรันด้วยสคริปต์แยก phase และสรุป guideline

## โครงสร้างโปรเจกต์ (แบ่งหมวดหมู่)

### 1. Core library (ราก โปรเจกต์)
- `multi_agent.py`:
  - นิยาม Agent 3 ตัว (Planner / Worker / Reviewer)
  - มี early termination เมื่อ Reviewer ตอบ `APPROVED`
  - รองรับ retry/timeout และบันทึก message timestamp
- `logger.py`:
  - จัดเก็บผล trial เป็น JSON
  - รวม message log, error/retry/timeout, resource snapshot และ outcome

  > ไฟล์ทั้งสองนี้อยู่ที่ root โดยตั้งใจ เพราะ `experiment/`, `Tier2_แกนใหม่/`, `Tier5_Mitigation/`,
  > `tests_extended/` import แบบ relative path (`from multi_agent import ...`) โดยอ้างอิงตำแหน่งนี้
  > ห้ามย้ายไฟล์นี้โดยไม่แก้ import ในทุกจุดที่กล่าวถึง

### 2. Core experiment engine — `experiment/`
- `run_experiment.py`: entry point (`--quick`, `--pilot`, `--three-day`, `--dry-run`, `--resume`)
- `scenarios.py`: factorial / tournament / combined / three-day bounded design
- `tasks.py`: benchmark task prompts + rubric สำหรับ ground-truth evaluation
- `evaluator.py`: ประเมินคำตอบแบบ heuristic / llm / both
- `evaluate_logs.py`: post-hoc evaluation สำหรับ log ที่รันเสร็จแล้ว
- `analyze_pilot.py`: วิเคราะห์ความพร้อมก่อน full run
- `analyze_guidelines.py`: สร้าง practical threshold/guideline จากผล three-day/full

### 3. Infrastructure
- `docker/`: Docker image + compose สำหรับรันใน container ที่มีสิทธิ์ `NET_ADMIN`
  (mount ทั้งโฟลเดอร์โปรเจกต์เป็น `/workspace` — Tier1-5/logs ใหม่มองเห็นอัตโนมัติ)
- `scripts/`: helper scripts (`test_conn.py` เช็คการเชื่อมต่อ Ollama, `test_netem.sh` เช็ค `tc netem`)

### 4. ข้อมูลผลการทดลอง (raw + summary)
- `logs_three_day/`: JSON log ดิบรายรัน ของชุดทดลอง three-day (1,544 trials)
- `logs_tierN/`: JSON log ดิบของแต่ละ Tier — อยู่ข้างในโฟลเดอร์ของ Tier นั้นๆ ไม่ใช่ที่ root (เช่น `Tier1_เจาะจุดในแกนที่มีอยู่/logs_tier1/`, `Tier5_Mitigation/logs_tier5_none/`, `Tier8_EnsureScopeClosure/results_completed/`, `Tier9_CriticalThresholdRecalibration/logs_tier9_*` ฯลฯ) — **Tier1-9 รันเสร็จแล้วทั้งหมด** (ดูหมวด 6 ด้านล่างสำหรับสถานะละเอียดของแต่ละ Tier)
- `results/`: ตาราง CSV สรุปผลระดับ phase/task/main-effect/combined ที่ export มาจาก log ดิบ
  (`results_three_day_combined.csv`, `results_three_day_main_effect.csv`,
  `results_three_day_phase.csv`, `results_three_day_task.csv`)

### 5. การวิเคราะห์ผลเบื้องต้น — `Analysis_เบื้องต้น/`
โครงสร้างย่อย: `scripts/` (โค้ดที่รันเพื่อสร้างผลลัพธ์ — `parse_logs.py`, `generate_charts.py`, `generate_charts_tier1.py`), `data/` (CSV ที่ parse แล้ว — `netimpact_master.csv`, `tier1_master.csv`), `charts/three_day/` และ `charts/tier1/` (ภาพกราฟที่ได้) — ไฟล์ตีความผล (`findings.md`) และภาพรวมโฟลเดอร์ (`README.md`) ย้ายไปรวมกับเอกสารอธิบายงานทั้งหมดที่ `Paper/` แล้ว (ดู `Paper/NetImpact.md/Archive_Legacy/NetImpact_14_Analysis_Folder_Overview.md` และ `Paper/NetImpact.md/Archive_Legacy/NetImpact_15_Findings_List.md`)

### 6. การทดลองส่วนขยาย — `Tier1_เจาะจุดในแกนที่มีอยู่/` ถึง `Tier9_CriticalThresholdRecalibration/`
- ✅ Tier1: จุดเพิ่มเติมบนแกนเดิม (delay/loss/jitter ละเอียดขึ้น) — **รันเสร็จแล้ว** (320 trials, แคบ degradation region ของ loss จาก 50-75% เดิมเหลือ 70-75% — ภูมิภาคนี้จำเพาะกับช่วงเวลาที่วัดครั้งนี้เท่านั้น ดู Tier8/9)
- ✅ Tier2: แกนใหม่ (bandwidth throttling, multi-round strict reviewer) — **รันเสร็จแล้ว** (272 trials, พบ network effect จริงในโหมด multi-round — ผลนี้เป็น exploratory, ไม่ reproduce ในการควบคุมภายหลัง ดู Tier6)
- ✅ Tier3: โครงสร้างพื้นฐาน (LLM-judge คู่, GPU logging) — **dual-judge ส่วนรันเสร็จแล้ว** (200-sample, agreement ต่ำมากเพราะ judge bias — ยึด heuristic ต่อไป), GPU logging ยังไม่มี log ใหม่ให้ตรวจ
- ✅ Tier4: Replication (temporal + cross-model) — **รันเสร็จแล้ว** (2,384 trials, ผลหลัก reproduce ได้ข้ามเวลา แต่พบว่า heuristic evaluator ไม่ transfer ข้ามโมเดล agent)
- ✅ Tier5: Mitigation (adaptive timeout + context caching) — **รันเสร็จแล้ว** (660 trials, adaptive_timeout ให้ completion สูงขึ้นอย่างมีนัยสำคัญที่ loss=75% ของช่วงเวลาที่วัดครั้งนี้ 14/20→20/20, p=0.020, context_cache ไม่มีนัยสำคัญ — ผลนี้จำเพาะกับช่วงเวลาที่วัด ดู Tier9 ที่พบผลตรงข้ามที่จุดวิกฤตของช่วงเวลาถัดมา)
- ✅ Tier6: Mitigation × Multi-Round (optional stretch) — **รันเสร็จแล้ว** (120 trials, 0 ไฟล์เสีย — ทดสอบว่า adaptive_timeout/context_cache ช่วยแก้ปัญหา multi-round ที่ moderate_delay ซึ่ง Tier2 พบว่าแย่สุดได้ไหม: ไม่มีคู่เปรียบเทียบไหนถึงนัยสำคัญทางสถิติ และการตรวจสอบ falsification ล้มเหลว — arm ที่ไม่มีมาตรการทำงานอยู่เลยที่ scenario ไม่มี impairment ก็ยังให้ completion ต่างกัน 15-20pp เอง แปลว่าดีไซน์นี้แยกผลของ mitigation จากความผันแปรระหว่าง block ไม่ได้)
- ✅ Tier7: ความพยายามปิดช่องว่าง 3 จุด (fixed-long-timeout arm, bidirectional shaping, agent attribution ใน log) — **รันครบทั้ง 3 ส่วนแล้ว** (7A 60/60, 7B 80/80, 7C ตรวจย้อนหลัง 38 เหตุการณ์) แต่ 7A และ 7B ใช้ไม่ได้จากบั๊ก logging/falsification check ล้มเหลวตามลำดับ — ทั้งสองช่องว่างถูกปิดสำเร็จในภายหลังโดย Tier 9 (7A) และ Tier 8 item 4 (7B); 7C สำเร็จบางส่วน
- ✅ Tier8: ปิดช่องว่างของ scope 5 จุด + diagnostic เพิ่ม 80 trials — **รันเสร็จแล้วทั้งหมด** (1,020+80=1,100 trials — ยืนยันจากการนับไฟล์ log ดิบจริง: item1=80, item2=180 (รวม reference arms), item3=660, item4=80, item5=20) ปิดช่องว่าง achieved-path measurement, fixed-timeout arm, randomized-order mitigation comparison, bidirectional (ingress+egress) shaping, และ jitter delay-floor control สำเร็จบางส่วน/เต็มรูปแบบตามแต่ละข้อ — และค้นพบข้อค้นพบสำคัญที่ไม่ได้วางแผนไว้: **75% configured loss ไม่ทำให้ completion ตกอีกต่อไปในสภาพแวดล้อมช่วงเวลาหลัง** (inference เร็วขึ้นราว 2 เท่า ไม่ใช่เพราะ thinking mode ซึ่งตรวจสอบแยกต่างหากแล้วว่าไม่ใช่สาเหตุ)
- ✅ Tier9: หาจุดวิกฤต loss ใหม่ของสภาพแวดล้อมปัจจุบัน + เปรียบเทียบ mitigation ที่จุดนั้น — **รันเสร็จแล้ว** (120 trials: 60 exploratory scan + 60 critical comparison) พบจุดวิกฤตใหม่ที่ **80%** (ไม่ใช่ 75% เดิม) และที่จุดนี้ **fixed timeout คงที่ให้ผลดีกว่า adaptive timeout scaling อย่างมีนัยสำคัญ** (65% vs 5% completion, p<0.001) — เป็นลำดับผลตรงข้ามกับ Tier5 เดิม ไม่ได้เขียนทับผล Tier5 (ยังถูกต้องสำหรับช่วงเวลาที่วัด) แต่เป็นหลักฐานล่าสุดของสภาพแวดล้อมปัจจุบัน
- แต่ละโฟลเดอร์มี `README.md` อธิบายวิธีรันของตัวเองและสถานะ/ผลสรุป — ผลการทดลองแบบละเอียดของแต่ละ Tier พร้อมสถิติเต็มรูปแบบอยู่ที่ `Paper/NetImpact.md/Current/` (ดูหมวด 8 ด้านล่าง) สรุปผลรวมทุก Tier แบบอ่านเร็ว (ผลลัพธ์ล้วนๆ ไม่มีลำดับเหตุการณ์) อยู่ที่ `Docs/NetImpact_Summary_All_Tiers.md`

### 7. เอกสารประกอบ (ภาพ/ไฟล์ร่างตั้งต้น) — `Docs/`
- `Docs/Diagram/`: แผนภาพ `.svg` (architecture, agent workflow, experiment design, analysis pipeline)
- `Docs/Draft_Idea/`: เอกสารร่าง/ไอเดียตั้งต้น (`.pdf`)
- ไฟล์ `.md` ที่เคยอยู่ที่นี่ (คำอธิบายโครงการ, ผลการทดลองเชิงลึก, แผนขยายการทดลอง, ความพร้อมสำหรับ AINTEC2026) ย้ายไปรวมกับเอกสารอธิบายงานทั้งหมดที่ `Paper/` แล้ว (ไฟล์ 10-13)

### 8. เอกสารอธิบายงานทั้งหมด (รวมศูนย์) — `Paper/`
รวมเอกสารอธิบายงานวิจัยทั้งหมดของโปรเจกต์ไว้ที่เดียว แบ่งเป็น 2 โฟลเดอร์ย่อยตามสถานะ — **ห้ามอ้างอิง
ไฟล์ใน `Archive_Legacy/` เป็นแหล่งข้อมูลของ manuscript อีกต่อไป** ไฟล์ที่ยังใช้งานจริงทั้งหมดอยู่ใน
`Current/` เท่านั้น

- **`Paper/NetImpact.md/Current/`** — เอกสารชุดที่เป็นปัจจุบันและมีอำนาจอ้างอิงสูงสุดของโปรเจกต์ (ไฟล์
  00-09 และ 16-22): `00` (สารบัญ/ลำดับการอ่าน), `01` (baseline + architecture), `02` (Tier1+Tier2), `03`
  (Tier3 evaluator validity), `04` (Tier4 replication), `05` (Tier5 mitigation), `06` (Tier6 — ผลจริงครบ
  แล้ว, ไฟล์ชื่อเดิมยังใช้คำว่า "Pending" เพื่อความคงที่ของลิงก์อ้างอิง เนื้อหาข้างในเป็นผลจริง), `07`
  (paper positioning/related work/checklist), `08` (สรุปรวมทุก Tier แบบ end-to-end), `09` (กฎการเขียน
  paper — ห้ามวันที่/ห้าม Tier label, narrative arc, ห้ามคำต้องห้ามเช่น "loss cliff"/"controlled"/
  "pre-registered", ห้าม overclaim ฯลฯ), `16` (การจัดวางรูป/คำบรรยายภาพ), `17` (Claim Calibration
  Spec — กำหนดความแรงของทุก claim ที่อนุญาตให้เขียน), `18` (Implementation Verification Addendum —
  **มีอำนาจอ้างอิงสูงสุดในเซ็ตนี้ ถ้าขัดแย้งกับไฟล์อื่นให้ยึดไฟล์นี้**), `19` (รายการอ้างอิง related
  work), `20` (Tier7 scope closure), `21` (Tier8 scope closure + current-environment finding), `22`
  (Tier9 critical threshold recalibration)
- **`Paper/NetImpact.md/Archive_Legacy/`** — เอกสารกระบวนการ/การวิเคราะห์ภาษาไทยรุ่นเก่า (ไฟล์ 10-15)
  ที่ถูกแทนที่ด้วยเอกสารใน `Current/` แล้ว เก็บไว้เพื่อประวัติเท่านั้น: `10` (ความพร้อม AINTEC2026 —
  รุ่นเก่า), `11` (คำอธิบายโครงการแบบละเอียด), `12` (ผลการทดลองเชิงลึก), `13` (แผนขยายการทดลองฉบับ
  สมบูรณ์), `14` (ภาพรวมโฟลเดอร์ analysis), `15` (findings list — แทนที่แล้วด้วย
  `Docs/NetImpact_Summary_All_Tiers.md` ซึ่งครอบคลุมถึง Tier9)
- ลำดับความสำคัญเมื่อเอกสารขัดแย้งกัน: `18` > `17` > (`01`-`08`, `16`) — `09` ควบคุมกฎการเขียนแยกต่างหาก
  (บังคับใช้กับทุกไฟล์) `20`/`21`/`22` เป็นเอกสารเฉพาะ Tier ที่ตัวเองมีอำนาจสูงสุดในขอบเขตของตัวเอง
- Tier6-9 มีผลจริงครบแล้วทั้งหมด — ไฟล์ `06`, `20`, `21`, `22` และจุดที่ `00`/`07`/`08` อ้างถึง
  Tier6-9 อัปเดตครบแล้วทั้งหมด ไม่มีไฟล์ไหนใน `Current/` ยังเขียนเป็นแผนที่รอรันอีกต่อไป

### 9. ชุดทดสอบ — `tests_extended/`
- pytest suite ครอบคลุม Tier1-6 ทั้งหมด (82 tests) ใช้ `fake_autogen.py` stub เพื่อไม่ต้องมี Ollama/GPU/tc จริง
- รัน: `python -m pytest tests_extended/ -v`

## Requirements

1. macOS/Linux ที่รัน Docker ได้
2. Docker Desktop / Docker Engine
3. Ollama ทำงานอยู่บน host
4. มีโมเดลใน Ollama (ตัวอย่าง `qwen3:8b`)

## Quick Start

### 1) เปิด Ollama บน host

```bash
ollama serve
ollama pull qwen3:8b
```

### 2) สร้างและรัน container

จากโฟลเดอร์ `docker/`

```bash
docker compose up -d --build
```

### 3) เข้า container

```bash
docker compose exec agent-lab bash
```

### 4) ทดสอบการเชื่อมต่อโมเดล

```bash
python3 /workspace/scripts/test_conn.py
```

### 5) รันทดลองแบบเร็ว

```bash
python3 /workspace/experiment/run_experiment.py --quick
```

log จะถูกบันทึกในโฟลเดอร์ที่ mount ไว้บน host (เช่น `logs/` หรือ `logs_three_day/` ตามที่กำหนด)

## โหมดการรันหลัก

### Quick sanity

```bash
python3 experiment/run_experiment.py --quick
```

### Pilot

```bash
python3 experiment/run_experiment.py --pilot
```

### Three-day bounded design

```bash
python3 experiment/run_experiment.py --three-day --log-dir logs_three_day
```

### Dry run (ไม่รันจริง)

```bash
python3 experiment/run_experiment.py --three-day --dry-run
```

### Resume จาก checkpoint

```bash
python3 experiment/run_experiment.py --three-day --resume --log-dir logs_three_day
```

### เลือกเฉพาะ phase

```bash
python3 experiment/run_experiment.py --tournament-only
python3 experiment/run_experiment.py --combined-only
```

## การวิเคราะห์ผล

### Pilot readiness

```bash
python3 experiment/analyze_pilot.py --log-dir logs
```

### Guideline จาก three-day/full

```bash
python3 experiment/analyze_guidelines.py --log-dir logs_three_day
python3 experiment/analyze_guidelines.py --log-dir logs_three_day --csv guideline_summary.csv
```

### Post-hoc ground-truth evaluation

```bash
python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode llm --sample 200
python3 experiment/evaluate_logs.py --log-dir logs_three_day --mode both --all
```

## Environment Variables สำคัญ

- `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434/v1`)
- `MODEL_NAME` (default `qwen3:8b`)
- `MAX_ROUNDS` (default `6`)
- `MAX_RETRIES` (default `2`)
- `LLM_TIMEOUT` (default `120` วินาที)
- `ENABLE_GROUND_TRUTH_EVAL` (`1/0`, default `1`)
- `GROUND_TRUTH_EVAL_MODE` (`heuristic|llm|both`, default `heuristic`)

ตัวอย่าง:

```bash
MODEL_NAME=qwen3:8b MAX_ROUNDS=8 MAX_RETRIES=3 LLM_TIMEOUT=180 \
python3 experiment/run_experiment.py --pilot
```

## ข้อควรระวัง

- ต้องมีสิทธิ์ `NET_ADMIN` ใน container ไม่เช่นนั้น `tc netem` จะใช้ไม่ได้
- `jitter > 0` โดยไม่มี delay จะถูกปรับเป็น delay ขั้นต่ำตาม logic ใน `scenarios.py`
- ถ้า `host.docker.internal` ใช้ไม่ได้ ให้ตรวจ Docker Desktop และค่า `extra_hosts`
- full combined run มีจำนวน trial สูงมาก ควรเริ่มจาก `--pilot` หรือ `--three-day` ก่อน

## ไฟล์ผลลัพธ์

- ต่อ trial จะได้ไฟล์ JSON 1 ไฟล์
- ข้อมูลสำคัญใน `outcome` เช่น:
  - `success`, `rounds`, `reviewer_rejections`
  - `elapsed_seconds`, `total_tokens`
  - `quality_score`, `ground_truth_score`, `ground_truth_passed`
  - `retry_count`, `timeout_count`, `total_error_count`

## แนะนำ workflow ที่ปลอดภัย

1. `--quick` เพื่อเช็คระบบ
2. `--pilot` เพื่อดู variance/crash/parse rate
3. `--three-day` พร้อม `--resume`
4. `analyze_guidelines.py` เพื่อสรุป threshold
5. `evaluate_logs.py` เพื่อเพิ่ม ground-truth post-hoc ในจุดที่ต้องการ
