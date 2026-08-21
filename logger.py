"""
Logging Module
===============
เก็บ log 4 กลุ่มตาม diagram:
  1. Message Log            (timestamp, from, to, content, token count)
  2. Network Condition Log  (delay/loss/jitter ที่ตั้งไว้ตอนนั้น)
  3. Retry/Timeout/Error Log
  4. Resource Log           (CPU/RAM)

เพิ่มจากที่คุยไว้ก่อนหน้า:
  5. Task Outcome Log       (success/fail + rounds + rejections)

บันทึกออกมาเป็นไฟล์ JSON 1 ไฟล์ต่อ 1 run ใน logs/
"""
import json
import os
import time
import uuid
import psutil


def _estimate_tokens(text: str) -> int:
    """ประมาณ token คร่าวๆ (ไม่ต้องพึ่ง tiktoken/network) ~1 token ทุก 4 ตัวอักษร"""
    if not text:
        return 0
    return max(1, len(text) // 4)


class ExperimentLogger:
    def __init__(self, scenario: dict, task_name: str, run_index: int, log_dir: str = "logs"):
        """
        Args:
            scenario: dict เช่น {"name": "delay_300ms", "delay_ms": 300, "loss_pct": 0,
                                  "jitter_ms": 0, "bandwidth_limit": None}
            task_name: ชื่อ task ที่กำลังทดสอบ เช่น "coding_task"
            run_index: รอบที่เท่าไหร่ (สำหรับ repeat N >= 10 ครั้ง)
            log_dir: โฟลเดอร์ที่จะเขียนไฟล์ log ลงไป
        """
        self.run_id = str(uuid.uuid4())[:8]
        self.scenario = scenario
        self.task_name = task_name
        self.run_index = run_index
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        self.start_time = time.time()

        self.data = {
            "run_id": self.run_id,
            "task_name": task_name,
            "run_index": run_index,
            "started_at": self.start_time,
            # 2. Network Condition Log
            "network_condition": scenario,
            # 1. Message Log
            "messages": [],
            # 3. Retry/Timeout/Error Log
            "errors": [],
            # 4. Resource Log
            "resource_snapshots": [],
            # 5. Task Outcome Log
            "outcome": None,
            # 6. Ground Truth Evaluation Log
            "evaluation": None,
        }

        # snapshot resource ตอนเริ่ม
        self.log_resource(tag="start")

    # ---------- 1. Message Log ----------
    def log_message(self, from_agent: str, to_agent: str, content: str, timestamp: float = None):
        """
        Args:
            timestamp: เวลาจริง (จาก time.time()) ที่ message ถูกส่งออกไปจริงๆ
                ถ้าไม่ส่งมา จะใช้เวลา ณ ตอนเรียกฟังก์ชันนี้แทน (fallback เดิม)
                สำคัญ: caller (multi_agent.py) ควรส่ง timestamp จริงมาเสมอ
                เพราะถ้า log_message() ถูกเรียกทีเดียวหลังบทสนทนาทั้งหมดจบแล้ว
                (เช่นวน loop ใน finally block) ทุก message จะได้ timestamp
                เกาะติดกันเป็นก้อนเดียว ทำให้วัด latency ต่อ message จาก
                network delay ไม่ได้เลย
        """
        entry = {
            "timestamp": timestamp if timestamp is not None else time.time(),
            "from": str(from_agent),
            "to": str(to_agent),
            "content": content,
            "tokens": _estimate_tokens(content),
        }
        self.data["messages"].append(entry)

    # ---------- 3. Retry / Timeout / Error Log ----------
    def log_error(self, error_type: str, detail: str = ""):
        entry = {
            "timestamp": time.time(),
            "error_type": error_type,
            "detail": detail,
        }
        self.data["errors"].append(entry)

    def log_retry(self, reason: str = ""):
        self.log_error(error_type="retry", detail=reason)

    def log_timeout(self, detail: str = ""):
        self.log_error(error_type="timeout", detail=detail)

    # ---------- 6. Ground Truth Evaluation Log ----------
    def log_evaluation(self, evaluation: dict):
        self.data["evaluation"] = evaluation

    # ---------- 4. Resource Log ----------
    def log_resource(self, tag: str = ""):
        entry = {
            "timestamp": time.time(),
            "tag": tag,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
        }
        self.data["resource_snapshots"].append(entry)

    # ---------- 5. Task Outcome Log ----------
    def log_outcome(self, success: bool, rounds: int, rejections: int, elapsed_seconds: float,
                     quality_score=None, retries: int = 0, evaluation: dict = None):
        if evaluation is not None:
            self.log_evaluation(evaluation)

        total_tokens = sum(m["tokens"] for m in self.data["messages"])
        ground_truth_score = None
        ground_truth_passed = None
        if self.data.get("evaluation"):
            ground_truth_score = self.data["evaluation"].get("score")
            ground_truth_passed = self.data["evaluation"].get("passed")

        # แก้ไข: เดิมบวก `retries` (ที่ multi_agent.py ส่งเข้ามา) เข้ากับจำนวน
        # entry ที่ error_type == "retry" ใน self.data["errors"] ซึ่งเป็นตัวเลข
        # เดียวกัน (multi_agent.py เรียก logger.log_retry() ทุกครั้งที่ retry
        # พร้อมกับส่ง retries_used เข้า log_outcome ด้วย) ผลคือนับซ้ำ 2 เท่า
        # เช่น retry จริง 2 ครั้ง -> retry_count ในไฟล์ log กลายเป็น 4
        # ตอนนี้ใช้ค่า `retries` ที่ส่งเข้ามาเพียงอย่างเดียว ไม่บวกซ้ำกับ errors log
        self.data["outcome"] = {
            "success": success,
            "rounds": rounds,
            "reviewer_rejections": rejections,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total_tokens": total_tokens,
            "quality_score": quality_score,   # 1-5 จาก Reviewer, None ถ้า parse ไม่ได้
            "ground_truth_score": ground_truth_score,  # 1-5 จาก evaluator หลังจบงาน
            "ground_truth_passed": ground_truth_passed,
            "retry_count": retries,
            "timeout_count": len([e for e in self.data["errors"] if e["error_type"] == "timeout"]),
            "total_error_count": len(self.data["errors"]),
        }

    # ---------- บันทึกไฟล์ ----------
    def save(self) -> str:
        """บันทึกลงไฟล์ JSON คืนค่า path ของไฟล์ที่บันทึก"""
        self.log_resource(tag="end")
        self.data["ended_at"] = time.time()

        scenario_name = self.scenario.get("name", "scenario")
        phase = self.scenario.get("experiment_phase")
        if phase:
            scenario_name = f"{phase}__{scenario_name}"

        tournament = self.scenario.get("tournament") or {}
        if tournament.get("match_id") and tournament.get("side"):
            scenario_name = f"{tournament['match_id']}__side{tournament['side']}__{scenario_name}"

        filename = f"{self.task_name}__{scenario_name}__run{self.run_index}__{self.run_id}.json"
        filepath = os.path.join(self.log_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

        return filepath