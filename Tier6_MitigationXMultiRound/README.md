# Tier 6 — Mitigation × Multi-Round (optional stretch experiment)

**Status:** ✅ Completed - 120/120 trials, 0 corrupted files. This was an **optional stretch** experiment beyond the five main tiers. Results are summarized below, with full details in
`Paper/NetImpact.md/Current/NetImpact_06_Tier6_Pending_Experiment.md` (the filename still contains
"Pending" to preserve links from other documents; its contents are completed results, not an unrun plan.)

## Goal

Connect the two strongest findings in the project:

1. **Tier2 finding:** With hard tasks and `strict_reviewer=True`, overall success fell from ~100% to 83.75%. **`moderate_delay` (delay=300ms) was worst at 75%**, below baseline (95%), high_loss (85%), and combined_bad (80%), showing that delay accumulates across rounds.
2. **Tier5 finding:** `adaptive_timeout` significantly improved the loss cliff (70% to 100% at loss=75%, Fisher p=0.020), but was tested only in single-pass mode (`strict_reviewer=False`).

**Tier6 question:** Can a mitigation proven to help the single-pass loss axis also help Tier2's multi-round accumulated-delay problem? No previous tier had called `strict_reviewer=True` and `mitigation=<...>` together.

If effective, the paper can show that the mitigation generalizes from the loss cliff to a distinct multi-round delay problem. If not, the result still clarifies the mitigation boundary and supports a limitation or future-work statement.

## Why This Scope (Not Full Factorial)

Test only two necessary scenarios: `baseline` (control, with strict review but no network impairment) and `moderate_delay` (Tier2's worst point at delay=300ms). `high_loss` and `combined_bad` are excluded because the specific target is moderate_delay. More scenarios can be added to `TEST_SCENARIOS` later.

## ⚠️ Pre-Run Steps

```bash
cd NetImpact
cp multi_agent.py multi_agent.py.backup_original   # Always back up the original.
cp "Tier6_MitigationXMultiRound/multi_agent.py" multi_agent.py
```

This file is a 1:1 copy of `Tier5_Mitigation/multi_agent.py` and keeps Tier6 self-contained. It supports `strict_reviewer` from Tier2 and `mitigation`/`network_condition` from Tier5 **together**. Defaults remain (`strict_reviewer=False`, `mitigation="none"`), preserving original behavior when omitted.

`run_tier6_mitigation_multiround.py` automatically verifies that the root `multi_agent.py` supports all three parameters. Copying the wrong file produces a clear error before execution.

## How to Run

```bash
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --dry-run

# Run one condition at a time (recommended; --resume is safe after interruption):
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition none --resume             # control; mitigation disabled
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition adaptive_timeout --resume  # Mitigation A
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition context_cache --resume     # Mitigation B

# Or run all three conditions at once (120 trials total).
python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition all --resume
```

Trial count: 2 scenarios x 2 hard tasks borrowed directly from Tier2 x 10 repeats = **40 trials per condition** x 3 conditions = **120 total trials**.

Logs are separated into `logs_tier6_none/`, `logs_tier6_adaptive_timeout/`, and `logs_tier6_context_cache/`. Compare:

- success rate at `t6_moderate_delay` (none vs adaptive_timeout vs context_cache), the main question
- success rate at `t6_baseline`, which should be similar across all three conditions
- mean `reviewer_rejections` per trial at `t6_moderate_delay`
- mean `elapsed_seconds`, the time cost of mitigation

**Code note (inherited from Tier5):** `mitigation` is included in the return dict but not written to JSON because `logger.log_outcome()` does not accept it. This does not affect analysis because Tier6 uses separate condition directories and `network_condition.experiment_phase` identifies each condition.

## Files in This Folder

| File | Purpose |
|---|---|
| `multi_agent.py` | 1:1 copy of `Tier5_Mitigation/multi_agent.py`; **replaces** the root version and combines Tier2 `strict_reviewer` with Tier5 mitigations. |
| `run_tier6_mitigation_multiround.py` | Runs the comparison on `t6_baseline` and `t6_moderate_delay` using Tier2 hard tasks and `strict_reviewer=True`. |

There are no local task/scenario definitions. The runner imports `TIER2_HARD_TASKS` and `TIER2_HARD_TASK_GROUND_TRUTH` directly from `Tier2_NewAxis/tier2_tasks_multiround.py`.

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
