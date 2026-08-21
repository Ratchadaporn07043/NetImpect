"""
conftest.py — pytest configuration สำหรับ Tier9_CriticalThresholdRecalibration/tests_tier9/
================================================================================
รันทั้งชุดแบบ offline ล้วนๆ ไม่แตะ Ollama/GPU/tc จริงเลย:
  - autogen ถูกแทนที่ด้วย fake_autogen.py (deterministic, scriptable, มี
    register_model_client() no-op เพื่อรองรับ Tier9's multi_agent.py ที่ผูก
    custom client จริง)
  - subprocess.run (สำหรับ tc/ip/ping/curl/ethtool ของ tier9_controller.py)
    ถูก monkeypatch ผ่าน fixture mock_tc
  - psutil ใช้ของจริง (เบา ไม่มีผลข้างเคียง)

Tier 9 standalone เต็มรูปแบบ — ไม่ต้องพึ่ง Tier8_EnsureScopeClosure/ หรือ
experiment/ ที่ root โปรเจกต์เลย (tier9_controller.py, tier9_logger.py,
tier9_checkpoint_utils.py, tier9_tasks.py, tier9_evaluator.py เป็นสำเนา
standalone ของตัวเองทั้งหมด) sys.path จึงต้องมีแค่ 2 ระดับ:
  1. TIER9_DIR — multi_agent.py, ollama_native_client.py, tier9_*.py ทั้งหมด
  2. TESTS_DIR — fake_autogen.py (เฉพาะตอนรันเทส)

รันด้วย:
    cd Tier9_CriticalThresholdRecalibration
    python3 -m pytest tests_tier9/ -q
"""
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TIER9_DIR = os.path.dirname(TESTS_DIR)

for p in (TESTS_DIR, TIER9_DIR):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, TESTS_DIR)  # fake_autogen.py อยู่ในนี้
sys.path.insert(0, TIER9_DIR)  # insert ท้ายสุด -> อยู่ index 0 จริง

import fake_autogen  # noqa: E402

sys.modules["autogen"] = fake_autogen


def load_module_from_path(module_name: str, file_path: str):
    """Load a .py file from any path as a uniquely-named module"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_fake_autogen_state():
    fake_autogen.reset_scripts()
    fake_autogen.reset_registered_model_clients()
    yield
    fake_autogen.reset_scripts()
    fake_autogen.reset_registered_model_clients()


@pytest.fixture
def mock_tc(monkeypatch):
    """Monkeypatch subprocess.run สำหรับ tier9_controller.py — ทุกคำสั่ง
    tc/ip/ping/curl/ethtool คืน list ของคำสั่งที่
    ถูกเรียกจริง (list of list[str]) เพื่อใช้ assert รูปแบบคำสั่ง โดย default
    คืน returncode=0, stdout ว่าง — ใช้ stdout_map เพื่อกำหนด stdout เฉพาะ
    สำหรับคำสั่งที่ต้องการ parse ผล"""
    import subprocess

    class _CallList(list):
        pass

    calls = _CallList()
    calls.stdout_map = {}

    class _FakeCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(list(cmd))
        joined = " ".join(cmd)
        for substr, stdout in calls.stdout_map.items():
            if substr in joined:
                return _FakeCompletedProcess(returncode=0, stdout=stdout, stderr="")
        return _FakeCompletedProcess(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls


@pytest.fixture
def tmp_log_dir(tmp_path):
    d = tmp_path / "logs_test"
    d.mkdir()
    return str(d)
