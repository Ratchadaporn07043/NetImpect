"""
conftest.py — pytest configuration สำหรับ Tier8_EnsureScopeClosure/tests_tier8/
================================================================================
รันทั้งชุดแบบ offline ล้วนๆ ไม่แตะ Ollama/GPU/tc จริงเลย เหมือนกับ
tests_extended/ เดิมของโปรเจกต์:
  - autogen ถูกแทนที่ด้วย fake_autogen.py (deterministic, scriptable)
  - subprocess.run (สำหรับ tc/ip/ping/curl/ethtool) ถูก monkeypatch ผ่าน
    fixture mock_tc
  - psutil ใช้ของจริง (เบา ไม่มีผลข้างเคียง)

รันด้วย:
    cd Tier8_EnsureScopeClosure
    python3 -m pytest tests_tier8/ -q
"""
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TIER8_DIR = os.path.dirname(TESTS_DIR)
PROJECT_ROOT = os.path.dirname(TIER8_DIR)

# ต้องใส่ Tier8_EnsureScopeClosure ก่อน project root เสมอ กัน Python เผลอไปเจอ
# experiment/controller.py, logger.py, หรือ multi_agent.py ที่ root (ไม่มี
# ความสามารถที่ Tier8 ใช้ — ตรวจพบจริงระหว่างเขียนเทสชุดนี้ว่าถ้าใส่ผิดลำดับ
# `import multi_agent` จะไปโดนไฟล์ที่ root แทน เพราะ list.insert(0, p) วนซ้ำ
# ทำให้ตัวที่ insert "หลังสุด" ไปอยู่ตำแหน่ง 0 จริง ไม่ใช่ตัวแรกในลำดับที่เขียน)
# ต้อง insert(0, TIER8_DIR) เป็นลำดับสุดท้ายเพื่อให้ TIER8_DIR อยู่ตำแหน่ง 0 จริง
for p in (TESTS_DIR, PROJECT_ROOT, TIER8_DIR):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import fake_autogen  # noqa: E402

sys.modules["autogen"] = fake_autogen


def load_module_from_path(module_name: str, file_path: str):
    """Load a .py file from any path as a uniquely-named module (ใช้เทส
    run_tier8_*.py ทุกตัวว่า import ได้ไม่ error โดยไม่ต้องรันจริง)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_fake_autogen_scripts():
    fake_autogen.reset_scripts()
    yield
    fake_autogen.reset_scripts()


@pytest.fixture
def mock_tc(monkeypatch):
    """Monkeypatch subprocess.run สำหรับ controller.py ของ Tier8 (ทุกคำสั่ง:
    tc/ip/ping/curl/ethtool) คืน list ของคำสั่งที่ถูกเรียกจริง (list of list[str])
    เพื่อใช้ assert รูปแบบคำสั่ง โดย default คืน returncode=0, stdout ว่าง —
    ใช้ค่า stdout_map เพื่อกำหนด stdout เฉพาะสำหรับคำสั่งที่ต้องการ parse ผล"""
    import subprocess

    class _CallList(list):
        """list ธรรมดา set attribute เพิ่มไม่ได้ (ไม่มี __dict__) ต้อง subclass
        เพื่อแนบ stdout_map ไว้กับ object เดียวกันที่เทสรับไป"""
        pass

    calls = _CallList()
    calls.stdout_map = {}  # substring ของ cmd -> stdout ที่จะคืน

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
