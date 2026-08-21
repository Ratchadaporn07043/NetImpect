"""
Sanity import test สำหรับทุก runner script ของทุก Tier
================================================================
เป้าหมาย: จับ syntax error / import error / typo ตั้งแต่ตอนนี้ ก่อน user เอาไป
รันจริงบนเครื่องที่มี Ollama/GPU (ซึ่งกว่าจะรู้ว่าพังอาจเสียเวลาหลายชั่วโมง)

ทุกไฟล์ที่เทสในนี้ออกแบบให้ import ได้อย่างปลอดภัยโดยไม่เรียก network/LLM จริง
เพราะ logic ทั้งหมดที่แตะ network/subprocess/LLM ถูกห่อไว้ใน main()/if __name__
== '__main__' เท่านั้น การ import จึงแค่ประกาศฟังก์ชัน/ค่าคงที่ ไม่รันอะไรจริง
"""
import os

import pytest
from conftest import TIER_DIRS, load_module_from_path

RUNNER_SCRIPTS = [
    ("tier1_run_import", "tier1", "run_tier1.py"),
    ("tier2_bandwidth_run_import", "tier2", "run_tier2_bandwidth.py"),
    ("tier2_multiround_run_import", "tier2", "run_tier2_multiround.py"),
    ("tier4_main_effect_run_import", "tier4", "run_tier4_main_effect_only.py"),
    ("tier5_mitigation_run_import", "tier5", "run_tier5_mitigation_comparison.py"),
    ("tier3_dual_judge_run_import", "tier3", "run_dual_judge_sample.py"),
    ("tier6_mitigation_multiround_run_import", "tier6", "run_tier6_mitigation_multiround.py"),
]


@pytest.mark.parametrize("module_name,tier_key,filename", RUNNER_SCRIPTS)
def test_runner_script_imports_without_error(module_name, tier_key, filename):
    path = os.path.join(TIER_DIRS[tier_key], filename)
    assert os.path.isfile(path), f"ไม่พบไฟล์ {path}"
    mod = load_module_from_path(module_name, path)
    assert hasattr(mod, "main")
    assert callable(mod.main)


SHELL_SCRIPTS = [
    ("tier3", "run_full_llm_judge.sh"),
    ("tier4", "run_tier4_temporal_replicate.sh"),
]


@pytest.mark.parametrize("tier_key,filename", SHELL_SCRIPTS)
def test_shell_script_exists_and_is_nonempty(tier_key, filename):
    path = os.path.join(TIER_DIRS[tier_key], filename)
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("#!/usr/bin/env bash")
    assert len(content) > 100


def test_every_tier_has_a_readme():
    for tier_key, tier_dir in TIER_DIRS.items():
        readme_path = os.path.join(tier_dir, "README.md")
        assert os.path.isfile(readme_path), f"{tier_key} ขาด README.md"
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 200
