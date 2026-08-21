"""
Logging Module
===============
Stores four log groups according to the diagram:
  1. Message Log            (timestamp, from, to, content, token count)
  2. Network Condition Log  (delay/loss/jitter ที่ตั้งไว้ตอนนั้น)
  3. Retry/Timeout/Error Log
  4. Resource Log           (CPU/RAM)

Added beyond the original design:
  5. Task Outcome Log       (success/fail + rounds + rejections)

Writes one JSON file per run under logs/.
"""
import json
import os
import time
import uuid
import psutil


def _estimate_tokens(text: str) -> int:
    """Estimate tokens without requiring tiktoken or network access."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class ExperimentLogger:
    def __init__(self, scenario: dict, task_name: str, run_index: int, log_dir: str = "logs"):
        """
        Args:
            scenario: Network scenario dictionary, such as delay_300ms.
            task_name: Name of the task being tested.
            run_index: Repeat index.
            log_dir: Directory where log files are written.
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

        # Capture the initial resource snapshot.
        self.log_resource(tag="start")

    # ---------- 1. Message Log ----------
    def log_message(self, from_agent: str, to_agent: str, content: str, timestamp: float = None):
        """
        Args:
            timestamp: Actual send time from time.time(). If omitted, use the
                function-call time as a fallback. Callers should provide the
                actual timestamp so per-message network latency remains measurable.
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

        # Use the caller-provided retry count once. Previously it was added to
        # the retry error entries, double-counting retries in the output log.
        self.data["outcome"] = {
            "success": success,
            "rounds": rounds,
            "reviewer_rejections": rejections,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total_tokens": total_tokens,
            "quality_score": quality_score,   # 1-5 from the Reviewer, or None if unavailable.
            "ground_truth_score": ground_truth_score,  # 1-5 from the post-task evaluator.
            "ground_truth_passed": ground_truth_passed,
            "retry_count": retries,
            "timeout_count": len([e for e in self.data["errors"] if e["error_type"] == "timeout"]),
            "total_error_count": len(self.data["errors"]),
        }

    # ---------- File persistence ----------
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