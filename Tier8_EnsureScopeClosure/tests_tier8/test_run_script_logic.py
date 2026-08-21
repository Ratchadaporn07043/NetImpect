"""
เทส logic เฉพาะของแต่ละ run_tier8_*.py ที่ไม่ต้องแตะ network/LLM จริง:
  - checkpoint_utils.py roundtrip (load/save/mark_completed/should_skip)
  - run_tier8_randomized_mitigation.py: การสุ่มลำดับ trial (ข้อ 3)
  - run_tier8_jitter_floor.py: scenario ตรงกับ MIN_DELAY_FOR_JITTER_MS ของโปรเจกต์จริง (ข้อ 5)
  - run_tier8_achieved_path.py: การดึง host/url จาก OLLAMA_BASE_URL (ข้อ 1)
"""
import os

from conftest import TIER8_DIR, load_module_from_path
from checkpoint_utils import load_checkpoint, save_checkpoint, mark_completed, should_skip


# ---------- checkpoint_utils ----------

def test_checkpoint_roundtrip(tmp_log_dir):
    checkpoint = load_checkpoint(tmp_log_dir)
    assert checkpoint == {"completed": {}}

    mark_completed(tmp_log_dir, checkpoint, "key1", "path/to/log1.json")
    assert should_skip(True, checkpoint, "key1") is True
    assert should_skip(True, checkpoint, "key2") is False

    reloaded = load_checkpoint(tmp_log_dir)
    assert "key1" in reloaded["completed"]
    assert reloaded["completed"]["key1"]["log_file"] == "path/to/log1.json"


def test_should_skip_false_when_not_resuming(tmp_log_dir):
    checkpoint = load_checkpoint(tmp_log_dir)
    mark_completed(tmp_log_dir, checkpoint, "key1", "x.json")
    assert should_skip(False, checkpoint, "key1") is False  # resume=False -> ไม่ skip แม้เคยเสร็จแล้ว


def test_should_skip_false_when_checkpoint_is_none():
    assert should_skip(True, None, "any_key") is False


# ---------- run_tier8_randomized_mitigation.py (ข้อ 3) ----------

def _load_randomized_module():
    return load_module_from_path(
        "t8_randomized_logic_test",
        os.path.join(TIER8_DIR, "run_tier8_randomized_mitigation.py"),
    )


def test_shuffled_trial_list_has_correct_total_count():
    mod = _load_randomized_module()
    trials = mod.build_shuffled_trial_list(seed=42)
    expected = len(mod.PACKET_LOSS_LEVELS_PCT) * len(mod.TASKS) * mod.REPEATS * len(mod.CONDITIONS)
    assert len(trials) == expected == 660


def test_shuffled_trial_list_has_correct_per_condition_count():
    mod = _load_randomized_module()
    trials = mod.build_shuffled_trial_list(seed=42)
    for condition in mod.CONDITIONS:
        count = sum(1 for t in trials if t["condition"] == condition)
        assert count == 220  # 11 loss levels x 4 tasks x 5 repeats


def test_shuffle_is_reproducible_with_same_seed():
    mod = _load_randomized_module()
    trials_a = mod.build_shuffled_trial_list(seed=12345)
    trials_b = mod.build_shuffled_trial_list(seed=12345)
    order_a = [(t["condition"], t["scenario"]["name"], t["task_name"], t["repeat_index"]) for t in trials_a]
    order_b = [(t["condition"], t["scenario"]["name"], t["task_name"], t["repeat_index"]) for t in trials_b]
    assert order_a == order_b


def test_shuffle_actually_interleaves_conditions_not_left_as_blocks():
    """ยืนยันว่าผลของการสุ่มไม่ได้ปล่อยให้ condition เดียวกันอยู่ติดกันเป็นบล็อก
    ยาวเหมือน Tier 5 เดิม (ซึ่งเป็นปัญหาที่ข้อ 3 ตั้งใจแก้) วัดง่ายๆ ด้วยจำนวน
    ครั้งที่ condition เปลี่ยนระหว่าง trial ที่ติดกัน ถ้าเป็นบล็อกล้วนจะมีแค่ 2
    จุดเปลี่ยน (none->adaptive->cache) จาก 659 คู่ที่ติดกัน ถ้าสุ่มดีควรเปลี่ยน
    บ่อยกว่านั้นมาก"""
    mod = _load_randomized_module()
    trials = mod.build_shuffled_trial_list(seed=RANDOM_SEED_FOR_TEST)
    conditions_in_order = [t["condition"] for t in trials]
    changes = sum(
        1 for i in range(1, len(conditions_in_order))
        if conditions_in_order[i] != conditions_in_order[i - 1]
    )
    # สุ่มจริงจาก 3 ค่าเท่าๆ กันควรเปลี่ยนราว 2/3 ของคู่ที่ติดกัน (~440 จาก 659)
    # ตั้งเกณฑ์แบบหลวมมากพอที่จะไม่ flaky แต่ยังจับบั๊ก "ลืมสุ่ม" ได้แน่นอน
    assert changes > 100, (
        f"condition เปลี่ยนแค่ {changes} ครั้งจาก 659 คู่ — ดูเหมือนลำดับยังเป็นบล็อกต่อเนื่องอยู่ "
        "ตรวจว่า random.shuffle() ถูกเรียกจริงหรือไม่"
    )


RANDOM_SEED_FOR_TEST = 20260101


def test_execution_order_manifest_matches_seed_used():
    mod = _load_randomized_module()
    assert mod.RANDOM_SEED == RANDOM_SEED_FOR_TEST


# ---------- run_tier8_jitter_floor.py (ข้อ 5) ----------

def test_jitter_floor_scenario_uses_projects_own_min_delay_constant():
    mod = load_module_from_path(
        "t8_jitter_floor_logic_test", os.path.join(TIER8_DIR, "run_tier8_jitter_floor.py"),
    )
    from experiment.scenarios import MIN_DELAY_FOR_JITTER_MS
    assert mod.JITTER_FLOOR_SCENARIO["delay_ms"] == MIN_DELAY_FOR_JITTER_MS
    assert mod.JITTER_FLOOR_SCENARIO["jitter_ms"] == 0
    assert mod.JITTER_FLOOR_SCENARIO["loss_pct"] == 0
    assert mod.JITTER_FLOOR_SCENARIO["bandwidth_kbit"] is None


# ---------- run_tier8_achieved_path.py (ข้อ 1) ----------

def _load_achieved_path_module():
    return load_module_from_path(
        "t8_achieved_path_logic_test", os.path.join(TIER8_DIR, "run_tier8_achieved_path.py"),
    )


def test_ollama_host_extracted_from_default_base_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    mod = _load_achieved_path_module()
    assert mod._ollama_host() == "host.docker.internal"


def test_ollama_host_extracted_from_custom_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.50:11434/v1")
    mod = _load_achieved_path_module()
    assert mod._ollama_host() == "192.168.1.50"


def test_ollama_probe_url_uses_api_tags_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.50:11434/v1")
    mod = _load_achieved_path_module()
    assert mod._ollama_probe_url() == "http://192.168.1.50:11434/api/tags"


def test_four_achieved_path_scenarios_match_papers_reference_points():
    """4 จุดต้องตรงกับจุดที่ sigconf.tex อ้างอิงอยู่แล้ว (loss=75%, delay=3000ms,
    bandwidth=50kbit, baseline) ไม่ใช่จุดใหม่ที่ไม่เคยมีในเปเปอร์"""
    mod = _load_achieved_path_module()
    names = {s["name"] for s in mod.TEST_SCENARIOS}
    assert names == {"t8ap_baseline", "t8ap_loss75", "t8ap_delay3000", "t8ap_bw50"}

    by_name = {s["name"]: s for s in mod.TEST_SCENARIOS}
    assert by_name["t8ap_loss75"]["loss_pct"] == 75
    assert by_name["t8ap_delay3000"]["delay_ms"] == 3000
    assert by_name["t8ap_bw50"]["bandwidth_kbit"] == 50
