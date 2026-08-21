"""
ยืนยันโดยเฉพาะว่า Tier8_EnsureScopeClosure/logger.py แก้บั๊กที่ทำให้ 7A ของ Tier 7
ใช้ไม่ได้แล้วจริง: log_error()/log_retry()/log_timeout() ต้องรับ agent=
kwarg ได้โดยไม่ throw TypeError ทั้งตอนส่งและไม่ส่ง (backward compatible)

นี่คือเทสที่สำคัญที่สุดของทั้งชุด — ถ้าเทสนี้ผ่านแต่ของจริงยังพังแปลว่ามีไฟล์
logger.py อื่นถูก import แทน (เช่น sys.path ผิดลำดับ) ไม่ใช่โค้ดนี้เอง
"""
from logger import ExperimentLogger


def _new_logger(tmp_log_dir):
    return ExperimentLogger(
        scenario={"name": "test_scenario", "delay_ms": 0, "loss_pct": 0, "jitter_ms": 0},
        task_name="coding_task", run_index=1, log_dir=tmp_log_dir,
    )


def test_log_timeout_accepts_agent_kwarg(tmp_log_dir):
    logger = _new_logger(tmp_log_dir)
    logger.log_timeout(detail="simulated timeout", agent="Worker")
    entry = logger.data["errors"][-1]
    assert entry["error_type"] == "timeout"
    assert entry["agent"] == "Worker"


def test_log_error_accepts_agent_kwarg(tmp_log_dir):
    logger = _new_logger(tmp_log_dir)
    logger.log_error(error_type="APIConnectionError", detail="simulated", agent="Reviewer")
    entry = logger.data["errors"][-1]
    assert entry["agent"] == "Reviewer"


def test_log_retry_accepts_agent_kwarg(tmp_log_dir):
    logger = _new_logger(tmp_log_dir)
    logger.log_retry(reason="retrying", agent="Planner")
    entry = logger.data["errors"][-1]
    assert entry["error_type"] == "retry"
    assert entry["agent"] == "Planner"


def test_log_timeout_without_agent_still_works_backward_compatible(tmp_log_dir):
    """เรียกแบบเดิม (ไม่ส่ง agent เลย) ต้องยังใช้ได้เป๊ะ — ไม่บังคับให้ caller เก่า
    ต้องแก้โค้ดตาม"""
    logger = _new_logger(tmp_log_dir)
    logger.log_timeout(detail="simulated timeout")
    entry = logger.data["errors"][-1]
    assert entry["agent"] is None


def test_log_error_without_agent_defaults_to_none(tmp_log_dir):
    logger = _new_logger(tmp_log_dir)
    logger.log_error(error_type="fatal_error", detail="x")
    assert logger.data["errors"][-1]["agent"] is None


def test_log_achieved_stores_under_separate_key_from_network_condition(tmp_log_dir):
    """achieved-path data (ข้อ 1) ต้องไม่ปนกับ network_condition (configured)"""
    logger = _new_logger(tmp_log_dir)
    achieved = {"before": {"qdisc_egress": {"dropped": 0}}, "after": {"qdisc_egress": {"dropped": 15}}}
    logger.log_achieved(achieved)
    assert logger.data["achieved"] == achieved
    assert logger.data["network_condition"] != achieved


def test_save_writes_valid_json_with_agent_field(tmp_log_dir):
    import json
    logger = _new_logger(tmp_log_dir)
    logger.log_timeout(detail="x", agent="Worker")
    logger.log_outcome(success=False, rounds=1, rejections=0, elapsed_seconds=12.3)
    path = logger.save()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["errors"][0]["agent"] == "Worker"
    assert data["outcome"]["timeout_count"] == 1
