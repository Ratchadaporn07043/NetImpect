"""
conftest.py -- shared pytest configuration for the whole Tier1-5 test suite
================================================================
Expected directory layout (already set up under netimpact_extended/):

    netimpact_extended/
      project_root/            <- baseline codebase copy (unmodified)
        logger.py
        multi_agent.py
        experiment/
          __init__.py
          scenarios.py
          tasks.py
          controller.py
          evaluator.py
          run_experiment.py
      Tier1_.../
      Tier2_.../
      Tier3_.../
      Tier4_.../
      Tier5_.../
      tests/                  <- this file lives here
        conftest.py
        fake_autogen.py
        test_*.py

All tests run fully offline -- no real Ollama/GPU/tc calls at all:
  - autogen is replaced by fake_autogen.py (deterministic, scriptable)
  - subprocess.run (for tc/netem) is monkeypatched via the mock_tc fixture
  - psutil is used for real (cheap, no side effects); pynvml is mocked
    separately in test_tier3_logger_gpu.py to test both the with/without-GPU cases
"""
import importlib.util
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENDED_ROOT = os.path.dirname(TESTS_DIR)

# PROJECT_ROOT = where the baseline multi_agent.py/logger.py/experiment/ live,
# used as the regression baseline by this test suite.
#
# Two supported cases:
#   1. Production (after copying tests_extended/ into the real NetImpact
#      project): tests_extended/ sits at the same level as multi_agent.py/
#      logger.py/experiment/ and the Tier1-5 folders directly -> PROJECT_ROOT
#      = EXTENDED_ROOT (the default).
#   2. Sandbox/dev (while building Tier1-5 itself): a separate project_root/
#      folder is kept so tests never touch the real files -> use that folder
#      instead if it actually exists.
# Can always be overridden directly with the NETIMPACT_PROJECT_ROOT env var.
_sandbox_project_root = os.path.join(EXTENDED_ROOT, "project_root")
if os.environ.get("NETIMPACT_PROJECT_ROOT"):
    PROJECT_ROOT = os.environ["NETIMPACT_PROJECT_ROOT"]
elif os.path.isdir(_sandbox_project_root) and os.path.isfile(
    os.path.join(_sandbox_project_root, "multi_agent.py")
):
    PROJECT_ROOT = _sandbox_project_root
else:
    PROJECT_ROOT = EXTENDED_ROOT

TIER_DIRS = {
    "tier1": os.path.join(EXTENDED_ROOT, "Tier1_เจาะจุดในแกนที่มีอยู่"),
    "tier2": os.path.join(EXTENDED_ROOT, "Tier2_แกนใหม่"),
    "tier3": os.path.join(EXTENDED_ROOT, "Tier3_โครงสร้างพื้นฐาน"),
    "tier4": os.path.join(EXTENDED_ROOT, "Tier4_Replication"),
    "tier5": os.path.join(EXTENDED_ROOT, "Tier5_Mitigation"),
    "tier6": os.path.join(EXTENDED_ROOT, "Tier6_MitigationXMultiRound"),
}

# make sure every tier runner script that reads NETIMPACT_PROJECT_ROOT sees the same project_root
os.environ.setdefault("NETIMPACT_PROJECT_ROOT", PROJECT_ROOT)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import fake_autogen  # noqa: E402

# always install fake_autogen in place of the real autogen for unit tests (deterministic, offline)
sys.modules["autogen"] = fake_autogen


def load_module_from_path(module_name: str, file_path: str):
    """Load a .py file from any path as a uniquely-named module.
    Needed when comparing multiple versions of multi_agent.py/logger.py/
    evaluator.py (base vs Tier2 vs Tier5 etc.) within the same test, without
    clobbering sys.modules."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_fake_autogen_scripts():
    """Reset fake_autogen's scripts before/after every test to avoid state leaking across tests."""
    fake_autogen.reset_scripts()
    yield
    fake_autogen.reset_scripts()


@pytest.fixture
def mock_tc(monkeypatch):
    """Monkeypatch subprocess.run so real tc/netem is never invoked while testing controller.py.
    Returns the list of commands invoked (list of list[str]) for assertions."""
    import subprocess

    calls = []

    class _FakeCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _fake_run(cmd, capture_output=True, text=True):
        calls.append(list(cmd))
        return _FakeCompletedProcess(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls


@pytest.fixture
def tmp_log_dir(tmp_path):
    d = tmp_path / "logs_test"
    d.mkdir()
    return str(d)
