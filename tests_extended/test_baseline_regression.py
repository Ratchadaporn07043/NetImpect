"""
test_baseline_regression.py — เทสที่สำคัญที่สุดในชุดนี้
================================================================
ยืนยันด้วย "พฤติกรรมจริง" (ไม่ใช่แค่อ่าน signature) ว่า multi_agent.py เวอร์ชัน
Tier2/Tier5 (ที่จะเข้าไปแทนที่ไฟล์ root) ให้ผลลัพธ์ "เหมือนต้นฉบับ 100%" เมื่อ
เรียกด้วย default parameter (ไม่ส่ง strict_reviewer/mitigation ใดๆ) — เพราะ
README ของทุก Tier สัญญาไว้แบบนี้ ต้องพิสูจน์จริง ไม่ใช่แค่อ้าง

ถ้าเทสไฟล์นี้ล้มเหลว = ห้ามเอา Tier2/Tier5 multi_agent.py ไปแทนที่ไฟล์ root
เด็ดขาด เพราะจะทำให้ experiment เดิม (logs_three_day/) หรือ Tier1 พังพฤติกรรม
"""
import os

import fake_autogen
from conftest import PROJECT_ROOT, TIER_DIRS, load_module_from_path

BASE_MULTI_AGENT_PATH = os.path.join(PROJECT_ROOT, "multi_agent.py")
TIER2_MULTI_AGENT_PATH = os.path.join(TIER_DIRS["tier2"], "multi_agent.py")
TIER5_MULTI_AGENT_PATH = os.path.join(TIER_DIRS["tier5"], "multi_agent.py")


def _load(name, path):
    return load_module_from_path(name, path)


def _run_with_default_params(mod, script):
    fake_autogen.reset_scripts()
    for agent_name, replies in script.items():
        fake_autogen.set_script(agent_name, list(replies))
    return mod.run_multi_agent_task("โจทย์ทดสอบเดียวกัน", task_name="coding_task")


HAPPY_PATH_SCRIPT = {
    "Reviewer": ["APPROVED เยี่ยมมาก\nSCORE: 5"],
}

REVISE_THEN_APPROVE_SCRIPT = {
    "Reviewer": ["REVISE ยังไม่ดีพอ\nSCORE: 2", "APPROVED ดีขึ้นแล้ว\nSCORE: 4"],
}


def _assert_core_fields_match(base_result, variant_result):
    core_fields = [
        "success", "final_answer", "rounds", "rejections", "quality_score",
        "ground_truth_score", "ground_truth_passed", "retries", "elapsed_seconds",
    ]
    for field in core_fields:
        if field == "elapsed_seconds":
            continue  # เวลาไม่มีทางเท่ากันเป๊ะ ข้ามไป
        assert base_result[field] == variant_result[field], (
            f"field '{field}' ไม่ตรงกัน: base={base_result[field]!r} vs variant={variant_result[field]!r}"
        )


def test_tier2_multi_agent_matches_baseline_happy_path():
    base = _load("baseline_ma_happy", BASE_MULTI_AGENT_PATH)
    base_result = _run_with_default_params(base, HAPPY_PATH_SCRIPT)

    tier2 = _load("tier2_ma_happy", TIER2_MULTI_AGENT_PATH)
    tier2_result = _run_with_default_params(tier2, HAPPY_PATH_SCRIPT)

    _assert_core_fields_match(base_result, tier2_result)


def test_tier2_multi_agent_matches_baseline_revise_then_approve():
    base = _load("baseline_ma_revise", BASE_MULTI_AGENT_PATH)
    base_result = _run_with_default_params(base, REVISE_THEN_APPROVE_SCRIPT)

    tier2 = _load("tier2_ma_revise", TIER2_MULTI_AGENT_PATH)
    tier2_result = _run_with_default_params(tier2, REVISE_THEN_APPROVE_SCRIPT)

    _assert_core_fields_match(base_result, tier2_result)


def test_tier5_multi_agent_matches_baseline_happy_path():
    base = _load("baseline_ma_happy2", BASE_MULTI_AGENT_PATH)
    base_result = _run_with_default_params(base, HAPPY_PATH_SCRIPT)

    tier5 = _load("tier5_ma_happy", TIER5_MULTI_AGENT_PATH)
    tier5_result = _run_with_default_params(tier5, HAPPY_PATH_SCRIPT)

    _assert_core_fields_match(base_result, tier5_result)
    assert tier5_result["mitigation"] == "none"  # key ใหม่ที่เพิ่ม ต้องเป็นค่า default เสมอ


def test_tier5_multi_agent_matches_baseline_revise_then_approve():
    base = _load("baseline_ma_revise2", BASE_MULTI_AGENT_PATH)
    base_result = _run_with_default_params(base, REVISE_THEN_APPROVE_SCRIPT)

    tier5 = _load("tier5_ma_revise", TIER5_MULTI_AGENT_PATH)
    tier5_result = _run_with_default_params(tier5, REVISE_THEN_APPROVE_SCRIPT)

    _assert_core_fields_match(base_result, tier5_result)


def test_tier2_build_agents_default_produces_identical_prompts_to_baseline():
    base = _load("baseline_ma_prompts", BASE_MULTI_AGENT_PATH)
    tier2 = _load("tier2_ma_prompts", TIER2_MULTI_AGENT_PATH)

    base_planner, base_worker, base_reviewer = base.build_agents()
    tier2_planner, tier2_worker, tier2_reviewer = tier2.build_agents()  # ไม่ส่ง strict_reviewer

    assert base_planner.system_message == tier2_planner.system_message
    assert base_worker.system_message == tier2_worker.system_message
    assert base_reviewer.system_message == tier2_reviewer.system_message


def test_tier5_build_agents_default_produces_identical_prompts_to_baseline():
    base = _load("baseline_ma_prompts2", BASE_MULTI_AGENT_PATH)
    tier5 = _load("tier5_ma_prompts", TIER5_MULTI_AGENT_PATH)

    base_planner, base_worker, base_reviewer = base.build_agents()
    tier5_planner, tier5_worker, tier5_reviewer = tier5.build_agents()  # ไม่ส่ง strict_reviewer/timeout

    assert base_planner.system_message == tier5_planner.system_message
    assert base_worker.system_message == tier5_worker.system_message
    assert base_reviewer.system_message == tier5_reviewer.system_message
