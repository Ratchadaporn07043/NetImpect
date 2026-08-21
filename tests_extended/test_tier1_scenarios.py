"""Tier1 scenario generation tests — ไม่ต้องใช้ network/LLM จริงเลย เป็น pure
data-generation logic ล้วนๆ"""
import os
import sys

from conftest import TIER_DIRS, load_module_from_path

import experiment.scenarios as base_scenarios  # noqa: E402  (จาก project_root ที่อยู่ใน sys.path แล้ว)

TIER1_DIR = TIER_DIRS["tier1"]


def _load_tier1_scenarios():
    return load_module_from_path("tier1_scenarios_under_test", os.path.join(TIER1_DIR, "tier1_scenarios.py"))


def test_loss_cliff_levels_are_exactly_55_60_65_70():
    mod = _load_tier1_scenarios()
    assert mod.LOSS_CLIFF_LEVELS_PCT == [55, 60, 65, 70]
    names = [s["name"] for s in mod.TIER1_LOSS_CLIFF_SCENARIOS]
    assert names == ["main_loss_loss55", "main_loss_loss60", "main_loss_loss65", "main_loss_loss70"]
    for s in mod.TIER1_LOSS_CLIFF_SCENARIOS:
        assert s["delay_ms"] == 0
        assert s["jitter_ms"] == 0
        assert s["scenario_type"] == "main_effect"
        assert s["main_effect_axis"] == "loss"


def test_loss_cliff_levels_do_not_collide_with_original_levels():
    mod = _load_tier1_scenarios()
    original_names = {s["name"] for s in base_scenarios.MAIN_EFFECT_SCENARIOS}
    new_names = {s["name"] for s in mod.TIER1_LOSS_CLIFF_SCENARIOS}
    assert original_names.isdisjoint(new_names), "ชื่อ scenario ใหม่ต้องไม่ชนกับของเดิม (กัน log ทับกัน)"
    assert set(base_scenarios.PACKET_LOSS_LEVELS_PCT).isdisjoint(set(mod.LOSS_CLIFF_LEVELS_PCT))


def test_delay_extended_levels_are_beyond_original_range():
    mod = _load_tier1_scenarios()
    assert mod.DELAY_EXTENDED_LEVELS_MS == [1200, 1500, 2000, 2500, 3000]
    assert max(base_scenarios.DELAY_LEVELS_MS) < min(mod.DELAY_EXTENDED_LEVELS_MS)
    for s, expected_ms in zip(mod.TIER1_DELAY_EXTENDED_SCENARIOS, mod.DELAY_EXTENDED_LEVELS_MS):
        assert s["delay_ms"] == expected_ms
        assert s["requested_delay_ms"] == expected_ms
        assert s["jitter_ms"] == 0
        assert s["loss_pct"] == 0
        assert s["name"] == f"main_delay_d{expected_ms:04d}"


def test_jitter_extended_applies_min_delay_for_jitter():
    mod = _load_tier1_scenarios()
    assert mod.JITTER_EXTENDED_LEVELS_MS == [100, 125, 150, 200]
    for s, expected_jitter in zip(mod.TIER1_JITTER_EXTENDED_SCENARIOS, mod.JITTER_EXTENDED_LEVELS_MS):
        # requested delay=0 แต่ jitter>0 -> ต้องถูกยกไป MIN_DELAY_FOR_JITTER_MS (netem constraint)
        assert s["requested_delay_ms"] == 0
        assert s["jitter_ms"] == expected_jitter
        assert s["delay_ms"] == base_scenarios.MIN_DELAY_FOR_JITTER_MS
        assert s["note"] != ""  # ต้องมี note อธิบายว่าทำไม delay ถูกปรับ


def test_delay_250_recheck_matches_original_scenario_name_and_levels():
    mod = _load_tier1_scenarios()
    s = mod.TIER1_DELAY_250_RECHECK_SCENARIO
    assert s["name"] == "main_delay_d0250"
    assert s["delay_ms"] == 250
    assert s["jitter_ms"] == 0
    assert s["loss_pct"] == 0
    # ต้องตรงกับชื่อ scenario เดิมเป๊ะ เพื่อให้เอาไปรวมวิเคราะห์กับของเดิมได้
    original = base_scenarios.get_scenario_by_name("main_delay_d0250")
    assert original["delay_ms"] == s["delay_ms"]


def test_delay_250_recheck_repeat_bookkeeping_avoids_run_index_collision():
    mod = _load_tier1_scenarios()
    # เดิมมี run1..run5 อยู่แล้ว (THREE_DAY_MAIN_EFFECT_REPEATS=5) ตัวใหม่ต้องเริ่มที่ 6
    assert mod.DELAY_250_RECHECK_START_RUN_INDEX == base_scenarios.THREE_DAY_MAIN_EFFECT_REPEATS + 1
    assert mod.DELAY_250_RECHECK_REPEATS == 15
    # รวมแล้วต้องได้ 20 repeats ทั้งหมด (5 เดิม + 15 ใหม่)
    last_run_index = mod.DELAY_250_RECHECK_START_RUN_INDEX + mod.DELAY_250_RECHECK_REPEATS - 1
    assert last_run_index == 20


def test_tier1_all_new_level_scenarios_combines_all_three_groups():
    mod = _load_tier1_scenarios()
    expected_count = (
        len(mod.TIER1_LOSS_CLIFF_SCENARIOS)
        + len(mod.TIER1_DELAY_EXTENDED_SCENARIOS)
        + len(mod.TIER1_JITTER_EXTENDED_SCENARIOS)
    )
    assert len(mod.TIER1_ALL_NEW_LEVEL_SCENARIOS) == expected_count == 13
