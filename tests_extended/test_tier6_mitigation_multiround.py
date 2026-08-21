"""Tier6 (mitigation x multi-round) tests — offline ผ่าน fake_autogen ทั้งหมด

ต่างจาก test_tier2_multi_agent_strict_reviewer.py และ
test_tier5_multi_agent_mitigation.py ตรงที่ไฟล์นี้เน้นทดสอบ **การเรียกใช้
strict_reviewer และ mitigation พร้อมกัน** ซึ่งเป็นจุดใหม่ที่ Tier6 เพิ่มเข้ามา
(ไม่มี Tier ไหนก่อนหน้าเคยเรียกสองพารามิเตอร์นี้พร้อมกันจริง) — ถ้า multi_agent.py
ของ Tier6 มี regression ที่ทำให้พารามิเตอร์ใดพารามิเตอร์หนึ่งถูก "เมิน" เมื่อใช้
คู่กับอีกอัน (เช่น bug ที่พบบ่อย: เผลอ hardcode strict_reviewer=False ใน
_attempt_once ระหว่าง merge) เทสกลุ่มนี้จะจับได้ทันที
"""
import inspect
import os

import fake_autogen
from conftest import TIER_DIRS, load_module_from_path

TIER6_DIR = TIER_DIRS["tier6"]
TIER2_DIR = TIER_DIRS["tier2"]


def _load_tier6_multi_agent():
    return load_module_from_path("tier6_multi_agent_under_test", os.path.join(TIER6_DIR, "multi_agent.py"))


def _load_tier6_runner():
    return load_module_from_path(
        "tier6_runner_under_test",
        os.path.join(TIER6_DIR, "run_tier6_mitigation_multiround.py"),
    )


# ---------- multi_agent.py: รองรับทั้งสองพารามิเตอร์พร้อมกัน (ไม่ใช่แค่มี signature) ----------

def test_signature_has_strict_reviewer_and_mitigation_with_safe_defaults():
    mod = _load_tier6_multi_agent()
    sig = inspect.signature(mod.run_multi_agent_task)
    assert sig.parameters["strict_reviewer"].default is False
    assert sig.parameters["mitigation"].default == "none"
    assert sig.parameters["network_condition"].default is None


def test_identical_to_tier5_multi_agent_logic_except_intentional_timeout_default():
    """Tier6 เป็นสำเนา 1:1 ของ Tier5 ทุกจุด ยกเว้น 1 อย่างที่ต่างกันโดยตั้งใจ:
    BASE_LLM_TIMEOUT default (Tier6=600 ตรงกับ config จริงที่ Tier2 ใช้รัน
    moderate_delay, Tier5=120 default เดิม) — ดูคอมเมนต์ "TIER6 CHANGE" ใน
    Tier6's multi_agent.py เทสนี้ยืนยันว่าทุกอย่าง "อื่น" ยังเหมือนกันเป๊ะ
    และ _adaptive_timeout_seconds() ยังใช้สูตรเดียวกัน (ต่างกันแค่ที่ base)"""
    tier6 = _load_tier6_multi_agent()
    tier5 = load_module_from_path(
        "tier5_multi_agent_for_comparison", os.path.join(TIER_DIRS["tier5"], "multi_agent.py")
    )
    assert tier6.VALID_MITIGATIONS == tier5.VALID_MITIGATIONS
    assert tier6.REVIEWER_SYSTEM_MESSAGE_STRICT == tier5.REVIEWER_SYSTEM_MESSAGE_STRICT
    assert tier6.REVIEWER_SYSTEM_MESSAGE_DEFAULT == tier5.REVIEWER_SYSTEM_MESSAGE_DEFAULT

    # จุดต่างที่ตั้งใจ: Tier6 default=600, Tier5 default=120 (คนละ config จริง)
    assert tier6.BASE_LLM_TIMEOUT == 600
    assert tier5.BASE_LLM_TIMEOUT == 120
    assert tier6.BASE_LLM_TIMEOUT != tier5.BASE_LLM_TIMEOUT

    # แต่สูตรขยาย timeout ("extra" ที่บวกเพิ่มจาก base) ต้องเหมือนกันเป๊ะ ต่างกัน
    # แค่ base ตั้งต้นเท่านั้น (ไม่ใช่ copy โค้ดผิดจน logic การคำนวณเพี้ยนไปด้วย)
    same_network = {"delay_ms": 500, "loss_pct": 20, "jitter_ms": 10}
    tier6_extra = tier6._adaptive_timeout_seconds(same_network) - tier6.BASE_LLM_TIMEOUT
    tier5_extra = tier5._adaptive_timeout_seconds(same_network) - tier5.BASE_LLM_TIMEOUT
    assert tier6_extra == tier5_extra


def test_strict_reviewer_and_adaptive_timeout_both_take_effect_together():
    """หัวใจของ Tier6: เรียก strict_reviewer=True + mitigation='adaptive_timeout'
    พร้อมกัน แล้วต้องเห็นผลของ *ทั้งคู่* ในการเรียก build_agents ครั้งเดียวกัน
    (reviewer message ต้องเป็นแบบเข้มงวด และ timeout ต้องถูกขยายตาม network_condition)
    """
    mod = _load_tier6_multi_agent()
    captured = []
    original_build_agents = mod.build_agents

    def _spy(strict_reviewer=False, timeout_seconds=None):
        captured.append((strict_reviewer, timeout_seconds))
        return original_build_agents(strict_reviewer=strict_reviewer, timeout_seconds=timeout_seconds)

    mod.build_agents = _spy
    try:
        mod.run_multi_agent_task(
            "โจทย์ทดสอบ", task_name="coding_task_hard",
            strict_reviewer=True, mitigation="adaptive_timeout",
            network_condition={"delay_ms": 300, "loss_pct": 0, "jitter_ms": 0},
        )
    finally:
        mod.build_agents = original_build_agents

    assert len(captured) >= 1
    strict_used, timeout_used = captured[0]
    expected_timeout = mod._adaptive_timeout_seconds({"delay_ms": 300, "loss_pct": 0, "jitter_ms": 0})
    assert strict_used is True, "strict_reviewer ต้องเป็น True จริง ไม่ถูกเมินเมื่อใช้คู่กับ mitigation"
    assert timeout_used == expected_timeout, "adaptive_timeout ต้องคำนวณจริง ไม่ถูกเมินเมื่อใช้คู่กับ strict_reviewer"
    assert timeout_used > mod.BASE_LLM_TIMEOUT


def test_strict_reviewer_reflected_in_reviewer_system_message_regardless_of_mitigation():
    """ตรวจตรงๆ ผ่าน build_agents ว่า reviewer ได้ system_message เข้มงวดจริง
    ไม่ว่าจะเปิด mitigation อันไหนอยู่ก็ตาม (strict_reviewer ไม่ควรถูกกระทบจาก
    mitigation เลย เพราะเป็นคนละ concern กัน)"""
    mod = _load_tier6_multi_agent()
    for timeout_val in (None, mod._adaptive_timeout_seconds({"delay_ms": 300, "loss_pct": 0, "jitter_ms": 0})):
        _, _, reviewer = mod.build_agents(strict_reviewer=True, timeout_seconds=timeout_val)
        assert reviewer.system_message == mod.REVIEWER_SYSTEM_MESSAGE_STRICT


def test_strict_reviewer_and_context_cache_both_take_effect_together():
    """เหมือน adaptive_timeout แต่กับ Mitigation B: strict_reviewer=True ต้องยัง
    ทำงาน (นับ rejection ได้ถูกต้อง) แม้ระหว่างนั้นจะข้าม Planner ไปด้วย context_cache"""
    mod = _load_tier6_multi_agent()
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "คำตอบสุดท้ายหลัง retry"])

    captured_strict_flags = []
    original_attempt_once = mod._attempt_once

    def _spy_attempt_once(task_prompt, max_rounds, logger=None, strict_reviewer=False,
                           timeout_seconds=None, cached_plan=None):
        captured_strict_flags.append(strict_reviewer)
        return original_attempt_once(task_prompt, max_rounds, logger, strict_reviewer,
                                      timeout_seconds, cached_plan)

    mod._attempt_once = _spy_attempt_once
    try:
        result = mod.run_multi_agent_task(
            "โจทย์ทดสอบ", task_name="coding_task_hard",
            strict_reviewer=True, mitigation="context_cache",
        )
    finally:
        mod._attempt_once = original_attempt_once

    # ทั้ง attempt แรก (ล้มเหลว, ไม่มี cached_plan) และ attempt ที่สอง (สำเร็จ,
    # มี cached_plan ข้าม Planner) ต้องเห็น strict_reviewer=True เหมือนกันหมด
    assert len(captured_strict_flags) == 2
    assert all(flag is True for flag in captured_strict_flags)
    assert result["success"] is True
    assert result["mitigation"] == "context_cache"


def test_default_call_with_no_params_matches_original_baseline_behavior():
    """regression กันเผลอเปลี่ยน default พฤติกรรมของ call site เดิม (Tier1/
    Tier3/Tier4/experiment เดิม) ที่เรียก run_multi_agent_task() โดยไม่ส่ง
    strict_reviewer/mitigation เลย"""
    mod = _load_tier6_multi_agent()
    result = mod.run_multi_agent_task("โจทย์ทดสอบ", task_name="coding_task")
    assert result["success"] is True
    assert result["mitigation"] == "none"
    assert result["retries"] == 0


def test_invalid_mitigation_value_still_raises_even_with_strict_reviewer():
    mod = _load_tier6_multi_agent()
    import pytest
    with pytest.raises(ValueError):
        mod.run_multi_agent_task(
            "โจทย์", task_name="coding_task_hard", strict_reviewer=True, mitigation="not_a_real_mitigation"
        )


# ---------- run_tier6_mitigation_multiround.py: scenario/task/guard ----------

def test_verify_guard_rejects_module_missing_mitigation_param():
    """จำลอง user เผลอ cp multi_agent.py ของ Tier2 เดิม (มีแค่ strict_reviewer
    ไม่มี mitigation) มาแทนที่ root — guard ต้อง raise พร้อมข้อความช่วยเหลือ"""
    runner = _load_tier6_runner()
    import sys
    import pytest

    tier2_old_multi_agent = load_module_from_path(
        "tier2_old_multi_agent_for_guard_test", os.path.join(TIER2_DIR, "multi_agent.py")
    )
    original = sys.modules.get("multi_agent")
    sys.modules["multi_agent"] = tier2_old_multi_agent
    try:
        with pytest.raises(RuntimeError, match="mitigation"):
            runner._verify_multi_agent_supports_strict_reviewer_and_mitigation()
    finally:
        if original is not None:
            sys.modules["multi_agent"] = original
        else:
            del sys.modules["multi_agent"]


def test_verify_guard_accepts_tier6_own_multi_agent():
    runner = _load_tier6_runner()
    import sys

    tier6_multi_agent = _load_tier6_multi_agent()
    original = sys.modules.get("multi_agent")
    sys.modules["multi_agent"] = tier6_multi_agent
    try:
        mod = runner._verify_multi_agent_supports_strict_reviewer_and_mitigation()
        assert mod is tier6_multi_agent
    finally:
        if original is not None:
            sys.modules["multi_agent"] = original
        else:
            del sys.modules["multi_agent"]


def test_scenarios_match_tier2_moderate_delay_and_baseline_exactly():
    """ค่า delay/jitter/loss ต้องตรงกับ Tier2's TEST_SCENARIOS เป๊ะ เพื่อให้
    เทียบผลกันได้ตรง (คนละ 'name'/phase ก็จริง แต่ network condition ต้องเหมือนกัน)"""
    runner = _load_tier6_runner()
    tier2_runner = load_module_from_path(
        "tier2_runner_for_comparison", os.path.join(TIER2_DIR, "run_tier2_multiround.py")
    )
    tier2_by_name = {s["name"]: s for s in tier2_runner.TEST_SCENARIOS}
    tier2_baseline = tier2_by_name["t2mr_baseline"]
    tier2_moderate = tier2_by_name["t2mr_moderate_delay"]

    tier6_by_name = {s["name"]: s for s in runner.TEST_SCENARIOS}
    assert set(tier6_by_name.keys()) == {"t6_baseline", "t6_moderate_delay"}

    for field in ("delay_ms", "jitter_ms", "loss_pct"):
        assert tier6_by_name["t6_baseline"][field] == tier2_baseline[field]
        assert tier6_by_name["t6_moderate_delay"][field] == tier2_moderate[field]


def test_reuses_tier2_hard_tasks_directly_not_a_copy():
    runner = _load_tier6_runner()
    tier2_tasks = load_module_from_path(
        "tier2_tasks_for_comparison", os.path.join(TIER2_DIR, "tier2_tasks_multiround.py")
    )
    assert runner.TIER2_HARD_TASKS == tier2_tasks.TIER2_HARD_TASKS
    assert runner.TIER2_HARD_TASK_GROUND_TRUTH == tier2_tasks.TIER2_HARD_TASK_GROUND_TRUTH
    assert set(runner.TIER2_HARD_TASKS.keys()) == {"coding_task_hard", "planning_decision_hard"}


def test_repeats_matches_tier2_for_comparable_sample_size():
    runner = _load_tier6_runner()
    tier2_runner = load_module_from_path(
        "tier2_runner_for_repeats_comparison", os.path.join(TIER2_DIR, "run_tier2_multiround.py")
    )
    assert runner.REPEATS == tier2_runner.REPEATS == 10


def test_conditions_match_tier5_three_main_conditions():
    runner = _load_tier6_runner()
    assert runner.CONDITIONS == ["none", "adaptive_timeout", "context_cache"]


def test_total_trial_count_is_120():
    runner = _load_tier6_runner()
    per_condition = len(runner.TEST_SCENARIOS) * len(runner.TIER2_HARD_TASKS) * runner.REPEATS
    assert per_condition == 40
    assert per_condition * len(runner.CONDITIONS) == 120


def test_runner_main_is_present_and_callable():
    runner = _load_tier6_runner()
    assert hasattr(runner, "main")
    assert callable(runner.main)
