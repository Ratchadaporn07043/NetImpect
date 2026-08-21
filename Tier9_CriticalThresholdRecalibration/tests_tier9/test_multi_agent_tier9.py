"""
Tier9 multi_agent.py — เทส end-to-end
================================================================================
ต่อยอดจาก Tier8_EnsureScopeClosure/tests_tier8/test_multi_agent_tier8.py ทุก
เทสเดิมยังต้องผ่านเหมือนเดิม (retry/timeout/agent-blame/mitigation dispatch
ไม่ได้เปลี่ยนเลยจาก Tier 8) กลุ่มเทสใหม่ที่เพิ่มมาเฉพาะ Tier 9 คือกลุ่ม
"native client wiring" — ยืนยันว่า OllamaNativeThinkOffClient ถูกผูกเข้ากับ
ทุก agent + manager จริง ไม่ใช่แค่เขียนโค้ดไว้เฉยๆ แต่ลืมเรียก
"""
import os

import fake_autogen
from tier9_logger import ExperimentLogger

import multi_agent as mod
from ollama_native_client import OllamaNativeThinkOffClient


def _fresh_logger(tmp_log_dir):
    return ExperimentLogger(
        scenario={"name": "test", "delay_ms": 0, "loss_pct": 75, "jitter_ms": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )


# ---------- TIER9: native client wiring (กลุ่มเทสใหม่) ----------

def test_llm_config_declares_native_think_off_client_in_config_list():
    """config_list ทุก entry ต้องมี model_client_cls ตรงกับชื่อคลาสเป๊ะ —
    ไม่งั้น autogen.oai.client.OpenAIWrapper จะพยายามสร้าง OpenAI client ปกติ
    แทน (คุยผ่าน /v1/chat/completions เดิม ซึ่งเป็นบั๊กที่ Tier 9 มีไว้แก้)"""
    config = mod._llm_config()
    assert config["config_list"][0]["model_client_cls"] == "OllamaNativeThinkOffClient"


def test_build_agents_registers_native_client_on_all_three_agents():
    planner, worker, reviewer = mod.build_agents()
    registered_names = [name for name, cls in fake_autogen.REGISTERED_MODEL_CLIENTS]
    assert registered_names.count("Planner") == 1
    assert registered_names.count("Worker") == 1
    assert registered_names.count("Reviewer") == 1
    assert all(cls is OllamaNativeThinkOffClient for _, cls in fake_autogen.REGISTERED_MODEL_CLIENTS)


def test_attempt_once_also_registers_native_client_on_manager(tmp_log_dir):
    """จุดที่ Tier 8's monkey-patch เดิมต้องใช้ subclass พิเศษเพื่อทำสิ่งนี้
    (เพราะ _attempt_once() สร้าง GroupChatManager ตรงๆ ไม่ผ่าน build_agents())
    — Tier 9 เขียนการเรียกนี้ตรงๆ ในซอร์สเลย เทสนี้ยืนยันว่าไม่ลืมบรรทัดนั้น"""
    logger = _fresh_logger(tmp_log_dir)
    mod.run_multi_agent_task("โจทย์ทดสอบ", logger=logger, task_name="coding_task", mitigation="none")

    registered_names = [name for name, cls in fake_autogen.REGISTERED_MODEL_CLIENTS]
    assert "chat_manager" in registered_names, (
        "GroupChatManager ไม่ได้ถูก register_model_client() เลย — ถ้าเกิดกับ Tier 9 "
        "จริง manager จะยังคุยผ่าน /v1/chat/completions เดิม (thinking mode ยังเปิดอยู่ "
        "สำหรับการเลือก speaker/จัดการบทสนทนา แม้ agent อื่นจะปิดแล้วก็ตาม)"
    )


def test_every_attempt_including_retries_registers_manager_client(tmp_log_dir):
    """แต่ละ attempt สร้าง manager ใหม่ทุกครั้ง (ดู _attempt_once ที่เรียกทุก
    รอบ retry) ต้อง register client ใหม่ทุกรอบด้วย ไม่ใช่แค่รอบแรก"""
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "สำเร็จหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)
    mod.run_multi_agent_task("โจทย์", logger=logger, task_name="coding_task", mitigation="none")

    manager_registrations = [c for name, c in fake_autogen.REGISTERED_MODEL_CLIENTS if name == "chat_manager"]
    assert len(manager_registrations) == 2  # 2 attempts เกิดขึ้นจริง (fail แล้ว retry สำเร็จ)


# ---------- ยืนยันว่าไม่พังแบบ 7A อีก (สืบทอดจาก Tier 8) ----------

def test_timeout_with_real_tier8_logger_does_not_raise_typeerror(tmp_log_dir):
    fake_autogen.set_script("Worker", [TimeoutError("simulated timeout"), "คำตอบสุดท้ายหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)

    result = mod.run_multi_agent_task(
        "โจทย์ทดสอบ", logger=logger, task_name="coding_task", mitigation="fixed_long_timeout",
    )

    assert result["success"] is True
    timeout_entries = [e for e in logger.data["errors"] if e["error_type"] == "timeout"]
    assert len(timeout_entries) == 1
    assert timeout_entries[0]["agent"] == "Worker"


def test_retry_actually_happens_after_timeout(tmp_log_dir):
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), "สำเร็จหลัง retry"])
    logger = _fresh_logger(tmp_log_dir)

    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="none",
    )
    retry_events = [e for e in logger.data["errors"] if e["error_type"] == "retry"]
    assert len(retry_events) == 1
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


# ---------- fixed_long_timeout mode (recalibrate ที่ critical loss ใหม่) ----------

def test_valid_mitigations_include_fixed_long_timeout():
    assert "fixed_long_timeout" in mod.VALID_MITIGATIONS


def test_fixed_long_timeout_default_fallback_matches_old_tier8_critical_point():
    """ค่า fallback (ไม่ตั้ง env var) ยังคงอิงจากสูตรเดิมที่ loss=75% ไว้เป็น
    baseline sanity check เท่านั้น — Tier 9 ของจริงต้องตั้ง env var
    FIXED_LONG_TIMEOUT ก่อน import เสมอ ให้ตรงกับ critical loss ใหม่ที่พบจาก
    run_tier9_exploratory_scan.py (ดู run_tier9_critical_comparison.py)"""
    expected = mod.BASE_LLM_TIMEOUT + int(75 * 3)
    assert mod.FIXED_LONG_TIMEOUT == expected == 345


def test_fixed_long_timeout_ignores_network_condition(tmp_log_dir):
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
    zero_impairment = {"delay_ms": 0, "loss_pct": 0, "jitter_ms": 0}
    adaptive_value = mod._adaptive_timeout_seconds(zero_impairment)
    assert adaptive_value == mod.BASE_LLM_TIMEOUT
    assert mod.FIXED_LONG_TIMEOUT != adaptive_value


def test_overriding_fixed_long_timeout_after_import_takes_effect(tmp_log_dir):
    """run_tier9_critical_comparison.py ไม่ได้ตั้ง env var ก่อน import — มันเรียก
    `import multi_agent as multi_agent_module` ก่อน แล้วค่อย assign
    `multi_agent_module.FIXED_LONG_TIMEOUT = computed_value` ทับทีหลัง เทสนี้
    จำลองรูปแบบนั้นตรงๆ (ไม่ใช่ตั้ง env var ก่อน import แบบเทสด้านบน) เพื่อยืนยัน
    ว่า _attempt_once() อ่านค่า global ตอนถูกเรียกจริง ไม่ใช่ค่าที่ถูก bind ไว้
    ตอน import ครั้งแรก — ถ้าเทสนี้ fail แปลว่า run_tier9_critical_comparison.py
    ทั้งสคริปต์ใช้ timeout ผิดค่าไปตลอด (bug ร้ายแรงที่ต้องจับให้ได้ก่อนรันจริง)"""
    original_value = mod.FIXED_LONG_TIMEOUT
    captured = []
    original_build_agents = mod.build_agents

    def _spy(strict_reviewer=False, timeout_seconds=None):
        captured.append(timeout_seconds)
        return original_build_agents(strict_reviewer=strict_reviewer, timeout_seconds=timeout_seconds)

    mod.build_agents = _spy
    try:
        override_value = original_value + 999  # ค่าที่ไม่มีทางเกิดจาก fallback เดิม
        mod.FIXED_LONG_TIMEOUT = override_value  # จำลอง run script assign ทับหลัง import

        logger = _fresh_logger(tmp_log_dir)
        mod.run_multi_agent_task(
            "โจทย์", logger=logger, task_name="coding_task", mitigation="fixed_long_timeout",
            network_condition={"delay_ms": 0, "loss_pct": 90, "jitter_ms": 0},
        )
        assert captured[-1] == override_value, (
            f"คาดว่า timeout ที่ใช้จริงคือค่าที่ override ทับหลัง import ({override_value}) "
            f"แต่ได้ {captured[-1]} แทน — ถ้าไม่ตรงกัน run_tier9_critical_comparison.py "
            "จะรันด้วย timeout ผิดค่าตลอดทั้ง fixed_long_timeout arm"
        )
    finally:
        mod.build_agents = original_build_agents
        mod.FIXED_LONG_TIMEOUT = original_value


# ---------- agent-blame logic (สืบทอดจาก Tier 7/8, ต้องยังถูกต้องเป๊ะ) ----------

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


# ---------- mitigation dispatch พื้นฐาน (สืบทอดจาก Tier 5/7/8) ----------

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
    logger = _fresh_logger(tmp_log_dir)
    result = mod.run_multi_agent_task(
        "โจทย์", logger=logger, task_name="coding_task", mitigation="none",
    )
    assert result["success"] is True
    speakers = [m["from"] for m in logger.data["messages"]]
    assert speakers == ["Planner", "Worker", "Reviewer"]
