"""
Logging Module — Tier 8 (Scope Closure, fresh-environment build)
==================================================================
สำเนาของ `logger.py` ที่ root โปรเจกต์ บวก 2 อย่างที่ Tier 8 ต้องใช้ ซึ่งทั้งคู่
เป็น additive ล้วนๆ (ของเดิมที่ root/`Tier3_.../logger.py` ยังไม่มีอะไรพวกนี้เลย
— ตรวจยืนยันแล้วก่อนเริ่มเขียนไฟล์นี้):

TIER8 CHANGE 1 — พารามิเตอร์ `agent=None` ใน log_error()/log_retry()/log_timeout()
    นี่คือจุดที่ Tier 7 (7A) พังจริง: `Tier7_ScopeClosure/multi_agent.py` เรียก
    `logger.log_timeout(..., agent=blamed_agent)` แต่ `logger.py` ที่ root
    ไม่มีพารามิเตอร์นี้เลย ทำให้ทุก timeout/error จริงกลายเป็น TypeError ที่หลุด
    ออกจาก try/except ของ attempt เดี่ยว ตัด retry ทิ้งทั้งหมด (ดูรายละเอียดเต็ม
    ที่ `Paper/NetImpact.md/Current/NetImpact_20_Tier7_Scope_Closure.md` §3.1)
    ที่นี่เพิ่มพารามิเตอร์จริง มี default เป็น None จึงเรียกแบบเดิมได้เป๊ะ
    (backward compatible) — และมีเทสยืนยันเป็นการเฉพาะใน tests_tier8/ ว่า
    เรียกทั้งแบบมี agent= และไม่มี agent= ก็ไม่ throw

TIER8 CHANGE 2 — log_achieved() สำหรับข้อมูล achieved-path (ข้อ 1 ใน 5 ข้อ)
    เก็บผลจาก NetworkController.snapshot_achieved()/measure_rtt_ms()/
    background_transfer_probe() ไว้คนละ key จาก network_condition (ซึ่งเป็นค่า
    configured เท่านั้น) เพื่อไม่ให้ configured กับ achieved ปนกันในไฟล์เดียว
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
            scenario: dict ของ configured network condition เช่น {"name": ...,
                "delay_ms": ..., "loss_pct": ..., "jitter_ms": ..., "bandwidth_kbit": ...}
            task_name: ชื่อ task ที่กำลังทดสอบ เช่น "coding_task"
            run_index: รอบที่เท่าไหร่ (สำหรับ repeat N >= 1 ครั้ง)
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
            # 2. Network Condition Log (configured values only)
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
            # 7. TIER8: achieved-path measurement log (ไม่ใช่ configured — ดูหัวข้อ log_achieved)
            "achieved": None,
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
    def log_error(self, error_type: str, detail: str = "", agent: str = None):
        """TIER8 CHANGE 1: เพิ่ม agent=None (backward compatible — เรียกแบบเดิม
        โดยไม่ส่ง agent ก็ยังใช้ได้เป๊ะ) บันทึกว่า agent ตัวไหนกำลังจะถูกเรียก
        ต่อ (round-robin) ตอนที่ error/timeout เกิดขึ้น อนุมานจาก transcript ณ
        เวลานั้นโดย caller (ดู multi_agent.py::_blame_agent) ไม่ใช่การเดาที่นี่"""
        entry = {
            "timestamp": time.time(),
            "error_type": error_type,
            "detail": detail,
            "agent": agent,
        }
        self.data["errors"].append(entry)

    def log_retry(self, reason: str = "", agent: str = None):
        self.log_error(error_type="retry", detail=reason, agent=agent)

    def log_timeout(self, detail: str = "", agent: str = None):
        self.log_error(error_type="timeout", detail=detail, agent=agent)

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

    # ---------- 7. TIER8: Achieved-path Measurement Log ----------
    def log_achieved(self, achieved: dict):
        """บันทึกผลวัด achieved path (ข้อ 1/5) แยกจาก network_condition โดย
        เจตนา: network_condition คือค่าที่ "ตั้ง" (configured), ส่วนคีย์นี้คือค่า
        ที่ "วัดได้จริง" (achieved) — สองอย่างนี้ต้องไม่ปนกันไม่ว่ากรณีใด เพราะ
        คือใจความสำคัญของช่องว่างที่ Tier 8 ข้อ 1 ปิดอยู่
        โครงสร้างที่คาดหวัง (จาก controller.py):
          {
            "before": {"qdisc_egress": {...}, "qdisc_ingress": {...}|None,
                       "tcp_retrans_segs": int, "timestamp": float},
            "after":  {same shape},
            "rtt_probe": {"min_ms":..,"avg_ms":..,"max_ms":..,"mdev_ms":..,
                          "packet_loss_pct":.., "target": str} | None,
            "throughput_probe": {"bytes": int, "seconds": float,
                                  "achieved_kbit_s": float, "target": str} | None,
          }
        """
        self.data["achieved"] = achieved

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

        # ใช้ค่า `retries` ที่ caller ส่งเข้ามาเพียงอย่างเดียว ไม่บวกซ้ำกับจำนวน
        # entry ที่ error_type == "retry" ใน errors log (จุดที่เคยแก้ไว้แล้วใน
        # logger.py รุ่นก่อนหน้า — คงพฤติกรรมเดิมไว้ที่นี่)
        self.data["outcome"] = {
            "success": success,
            "rounds": rounds,
            "reviewer_rejections": rejections,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total_tokens": total_tokens,
            "quality_score": quality_score,
            "ground_truth_score": ground_truth_score,
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
