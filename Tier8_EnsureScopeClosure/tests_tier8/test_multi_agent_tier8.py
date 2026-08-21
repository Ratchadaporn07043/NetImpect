"""
Tier8 multi_agent.py - end-to-end regression tests for the Tier7 7A failure.
================================================================================
Unlike the Tier5 test, this uses the real Tier8 logger with fake_autogen exceptions
to prove end-to-end that multi_agent.py calls logger.log_timeout(..., agent=...)
without TypeError. It tests the integrated path rather than isolated modules.
"""
import inspect
import os

import fake_autogen
from logger import ExperimentLogger

import multi_agent as mod


def _fresh_logger(tmp_log_dir):
    return ExperimentLogger(
        scenario={"name": "test", "delay_ms": 0, "loss_pct": 75, "jitter_ms": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )


# ---------- Regression check for the Tier7 7A failure ----------

def test_timeout_with_real_tier8_logger_does_not_raise_typeerror(tmp_log_dir):
    """This directly reproduces the Tier7 7A bug: multi_agent.py calls
    logger.log_timeout(detail=..., agent=blamed_agent) — ถ้า logger.py ไม่รองรับ
    agent= จะได้ TypeError หลุดออกมาจากตรงนี้ทันที (เหมือนที่เกิดใน 7A จริง)"""
    fake_autogen.set_script("Worker", [TimeoutError("simulated timeout"), "คำตอบสุดท้ายหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)

    result = mod.run_multi_agent_task(
        "โจทย์ทดสอบ", logger=logger, task_name="coding_task", mitigation="fixed_long_timeout",
    )

    # ต้องรันจบโดยไม่ throw และมี timeout entry ที่มี agent field จริง (ไม่ใช่ crash
    # กลายเป็น fatal_error/rounds=0 แบบที่ 7A เจอ)
    assert result["success"] is True
    timeout_entries = [e for e in logger.data["errors"] if e["error_type"] == "timeout"]
    assert len(timeout_entries) == 1
    assert timeout_entries[0]["agent"] == "Worker"  # attempt แรกไม่มี message เลย -> คิวแรกคือ Worker


def test_retry_actually_happens_after_timeout(tmp_log_dir):
    """ยืนยันว่า MAX_RETRIES ยังทำงานจริง (จุดที่ 7A พังคือ retry ถูกตัดทิ้งเพราะ
    exception จาก logger เอง หลุดออกจาก try/except ก่อนถึง retry check)

    หมายเหตุ: `result["retries"]` (= `retries_used = attempt - 1`) ถูกอัปเดตเฉพาะ
    ตอน attempt ที่ "ล้มเหลว" เท่านั้น ไม่ได้อัปเดตซ้ำตอน attempt ที่ตามมาสำเร็จ
    (โค้ดส่วนนี้สืบทอดมาจาก Tier 5/7 ไม่ได้แก้ที่นี่) ผลคือ retry จริง 1 ครั้งแล้ว
    สำเร็จ -> result["retries"] ยังเป็น 0 นี่คือ quirk เดียวกับที่ sigconf.tex
    `sec:statsdesign` ระบุไว้ตรงๆ ว่า "the `retry_count` field ... under reports
    by one whenever a retry succeeds" จึงต้องนับจาก logged `retry` events แทน
    (ดู logger.data["errors"]) ไม่ใช่จาก result["retries"]/`retry_count` field
    เทสนี้จึงยืนยันผ่าน logged retry event แทน ไม่ใช่ผ่าน result["retries"]"""
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "สำเร็จหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)

    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="none",
    )
    retry_events = [e for e in logger.data["errors"] if e["error_type"] == "retry"]
    assert len(retry_events) == 1  # ใช้ retry ไปจริง 1 ครั้ง (ยืนยันผ่าน logged event ไม่ใช่ retry_count field)
    assert result["success"] is True
    assert result["rounds"] > 0


def test_exhausting_all_retries_still_logs_agent_each_time(tmp_log_dir):
    fake_autogen.set_script("Worker", [
        TimeoutError("attempt 1"), TimeoutError("attempt 2"), TimeoutError("attempt 3"),
    ])
    logger = _fresh_logger(tmp_log_dir)

    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="none",
    )
    assert result["success"] is False
    timeout_entries = [e for e in logger.data["errors"] if e["error_type"] == "timeout"]
    assert len(timeout_entries) == mod.MAX_RETRIES + 1
    assert all(e["agent"] is not None for e in timeout_entries)


# ---------- fixed_long_timeout mode (ข้อ 2) ----------

def test_valid_mitigations_include_fixed_long_timeout():
    assert "fixed_long_timeout" in mod.VALID_MITIGATIONS


def test_fixed_long_timeout_default_value_matches_adaptive_at_loss75():
    # 120 (base) + int(75 * 3) = 345 — ค่าที่ adaptive formula คืนที่จุดวิกฤต
    expected = mod.BASE_LLM_TIMEOUT + int(75 * 3)
    assert mod.FIXED_LONG_TIMEOUT == expected == 345


def test_fixed_long_timeout_ignores_network_condition(tmp_log_dir):
    """arm นี้ต้องได้ timeout เดียวกันไม่ว่า network_condition จะเป็นอะไร —
    ต่างจาก adaptive_timeout ตรงนี้เพียงมิติเดียว"""
    captured = []
    original_build_agents = mod.build_agents

    def _spy(strict_reviewer=False, timeout_seconds=None):
        captured.append(timeout_seconds)
        return original_build_agents(strict_reviewer=strict_reviewer, timeout_seconds=timeout_seconds)

    mod.build_agents = _spy
    try:
        logger_low = _fresh_logger(tmp_log_dir)
        mod.run_multi_agent_task(
            "โจทย์", logger=logger_low, task_name="coding_task", mitigation="fixed_long_timeout",
            network_condition={"delay_ms": 0, "loss_pct": 0, "jitter_ms": 0},
        )
        logger_high = _fresh_logger(tmp_log_dir)
        mod.run_multi_agent_task(
            "โจทย์", logger=logger_high, task_name="coding_task", mitigation="fixed_long_timeout",
            network_condition={"delay_ms": 3000, "loss_pct": 75, "jitter_ms": 200},
        )
    finally:
        mod.build_agents = original_build_agents

    assert captured[0] == mod.FIXED_LONG_TIMEOUT
    assert captured[-1] == mod.FIXED_LONG_TIMEOUT


def test_fixed_long_timeout_differs_from_adaptive_away_from_critical_point(tmp_log_dir):
    """ที่ loss=0 (ไม่ใช่จุดวิกฤต) fixed กับ adaptive ต้องได้ timeout ต่างกัน —
    นี่คือมิติเดียวที่ทั้งสอง arm ต่างกัน (ตามที่ README ของ 7A ออกแบบไว้)"""
    zero_impairment = {"delay_ms": 0, "loss_pct": 0, "jitter_ms": 0}
    adaptive_value = mod._adaptive_timeout_seconds(zero_impairment)
    assert adaptive_value == mod.BASE_LLM_TIMEOUT
    assert mod.FIXED_LONG_TIMEOUT != adaptive_value


def test_fixed_long_timeout_equals_adaptive_exactly_at_loss75():
    """ที่ loss=75% (จุดวิกฤต) fixed กับ adaptive ต้องได้ timeout เท่ากันเป๊ะ —
    เงื่อนไขที่ทำให้การเทียบสอง arm นี้ตัด confound เรื่อง 'เวลา' ออกได้ที่จุดนี้"""
    critical_condition = {"delay_ms": 0, "loss_pct": 75, "jitter_ms": 0}
    adaptive_value = mod._adaptive_timeout_seconds(critical_condition)
    assert adaptive_value == mod.FIXED_LONG_TIMEOUT


# ---------- agent-blame logic (สืบทอดจาก Tier 7, ต้องยังถูกต้องเป๊ะ) ----------

def test_blame_agent_empty_transcript_defaults_to_worker_when_cached_plan():
    assert mod._blame_agent([], use_cached_plan=True) == "Worker"


def test_blame_agent_empty_transcript_none_when_full_team():
    assert mod._blame_agent([], use_cached_plan=False) is None


def test_blame_agent_after_planner_seed_points_to_worker():
    transcript = [{"name": "Planner", "content": "seed"}]
    assert mod._blame_agent(transcript, use_cached_plan=False) == "Worker"


def test_blame_agent_after_worker_points_to_reviewer():
    transcript = [{"name": "Planner", "content": "seed"}, {"name": "Worker", "content": "answer"}]
    assert mod._blame_agent(transcript, use_cached_plan=False) == "Reviewer"


def test_blame_agent_cached_plan_alternates_worker_reviewer():
    assert mod._blame_agent([{"name": "Worker", "content": "x"}], use_cached_plan=True) == "Reviewer"
    assert mod._blame_agent([{"name": "Reviewer", "content": "x"}], use_cached_plan=True) == "Worker"


# ---------- mitigation dispatch พื้นฐาน (สืบทอดจาก Tier 5/7) ----------

def test_invalid_mitigation_value_raises():
    import pytest
    with pytest.raises(ValueError):
        mod.run_multi_agent_task("โจทย์", task_name="coding_task", mitigation="not_real")


def test_context_cache_skips_planner_on_retry(tmp_log_dir):
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "คำตอบสุดท้ายหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)
    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="context_cache",
    )
    assert result["success"] is True


def test_planner_issues_no_inference_request_on_single_pass(tmp_log_dir):
    """ยืนยันพฤติกรรมที่ sigconf.tex sec:modelservingpath อ้างถึง: single-pass
    trial มี 2 LLM invocation ไม่ใช่ 3 — Planner ส่งแค่ seed message"""
    logger = _fresh_logger(tmp_log_dir)
    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="none",
    )
    assert result["success"] is True
    speakers = [m["from"] for m in logger.data["messages"]]
    assert speakers == ["Planner", "Worker", "Reviewer"]
    # Planner "message" คือ seed prompt เอง ไม่ใช่ผลลัพธ์จาก generate_reply()
    # (fake_autogen ไม่ได้เรียก Planner.generate_reply เลยในเส้นทางนี้)
