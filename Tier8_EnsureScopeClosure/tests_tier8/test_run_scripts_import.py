"""
Sanity import test สำหรับ run_tier8_*.py ทั้ง 5 ตัว
================================================================
เป้าหมายเดียวกับ tests_extended/test_tier_runners_import.py ของโปรเจกต์เดิม:
จับ syntax error/import error/typo ตั้งแต่ตอนนี้ ก่อนเอาไปรันจริงบนเครื่องใหม่ที่
มี Ollama/GPU (ซึ่งกว่าจะรู้ว่าพังอาจเสียเวลาหลายชั่วโมงต่อ arm)

ทุกไฟล์ที่เทสในนี้ออกแบบให้ import ได้อย่างปลอดภัยโดยไม่เรียก network/LLM จริง —
logic ทั้งหมดที่แตะ network/subprocess/LLM ถูกห่อไว้ใน main()/if __name__ ==
'__main__' เท่านั้น (การ import ที่หนักสุด คือ `import multi_agent` ก็ถูกเลื่อน
ไปเรียกข้างใน main() ไม่ใช่ตอน import module เอง)
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
    assert os.path.isfile(path), f"ไม่พบไฟล์ {path}"
    mod = load_module_from_path(module_name, path)
    assert hasattr(mod, "main")
    assert callable(mod.main)


def test_tier8_has_a_readme():
    readme_path = os.path.join(TIER8_DIR, "README.md")
    assert os.path.isfile(readme_path), "Tier8_EnsureScopeClosure ขาด README.md"
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()
    assert len(content) > 500


def test_tier8_checkpoint_utils_functions_exist():
    from checkpoint_utils import load_checkpoint, save_checkpoint, mark_completed, should_skip
    assert callable(load_checkpoint)
    assert callable(save_checkpoint)
    assert callable(mark_completed)
    assert callable(should_skip)
