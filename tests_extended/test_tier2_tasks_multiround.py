"""Tier2 hard-task definition tests"""
import os

from conftest import TIER_DIRS, load_module_from_path

TIER2_DIR = TIER_DIRS["tier2"]


def _load():
    return load_module_from_path(
        "tier2_tasks_multiround_under_test", os.path.join(TIER2_DIR, "tier2_tasks_multiround.py")
    )


def test_two_hard_tasks_defined():
    mod = _load()
    assert set(mod.TIER2_HARD_TASKS.keys()) == {"coding_task_hard", "planning_decision_hard"}
    for name, prompt in mod.TIER2_HARD_TASKS.items():
        assert isinstance(prompt, str)
        assert len(prompt) > 50  # ต้องเป็นโจทย์ที่มีรายละเอียดจริง ไม่ใช่ placeholder สั้นๆ


def test_ground_truth_specs_exist_for_every_hard_task():
    mod = _load()
    for task_name in mod.TIER2_HARD_TASKS:
        assert task_name in mod.TIER2_HARD_TASK_GROUND_TRUTH, f"ขาด ground truth spec ของ {task_name}"
        spec = mod.TIER2_HARD_TASK_GROUND_TRUTH[task_name]
        assert "checks" in spec and len(spec["checks"]) >= 3
        assert "max_score" in spec and "pass_score" in spec
        assert spec["pass_score"] <= spec["max_score"]


def test_ground_truth_checks_have_required_fields():
    mod = _load()
    for spec in mod.TIER2_HARD_TASK_GROUND_TRUTH.values():
        for check in spec["checks"]:
            assert "id" in check
            assert "description" in check
            assert "any" in check and len(check["any"]) >= 1


def test_hard_task_ground_truth_can_be_merged_into_original_task_ground_truth():
    """จำลองสิ่งที่ run_tier2_multiround.py ทำจริง: merge เข้า
    experiment.tasks.TASK_GROUND_TRUTH โดยไม่ทำให้ของเดิมหาย"""
    mod = _load()
    import experiment.tasks as base_tasks

    original_keys = set(base_tasks.TASK_GROUND_TRUTH.keys())
    merged = dict(base_tasks.TASK_GROUND_TRUTH)
    merged.update(mod.TIER2_HARD_TASK_GROUND_TRUTH)

    assert original_keys.issubset(merged.keys())
    assert set(mod.TIER2_HARD_TASK_GROUND_TRUTH.keys()).issubset(merged.keys())
    assert len(merged) == len(original_keys) + len(mod.TIER2_HARD_TASK_GROUND_TRUTH)
