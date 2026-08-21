"""Tier5 multi_agent.py (mitigation A/B) tests — offline ผ่าน fake_autogen"""
import inspect
import os

import fake_autogen
from conftest import TIER_DIRS, load_module_from_path

TIER5_DIR = TIER_DIRS["tier5"]


def _load():
    return load_module_from_path("tier5_multi_agent_under_test", os.path.join(TIER5_DIR, "multi_agent.py"))


def test_mitigation_default_is_none():
    mod = _load()
    sig = inspect.signature(mod.run_multi_agent_task)
    assert sig.parameters["mitigation"].default == "none"
    assert sig.parameters["network_condition"].default is None


def test_invalid_mitigation_value_raises():
    mod = _load()
    import pytest
    with pytest.raises(ValueError):
        mod.run_multi_agent_task("โจทย์", task_name="coding_task", mitigation="not_a_real_mitigation")


def test_mitigation_none_result_dict_reports_none():
    mod = _load()
    result = mod.run_multi_agent_task("โจทย์", task_name="coding_task", mitigation="none")
    assert result["mitigation"] == "none"
    assert result["success"] is True  # happy-path default script (APPROVED SCORE:5)


# ---------- Mitigation A: Adaptive Timeout ----------

def test_adaptive_timeout_returns_base_when_no_network_condition():
    mod = _load()
    assert mod._adaptive_timeout_seconds(None) == mod.BASE_LLM_TIMEOUT
    assert mod._adaptive_timeout_seconds({}) == mod.BASE_LLM_TIMEOUT


def test_adaptive_timeout_scales_up_with_delay_and_loss():
    mod = _load()
    baseline = mod._adaptive_timeout_seconds({"delay_ms": 0, "loss_pct": 0, "jitter_ms": 0})
    bad_network = mod._adaptive_timeout_seconds({"delay_ms": 1000, "loss_pct": 50, "jitter_ms": 30})
    assert baseline == mod.BASE_LLM_TIMEOUT
    assert bad_network > baseline


def test_adaptive_timeout_is_capped_at_ten_times_base():
    mod = _load()
    extreme = mod._adaptive_timeout_seconds({"delay_ms": 100000, "loss_pct": 100, "jitter_ms": 100000})
    assert extreme == mod.BASE_LLM_TIMEOUT * 10


def test_run_multi_agent_task_adaptive_timeout_uses_network_condition():
    mod = _load()
    captured_timeouts = []
    original_build_agents = mod.build_agents

    def _spy(strict_reviewer=False, timeout_seconds=None):
        captured_timeouts.append(timeout_seconds)
        return original_build_agents(strict_reviewer=strict_reviewer, timeout_seconds=timeout_seconds)

    mod.build_agents = _spy
    try:
        mod.run_multi_agent_task(
            "โจทย์", task_name="coding_task", mitigation="adaptive_timeout",
            network_condition={"delay_ms": 500, "loss_pct": 20, "jitter_ms": 0},
        )
    finally:
        mod.build_agents = original_build_agents

    expected = mod._adaptive_timeout_seconds({"delay_ms": 500, "loss_pct": 20, "jitter_ms": 0})
    assert captured_timeouts[0] == expected
    assert expected > mod.BASE_LLM_TIMEOUT


def test_run_multi_agent_task_none_mitigation_uses_base_timeout():
    mod = _load()
    captured_timeouts = []
    original_build_agents = mod.build_agents

    def _spy(strict_reviewer=False, timeout_seconds=None):
        captured_timeouts.append(timeout_seconds)
        return original_build_agents(strict_reviewer=strict_reviewer, timeout_seconds=timeout_seconds)

    mod.build_agents = _spy
    try:
        mod.run_multi_agent_task(
            "โจทย์", task_name="coding_task", mitigation="none",
            network_condition={"delay_ms": 1000, "loss_pct": 75, "jitter_ms": 30},
        )
    finally:
        mod.build_agents = original_build_agents

    # mitigation="none" -> ต้องไม่ขยาย timeout แม้ network_condition จะแย่มากก็ตาม
    assert captured_timeouts[0] is None


# ---------- Mitigation B: Context Caching ----------

def test_context_cache_skips_planner_on_retry():
    """จำลอง: attempt แรก Worker throw exception (ต้อง retry), attempt สองสำเร็จ
    ต้องเห็นว่า attempt สองข้าม Planner ไปเลย (agents ที่ใช้เหลือแค่ [Worker, Reviewer])"""
    mod = _load()
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "คำตอบสุดท้ายหลัง retry"])

    captured_agent_counts = []
    original_attempt_once = mod._attempt_once

    def _spy_attempt_once(task_prompt, max_rounds, logger=None, strict_reviewer=False,
                           timeout_seconds=None, cached_plan=None):
        captured_agent_counts.append(cached_plan is not None)
        return original_attempt_once(task_prompt, max_rounds, logger, strict_reviewer,
                                      timeout_seconds, cached_plan)

    mod._attempt_once = _spy_attempt_once
    try:
        result = mod.run_multi_agent_task("โจทย์", task_name="coding_task", mitigation="context_cache")
    finally:
        mod._attempt_once = original_attempt_once

    # attempt แรก cached_plan ต้องเป็น None (ยังไม่มี plan จะ cache)
    assert captured_agent_counts[0] is False
    # attempt ถัดไป (retry) ต้องมี cached_plan แล้ว (มาจาก planner_output ของ attempt แรก)
    assert True in captured_agent_counts[1:]
    assert len(captured_agent_counts) == 2  # attempt แรกล้มเหลว + attempt สองสำเร็จด้วย cached plan
    assert result["success"] is True


def test_context_cache_none_mitigation_never_uses_cached_plan():
    mod = _load()
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "คำตอบสุดท้ายหลัง retry"])

    captured_cached_plans = []
    original_attempt_once = mod._attempt_once

    def _spy_attempt_once(task_prompt, max_rounds, logger=None, strict_reviewer=False,
                           timeout_seconds=None, cached_plan=None):
        captured_cached_plans.append(cached_plan)
        return original_attempt_once(task_prompt, max_rounds, logger, strict_reviewer,
                                      timeout_seconds, cached_plan)

    mod._attempt_once = _spy_attempt_once
    try:
        mod.run_multi_agent_task("โจทย์", task_name="coding_task", mitigation="none")
    finally:
        mod._attempt_once = original_attempt_once

    # mitigation="none" -> cached_plan ต้องเป็น None เสมอทุก attempt แม้จะ retry ก็ตาม
    assert all(p is None for p in captured_cached_plans)


def test_attempt_once_with_cached_plan_uses_only_worker_and_reviewer():
    mod = _load()
    success, final_answer, rounds, rejections, quality_score, error, planner_output = mod._attempt_once(
        "โจทย์ทดสอบ", max_rounds=6, logger=None, strict_reviewer=False,
        timeout_seconds=None, cached_plan="แผนเก่าที่ cache ไว้",
    )
    assert error is None
    assert planner_output == "แผนเก่าที่ cache ไว้"
    # ไม่มี message จาก Planner เลยใน attempt นี้ (ข้ามไปจริง)
    # (ตรวจทางอ้อมผ่านว่า final_answer/success ยังทำงานถูกต้องแม้ไม่มี Planner turn)
    assert final_answer != ""
    assert success is True
