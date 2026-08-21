# Test Suite — Tier1-6 Extension Code

Test suite นี้เช็คความถูกต้องของโค้ดทั้ง 6 Tier **แบบ offline ทั้งหมด** — ไม่ต้องมี Ollama/GPU/tc รันอยู่จริงเลย รันได้ทุกเครื่อง เร็ว (<3 วินาที) เหมาะรันซ้ำได้ทุกครั้งก่อนเอาโค้ดไปใช้จริงบนเครื่องที่มี infra ครบ

## วิธีติดตั้ง/วางไฟล์

คัดลอกโฟลเดอร์ `tests/` (แนะนำเปลี่ยนชื่อเป็น `tests_extended/` กันสับสนกับ test อื่นในอนาคต) ไปวางที่ root ของโปรเจกต์ NetImpact — **ระดับเดียวกับ** `multi_agent.py`, `logger.py`, `experiment/`, และโฟลเดอร์ Tier1-6 ทั้งหมด:

```
NetImpact/
  multi_agent.py
  logger.py
  experiment/
  Tier1_เจาะจุดในแกนที่มีอยู่/
  Tier2_แกนใหม่/
  Tier3_โครงสร้างพื้นฐาน/
  Tier4_Replication/
  Tier5_Mitigation/
  Tier6_MitigationXMultiRound/
  tests_extended/          <- โฟลเดอร์นี้
    conftest.py
    fake_autogen.py
    test_*.py
```

## วิธีรัน

```bash
cd NetImpact
pip install pytest --break-system-packages   # ถ้ายังไม่มี pytest
python3 -m pytest tests_extended/ -v
```

ควรได้ `82 passed` (หรือมากกว่า ถ้ามีการเพิ่มเทสทีหลัง)

## ทดสอบอะไรบ้าง

| ไฟล์ | ทดสอบ |
|---|---|
| `test_tier1_scenarios.py` | scenario ใหม่ของ Tier1 (loss cliff/delay extended/jitter extended/delay recheck) ถูกต้อง ไม่ชนกับของเดิม |
| `test_tier2_scenarios_bandwidth.py` | bandwidth scenario สร้างถูกต้อง ใช้ key `bandwidth_kbit` ตรงกับที่ controller.py อ่าน |
| `test_tier2_tasks_multiround.py` | hard task + ground truth spec ครบถ้วน merge เข้ากับของเดิมได้ |
| `test_tier2_multi_agent_strict_reviewer.py` | strict_reviewer ทำงานถูกต้อง (offline ผ่าน fake_autogen) รวมถึง retry/timeout logic |
| `test_tier3_logger_gpu.py` | GPU logging fallback ปลอดภัยทั้งกรณีมี/ไม่มี pynvml/GPU/driver error |
| `test_tier3_evaluator_dual_judge.py` | JUDGE_MODEL_NAME แยกจาก agent model ได้ถูกต้อง, backward compatible |
| `test_tier4_replication.py` | scenario/repeat count และ model dirname sanitization ถูกต้อง |
| `test_tier5_multi_agent_mitigation.py` | adaptive timeout formula, context caching skip-planner logic |
| `test_tier6_mitigation_multiround.py` | `multi_agent.py` ของ Tier6 รองรับ `strict_reviewer`+`mitigation`+`network_condition` พร้อมกันจริง, guard เช็ค version ทำงานถูกต้อง, `TEST_SCENARIOS` ตรงกับ Tier2, runner script import ได้ไม่ error |
| `test_controller_bandwidth.py` | `NetworkController.apply()` ต้นฉบับ ออกคำสั่ง tc/tbf ถูกต้องสำหรับ bandwidth (precondition ของ Tier2) |
| `test_tier_runners_import.py` | ทุก runner script/shell script/README มีอยู่จริง import ได้ไม่ error |
| **`test_baseline_regression.py`** | **สำคัญที่สุด** — ยืนยันว่า multi_agent.py เวอร์ชัน Tier2/Tier5 ให้ผลเหมือนต้นฉบับ 100% เมื่อเรียกด้วย default parameter (พิสูจน์คำสัญญาที่เขียนไว้ในทุก README ว่า "ปลอดภัยที่จะแทนที่ไฟล์") |

## เทคนิคที่ใช้

- **`fake_autogen.py`**: stub เลียนแบบ `pyautogen` (ConversableAgent/GroupChat/GroupChatManager) แบบ scriptable/deterministic — เขียน test scenario เช่น "Reviewer REVISE แล้วค่อย APPROVED" หรือ "Worker throw TimeoutError" ได้ตรงๆ ผ่าน `fake_autogen.set_script(agent_name, [...])`
- **`mock_tc` fixture**: monkeypatch `subprocess.run` กัน `tc`/`netem` จริงถูกเรียกตอนเทส `controller.py`
- **`load_module_from_path()`**: โหลดไฟล์ `.py` เดียวกันชื่อ (เช่น `multi_agent.py` ของ base/Tier2/Tier5) เป็นคนละ module พร้อมกันได้ โดยไม่ชนกันใน `sys.modules` — จำเป็นเพราะต้องเทียบพฤติกรรมของหลายเวอร์ชันในเทสเดียวกัน (ดู `test_baseline_regression.py`)

## ข้อจำกัด (บอกไว้ตรงๆ)

Test suite นี้ทดสอบ **logic/wiring/backward-compatibility** เท่านั้น (การนับ round, การ parse score, scenario generation, parameter threading ฯลฯ) — **ไม่ได้** ทดสอบว่าโมเดล LLM จริงตอบคำถามได้ดีแค่ไหน หรือ tc/netem apply บน network interface จริงทำงานถูกต้องไหม (ต้องทดสอบเหล่านั้นด้วยการรันจริงบนเครื่องที่มี infra ครบ เช่น `--dry-run` ก่อน แล้วค่อยรันจริงทีละ tier เล็กๆ)
