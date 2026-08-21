"""Tier2 multi_agent.py (strict_reviewer) tests — ทั้งหมดรันแบบ offline ผ่าน
fake_autogen (ดู tests/fake_autogen.py) ไม่มีการเรียก Ollama จริงเลย"""
import inspect
import os

import fake_autogen
from conftest import TIER_DIRS, load_module_from_path

from logger import ExperimentLogger

TIER2_DIR = TIER_DIRS["tier2"]


def _load_tier2_multi_agent():
    return load_module_from_path("tier2_multi_agent_under_test", os.path.join(TIER2_DIR, "multi_agent.py"))


def test_build_agents_default_uses_default_reviewer_message():
    mod = _load_tier2_multi_agent()
    _, _, reviewer = mod.build_agents(strict_reviewer=False)
    assert reviewer.system_message == mod.REVIEWER_SYSTEM_MESSAGE_DEFAULT


def test_build_agents_strict_uses_strict_reviewer_message():
    mod = _load_tier2_multi_agent()
    _, _, reviewer = mod.build_agents(strict_reviewer=True)
    assert reviewer.system_message == mod.REVIEWER_SYSTEM_MESSAGE_STRICT
    assert reviewer.system_message != mod.REVIEWER_SYSTEM_MESSAGE_DEFAULT


def test_build_agents_default_parameter_is_false():
    """สำคัญมาก: ต้องเป็น False เป็นค่า default เสมอ กันไม่ให้ call site เดิม
    (run_experiment.py เดิม, Tier1) ที่เรียก build_agents()/run_multi_agent_task()
    โดยไม่ส่ง strict_reviewer= ได้พฤติกรรมเปลี่ยนไปแบบไม่ตั้งใจ"""
    mod = _load_tier2_multi_agent()
    sig = inspect.signature(mod.build_agents)
    assert sig.parameters["strict_reviewer"].default is False

    sig2 = inspect.signature(mod.run_multi_agent_task)
    assert sig2.parameters["strict_reviewer"].default is False


def test_run_multi_agent_task_happy_path_approved_first_try(tmp_log_dir):
    mod = _load_tier2_multi_agent()
    logger = ExperimentLogger(
        scenario={"name": "unit_test_scenario", "delay_ms": 0, "jitter_ms": 0, "loss_pct": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )
    result = mod.run_multi_agent_task("โจทย์ทดสอบ", logger=logger, task_name="coding_task")
    assert result["success"] is True
    assert result["rejections"] == 0
    assert result["quality_score"] == 5
    assert result["retries"] == 0


def test_run_multi_agent_task_counts_reviewer_rejections_before_approval():
    mod = _load_tier2_multi_agent()
    fake_autogen.set_script("Reviewer", [
        "REVISE ยังไม่ครบ\nSCORE: 2",
        "APPROVED ครบแล้ว\nSCORE: 4",
    ])
    result = mod.run_multi_agent_task("โจทย์ทดสอบ", task_name="coding_task")
    assert result["success"] is True
    assert result["rejections"] == 1
    assert result["quality_score"] == 4  # คะแนนล่าสุดจาก Reviewer (SCORE:4 ทับ SCORE:2 เดิม)


def test_run_multi_agent_task_retries_on_exception_and_respects_max_retries():
    mod = _load_tier2_multi_agent()
    # ทุก attempt ของ Worker จะ raise TimeoutError -> ต้อง retry ครบ MAX_RETRIES แล้วยอมแพ้
    fake_autogen.set_script("Worker", [TimeoutError("simulated"), TimeoutError("simulated"), TimeoutError("simulated")])
    result = mod.run_multi_agent_task("โจทย์ทดสอบ", task_name="coding_task")
    assert result["retries"] == mod.MAX_RETRIES
    assert result["success"] is False


def test_strict_reviewer_flag_is_threaded_through_to_build_agents():
    """ตรวจว่า run_multi_agent_task(strict_reviewer=True) จริงๆ แล้วทำให้ Reviewer
    ใช้ system_message เข้มงวด (ตรวจทางอ้อมผ่านการที่ REVISE เกิดง่ายกว่าไม่ได้
    เพราะ fake_autogen ไม่อ่าน system_message มาตัดสินใจ - จึงตรวจที่ build_agents
    โดยตรงแทนซึ่งครอบคลุมกว่า เพราะเป็น unit ที่แท้จริงของการ 'ส่งพารามิเตอร์ต่อ')"""
    mod = _load_tier2_multi_agent()
    captured = {}
    original_build_agents = mod.build_agents

    def _spy_build_agents(strict_reviewer=False):
        captured["strict_reviewer"] = strict_reviewer
        return original_build_agents(strict_reviewer=strict_reviewer)

    mod.build_agents = _spy_build_agents
    try:
        mod.run_multi_agent_task("โจทย์ทดสอบ", task_name="coding_task", strict_reviewer=True)
    finally:
        mod.build_agents = original_build_agents

    assert captured["strict_reviewer"] is True
