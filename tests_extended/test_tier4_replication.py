"""Tier4 replication scripts — เทส pure-logic ส่วนที่ import ได้โดยไม่ต้องรัน
network/LLM จริง (การ import เฉยๆ ปลอดภัย เพราะ network/LLM logic อยู่ใต้
if __name__ == '__main__' หรือถูกเรียกจาก main() เท่านั้น)"""
import os

from conftest import TIER_DIRS, load_module_from_path


def test_run_tier4_main_effect_only_imports_cleanly_and_exposes_scenarios():
    mod = load_module_from_path(
        "tier4_main_effect_only_under_test",
        os.path.join(TIER_DIRS["tier4"], "run_tier4_main_effect_only.py"),
    )
    # scenarios.py ต้นฉบับ: delay 21 ระดับ (0..1000 step 50) + loss 11 ระดับ + jitter 10 ระดับ = 42
    assert len(mod.MAIN_EFFECT_SCENARIOS) == 21 + 11 + 10 == 42


def test_safe_model_dirname_sanitizes_special_characters():
    mod = load_module_from_path(
        "tier4_dirname_under_test",
        os.path.join(TIER_DIRS["tier4"], "run_tier4_main_effect_only.py"),
    )
    assert mod._safe_model_dirname("llama3.1:8b") == "llama3.1_8b"
    assert mod._safe_model_dirname("qwen3:8b") == "qwen3_8b"
    assert mod._safe_model_dirname("simple-name") == "simple-name"


def test_default_repeats_matches_three_day_main_effect_repeats():
    mod = load_module_from_path(
        "tier4_repeats_under_test",
        os.path.join(TIER_DIRS["tier4"], "run_tier4_main_effect_only.py"),
    )
    assert mod.THREE_DAY_MAIN_EFFECT_REPEATS == 5
