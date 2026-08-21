"""Tier3 evaluator.py (dual-judge / JUDGE_MODEL_NAME) tests — offline ผ่าน fake_autogen"""
import inspect
import os

import fake_autogen
from conftest import TIER_DIRS, load_module_from_path

TIER3_DIR = TIER_DIRS["tier3"]
EVALUATOR_PATH = os.path.join(TIER3_DIR, "evaluator.py")


def _load(monkeypatch=None, judge_model_name=None, agent_model_name=None):
    if monkeypatch is not None:
        if judge_model_name is not None:
            monkeypatch.setenv("JUDGE_MODEL_NAME", judge_model_name)
        else:
            monkeypatch.delenv("JUDGE_MODEL_NAME", raising=False)
        if agent_model_name is not None:
            monkeypatch.setenv("MODEL_NAME", agent_model_name)
    return load_module_from_path("tier3_evaluator_under_test", EVALUATOR_PATH)


def test_judge_model_name_falls_back_to_agent_model_when_unset(monkeypatch):
    mod = _load(monkeypatch, judge_model_name=None, agent_model_name="qwen3:8b")
    assert mod.JUDGE_MODEL_NAME == mod.AGENT_MODEL_NAME == "qwen3:8b"


def test_judge_model_name_can_be_set_independently(monkeypatch):
    mod = _load(monkeypatch, judge_model_name="llama3.1:8b", agent_model_name="qwen3:8b")
    assert mod.AGENT_MODEL_NAME == "qwen3:8b"
    assert mod.JUDGE_MODEL_NAME == "llama3.1:8b"
    assert mod.JUDGE_MODEL_NAME != mod.AGENT_MODEL_NAME


def test_heuristic_mode_unaffected_by_judge_model_name(monkeypatch):
    mod = _load(monkeypatch, judge_model_name="llama3.1:8b")
    monkeypatch.setenv("GROUND_TRUTH_EVAL_MODE", "heuristic")
    result = mod._heuristic_evaluate(
        "coding_task", "เขียนฟังก์ชัน", "def is_prime(n): ... True False <= 1 n == 2 sqrt หลักการ"
    )
    assert result["mode"] == "heuristic"
    assert "judge_model_name" not in result  # heuristic ไม่เกี่ยวกับ judge model เลย


def test_llm_evaluate_records_which_judge_model_was_used(monkeypatch):
    mod = _load(monkeypatch, judge_model_name="llama3.1:8b")
    fake_autogen.set_script(
        "GroundTruthEvaluator",
        ['{"score": 4, "passed": true, "missing_points": [], "rationale": "ครบถ้วนดี"}'],
    )
    result = mod._llm_evaluate("coding_task", "โจทย์", "คำตอบ", judge_model_name="llama3.1:8b")
    assert result["judge_model_name"] == "llama3.1:8b"
    assert result["score"] == 4
    assert result["passed"] is True


def test_llm_evaluate_judge_model_name_param_overrides_env(monkeypatch):
    mod = _load(monkeypatch, judge_model_name="llama3.1:8b")
    fake_autogen.set_script(
        "GroundTruthEvaluator",
        ['{"score": 3, "passed": false, "missing_points": ["x"], "rationale": "..."}'],
    )
    # ส่ง judge_model_name อื่นตรงๆ ต้อง override ค่า env
    result = mod._llm_evaluate("coding_task", "โจทย์", "คำตอบ", judge_model_name="mistral:7b")
    assert result["judge_model_name"] == "mistral:7b"


def test_evaluate_answer_backward_compatible_without_judge_model_name_param(monkeypatch):
    """เหมือน call site เดิมใน multi_agent.py: evaluate_answer(task_name, prompt, answer)
    โดยไม่ส่ง judge_model_name เลย ต้องยังทำงานได้ปกติ"""
    mod = _load(monkeypatch, judge_model_name=None)
    monkeypatch.setenv("GROUND_TRUTH_EVAL_MODE", "heuristic")
    sig = inspect.signature(mod.evaluate_answer)
    assert "judge_model_name" in sig.parameters
    assert sig.parameters["judge_model_name"].default is None

    result = mod.evaluate_answer("coding_task", "โจทย์", "def is_prime(n): pass True False")
    assert result["task_name"] == "coding_task"
