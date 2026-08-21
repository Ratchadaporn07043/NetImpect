"""Tier2 bandwidth scenario generation tests"""
import os

from conftest import TIER_DIRS, load_module_from_path

TIER2_DIR = TIER_DIRS["tier2"]


def _load():
    return load_module_from_path(
        "tier2_scenarios_bandwidth_under_test", os.path.join(TIER2_DIR, "tier2_scenarios_bandwidth.py")
    )


def test_bandwidth_levels_do_not_include_none():
    mod = _load()
    assert None not in mod.BANDWIDTH_LEVELS_KBIT
    assert mod.BANDWIDTH_LEVELS_KBIT == [2000, 1000, 500, 250, 100, 50]


def test_bandwidth_main_effect_scenarios_have_bandwidth_kbit_key():
    mod = _load()
    scenarios = mod.TIER2_BANDWIDTH_MAIN_EFFECT_SCENARIOS
    assert len(scenarios) == len(mod.BANDWIDTH_LEVELS_KBIT)
    for s, bw in zip(scenarios, mod.BANDWIDTH_LEVELS_KBIT):
        assert s["bandwidth_kbit"] == bw
        assert s["delay_ms"] == 0
        assert s["loss_pct"] == 0
        assert s["jitter_ms"] == 0
        assert s["name"] == f"main_bandwidth_bw{bw:05d}"


def test_bandwidth_kbit_key_is_what_controller_apply_reads():
    """สำคัญมาก: NetworkController.apply() อ่าน key ชื่อ 'bandwidth_kbit' และ
    run_single_trial() ใน run_experiment.py เดิมก็อ่าน scenario.get('bandwidth_kbit')
    ต้องตรงกันเป๊ะ ไม่งั้น bandwidth จะไม่ถูก apply เลยแบบเงียบๆ"""
    mod = _load()
    for s in mod.TIER2_BANDWIDTH_MAIN_EFFECT_SCENARIOS + mod.TIER2_BANDWIDTH_X_LOSS_SCENARIOS:
        assert "bandwidth_kbit" in s
        assert isinstance(s["bandwidth_kbit"], int)
        assert s["bandwidth_kbit"] > 0


def test_bandwidth_x_loss_scenarios_pair_low_bandwidth_with_mid_high_loss():
    mod = _load()
    scenarios = mod.TIER2_BANDWIDTH_X_LOSS_SCENARIOS
    assert len(scenarios) == 6  # 2 bandwidths x 3 loss levels
    bandwidths = {s["bandwidth_kbit"] for s in scenarios}
    losses = {s["loss_pct"] for s in scenarios}
    assert bandwidths == {500, 100}
    assert losses == {10, 30, 50}
