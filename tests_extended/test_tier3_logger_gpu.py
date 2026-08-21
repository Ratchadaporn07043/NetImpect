"""Tier3 logger.py (GPU logging) tests — ทดสอบทั้ง 2 กรณี: (1) ไม่มี pynvml/GPU เลย
ต้อง fallback เป็น None แบบไม่ crash (2) มี pynvml + GPU จำลอง ต้องอ่านค่าออกมาได้ถูกต้อง"""
import json
import os
import sys

from conftest import TIER_DIRS, load_module_from_path

TIER3_DIR = TIER_DIRS["tier3"]
LOGGER_PATH = os.path.join(TIER3_DIR, "logger.py")


def _load_logger_without_pynvml():
    sys.modules.pop("pynvml", None)
    return load_module_from_path("tier3_logger_no_gpu", LOGGER_PATH)


class _FakeUtil:
    def __init__(self, gpu=42, memory=17):
        self.gpu = gpu
        self.memory = memory


class _FakeMemInfo:
    def __init__(self, used_bytes=2 * 1024 * 1024 * 1024, total_bytes=8 * 1024 * 1024 * 1024):
        self.used = used_bytes
        self.total = total_bytes


class _FakePynvml:
    NVML_TEMPERATURE_GPU = 0

    def nvmlInit(self):
        pass

    def nvmlDeviceGetCount(self):
        return 1

    def nvmlDeviceGetHandleByIndex(self, index):
        return f"handle-{index}"

    def nvmlDeviceGetUtilizationRates(self, handle):
        return _FakeUtil(gpu=42, memory=17)

    def nvmlDeviceGetMemoryInfo(self, handle):
        return _FakeMemInfo()

    def nvmlDeviceGetTemperature(self, handle, sensor_type):
        return 65

    def nvmlDeviceGetPowerUsage(self, handle):
        return 150000  # milliwatts -> 150.0 watts


def _load_logger_with_fake_pynvml():
    sys.modules["pynvml"] = _FakePynvml()
    try:
        return load_module_from_path("tier3_logger_with_gpu", LOGGER_PATH)
    finally:
        sys.modules.pop("pynvml", None)  # กัน leak ไปเทสอื่น


def test_logger_without_pynvml_falls_back_gracefully_no_crash(tmp_log_dir):
    mod = _load_logger_without_pynvml()
    assert mod._NVML_AVAILABLE is False

    logger = mod.ExperimentLogger(
        scenario={"name": "s", "delay_ms": 0, "jitter_ms": 0, "loss_pct": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )
    snapshot = logger.data["resource_snapshots"][-1]
    assert snapshot["gpu"] is None
    assert snapshot["gpu_all"] == []
    assert logger.data["gpu_monitoring_available"] is False

    # ยังต้องเซฟไฟล์ JSON ได้ปกติ schema เดิมครบทุก key
    path = logger.save()
    with open(path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert "resource_snapshots" in saved
    assert saved["resource_snapshots"][0]["cpu_percent"] is not None
    os.remove(path)


def test_logger_with_fake_gpu_reads_utilization_and_memory(tmp_log_dir):
    mod = _load_logger_with_fake_pynvml()
    assert mod._NVML_AVAILABLE is True

    logger = mod.ExperimentLogger(
        scenario={"name": "s", "delay_ms": 0, "jitter_ms": 0, "loss_pct": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )
    snapshot = logger.data["resource_snapshots"][-1]
    assert snapshot["gpu"]["gpu_util_percent"] == 42
    assert snapshot["gpu"]["vram_util_percent"] == 17
    assert snapshot["gpu"]["vram_used_mb"] == 2048.0
    assert snapshot["gpu"]["vram_total_mb"] == 8192.0
    assert snapshot["gpu"]["temperature_c"] == 65
    assert snapshot["gpu"]["power_watts"] == 150.0
    assert len(snapshot["gpu_all"]) == 1
    assert logger.data["gpu_monitoring_available"] is True


def test_gpu_read_failure_does_not_crash_the_trial(tmp_log_dir):
    """จำลอง driver hiccup กลางคัน (raise Exception ตอนอ่าน) ต้องได้ gpu=None
    ไม่ crash ทั้ง trial"""

    class _FlakyPynvml(_FakePynvml):
        def nvmlDeviceGetUtilizationRates(self, handle):
            raise RuntimeError("simulated driver hiccup")

    sys.modules["pynvml"] = _FlakyPynvml()
    try:
        mod = load_module_from_path("tier3_logger_flaky_gpu", LOGGER_PATH)
    finally:
        sys.modules.pop("pynvml", None)

    logger = mod.ExperimentLogger(
        scenario={"name": "s", "delay_ms": 0, "jitter_ms": 0, "loss_pct": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )
    snapshot = logger.data["resource_snapshots"][-1]
    assert snapshot["gpu"] is None  # อ่านไม่ได้ -> None ไม่ raise ออกมา


def test_log_schema_unchanged_besides_added_gpu_keys(tmp_log_dir):
    """ยืนยันว่า key เดิมทั้งหมดยังอยู่ครบ (เครื่องมือ parse log เดิม เช่น
    parse_logs.py ต้องยังใช้งานได้โดยไม่ต้องแก้)"""
    mod = _load_logger_without_pynvml()
    logger = mod.ExperimentLogger(
        scenario={"name": "s", "delay_ms": 0, "jitter_ms": 0, "loss_pct": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )
    logger.log_message(from_agent="Planner", to_agent="group", content="plan")
    logger.log_outcome(success=True, rounds=3, rejections=0, elapsed_seconds=12.3, quality_score=5)
    path = logger.save()
    with open(path, "r", encoding="utf-8") as f:
        saved = json.load(f)

    expected_top_level_keys = {
        "run_id", "task_name", "run_index", "started_at", "network_condition",
        "messages", "errors", "resource_snapshots", "outcome", "evaluation",
        "gpu_monitoring_available", "ended_at",
    }
    assert expected_top_level_keys.issubset(saved.keys())
    os.remove(path)
