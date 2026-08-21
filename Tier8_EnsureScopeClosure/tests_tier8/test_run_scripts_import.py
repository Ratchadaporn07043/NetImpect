"""
Sanity import tests for all five run_tier8_*.py scripts.
================================================================
The goal matches tests_extended/test_tier_runners_import.py: catch syntax, import,
and typo errors before running on a new machine.
has Ollama/GPU (where import failures could otherwise waste hours per arm)

Every file is designed to import safely without real network/LLM calls. Network,
subprocess, and LLM logic runs only under main(); even the heavy multi_agent import
is deferred until main().
"""
import os

import pytest
from conftest import TIER8_DIR, load_module_from_path

RUNNER_SCRIPTS = [
    ("t8_achieved_path_import", "run_tier8_achieved_path.py"),
    ("t8_fixed_timeout_import", "run_tier8_fixed_timeout.py"),
    ("t8_randomized_mitigation_import", "run_tier8_randomized_mitigation.py"),
    ("t8_ingress_import", "run_tier8_ingress.py"),
    ("t8_jitter_floor_import", "run_tier8_jitter_floor.py"),
]


@pytest.mark.parametrize("module_name,filename", RUNNER_SCRIPTS)
def test_runner_script_imports_without_error(module_name, filename):
    path = os.path.join(TIER8_DIR, filename)
    assert os.path.isfile(path), f"File not found: {path}"
    mod = load_module_from_path(module_name, path)
    assert hasattr(mod, "main")
    assert callable(mod.main)


def test_tier8_has_a_readme():
    readme_path = os.path.join(TIER8_DIR, "README.md")
    assert os.path.isfile(readme_path), "Tier8_EnsureScopeClosure is missing README.md"
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()
    assert len(content) > 500


def test_tier8_checkpoint_utils_functions_exist():
    from checkpoint_utils import load_checkpoint, save_checkpoint, mark_completed, should_skip
    assert callable(load_checkpoint)
    assert callable(save_checkpoint)
    assert callable(mark_completed)
    assert callable(should_skip)
