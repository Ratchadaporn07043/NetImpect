"""
run_tier6_mitigation_multiround.py — ทดสอบ Mitigation A/B กับจุดที่ Tier2 พบว่าแย่สุด
================================================================================================
บริบท: Tier2 (`Tier2_แกนใหม่/run_tier2_multiround.py`) รัน hard tasks +
strict_reviewer=True แล้วพบว่า success rate โดยรวมตกจาก ~100% (single-pass เดิม)
เหลือ 83.75% และ **moderate_delay คือ scenario ที่แย่ที่สุด (75%)** — ต่ำกว่า
baseline (95%) high_loss (85%) และ combined_bad (80%) เสียอีก แสดงว่า delay
สะสมผลข้ามรอบสนทนาได้ ทั้งที่ main-effect เดิม (single-pass) ไม่เห็นผลของ delay
เลย (ดู Tier2_แกนใหม่/README.md ส่วน "ผลที่ได้" และ
Analysis_เบื้องต้น/analysis/findings.md ข้อ 7-8)

Tier5 (`Tier5_Mitigation/run_tier5_mitigation_comparison.py`) พิสูจน์แล้วว่า
adaptive_timeout แก้ loss cliff ได้จริง (70%->100% ที่ loss=75%, p=0.020) แต่
Tier5 ทดสอบบนแกน loss เดี่ยวๆ แบบ single-pass (strict_reviewer=False) เท่านั้น
ไม่เคยทดสอบกับสถานการณ์ multi-round ที่ Tier2 พบปัญหาเลย

Tier6 นี้จึงเชื่อม 2 finding ที่แข็งแรงที่สุดของโปรเจกต์เข้าด้วยกัน: เอา
mitigation ของ Tier5 (adaptive_timeout / context_cache) ไปทดสอบกับ
scenario+task ที่ทำให้เกิด multi-round ปัญหาสุดของ Tier2 (moderate_delay +
hard tasks + strict_reviewer=True) เพื่อดูว่า mitigation ที่พิสูจน์แล้วว่าช่วย
แกน loss จะช่วยแกน "delay สะสมข้ามรอบสนทนา" ได้ด้วยหรือไม่ — เป็นคำถามที่ต่าง
จาก Tier5 เดิมโดยสิ้นเชิง (Tier5 ตอบว่า "mitigation ช่วยแกน loss ไหม" ส่วนนี้
ตอบว่า "mitigation ช่วยปัญหา multi-round/delay ไหม")

⚠️ ก่อนรันสคริปต์นี้ ต้อง "แทนที่" multi_agent.py ที่ root โปรเจกต์ด้วย
   Tier6_MitigationXMultiRound/multi_agent.py ก่อน (สำรองไฟล์เดิมไว้ด้วย!
   ไฟล์นี้เหมือนกับ Tier5_Mitigation/multi_agent.py ทุกประการ ใช้แทนกันได้จริง
   แต่ยังต้อง cp ตามขั้นตอนปกติเพื่อความชัดเจนและเพื่อให้ inspect.signature
   guard ด้านล่างเช็คได้ตรง):

    cd NetImpact
    cp multi_agent.py multi_agent.py.backup_original
    cp "Tier6_MitigationXMultiRound/multi_agent.py" multi_agent.py

สคริปต์นี้:
  1. เช็คก่อนว่า multi_agent.py ที่ import ได้รองรับ "ทั้ง" strict_reviewer และ
     mitigation/network_condition จริง (กัน user ลืมขั้นตอนด้านบน หรือ cp ไฟล์
     ผิดเวอร์ชัน เช่น cp Tier2 เดิมที่มีแค่ strict_reviewer ไม่มี mitigation)
  2. merge TIER2_HARD_TASK_GROUND_TRUTH เข้ากับ experiment.tasks.TASK_GROUND_TRUTH
     เหมือนที่ Tier2 ทำ (import task/ground-truth ตรงจาก Tier2_แกนใหม่/ เลย
     ไม่ duplicate นิยาม task ซ้ำ)
  3. รัน 2 scenario ตัวแทน (baseline = control, moderate_delay = จุดที่ Tier2
     พบว่าแย่สุด — ค่า delay/jitter/loss เหมือน Tier2 เป๊ะเพื่อเทียบกันได้ตรง)
     x 2 hard tasks x 10 repeats (เท่า Tier2 เพื่อเทียบ n ตรงกัน) x 3 เงื่อนไข
     mitigation (none / adaptive_timeout / context_cache) x strict_reviewer=True
     เสมอ = 2x2x10x3 = 120 trials ทั้งหมด เขียน log แยกโฟลเดอร์ต่อเงื่อนไข
     (logs_tier6_none/, logs_tier6_adaptive_timeout/, logs_tier6_context_cache/)

ทำไมเลือกแค่ baseline+moderate_delay (ไม่รวม high_loss/combined_bad ของ Tier2
ด้วย): นี่เป็น optional stretch experiment ภายใต้ deadline ที่ตึงมาก
(ดู Paper/NetImpact.md/Archive_Legacy/NetImpact_10_AINTEC2026_Readiness_Assessment.md
สำหรับบริบท timeline เดิม — ไฟล์ย้ายมาจาก Docs/ แล้ว) โจทย์เฉพาะเจาะจงคือ "mitigation
ช่วย multi-round/moderate_delay ไหม" — moderate_delay คือจุดที่แย่สุดและเป็น
จุดที่ contribution ของ paper แข็งแรงที่สุดถ้าพิสูจน์ได้ ส่วน baseline ใช้เป็น
control กลุ่มเทียบ (ไม่มี impairment แต่ยังมี strict_reviewer เพื่อแยกผลของ
"reviewer เข้มงวด" ออกจากผลของ "delay" ให้ชัดเจน) — ถ้ามีเวลาเหลือหลัง full
paper submission ค่อยขยายไป high_loss/combined_bad ทีหลังได้ (โครงสร้างโค้ด
รองรับอยู่แล้ว แค่เพิ่ม scenario เข้า TEST_SCENARIOS ด้านล่าง)

วิธีรัน:
    python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --dry-run
    python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition none --resume
    python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition adaptive_timeout --resume
    python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition context_cache --resume
    python3 "Tier6_MitigationXMultiRound/run_tier6_mitigation_multiround.py" --condition all --resume   # 120 trials รวด
"""
import argparse
import inspect
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get("NETIMPACT_PROJECT_ROOT", os.path.dirname(_THIS_DIR))
_TIER2_DIR = os.path.join(_PROJECT_ROOT, "Tier2_แกนใหม่")

# สำคัญ (เหมือน Tier2's run_tier2_multiround.py): ต้องแทรก _THIS_DIR และ
# _TIER2_DIR ก่อน แล้วค่อยแทรก _PROJECT_ROOT ทีหลัง เพื่อให้ _PROJECT_ROOT ไป
# อยู่ที่ index 0 (priority สูงสุด) — ทั้งโฟลเดอร์นี้และ Tier2_แกนใหม่/ ต่างก็มี
# multi_agent.py ของตัวเอง ถ้า path พวกนี้มี priority สูงกว่า _PROJECT_ROOT แล้ว
# guard ด้านล่างจะ import multi_agent.py ผิดไฟล์เสมอ (เช็คไม่ได้จริงว่า root
# ถูก cp ตามคำแนะนำหรือยัง)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
if _TIER2_DIR not in sys.path:
    sys.path.insert(0, _TIER2_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from experiment.controller import NetworkController  # noqa: E402
from experiment.run_experiment import (  # noqa: E402
    _network_result_problems,
    _log_network_result,
    _load_checkpoint,
    _mark_completed,
    _should_skip_trial,
    _trial_key,
    _open_progress,
    _print_dry_run_summary,
    _with_phase,
)
from logger import ExperimentLogger  # noqa: E402
import experiment.tasks as experiment_tasks  # noqa: E402

# ดึง hard tasks + ground truth ของ Tier2 มาใช้ตรงๆ (ไม่ duplicate นิยามซ้ำ)
from tier2_tasks_multiround import TIER2_HARD_TASKS, TIER2_HARD_TASK_GROUND_TRUTH  # noqa: E402

CONDITIONS = ["none", "adaptive_timeout", "context_cache"]
REPEATS = 10  # เท่ากับ Tier2's run_tier2_multiround.py เพื่อให้เทียบ n ต่อ scenario/task ตรงกันได้

# scenario เดียวกับ Tier2's TEST_SCENARIOS (ค่า delay/jitter/loss เป๊ะ) — เอา
# แค่ baseline (control) กับ moderate_delay (จุดที่ Tier2 พบว่า multi-round
# แย่สุด, success 75%) มาทดสอบ mitigation คู่กัน ตั้งชื่อ "t6_" กันสับสนกับ
# ไฟล์ log ของ Tier2 เดิม (คนละ phase/log_dir อยู่แล้วก็ไม่ชนกัน แต่ตั้งชื่อ
# แยกให้ชัดเจนกว่าตอนไล่อ่าน log ทีหลัง)
TEST_SCENARIOS = [
    {"name": "t6_baseline", "delay_ms": 0, "requested_delay_ms": 0, "jitter_ms": 0, "loss_pct": 0, "note": ""},
    {"name": "t6_moderate_delay", "delay_ms": 300, "requested_delay_ms": 300, "jitter_ms": 0, "loss_pct": 0, "note": ""},
]


def _verify_multi_agent_supports_strict_reviewer_and_mitigation():
    """เข้มงวดกว่า Tier2/Tier5 เดี่ยวๆ: ต้องเช็คว่ารองรับ 'ทั้งสาม' พารามิเตอร์
    พร้อมกัน (strict_reviewer, mitigation, network_condition) เพราะ Tier6 เป็น
    จุดแรกที่ใช้ strict_reviewer=True กับ mitigation!='none' พร้อมกันจริง —
    ถ้า user เผลอ cp multi_agent.py ของ Tier2 เดิม (มีแค่ strict_reviewer ไม่มี
    mitigation) มาแทน จะ error ชัดเจนแทนที่จะรันไปแล้วพัง/ได้ mitigation="none"
    แบบเงียบๆ โดยไม่รู้ตัว"""
    import multi_agent  # import เดียวกับที่ project จริงจะใช้ (root ของ project)
    sig = inspect.signature(multi_agent.run_multi_agent_task)
    missing = [p for p in ("strict_reviewer", "mitigation", "network_condition") if p not in sig.parameters]
    if missing:
        raise RuntimeError(
            f"multi_agent.py ที่ root โปรเจกต์ยังไม่รองรับพารามิเตอร์: {missing}\n"
            "Tier6 ต้องการ multi_agent.py แบบ 'สะสม' (รองรับ strict_reviewer "
            "จาก Tier2 และ mitigation จาก Tier5 พร้อมกัน) กรุณาแทนที่ไฟล์ก่อน:\n"
            "  cp multi_agent.py multi_agent.py.backup_original\n"
            '  cp "Tier6_MitigationXMultiRound/multi_agent.py" multi_agent.py'
        )
    return multi_agent


def _merge_hard_task_ground_truth():
    experiment_tasks.TASK_GROUND_TRUTH.update(TIER2_HARD_TASK_GROUND_TRUTH)


def run_single_trial_mitigation_multiround(net: NetworkController, scenario: dict, task_name: str,
                                            task_prompt: str, run_index: int, log_dir: str,
                                            mitigation: str, multi_agent_module):
    """เหมือน Tier5's run_single_trial_mitigation() ทุกประการ ยกเว้นเพิ่ม
    strict_reviewer=True เข้าไปในการเรียก run_multi_agent_task() ด้วย (Tier5
    เดิมไม่เคยส่ง strict_reviewer เลย จึงเป็น False ตลอด = single-pass)"""
    print(f"  [{scenario['name']}] task={task_name} run={run_index} mitigation={mitigation} "
          f"strict_reviewer=True -> delay={scenario['delay_ms']}ms loss={scenario['loss_pct']}%")

    logger = ExperimentLogger(scenario=scenario, task_name=task_name,
                               run_index=run_index, log_dir=log_dir)

    apply_result = net.apply(
        delay_ms=scenario["delay_ms"],
        jitter_ms=scenario["jitter_ms"],
        loss_pct=scenario["loss_pct"],
        bandwidth_kbit=scenario.get("bandwidth_kbit"),
    )
    _log_network_result(logger, action="apply", result=apply_result)

    apply_problems = _network_result_problems("apply", apply_result)
    if apply_problems:
        logger.log_error(error_type="invalid_trial", detail="network apply failed; skipped LLM run")
        elapsed = time.time() - logger.start_time
        logger.log_outcome(success=False, rounds=0, rejections=0, elapsed_seconds=elapsed)
        print("    -> INVALID TRIAL: network apply failed, skipped LLM run")
    else:
        try:
            result = multi_agent_module.run_multi_agent_task(
                task_prompt, logger=logger, task_name=task_name,
                strict_reviewer=True, mitigation=mitigation, network_condition=scenario,
            )
            print(f"    -> success={result['success']} rounds={result['rounds']} "
                  f"rejections={result['rejections']} reviewer_score={result.get('quality_score')} "
                  f"ground_truth_score={result.get('ground_truth_score')} "
                  f"elapsed={result['elapsed_seconds']}s")
        except Exception as e:
            logger.log_error(error_type="fatal_error", detail=str(e)[:300])
            elapsed = time.time() - logger.start_time
            logger.log_outcome(success=False, rounds=0, rejections=0, elapsed_seconds=elapsed)
            print(f"    -> FATAL ERROR: {e}")

    clear_result = net.clear()
    _log_network_result(logger, action="clear", result=clear_result)

    filepath = logger.save()
    print(f"    -> log saved: {filepath}")
    return filepath


def _run_condition(net, condition, tasks, log_dir, resume, multi_agent_module):
    total_trials = len(TEST_SCENARIOS) * len(tasks) * REPEATS
    print(f"\n######## Condition: mitigation={condition} (strict_reviewer=True, {total_trials} trials) ########")

    checkpoint = _load_checkpoint(log_dir) if resume else None
    if resume:
        print(f"เปิด resume mode: พบ completed trials เดิม {len(checkpoint.get('completed', {}))} รายการ")

    trial_state = {"count": 0}
    progress_bar = _open_progress(total_trials, f"tier6_{condition}")
    phase = f"tier6_mitigation_multiround__{condition}"
    try:
        for repeat_index in range(1, REPEATS + 1):
            print(f"\n######## Repeat {repeat_index}/{REPEATS} (mitigation={condition}) ########")
            for base_scenario in TEST_SCENARIOS:
                scenario = _with_phase(base_scenario, phase)
                for task_name, task_prompt in tasks.items():
                    trial_state["count"] += 1
                    trial_key = _trial_key(phase, scenario, task_name, repeat_index)
                    print(f"\n=== Trial {trial_state['count']}/{total_trials} (mitigation={condition}) ===")
                    if _should_skip_trial(resume, checkpoint, trial_key):
                        print(f"  [SKIP] completed checkpoint: {trial_key}")
                        if progress_bar is not None:
                            progress_bar.update(1)
                        continue
                    trial_scenario = dict(scenario)
                    trial_scenario["trial_key"] = trial_key
                    log_file = run_single_trial_mitigation_multiround(
                        net, trial_scenario, task_name, task_prompt, repeat_index, log_dir,
                        condition, multi_agent_module,
                    )
                    if checkpoint is not None:
                        _mark_completed(log_dir, checkpoint, trial_key, log_file)
                    if progress_bar is not None:
                        progress_bar.update(1)
    finally:
        if progress_bar is not None:
            progress_bar.close()


def main(condition_arg: str, iface: str, log_dir_prefix: str, dry_run: bool, resume: bool):
    conditions = CONDITIONS if condition_arg == "all" else [condition_arg]
    tasks = TIER2_HARD_TASKS
    per_condition_trials = len(TEST_SCENARIOS) * len(tasks) * REPEATS

    print("=== Tier 6: Mitigation x Multi-Round (moderate_delay, Tier2's worst scenario) ===")
    print(f"  {len(TEST_SCENARIOS)} scenarios (baseline/moderate_delay) x {len(tasks)} hard tasks "
          f"x {REPEATS} repeats = {per_condition_trials} trials ต่อเงื่อนไข")
    for c in conditions:
        print(f"  - mitigation={c} (strict_reviewer=True): {per_condition_trials} trials -> {log_dir_prefix}_{c}/")
    print(f"รวม {per_condition_trials * len(conditions)} trials")

    if dry_run:
        _print_dry_run_summary(per_condition_trials * len(conditions))
        return

    multi_agent_module = _verify_multi_agent_supports_strict_reviewer_and_mitigation()
    _merge_hard_task_ground_truth()

    net = NetworkController(iface=iface)
    start = time.time()

    for condition in conditions:
        log_dir = f"{log_dir_prefix}_{condition}"
        _run_condition(net, condition, tasks, log_dir, resume, multi_agent_module)

    elapsed = time.time() - start
    print(f"\nเสร็จสิ้น Tier6 mitigation x multiround ทั้งหมด ใช้เวลารวม {elapsed/60:.1f} นาที")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tier6: mitigation x multi-round (moderate_delay) comparison")
    parser.add_argument("--condition", choices=CONDITIONS + ["all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--log-dir-prefix", default="logs_tier6")
    args = parser.parse_args()

    main(condition_arg=args.condition, iface=args.iface, log_dir_prefix=args.log_dir_prefix,
         dry_run=args.dry_run, resume=args.resume)
