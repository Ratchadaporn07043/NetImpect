"""
Logging Module — Tier3 REPLACEMENT (เพิ่ม GPU/VRAM logging)
================================================================
ไฟล์นี้แทนที่ logger.py ต้นฉบับที่ root ของโปรเจกต์ (สำรองไฟล์เดิมไว้ก่อน!)

การเปลี่ยนแปลงจากต้นฉบับ (ค้นหาคำว่า "TIER3 CHANGE"):
  - log_resource() พยายามอ่าน GPU utilization / VRAM usage / GPU temperature
    ผ่าน pynvml (NVIDIA Management Library) เพิ่มเข้าไปในทุก snapshot
  - Graceful fallback แบบ 3 ชั้น: (1) pynvml ไม่ได้ติดตั้ง -> gpu=None ทั้งหมด
    ไม่ crash, (2) pynvml ติดตั้งแต่เครื่องไม่มี NVIDIA GPU (เช่นรันบน CPU-only
    หรือ Apple Silicon) -> gpu=None เหมือนกัน ไม่ crash, (3) เรียก pynvml สำเร็จ
    ครั้งแรกแต่ error ทีหลัง (เช่น driver hiccup) -> catch เฉพาะจุด ไม่ทำให้
    ทั้ง trial ล้ม
  - เหตุผลที่ต้องมี: multi-agent LLM inference (Qwen3:8b ผ่าน Ollama) ใช้ GPU
    เป็นคอขวดสำคัญ แต่ log เดิมมีแค่ CPU/RAM (psutil) เท่านั้น ทำให้วิเคราะห์
    ไม่ได้ว่า "ผลลัพธ์ที่ดูเหมือนเกิดจาก network delay สูง แท้จริงแล้วเกิดจาก
    GPU ติดขัด/VRAM เต็มร่วมด้วยหรือเปล่า" (โดยเฉพาะ trial ที่รันขนานกันหรือ
    เครื่องมีโหลดอื่นแทรก)

ผลกระทบต่อไฟล์ log เดิม: schema เดิมทุก key ยังอยู่ครบ (ไม่มีการลบ/เปลี่ยนชื่อ
key ใดๆ) มีแค่เพิ่ม key "gpu" เข้าไปใน resource_snapshots entry แต่ละอัน
เท่านั้น -> เครื่องมือ parse log เดิม (parse_logs.py, evaluate_logs.py ฯลฯ)
ยังใช้งานได้ปกติทุกประการ ไม่ต้องแก้อะไร
"""
import json
import os
import time
import uuid
import psutil

# TIER3 CHANGE: พยายาม import pynvml แบบ optional — ถ้าไม่มีให้ทำงานต่อได้ปกติ
try:
    import pynvml
    try:
        pynvml.nvmlInit()
        _NVML_AVAILABLE = True
    except Exception:
        _NVML_AVAILABLE = False
except ImportError:
    pynvml = None
    _NVML_AVAILABLE = False


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


# TIER3 CHANGE: ฟังก์ชันอ่าน GPU stats แบบ fail-safe เต็มรูปแบบ
def _read_gpu_stats(gpu_index: int = 0):
    """คืน dict ของสถานะ GPU ตัวที่ gpu_index หรือ None ทั้งหมดถ้าอ่านไม่ได้
    ไม่มีทาง raise exception ออกไปนอกฟังก์ชันนี้เด็ดขาด (fail-safe by design)
    เพราะ resource logging ไม่ควรทำให้ trial การทดลองจริงล้มเหลว"""
    if not _NVML_AVAILABLE:
        return None
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        try:
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        except Exception:
            temp = None
        try:
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
            power_watts = round(power_mw / 1000.0, 1)
        except Exception:
            power_watts = None

        return {
            "gpu_index": gpu_index,
            "gpu_util_percent": util.gpu,
            "vram_util_percent": util.memory,
            "vram_used_mb": round(mem.used / (1024 * 1024), 1),
            "vram_total_mb": round(mem.total / (1024 * 1024), 1),
            "temperature_c": temp,
            "power_watts": power_watts,
        }
    except Exception:
        # เครื่อง/driver มีปัญหาเฉพาะหน้า -> ไม่ crash ทั้ง trial แค่ไม่ได้ข้อมูล GPU รอบนี้
        return None


def _read_all_gpu_stats():
    """คืน list ของ dict สถานะ GPU ทุกตัวในเครื่อง (รองรับหลาย GPU) หรือ [] ถ้าไม่มี"""
    if not _NVML_AVAILABLE:
        return []
    try:
        count = pynvml.nvmlDeviceGetCount()
    except Exception:
        return []
    stats = []
    for i in range(count):
        s = _read_gpu_stats(i)
        if s is not None:
            stats.append(s)
    return stats


class ExperimentLogger:
    def __init__(self, scenario: dict, task_name: str, run_index: int, log_dir: str = "logs"):
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
            "network_condition": scenario,
            "messages": [],
            "errors": [],
            "resource_snapshots": [],
            "outcome": None,
            "evaluation": None,
            # TIER3 CHANGE: บันทึกไว้เฉยๆ ว่า run นี้มี GPU monitoring หรือไม่
            # (เผื่อ analysis ต้องแยกกลุ่ม trial ที่มี/ไม่มีข้อมูล GPU)
            "gpu_monitoring_available": _NVML_AVAILABLE,
        }

        self.log_resource(tag="start")

    def log_message(self, from_agent: str, to_agent: str, content: str, timestamp: float = None):
        entry = {
            "timestamp": timestamp if timestamp is not None else time.time(),
            "from": str(from_agent),
            "to": str(to_agent),
            "content": content,
            "tokens": _estimate_tokens(content),
        }
        self.data["messages"].append(entry)

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

    def log_evaluation(self, evaluation: dict):
        self.data["evaluation"] = evaluation

    def log_resource(self, tag: str = ""):
        """TIER3 CHANGE: เพิ่ม key 'gpu' (ตัวแรก, index 0) และ 'gpu_all' (ทุกตัว)
        เข้าไปในทุก snapshot นอกเหนือจาก cpu/ram เดิม"""
        entry = {
            "timestamp": time.time(),
            "tag": tag,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
            "gpu": _read_gpu_stats(0),
            "gpu_all": _read_all_gpu_stats(),
        }
        self.data["resource_snapshots"].append(entry)

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

    def save(self) -> str:
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
