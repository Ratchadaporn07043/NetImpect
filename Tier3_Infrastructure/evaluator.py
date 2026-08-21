"""
Ground Truth Evaluator — Tier3 REPLACEMENT (เพิ่ม dual-judge / decoupled judge model)
=========================================================================================
ไฟล์นี้แทนที่ experiment/evaluator.py ต้นฉบับ (สำรองไฟล์เดิมไว้ก่อน!)

⚠️ สำคัญ: ต้อง cp ไปทับที่ "experiment/evaluator.py" เท่านั้น (ไม่ใช่ root-level
evaluator.py) เพราะทุกจุดที่ใช้งานจริง (multi_agent.py, experiment/evaluate_logs.py,
run_dual_judge_sample.py) import ผ่าน `from experiment.evaluator import ...` เสมอ
ถ้า cp ไปไว้ที่ root จะได้ไฟล์ที่ไม่มีใครเรียกใช้ และ run_dual_judge_sample.py จะ
crash ด้วย TypeError (unexpected keyword argument 'judge_model_name') เพราะยังใช้
experiment/evaluator.py ตัวเดิมที่ไม่รองรับพารามิเตอร์นี้อยู่:
    cp experiment/evaluator.py experiment/evaluator.py.backup_original
    cp "Tier3_โครงสร้างพื้นฐาน/evaluator.py" experiment/evaluator.py

การเปลี่ยนแปลงจากต้นฉบับ (ค้นหาคำว่า "TIER3 CHANGE"):
  - เพิ่ม env var ใหม่ JUDGE_MODEL_NAME (แยกจาก MODEL_NAME ที่ agent ใช้)
    ถ้าไม่ตั้งค่า จะ fallback ไปใช้ MODEL_NAME เดิม (พฤติกรรมเหมือนต้นฉบับ 100%)
  - เหตุผลที่ต้องมี: การประเมิน "ground truth" ด้วย LLM ตัวเดียวกับที่สร้างคำตอบ
    (self-evaluation bias) มีความเสี่ยงลำเอียง — ควรมี judge model ที่แยกจาก
    agent model เพื่อความน่าเชื่อถือทางวิชาการ (ตามที่ระบุใน
    Paper/NetImpact.md/Archive_Legacy/NetImpact_10_AINTEC2026_Readiness_Assessment.md
    ว่าเป็นหนึ่งใน blocking gap — ไฟล์ย้ายมาจาก Docs/ แล้ว)
  - _llm_evaluate() ตอนนี้รับพารามิเตอร์ judge_model_name (optional) และสร้าง
    _llm_config() เองแทนที่จะ import จาก multi_agent.py ตรงๆ (กัน circular
    import + กัน judge ไปแชร์ config เดียวกับ agent โดยไม่ตั้งใจ)
  - evaluate_answer() ยังคง backward compatible: ถ้าไม่ตั้ง JUDGE_MODEL_NAME
    ผลลัพธ์เหมือนเดิมทุกประการ (ใช้ MODEL_NAME เดียวกับ agent เหมือนเดิม)

วิธีใช้ dual-judge (2 โมเดลตรวจไขว้กัน วัด inter-rater agreement):
    JUDGE_MODEL_NAME=llama3.1:8b python3 -c "from evaluator import evaluate_answer; ..."
    ดู run_dual_judge_sample.py สำหรับสคริปต์ที่รันสองโมเดลแล้วเทียบ Cohen's kappa
"""
import json
import os
import re
import time
from typing import Dict, List, Optional

from experiment.tasks import TASK_GROUND_TRUTH

ENABLE_GROUND_TRUTH_EVAL = os.environ.get("ENABLE_GROUND_TRUTH_EVAL", "1").lower() not in ("0", "false", "no")
GROUND_TRUTH_EVAL_MODE = os.environ.get("GROUND_TRUTH_EVAL_MODE", "heuristic").lower()

# TIER3 CHANGE: Agent MODEL_NAME, read from the same environment variable as multi_agent.py.
AGENT_MODEL_NAME = os.environ.get("MODEL_NAME", "qwen3:8b")
# TIER3 CHANGE: Separate judge model; fall back to AGENT_MODEL_NAME when unset.
JUDGE_MODEL_NAME = os.environ.get("JUDGE_MODEL_NAME", AGENT_MODEL_NAME)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")


def _contains_any(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(str(keyword).lower() in lowered for keyword in keywords)


def _heuristic_evaluate(task_name: str, task_prompt: str, final_answer: str) -> Dict:
    spec = TASK_GROUND_TRUTH.get(task_name)
    if not spec:
        return {
            "enabled": ENABLE_GROUND_TRUTH_EVAL,
            "mode": "heuristic",
            "task_name": task_name,
            "score": None,
            "max_score": None,
            "pass_score": None,
            "passed": None,
            "coverage": None,
            "matched_points": [],
            "missing_points": ["ไม่มี ground truth spec สำหรับ task นี้"],
            "rationale": "ยังไม่ได้กำหนด rubric",
        }

    checks = spec.get("checks", [])
    matched, missing = [], []
    for check in checks:
        ok = _contains_any(final_answer or "", check.get("any", []))
        item = {
            "id": check.get("id"),
            "description": check.get("description"),
        }
        if ok:
            matched.append(item)
        else:
            missing.append(item)

    max_score = int(spec.get("max_score", 5))
    pass_score = int(spec.get("pass_score", 4))
    coverage = len(matched) / len(checks) if checks else 0
    score = max(1, round(coverage * max_score)) if checks else None
    if final_answer and len(final_answer.strip()) >= 80 and score is not None:
        score = max(score, 2)
    passed = score is not None and score >= pass_score

    return {
        "enabled": ENABLE_GROUND_TRUTH_EVAL,
        "mode": "heuristic",
        "task_name": task_name,
        "score": score,
        "max_score": max_score,
        "pass_score": pass_score,
        "passed": passed,
        "coverage": round(coverage, 3),
        "matched_points": matched,
        "missing_points": missing,
        "rationale": f"matched {len(matched)}/{len(checks)} rubric checks",
    }


def _extract_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# TIER3 CHANGE: judge เดี๋ยวนี้สร้าง llm_config เองแทนการ import จาก multi_agent
# (เดิม import _llm_config จาก multi_agent.py ซึ่งบังคับให้ judge ใช้ MODEL_NAME
# เดียวกับ agent เสมอ ทำให้ dual-judge เป็นไปไม่ได้)
def _judge_llm_config(model_name: str, temperature: float = 0.0):
    return {
        "config_list": [
            {
                "model": model_name,
                "base_url": OLLAMA_BASE_URL,
                "api_key": "ollama",
            }
        ],
        "temperature": temperature,
        "timeout": int(os.environ.get("LLM_TIMEOUT", 120)),
        "cache_seed": None,
    }


def _llm_evaluate(task_name: str, task_prompt: str, final_answer: str,
                   judge_model_name: Optional[str] = None) -> Dict:
    """TIER3 CHANGE: เพิ่มพารามิเตอร์ judge_model_name (optional)
    ถ้าไม่ส่งมาจะใช้ JUDGE_MODEL_NAME จาก env (ซึ่ง fallback เป็น AGENT_MODEL_NAME
    ถ้าไม่ได้ตั้ง JUDGE_MODEL_NAME ไว้ -> พฤติกรรมเดิม 100%)"""
    spec = TASK_GROUND_TRUTH.get(task_name, {})
    rubric = spec.get("rubric", [])
    max_score = int(spec.get("max_score", 5) or 5)
    pass_score = int(spec.get("pass_score", 4) or 4)
    model_name = judge_model_name or JUDGE_MODEL_NAME

    try:
        from autogen import ConversableAgent

        evaluator = ConversableAgent(
            name="GroundTruthEvaluator",
            system_message=(
                "คุณคือ external ground-truth evaluator ที่ตรวจคำตอบสุดท้ายเท่านั้น "
                "ห้ามช่วยแก้งาน ห้ามสนทนาต่อกับ agent อื่น ให้ตัดสินจากโจทย์ rubric และคำตอบสุดท้าย "
                "ตอบเป็น JSON เท่านั้นตาม schema: "
                "{\"score\": 1-5, \"passed\": true/false, "
                "\"missing_points\": [string], \"rationale\": string}"
            ),
            llm_config=_judge_llm_config(model_name, temperature=0.0),
            human_input_mode="NEVER",
        )
        rubric_text = "\n".join(f"- {item}" for item in rubric)
        prompt = (
            f"TASK_NAME: {task_name}\n"
            f"TASK_PROMPT:\n{task_prompt}\n\n"
            f"GROUND_TRUTH_RUBRIC:\n{rubric_text}\n\n"
            f"FINAL_ANSWER:\n{final_answer}\n\n"
            f"ให้คะแนน 1-{max_score}; ผ่านเมื่อ score >= {pass_score}. ตอบ JSON เท่านั้น."
        )
        response = evaluator.generate_reply(messages=[{"role": "user", "content": prompt}])
        raw = response if isinstance(response, str) else str(response)
        parsed = _extract_json(raw) or {}
        score = parsed.get("score")
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            score = max(1, min(max_score, score))
        passed = parsed.get("passed")
        if not isinstance(passed, bool):
            passed = score is not None and score >= pass_score

        return {
            "enabled": ENABLE_GROUND_TRUTH_EVAL,
            "mode": "llm",
            "task_name": task_name,
            "judge_model_name": model_name,  # TIER3 CHANGE: Record the judging model.
            "score": score,
            "max_score": max_score,
            "pass_score": pass_score,
            "passed": passed,
            "missing_points": parsed.get("missing_points", []),
            "rationale": parsed.get("rationale", ""),
            "raw_response": raw[:1200],
        }
    except Exception as exc:
        return {
            "enabled": ENABLE_GROUND_TRUTH_EVAL,
            "mode": "llm",
            "task_name": task_name,
            "judge_model_name": model_name,
            "score": None,
            "max_score": max_score,
            "pass_score": pass_score,
            "passed": None,
            "missing_points": ["LLM evaluator failed"],
            "rationale": str(exc)[:300],
            "error_type": type(exc).__name__,
        }


def evaluate_answer(task_name: str, task_prompt: str, final_answer: str,
                     judge_model_name: Optional[str] = None) -> Dict:
    """TIER3 CHANGE: เพิ่มพารามิเตอร์ judge_model_name (optional, ส่งต่อไป
    _llm_evaluate เท่านั้น ไม่กระทบ heuristic mode) — call site เดิมที่ไม่ส่ง
    พารามิเตอร์นี้ (เช่น multi_agent.py เดิม) ทำงานเหมือนเดิมทุกประการ"""
    start = time.time()
    if not ENABLE_GROUND_TRUTH_EVAL:
        return {
            "enabled": False,
            "mode": GROUND_TRUTH_EVAL_MODE,
            "task_name": task_name,
            "score": None,
            "passed": None,
            "elapsed_seconds": 0,
            "rationale": "disabled by ENABLE_GROUND_TRUTH_EVAL=0",
        }

    mode = GROUND_TRUTH_EVAL_MODE
    if mode not in ("heuristic", "llm", "both"):
        mode = "heuristic"

    heuristic = _heuristic_evaluate(task_name, task_prompt, final_answer)
    if mode == "heuristic":
        result = heuristic
    elif mode == "llm":
        result = _llm_evaluate(task_name, task_prompt, final_answer, judge_model_name=judge_model_name)
        result["heuristic_reference"] = heuristic
    else:
        llm_result = _llm_evaluate(task_name, task_prompt, final_answer, judge_model_name=judge_model_name)
        result = llm_result
        result["mode"] = "both"
        result["heuristic_reference"] = heuristic

    result["elapsed_seconds"] = round(time.time() - start, 2)
    return result
