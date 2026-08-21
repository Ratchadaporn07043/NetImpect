# Tier 8 — Scope Closure (สภาพแวดล้อมใหม่ทั้งหมด สำหรับรันบนเครื่องอื่น)

โฟลเดอร์นี้สร้างขึ้นใหม่ทั้งหมด **ไม่แก้ไฟล์ใดๆ ที่ root โปรเจกต์เดิมเลย**
(`logger.py`, `experiment/controller.py`, `multi_agent.py` ที่ root ยังเป็นของ
เดิมทุกตัวอักษร) เพื่อให้:

1. รันบนเครื่องใหม่ได้โดยไม่กระทบข้อมูล 5,300 trials เดิม
2. ตรวจสอบ/ลบทิ้งทั้งโฟลเดอร์ได้ง่ายถ้าไม่ต้องการผลอีกต่อไป โดยไม่ทิ้งร่องรอยไว้ที่อื่น
3. ไม่ซ้ำปัญหาที่เจอใน Tier 7 — โค้ดที่ "เอกสารบอกว่าเพิ่มแล้ว" ไม่ตรงกับไฟล์ที่
   import จริงตอนรัน (ดูหัวข้อ "ทำไมต้องเป็น Tier 8" ด้านล่าง)

ปิดช่องว่าง 5 อย่างที่ตรวจสอบแล้วว่า **ยังไม่เคยรันสำเร็จสักอย่างในโปรเจกต์นี้**
(ตรวจโดยไล่อ่านโค้ดจริงทุกไฟล์ ไม่ใช่แค่เอกสาร ก่อนเริ่มเขียนโฟลเดอร์นี้):

| ข้อ | ปิดช่องว่างอะไร | ไฟล์หลัก |
|---|---|---|
| 1 | achieved-path measurement (ไม่เคยมีโค้ดนี้เลยในโปรเจกต์) | `run_tier8_achieved_path.py` |
| 2 | fixed-long-timeout arm (7A ของ Tier 7 พังเพราะ `logger.py` ไม่มี `agent=` param — บั๊กนี้ยังไม่ถูกแก้จนถึงตอนที่ตรวจ) | `run_tier8_fixed_timeout.py` |
| 3 | mitigation comparison แบบสุ่ม/สลับลำดับ แทน consecutive block | `run_tier8_randomized_mitigation.py` |
| 4 | bidirectional (ingress+egress) shaping ผ่าน IFB | `run_tier8_ingress.py` |
| 5 | jitter-floor matched control (delay=50ms คงที่, jitter=0) | `run_tier8_jitter_floor.py` |

---

## แผนที่โฟลเดอร์ + สถานะ (อ่านหัวข้อนี้ก่อนถ้างง ว่ารันอะไรไปแล้ว/ยังไม่ได้รัน)

```
Tier8_EnsureScopeClosure/
├── README.md                          <- ไฟล์นี้
├── logger.py / controller.py /        <- โค้ดหลัก (ห้ามแก้ ตรวจสอบแล้ว)
│   multi_agent.py / checkpoint_utils.py
├── run_tier8_*.py (5 ไฟล์)             <- ✅ รันจบครบทั้ง 5 ข้อแล้ว (ดูผลที่ results_completed/)
├── run_tier8_batch_1245.sh
├── tests_tier8/                       <- offline test suite (pytest)
│
├── results_completed/                 <- ✅ ผลจากการรัน 5 ข้อเดิม (thinking-on, เสร็จแล้ว)
│   ├── logs_tier8_achieved_path_No.1/         (ข้อ 1)
│   ├── logs_tier8_fixed_*_No.2/ (x3)          (ข้อ 2)
│   ├── logs_tier8_randomized_mitigation_*     (ข้อ 3)
│   ├── logs_tier8_ingress_No.4/               (ข้อ 4)
│   └── logs_tier8_jitter_floor_No.5/          (ข้อ 5)
│
└── thinking_off_diagnostic/           <- ✅ รันจบแล้วทั้งหมด (80 diagnostic trials — ดู README ในนี้)
    ├── README.md                      <- เริ่มที่นี่
    ├── diagnosis_output.txt / thinking_output.txt /      <- ✅ รันวินิจฉัยแล้ว (แค่เช็ค ไม่ใช่ trial จริง)
    │   openai_endpoint_output.txt / native_api_output.txt
    ├── ollama_native_client.py / multi_agent_thinking_off.py  <- โค้ดตัวแก้ปัญหา (เขียนเสร็จ, ทดสอบ wiring แล้ว)
    ├── smoke_test_thinking_off.py     <- ✅ รันแล้ว (ผ่านทั้ง 2 stage)
    ├── run_confirm_thinking_off.py        <- ✅ รันจบแล้ว (ข้อ 2/3, 20/20 trials)
    ├── run_confirm_thinking_off_item1.py  <- ✅ รันจบแล้ว (ข้อ 1, 20/20 trials)
    └── run_confirm_thinking_off_item4.py  <- ✅ รันจบแล้ว (ข้อ 4, 40/40 trials)
```

**สรุปสั้นๆ:** 5 ข้อหลัก (run_tier8_*.py) รันจบไปแล้วทั้งหมด ผลอยู่ใน
`results_completed/` แต่วิเคราะห์ผลแล้วพบว่า Ollama เปิด "thinking mode" อยู่
ตลอดการรัน ทำให้บาง scenario (loss=75% ในข้อ 1/2/3/4) ผลผิดเพี้ยน —
`thinking_off_diagnostic/` (80 diagnostic trials) ก็รันจบแล้วเช่นกัน และผลสรุปว่า
thinking mode **ไม่ใช่** สาเหตุ (completion ปิด-thinking แทบไม่ขยับจากผลเดิม) —
สาเหตุจริงคือความเร็ว inference ของสภาพแวดล้อมปัจจุบันเปลี่ยนไป ราว 2 เท่า
(รายละเอียดเต็มที่ `Paper/NetImpact.md/Current/NetImpact_21_Tier8_Ensure_Scope_Closure.md`
§6 และ `Tier9_CriticalThresholdRecalibration/README.md`) ไม่มีงานเหลือค้างใน
Tier 8 อีกแล้ว — ไม่ต้องแตะโฟลเดอร์ `results_completed/`, `thinking_off_diagnostic/`
หรือสคริปต์ `run_tier8_*.py` อีกเลย

---

## ทำไมต้องเป็น Tier 8 (ไม่ใช้ Tier 7 เดิม/ไม่แก้ root)

ตรวจโค้ดจริงก่อนเขียนไฟล์ในนี้แล้วพบ 2 อย่างที่ยืนยันว่าต้องแยกออกมาใหม่ทั้งหมด
ไม่ใช่แค่ "รันซ้ำ" ของเดิม:

- **`logger.py` ที่ root** ไม่มีพารามิเตอร์ `agent` ใน `log_error`/`log_retry`/
  `log_timeout` เลย ทั้งที่เอกสารของ Tier 7 (`Tier7_ScopeClosure/README.md`
  และ `Paper/NetImpact.md/Current/NetImpact_20_Tier7_Scope_Closure.md`) เขียนว่า
  เพิ่มไปแล้ว — นี่คือบั๊กที่ทำให้ 60 trial ของ 7A ใช้ไม่ได้จริง (ทุก timeout
  จริงกลายเป็น `TypeError` ที่ตัด retry ทิ้งหมด)
- **`experiment/controller.py` ที่ root** ไม่มีพารามิเตอร์ `direction`/`ifb_dev`
  และไม่มี `probe_ingress_support()` เลยแม้แต่นิดเดียว ทั้งที่เอกสารเขียนว่า
  เพิ่มแบบ additive ไปแล้ว — ถ้ารัน `run_tier7_ingress.py` ตอนนี้จะ crash ทันที

Tier 8 จึงมี **สำเนาของ `logger.py`, `controller.py`, `multi_agent.py` เป็นของ
ตัวเอง** ตรวจสอบ/เทสในตัวเอง ไม่พึ่งไฟล์ที่ root เลยสำหรับ 3 ไฟล์นี้ (ยัง import
`experiment/tasks.py`, `experiment/evaluator.py`, `experiment/scenarios.py` จาก
root ตามเดิม เพราะ 3 ไฟล์นั้นตรวจแล้วว่าไม่มีปัญหาอะไร ไม่มีเหตุผลต้องแยก)

---

## เตรียมเครื่องใหม่

**หมายเหตุ (เครื่องใหม่ = Ubuntu VM):** ย้ายมาที่นี่เพราะ `tc`/`ip`/IFB ต้องพึ่ง
Linux kernel โดยตรง (เดิมรันผ่าน Docker Desktop บน macOS ซึ่ง container จริงๆ
อยู่ใน VM ของ Docker Desktop อีกชั้น — เป็นไปได้ว่าเป็นสาเหตุหนึ่งที่ทำให้ความ
พยายามรัน ingress+IFB ครั้งก่อนไม่ผ่าน falsification check ของตัวเอง) บน Ubuntu
VM ยังใช้ docker-compose เดิมทุกอย่างเหมือนเดิม (ไม่ต้องแก้ `docker-compose.yml`/
`Dockerfile`) แค่ตัว host ที่รัน Docker เปลี่ยนจาก macOS เป็น Ubuntu โดยตรง ทำให้
kernel ที่ `tc`/`ip link add ifb0 type ifb` คุยด้วยเป็น kernel ของ Ubuntu VM เอง
ไม่ใช่ kernel ของ Docker Desktop VM ซ้อนอีกชั้น — โอกาสที่ข้อ 4 จะผ่าน
falsification check จึงสูงกว่าเดิม

### 0. ติดตั้ง Docker บน Ubuntu (ถ้ายังไม่มี)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # แล้ว logout/login ใหม่ 1 ครั้งให้มีผล
docker compose version            # ต้องเป็น v2 (คำสั่ง "docker compose" ไม่ใช่ "docker-compose")
```

`extra_hosts: host.docker.internal:host-gateway` ใน `docker-compose.yml` เดิม
ใช้ได้บน Docker Engine บน Linux เช่นกัน (ต้องการแค่ Docker ≥ 20.10 ซึ่งเป็นค่า
เริ่มต้นของการติดตั้งด้วยสคริปต์ข้างบนอยู่แล้ว) ไม่ต้องแก้ไฟล์อะไรเพิ่ม

### 1. คัดลอกทั้งโฟลเดอร์โปรเจกต์

Tier 8 import `experiment/tasks.py`, `experiment/evaluator.py`, และ
`experiment/scenarios.py` จาก root โปรเจกต์ (ไม่ได้ก็อปปี้ไฟล์เหล่านี้มาซ้ำ เพราะ
ไม่มีเหตุผลต้องแยก) **ต้องคัดลอกทั้งโฟลเดอร์ `AINTEC Project/` ไปเครื่องใหม่ ไม่ใช่
แค่ `Tier8_EnsureScopeClosure/`** โครงสร้างที่ต้องมีครบ:

```
AINTEC Project/
  experiment/
    tasks.py
    evaluator.py
    scenarios.py
  docker/
    Dockerfile
    docker-compose.yml
    requirements.txt
  Tier8_EnsureScopeClosure/    <- โฟลเดอร์นี้
```

### 2. ติดตั้ง Ollama บน host (นอก container — บน Ubuntu VM เอง ไม่ใช่ในเครื่องอื่น)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &     # หรือปล่อยให้ systemd service ที่ installer ตั้งไว้ให้จัดการเอง
ollama pull qwen3:8b
```

ถ้า Ubuntu VM มี GPU (NVIDIA) และต้องการให้ Ollama ใช้ GPU เร่งความเร็ว ต้อง
ติดตั้ง NVIDIA driver บน VM เองก่อน (เรื่องนี้ไม่เกี่ยวกับ Docker เลย เพราะ Ollama
รันนอก container — `ollama serve` จะ detect GPU เองอัตโนมัติถ้า driver พร้อม)

### 3. เข้า container ผ่าน docker-compose เดิมของโปรเจกต์

```bash
cd "AINTEC Project/docker"
docker compose up -d --build
docker compose exec agent-lab bash
```

Dockerfile เดิมของโปรเจกต์ติดตั้ง `iproute2` (`tc`/`ip`), `iputils-ping`,
`curl` ไว้แล้วทั้งหมด — Tier 8 ข้อ 1 (achieved-path) และข้อ 4 (ingress) ใช้
เครื่องมือพวกนี้โดยไม่ต้องติดตั้งอะไรเพิ่ม

**เฉพาะข้อ 4 (bidirectional/ingress)** ต้องโหลด kernel module บน **host**
ก่อนเข้า container (container โหลดเองไม่ได้แม้มี `NET_ADMIN`):

```bash
sudo modprobe ifb numifbs=0
lsmod | grep ifb   # ยืนยันว่าโหลดสำเร็จจริง ก่อนเข้า container
```

บน Ubuntu VM (kernel ของ Ubuntu เอง ไม่ใช่ kernel ซ้อนของ Docker Desktop แบบ
เดิม) คำสั่งนี้ควรสำเร็จตรงไปตรงมา ถ้ายัง fail ("Operation not permitted" หรือ
"ifb: not found") ให้ตรวจว่า VM เปิดใช้ nested virtualization/kernel module
loading ไว้จริง (สำหรับ VM บางประเภท เช่นบางค่าย cloud VM ที่ปิดการโหลด kernel
module ไว้โดย policy) ก่อนไปต่อ `--probe-only`

### 4. ทดสอบ offline ก่อนเสมอ (ในนี้ ก่อนแตะ Ollama/tc จริง)

```bash
cd /workspace/Tier8_EnsureScopeClosure
python3 -m pip install pytest psutil --break-system-packages   # เผื่อยังไม่มี
python3 -m pytest tests_tier8/ -q
```

ต้องเห็น `... passed` ทั้งหมดก่อนรันจริง — ชุดเทสนี้จับบั๊กจริงไปแล้ว 2 จุดระหว่าง
เขียน Tier 8 เอง (ลำดับ `sys.path` ที่ทำให้ `import multi_agent`/`logger` ไป
โดนไฟล์ที่ root แทน) ดังนั้นอย่าข้ามขั้นตอนนี้แม้จะรีบ

---

## ลำดับที่แนะนำให้รัน

✅ **ทั้ง 5 ข้อรันจบไปหมดแล้ว** ผลอยู่ที่ `results_completed/` หัวข้อนี้เก็บไว้
เป็นเอกสารอ้างอิงว่ารันด้วยลำดับ/คำสั่งอะไร เผื่อต้องรันซ้ำหรืออธิบายวิธีการ
ในเปเปอร์ — ไม่ต้องรันตามนี้อีกแล้ว (ข้ามไปหัวข้อ "ส่วนเสริม (diagnostic)"
ด้านล่างได้เลยถ้าต้องการรู้ว่าต้องทำอะไรต่อ)

1. **ข้อ 5 ก่อน** — เร็วที่สุด (20 trials, <1 ชม.) ใช้เป็น smoke test แรกสุด
   ทดสอบ logger/controller/multi_agent ของ Tier 8 ทั้งชุดในสภาพแวดล้อมจริง
   ด้วยต้นทุนเวลาต่ำสุด ก่อนลงทุนเวลากับข้ออื่นที่ยาวกว่ามาก
2. **ข้อ 2** — พิสูจน์ว่า logger fix (`agent=` param) ใช้งานได้จริงกับ trial
   จำนวนมาก (มี self-test ในตัวสคริปต์อยู่แล้ว, 60-180 trials, ~9-27 ชม.)
3. **ข้อ 4** — ต้องมี `modprobe ifb` พร้อมก่อน ใช้ `--probe-only` ตรวจก่อนเสมอ
   (80 trials, ~8 ชม.)
4. **ข้อ 1** — ปานกลาง (80 trials, ~2-3 ชม.)
5. **ข้อ 3** — ยาวที่สุด (660 trials, หลายวัน) เหมาะรันตอนมีเวลาต่อเนื่องยาวๆ

ลำดับนี้ (5 -> 2 -> 4 -> 1 -> 3) ตรงกับลำดับที่ `run_tier8_batch_1245.sh`
รันจริงทุกตัวอักษร (ดูหัวข้อถัดไป)

ทุกสคริปต์รองรับ `--dry-run` (ตรวจแผนการรันโดยไม่แตะอะไรจริง) และ `--resume`
(checkpoint แยกต่อสคริปต์ ปลอดภัยถ้าเครื่องดับกลางทาง)

**รัน 4 ข้อ (5, 2, 4, 1) ต่อกันในรวดเดียว แล้วค่อยรันข้อ 3 แยกทีหลังถ้าเวลาเพียงพอ:**

```bash
chmod +x run_tier8_batch_1245.sh   # ครั้งแรกครั้งเดียว
./run_tier8_batch_1245.sh
# เสร็จแล้วถ้าเวลาเพียงพอ:
python3 run_tier8_randomized_mitigation.py --resume
```

สคริปต์นี้รันเทสก่อนเสมอ, หยุดทันทีถ้าขั้นไหน fail (self-test ของข้อ 2 หรือ
`probe_ingress_support()` ของข้อ 4 ไม่ผ่าน), และ resume ได้ถ้าเครื่องดับกลางทาง
(รันสคริปต์เดิมซ้ำได้เลย ขั้นที่เสร็จแล้วจะข้ามเร็วๆ ผ่าน checkpoint ของแต่ละข้อ)
บันทึก log เต็มไว้ที่ `batch_1245_<timestamp>.log`

---

## ข้อ 1 — `run_tier8_achieved_path.py`

วัด achieved path จริง (ไม่ใช่แค่ configured) ที่ 4 จุดที่ `Paper/Manuscript/sigconf.tex`
อ้างอิงอยู่แล้ว: baseline, loss 75%, delay 3,000ms, bandwidth 50kbit/s — แนบ
`tc -s qdisc` counters, RTT จริงจาก `ping`, TCP retransmission counter จาก
`/proc/net/snmp`, และ background throughput probe จาก `curl` ไว้กับทุก trial
(ก่อน/หลัง) แทนที่การรันซ้ำทั้ง 5,300 trial ซึ่งไม่จำเป็น

```bash
python3 run_tier8_achieved_path.py --dry-run
python3 run_tier8_achieved_path.py --resume
```

80 trials (4 จุด × 4 tasks × 5 repeats), ~2-3 ชม. ✅ รันจบแล้ว ผลอยู่ที่
`results_completed/logs_tier8_achieved_path_No.1/`
แต่ละไฟล์ log มี key `"achieved"` แยกจาก `"network_condition"` (configured)
ชัดเจน เทียบกันได้ตรงๆ เช่น `network_condition.loss_pct=75` (configured) กับ
`achieved.after.qdisc_egress.dropped` (achieved)

---

## ข้อ 2 — `run_tier8_fixed_timeout.py`

ตอบว่า timeout scaling ที่ช่วย completion (14/20 → 20/20 ที่ 75% loss) มาจาก
"ปรับตามสภาพเครือข่าย" (condition-aware) จริง หรือแค่ "ให้เวลามากขึ้นเฉยๆ"
โดยตั้ง timeout คงที่ 345 วินาทีทุก scenario (ค่าเดียวกับที่สูตร adaptive คืนที่
loss=75%)

```bash
python3 run_tier8_fixed_timeout.py --dry-run
python3 run_tier8_fixed_timeout.py --resume --include-reference-arms
```

**แนะนำให้ใช้ `--include-reference-arms` เสมอถ้าเวลาเอื้อ** (180 trials รวม,
~27 ชม.) เพราะรัน `none`/`adaptive_timeout` ซ้ำในบล็อกเดียวกันด้วย ตัด
run-block confound ออกได้จริง ถ้ารันแค่ arm เดียว (60 trials, ~9 ชม.) ยังเทียบ
กับ Tier 5 เดิมได้แค่แบบมี run-block confound ปนอยู่ (ต้องเขียนใน Methods ตามจริง)

สคริปต์ self-test `logger.py` (เรียก `log_timeout(agent=...)` จริง) ก่อนเริ่มรัน
เสมอ ถ้า fail จะหยุดทันทีก่อนเสียเวลาไปหลายชั่วโมงเหมือนที่เกิดกับ 7A

✅ รันจบแล้ว ผลอยู่ที่ `results_completed/logs_tier8_fixed_fixed_long_timeout_No.2/`
(และ `results_completed/logs_tier8_fixed_none_No.2/`,
`results_completed/logs_tier8_fixed_adaptive_timeout_No.2/`)

**วิธีอ่านผลที่ 75% loss:**

| ผล | แปลว่า |
|---|---|
| fixed ≈ adaptive (ทั้งคู่สูงกว่า control) | สิ่งที่ช่วยคือเวลา ไม่ใช่ condition-awareness |
| fixed < adaptive ชัดเจน | condition-awareness ช่วยจริง |
| fixed ≈ control | ผิดคาด ตรวจว่า `FIXED_LONG_TIMEOUT` ถูกส่งถึง `llm_config` จริงก่อนตีความ |

---

## ข้อ 3 — `run_tier8_randomized_mitigation.py`

รัน 660 trial เดียวกับ Tier 5 เป๊ะ (11 loss levels × 4 tasks × 5 repeats × 3
conditions) แต่ **สุ่มลำดับการรันข้าม condition** (seed คงที่ = 20260101,
เปลี่ยนได้ผ่าน `--seed` แต่ต้องบันทึกไว้ว่าใช้ค่าไหนจริง) แทนการรันเป็นบล็อก
ต่อเนื่องแบบ Tier 5 เดิม เพื่อตัด run-block confound ที่ sigconf.tex
`sec:scopelimitations` ระบุไว้ว่าเป็นข้อจำกัด

```bash
python3 run_tier8_randomized_mitigation.py --dry-run
python3 run_tier8_randomized_mitigation.py --resume
```

ก่อนรันจริงจะเขียนไฟล์ `logs_tier8_randomized_mitigation_execution_order.json`
บันทึกลำดับที่สุ่มได้ทั้งหมดไว้ล่วงหน้า (ตรวจย้อนหลังได้ว่าเวลาที่รันจริงกับ
condition ไม่มีความสัมพันธ์กันอย่างเป็นระบบ) log แต่ละ trial ยังแยกโฟลเดอร์ตาม
condition เหมือนเดิม (`logs_tier8_randomized_mitigation_none/` ฯลฯ) ใช้กับ
`parse_logs.py` เดิมได้ทันที — ✅ รันจบแล้ว ผลอยู่ที่ `results_completed/logs_tier8_randomized_mitigation_*`

ใช้เวลานานที่สุดในบรรดา 5 ข้อ (หลายวัน) เพราะ 660 trials รวม — ถ้าเวลาจำกัด
ควรรันข้ออื่นก่อนแล้วค่อยมาข้อนี้ทีหลัง

**วิธีอ่านผล:** เทียบ completion ที่ 75% loss ระหว่าง `none` กับ
`adaptive_timeout` ในโฟลเดอร์นี้ ถ้าความต่าง (เดิม 14/20 vs 20/20) ยังปรากฏอยู่
หลังตัด run-block confound แล้ว ก็ยกระดับจาก "hypothesis generating" เป็น
ข้อค้นพบที่อ้างได้จริง

---

## ข้อ 4 — `run_tier8_ingress.py`

⚠️ **อ่านหัวข้อนี้ทั้งหมดก่อนรัน** — มีความพยายามรันชุดนี้มาก่อนหน้าครั้งหนึ่ง
(นอก Tier 8) ที่ falsification check (baseline + positive control) ไม่ผ่าน
พบสัญญาณว่าอาจเป็น host/CPU resource contention หรือ NIC checksum offload ที่
ยังเปิดอยู่ (ปัญหาที่รู้จักกันดีของ `tc mirred` redirect ไป IFB) — ไม่ใช่ผลจาก
network shaping จริง สคริปต์นี้เพิ่ม 2 มาตรการที่ความพยายามก่อนหน้าไม่มี:

1. `disable_checksum_offload()` — ปิด rx/tx checksum offload บน NIC ก่อนเริ่ม
   (best-effort ผ่าน `ethtool -K`, ไม่ fatal ถ้าทำไม่ได้)
2. resource gate — เช็ค CPU load ก่อนเริ่มทุก trial ถ้าสูงเกิน 70% จะรอ (สูงสุด
   120 วินาที) ก่อนรันจริง กันไม่ให้ trial ปนกับ host contention ที่ไม่เกี่ยวกับ
   network condition ที่กำลังทดสอบ

```bash
# 1. ตรวจสภาพแวดล้อมก่อนเสมอ (ต้องรัน sudo modprobe ifb numifbs=0 บน host มาก่อน)
python3 run_tier8_ingress.py --probe-only

# 2. ดูแผนการรันโดยไม่แตะอะไรจริง
python3 run_tier8_ingress.py --dry-run

# 3. รันจริง
python3 run_tier8_ingress.py --resume
```

80 trials (4 scenarios × 4 tasks × 5 repeats), ~8 ชม. ✅ รันจบแล้ว ผลอยู่ที่
`results_completed/logs_tier8_ingress_No.4/`

**สคริปต์พิมพ์คำตัดสิน PASS/FAIL ของ falsification check ให้อัตโนมัติตอนจบ
การรัน** ไม่ต้องนั่งนับเอง:

- Falsification check 1 (baseline ต้องไม่ตก, เกณฑ์ ≥ 85%)
- Falsification check 2 (positive control 75% loss ต้องแสดง degradation กว่า baseline)

**ถ้า FAIL แม้แต่จุดเดียว ห้ามตีความผลของ `t8in_bw50`/`t8in_delay1000` เด็ดขาด**
ตามกฎเดิมที่ `Tier7_ScopeClosure/README.md` และ
`NetImpact_20_Tier7_Scope_Closure.md` วางไว้ — ให้ตรวจ `resource_snapshots`
(`cpu_percent`) และ `cpu_gate` ในแต่ละ log ก่อนว่าเป็น host contention จริงไหม
ก่อนพยายามรันซ้ำ

---

## ข้อ 5 — `run_tier8_jitter_floor.py`

จุดควบคุมใหม่ที่ไม่เคยมีในโปรเจกต์: delay=50ms คงที่ (ค่า floor เดียวกับที่ทุก
ระดับ jitter>0 ได้รับ) แต่ jitter=0 เพื่อแยกผลของ floor เองออกจากผลของ jitter เอง

```bash
python3 run_tier8_jitter_floor.py --dry-run
python3 run_tier8_jitter_floor.py --resume
```

20 trials (4 tasks × 5 repeats), <1 ชม. ✅ รันจบแล้ว ผลอยู่ที่
`results_completed/logs_tier8_jitter_floor_No.5/`

**วิธีอ่านผล:** เทียบ completion กับ 2 จุดที่มีอยู่แล้วในเปเปอร์ — jitter=0 เดิม
(delay=0, 20/20) และ jitter=100ms เดิม (delay=50 floor + jitter, 19/20 จาก
Table 2) ถ้าจุดใหม่นี้ก็ ~20/20 เหมือน delay=0 เดิม แปลว่า floor เองไม่ใช่ตัวขับ
completion ที่สังเกตได้ที่ jitter=100ms

---

## ส่วนเสริม (diagnostic) — ปิด Qwen3 "thinking" mode เพื่อวินิจฉัยความผิดปกติของข้อ 1/2/3/4

✅ **สถานะ: รันจบครบทั้ง 3 confirmatory script แล้ว (80 diagnostic trials รวม) —
หัวข้อนี้เก็บไว้เป็นเอกสารอ้างอิงว่าทำไมถึงรัน/รันอะไร ไม่ต้องรันซ้ำอีก**
ผลสรุป: thinking mode **ไม่ใช่สาเหตุ** ของ ceiling/floor effect ที่พบในข้อ
1/2/3/4 — ดูตารางผลจริงในหัวข้อ "สรุป: ผลที่ได้จากทั้ง 3 script" ด้านล่าง
รายละเอียดสถิติเต็มอยู่ที่
`Paper/NetImpact.md/Current/NetImpact_21_Tier8_Ensure_Scope_Closure.md` §6
(ในนั้นมี README.md ของโฟลเดอร์ย่อย `thinking_off_diagnostic/` เองด้วย เป็น
checklist สั้นๆ ถ้าไม่อยากอ่านหัวข้อยาวนี้)

**บริบท:** หลังรันข้อ 2/3 จริงแล้วพบ completion rate สูงผิดปกติ (ใกล้ 100% ทุก
mitigation แม้แต่ `none` ที่ Tier 5 เดิมเคยได้แค่ 14/20 ที่ loss=75%) ตรวจสอบ
แล้วพบว่า Ollama เวอร์ชันของเครื่องตอนนี้ (0.32.5) เปิด "thinking" mode เป็น
ค่าเริ่มต้นให้ qwen3:8b ทำให้แต่ละ LLM call ช้าลง 10-30+ เท่า (ดูรายละเอียดเต็ม
ใน `thinking_off_diagnostic/diagnosis_output.txt`,
`thinking_off_diagnostic/thinking_output.txt`,
`thinking_off_diagnostic/openai_endpoint_output.txt`,
`thinking_off_diagnostic/native_api_output.txt`) — พารามิเตอร์ `"think": false` ที่ปิดได้
จริง ใช้งานได้เฉพาะกับ native `/api/chat` ของ Ollama เท่านั้น ไม่ใช่ผ่าน
`/v1/chat/completions` ที่ AutoGen ใช้อยู่ปกติ จึงต้องมี custom model client
เพื่อสลับ endpoint

ตรวจต่อพบว่า thinking mode เปิดอยู่ **ตลอดการรันข้อ 1/4/5 ด้วยเช่นกัน** (median
ช่วงห่างระหว่างข้อความ: ข้อ 1 = 91.6s, ข้อ 4 = 88.0s, ข้อ 5 = 73.5s — สัญญาณ
เดียวกับข้อ 2 ที่ 151.6s เทียบกับ <2s ถ้าปิดจริง) เพราะเป็นการตั้งค่าระดับ
Ollama server ตัวเดียว ไม่ผูกกับสคริปต์ไหนโดยเฉพาะ แต่ผลกระทบต่อความน่าเชื่อถือ
ของแต่ละข้อไม่เท่ากัน — ตรวจแยกตาม scenario แล้วพบ:

| ข้อ | scenario ที่น่าสงสัย | ผลเดิม (thinking-on) | ควรรันซ้ำไหม |
|---|---|---|---|
| 1 | `t8ap_loss75` (loss=75%, mitigation=none) | 20/20 (ceiling effect แบบเดียวกับข้อ 2) | **ควร** |
| 2, 3 | loss=75%, mitigation=none (ทุกจุด) | ~100% แทนที่จะเป็น 14/20 (Tier 5) | **ควร** |
| 4 | `t8in_loss75` (loss=75% ทั้งสองทิศทาง) | **0/20** (floor effect ตรงข้ามข้อ 1/2/3) | **ควร** |
| 5 | ทุกจุด (delay=50ms คงที่ ไม่มี loss เลย) | 20/20 ตรงกับ baseline เดิมที่มีอยู่แล้ว | ไม่จำเป็นเร่งด่วน |

ข้อ 1/2/3 ทุกจุดที่น่าสงสัยเป็น **ceiling effect** (สูงผิดปกติ) เหมือนกันหมด
แต่ข้อ 4 กลับเป็น **floor effect** (0/20 — ล้มเหลวทั้งหมดตั้งแต่ round แรก ด้วย
`APIConnectionError`/connection reset เป็นหลัก ไม่ใช่ timeout ธรรมดา) ซึ่งอาจ
เกิดจาก thinking mode ทำให้ connection เปิดค้างนานผิดปกติจนโดน drop ทั้งคู่ทาง
(bidirectional loss compound) หรืออาจเป็นผลจริงของ bidirectional shaking เองก็
ได้ ยังสรุปไม่ได้จนกว่าจะรันยืนยัน — ข้อ 5 ไม่ใช่เงื่อนไขที่มี packet loss เลย
จึงไม่ใช่แบบที่ thinking-mode latency จะไปดัน completion ให้ผิดปกติได้ และผล
ที่ได้ก็ตรงกับ baseline เดิมอยู่แล้ว จึงไม่ต้องรันซ้ำ

### สรุป: ผลที่ได้จากทั้ง 3 script (รันจบแล้ว — ลำดับที่รันจริง)

คำสั่งที่ใช้รันจริง (เก็บไว้อ้างอิง ไม่ต้องรันซ้ำ):

```bash
cd thinking_off_diagnostic   # ทุกคำสั่งด้านล่างรันจากในนี้

# ขั้นตอนที่ 0 — ทำครั้งเดียว ก่อนรัน confirmatory script ไหนก็ตาม
python3 smoke_test_thinking_off.py
#   ✅ ผ่านทั้ง 2 stage

# ขั้นตอนที่ 1 — ข้อ 2/3 (loss=75%, mitigation=none, 20 trials)
python3 run_confirm_thinking_off.py --dry-run
python3 run_confirm_thinking_off.py --resume

# ขั้นตอนที่ 2 — ข้อ 1 (t8ap_loss75 เท่านั้น, 20 trials)
python3 run_confirm_thinking_off_item1.py --dry-run
python3 run_confirm_thinking_off_item1.py --resume

# ขั้นตอนที่ 3 — ข้อ 4 (t8in_baseline + t8in_loss75, 40 trials, modprobe ifb
# บน host ก่อนเหมือน run_tier8_ingress.py เดิม)
sudo modprobe ifb numifbs=0        # บน host เท่านั้น ไม่ใช่ใน container
python3 run_confirm_thinking_off_item4.py --probe-only
python3 run_confirm_thinking_off_item4.py --dry-run
python3 run_confirm_thinking_off_item4.py --resume

# ข้อ 5 — ไม่ต้องรันซ้ำ (เหตุผลด้านบน)
```

**ผลจริง (thinking-off) เทียบกับผลเดิม (thinking-on) และ Tier5 baseline:**

| จุดที่เทียบ | thinking-off (ใหม่) | thinking-on (เดิม) | Tier5 baseline |
|---|---|---|---|
| ข้อ 2/3 (loss=75%, none) | 20/20 | ~100% | 14/20 |
| ข้อ 1 (`t8ap_loss75`) | 18/20 | 20/20 | 14/20 |
| ข้อ 4 baseline (`t8in_baseline`) | 100% | 20/20 | — |
| ข้อ 4 loss75 (`t8in_loss75`) | 0/20 | 0/20 | — |

**ทุกจุดยังคงห่างจาก Tier5 baseline (14/20) เหมือนเดิม ไม่มีจุดไหนขยับเข้าใกล้เลย** — สรุปว่า
**thinking mode ไม่ใช่สาเหตุของ ceiling/floor effect ที่พบในข้อ 1/2/3/4** สาเหตุจริงที่พบคือความเร็ว
inference ของสภาพแวดล้อมปัจจุบันเร็วขึ้นราว 2 เท่าเมื่อเทียบกับช่วงเวลาที่วัด Tier 5 เดิม (median elapsed
time ของ trial ที่สำเร็จตั้งแต่ครั้งแรกที่ 75% loss: 248 วินาที → 127 วินาที) — รายละเอียดเต็มและ wording
ที่อนุมัติให้ใช้ในเปเปอร์อยู่ที่
`Paper/NetImpact.md/Current/NetImpact_21_Tier8_Ensure_Scope_Closure.md` §6 ผลนี้เป็นจุดเริ่มต้นของ
`Tier9_CriticalThresholdRecalibration/` ซึ่งหา critical loss threshold ใหม่ของสภาพแวดล้อมปัจจุบัน (พบว่า
คือ 80%)

รวมเวลาทั้ง 3 confirmatory script ~1-2 ชั่วโมง (เร็วกว่าของเดิมมากเพราะ
thinking-off ทำให้แต่ละ trial เร็วขึ้น ไม่ใช่รอ 10-30+ เท่าเหมือนเดิม)

**ไฟล์ที่เพิ่ม (ไม่แตะ `multi_agent.py`/`controller.py`/`logger.py` ตัวจริงเลย
— ทำงานผ่าน monkey-patch จากภายนอกเท่านั้น ตรวจยืนยันด้วย fake HTTP server จำลอง
ก่อนส่งมอบแล้วว่าทุก LLM call ถูก route ไปที่ `/api/chat` พร้อม `think:false`
จริง ไม่มี request หลุดไปที่ `/v1/chat/completions` เดิมเลย):**

| ไฟล์ | หน้าที่ |
|---|---|
| `ollama_native_client.py` | custom AutoGen model client คุย Ollama ผ่าน native `/api/chat` + `think:false` |
| `multi_agent_thinking_off.py` | monkey-patch `multi_agent.py` ให้ใช้ client ข้างบน โดยไม่แก้ไฟล์จริง |
| `smoke_test_thinking_off.py` | ทดสอบเร็วๆ ว่า client/patch ทำงานถูกต้องก่อนรันจริง |
| `run_confirm_thinking_off.py` | confirmatory re-run ข้อ 2/3 (loss=75%/mitigation=none, 20 trials) |
| `run_confirm_thinking_off_item1.py` | confirmatory re-run ข้อ 1 (`t8ap_loss75` เท่านั้น, 20 trials, วัด achieved-path ด้วย) |
| `run_confirm_thinking_off_item4.py` | confirmatory re-run ข้อ 4 (`t8in_baseline`+`t8in_loss75`, 40 trials, falsification check ในตัว) |

**วิธีอ่านผลรวม:** เทียบ completion rate ที่ได้จาก thinking-off กับผลเดิม
(thinking-on) และ Tier 5 baseline (14/20) ตามตารางด้านบน — ถ้าตัวเลขขยับเข้าใกล้
Tier 5 เดิมมากกว่าใกล้ผล thinking-on เดิม แปลว่า thinking mode คือสาเหตุหลักจริง
สมควรพิจารณารันข้อนั้นใหม่ทั้งชุดด้วย thinking-off ก่อนเขียนผลลงเปเปอร์ —
`run_confirm_thinking_off_item4.py` มีคำตัดสินอัตโนมัติพิมพ์ท้ายการรันอยู่แล้ว
(เทียบ baseline/loss75 คู่กันตามหลัก falsification check เดิมของข้อ 4)

⚠️ ผลจากทั้ง 3 สคริปต์นี้เป็นการรันวินิจฉัย (diagnostic, n=20-40 ต่อสคริปต์)
ไม่ใช่ผลที่เอาไปแทนที่ข้อ 1/2/3/4 เดิมโดยตรง หรือเป็น Tier8 item ใหม่อย่างเป็น
ทางการ — ใช้เพื่อ "ตัดสินใจ" ว่าควรรันข้อไหนใหม่ทั้งชุดเท่านั้น

---

## หลังรันเสร็จ — แปลง log เป็น CSV

ใช้ `Analysis_เบื้องต้น/scripts/parse_logs.py` เดิมของโปรเจกต์ได้ทันที (schema
ของ log ตรงกันเป๊ะ เพราะ `Tier8_EnsureScopeClosure/logger.py` สืบทอดโครงสร้างเดิม
ทั้งหมด เพิ่มแค่ field `agent`/`achieved` ต่อท้าย):

```bash
cd Analysis_เบื้องต้น/scripts
python3 parse_logs.py --log-dir "../../Tier8_EnsureScopeClosure/results_completed/logs_tier8_achieved_path_No.1" \
                      --out ../data/tier8_achieved_path_master.csv
python3 parse_logs.py --log-dir "../../Tier8_EnsureScopeClosure/results_completed/logs_tier8_fixed_fixed_long_timeout_No.2" \
                      --out ../data/tier8_fixed_master.csv
python3 parse_logs.py --log-dir "../../Tier8_EnsureScopeClosure/results_completed/logs_tier8_randomized_mitigation_none" \
                      --out ../data/tier8_randomized_none_master.csv
# (ทำซ้ำสำหรับ _adaptive_timeout_No.3/ และ _context_cache_No.3/)
python3 parse_logs.py --log-dir "../../Tier8_EnsureScopeClosure/results_completed/logs_tier8_ingress_No.4" \
                      --out ../data/tier8_ingress_master.csv
python3 parse_logs.py --log-dir "../../Tier8_EnsureScopeClosure/results_completed/logs_tier8_jitter_floor_No.5" \
                      --out ../data/tier8_jitter_floor_master.csv
```

`parse_logs.py` ไม่รู้จัก field `agent`/`achieved` เป็นคอลัมน์ของตัวเอง (มันดึง
เฉพาะ field มาตรฐานที่มีมาตั้งแต่ Tier1-5) แต่ข้อมูลยังอยู่ครบในไฟล์ JSON ดิบ
ถ้าต้องการ `agent`/`achieved` เป็นคอลัมน์ใน CSV ด้วย ต้อง parse เพิ่มเองจาก JSON
โดยตรง (`logger.data["errors"][i]["agent"]` และ `logger.data["achieved"]`)

**สำคัญ:** อัปเดต `Paper/NetImpact.md/Current/NetImpact_18_Implementation_Verification_Addendum.md`
§11 (ตารางสถิติที่มีอำนาจสูงสุด) ให้ตรงกับผลจริงหลังรันเสร็จ — claim strength
ถูกล็อคไว้แล้วใน File 17/18 ผลใหม่ต้องเขียนตามกฎเดิม ไม่ใช่ตั้งกฎใหม่ให้เข้ากับผล
(หลักการเดียวกับที่ File 20 ของ Tier 7 ระบุไว้)

---

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `logger.py` | สำเนา + แก้ให้มี `agent=None` param จริง (แก้บั๊กของ 7A) + `log_achieved()` (ข้อ 1) |
| `controller.py` | สำเนา + `direction="both"`/IFB (ข้อ 4) + achieved-path measurement methods (ข้อ 1) + `probe_ingress_support()` |
| `multi_agent.py` | สำเนาจาก Tier 7 ปรับเล็กน้อย ใช้ logger.py ใหม่ของ Tier 8 |
| `checkpoint_utils.py` | checkpoint load/save ที่ใช้ร่วมกันโดย run_tier8_*.py ทุกตัว |
| `run_tier8_achieved_path.py` | ข้อ 1 |
| `run_tier8_fixed_timeout.py` | ข้อ 2 |
| `run_tier8_randomized_mitigation.py` | ข้อ 3 |
| `run_tier8_ingress.py` | ข้อ 4 |
| `run_tier8_jitter_floor.py` | ข้อ 5 |
| `run_tier8_batch_1245.sh` | รันข้อ 5, 2, 4, 1 ต่อกันในรวดเดียว (ไม่รวมข้อ 3) |
| `tests_tier8/` | offline test suite (pytest, ไม่แตะ Ollama/tc จริงเลย) |
| `results_completed/` | ✅ ผล log ทั้ง 9 ชุดจาก 5 ข้อหลัก (รันจบแล้ว) |
| `thinking_off_diagnostic/` | ✅ โค้ด+สคริปต์วินิจฉัย/แก้ thinking mode ทั้งหมด — รันจบแล้ว (80 diagnostic trials, ดู README ในนั้น) |

โค้ดที่แก้นอกโฟลเดอร์นี้: **ไม่มีเลย** — additive 100% ทุกไฟล์ที่ root โปรเจกต์
เดิมยังเหมือนเดิมทุกตัวอักษร ตรวจสอบได้ด้วย `git diff`/`diff` ถ้าต้องการยืนยัน
