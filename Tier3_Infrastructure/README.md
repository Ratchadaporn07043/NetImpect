# Tier 3 — โครงสร้างพื้นฐาน (GPU Logging + Dual-Judge LLM Evaluation)

**เป้าหมาย:** ปิด blocking gap 2 ข้อที่ระบุใน `Paper/NetImpact.md/Archive_Legacy/NetImpact_10_AINTEC2026_Readiness_Assessment.md`:
1. ไม่มีข้อมูล GPU/VRAM เลย (มีแค่ CPU/RAM) — วิเคราะห์ resource bottleneck ไม่ครบ
2. ทุก 1,544 trials ใช้ evaluator แบบ `heuristic` (keyword matching) เท่านั้น ไม่เคยรัน LLM-judge จริงเลย — เป็นจุดอ่อนสำคัญที่ reviewer AINTEC จะถามแน่นอน

## ส่วนที่ 1: GPU/VRAM Logging (`logger.py`)

**ต้องแทนที่ไฟล์ root ก่อนรันอะไรก็ตามที่ต้องการ GPU stats:**
```bash
cd NetImpact
cp logger.py logger.py.backup_original
cp "Tier3_โครงสร้างพื้นฐาน/logger.py" logger.py
pip install -r "Tier3_โครงสร้างพื้นฐาน/requirements_gpu.txt"   # ถ้าต้องการ GPU stats จริง
```

ปลอดภัย 100%: ถ้าไม่ติดตั้ง `pynvml`/เครื่องไม่มี NVIDIA GPU → `gpu: null` ในทุก snapshot โดยอัตโนมัติ ไม่ error ไม่ crash โครงสร้าง JSON เดิมยังอยู่ครบ (`test_tier3_logger_gpu.py` ทดสอบทั้ง 2 กรณี)

จากนั้นรัน experiment ตามปกติ (three-day เดิม, Tier1, Tier2 ฯลฯ) — ทุก log ใหม่จะมี key `gpu`/`gpu_all` เพิ่มเข้ามาในทุก `resource_snapshots` entry โดยอัตโนมัติ

## ส่วนที่ 2: Dual-Judge LLM Evaluation

**Step 1 — รัน LLM-judge เต็มรูปแบบบน log ที่มีอยู่แล้วทั้ง 1,544 ไฟล์** (post-hoc, ไม่ apply network/ไม่รัน agent ใหม่):

⚠️ **สำคัญ:** evaluator.py ต้นฉบับจริงอยู่ที่ `experiment/evaluator.py` (ไม่ใช่ root!)
ทุกจุดที่ import (`multi_agent.py`, `experiment/evaluate_logs.py`, `run_dual_judge_sample.py`)
เรียกผ่าน `from experiment.evaluator import ...` ทั้งหมด ต้อง cp ทับไฟล์นี้ที่ตำแหน่งนี้เท่านั้น
(ถ้า cp ไปสร้างเป็น root-level `evaluator.py` แทน จะได้ไฟล์ที่ไม่มีใครเรียกใช้เลย
และ `run_dual_judge_sample.py` จะ crash ด้วย `TypeError: _llm_evaluate() got an
unexpected keyword argument 'judge_model_name'` ทันทีที่รัน เพราะยังใช้
`experiment/evaluator.py` ตัวเดิมที่ไม่มีพารามิเตอร์นี้อยู่):
```bash
cd NetImpact
cp experiment/evaluator.py experiment/evaluator.py.backup_original
cp "Tier3_โครงสร้างพื้นฐาน/evaluator.py" experiment/evaluator.py

cp -r logs_three_day logs_three_day.backup   # backup ก่อนเสมอ! เขียนทับไฟล์เดิม

bash "Tier3_โครงสร้างพื้นฐาน/run_full_llm_judge.sh" logs_three_day --dry-run   # เช็คก่อน
bash "Tier3_โครงสร้างพื้นฐาน/run_full_llm_judge.sh" logs_three_day            # รันจริง (ใช้เวลานาน หลายชม.)
```
ใช้ `experiment/evaluate_logs.py --mode both --all` ที่มีอยู่แล้วเดิม (ไม่ต้องเขียนใหม่) — เขียนผล LLM-judge กลับเข้า field `posthoc_evaluation` ของทุกไฟล์

**Step 2 — วัดว่า LLM-judge เชื่อถือได้แค่ไหน ด้วย dual-judge agreement** (2 โมเดลตรวจไขว้กัน):
```bash
ollama pull llama3.1:8b   # โมเดลที่สอง ต้องต่างจาก agent model (qwen3:8b)

python3 "Tier3_โครงสร้างพื้นฐาน/run_dual_judge_sample.py" \
  --log-dir logs_three_day --sample 200 \
  --judge-a qwen3:8b --judge-b llama3.1:8b \
  --out Tier3_dual_judge_report
```
Read-only ต่อ log เดิม (ไม่เขียนทับ) — output เป็น `dual_judge_report.csv` (ราย trial) + `dual_judge_report_summary.json` (Cohen's kappa, quadratic weighted kappa, Pearson r) คำนวณเองแบบ pure Python ไม่พึ่ง sklearn

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|---|---|
| `logger.py` | **แทนที่** root เดิม — เพิ่ม GPU/VRAM/temperature/power logging (graceful fallback) |
| `evaluator.py` | **แทนที่** `experiment/evaluator.py` เดิม (ไม่ใช่ root!) — เพิ่ม `JUDGE_MODEL_NAME` env var แยกจาก agent model |
| `run_full_llm_judge.sh` | wrapper เรียก `evaluate_logs.py --mode both --all` |
| `run_dual_judge_sample.py` | รัน 2 judge model บน sample เดียวกัน + คำนวณ agreement metrics |
| `requirements_gpu.txt` | dependency `pynvml`/`nvidia-ml-py3` (optional) |

ไม่มี log dir ใหม่สำหรับ Tier3 ส่วนนี้ — ทำงานกับ `logs_three_day/` เดิมโดยตรง (post-hoc) และ log ใหม่จาก Tier1/2/4/5 จะได้ GPU field อัตโนมัติถ้าแทนที่ `logger.py` ไว้แล้ว

## สถานะการรัน

✅ dual-judge รันเสร็จแล้ว — sample 200/200, 0 ไฟล์เสีย, elapsed ≈ 5.2 ชม.
GPU/VRAM logging (`logger.py`) ทำงานถูกต้อง (graceful fallback ยืนยันแล้ว) — field `gpu` จะเริ่มปรากฏใน log ตั้งแต่ Tier4/5 เป็นต้นไป

ผลการวิเคราะห์แบบละเอียด (dual-judge agreement ต่ำ, การวินิจฉัย leniency bias ของ judge B) พร้อมสถิติและการตีความเต็มรูปแบบ รวมไว้ใน
`Paper/NetImpact.md/Current/NetImpact_03_Tier3_Evaluator_Validity.md` แล้ว — ไฟล์นี้เก็บไว้เฉพาะวิธีรันโค้ดและสถานะการรันเท่านั้น
กราฟดิบอยู่ที่ `Analysis_เบื้องต้น/charts/tier3/`
