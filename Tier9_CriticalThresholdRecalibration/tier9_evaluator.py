"""
Ground Truth Evaluator
======================
ตรวจ final answer หลังจบ Planner -> Worker -> Reviewer แล้วเท่านั้น
เพื่อแยกคุณภาพจริงออกจาก reviewer ภายใน workflow

โหมด:
  - heuristic (default): เช็กตาม rubric/keyword เร็ว ไม่เพิ่มเวลาทดลองมาก
  - llm: ใช้ LLM judge เทียบ rubric แบบละเอียดขึ้น
  - both: รัน heuristic ก่อน แล้วให้ LLM judge ตรวจซ้ำ

ตั้งค่าผ่าน env:
  ENABLE_GROUND_TRUTH_EVAL=1/0
  GROUND_TRUTH_EVAL_MODE=heuristic|llm|both
"""
import json
import os
import re
import time
from typing import Dict, List, Optional

from tier9_tasks import TASK_GROUND_TRUTH

ENABLE_GROUND_TRUTH_EVAL = os.environ.get("ENABLE_GROUND_TRUTH_EVAL", "1").lower() not in ("0", "false", "no")
GROUND_TRUTH_EVAL_MODE = os.environ.get("GROUND_TRUTH_EVAL_MODE", "heuristic").lower()


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


def _llm_evaluate(task_name: str, task_prompt: str, final_answer: str) -> Dict:
    spec = TASK_GROUND_TRUTH.get(task_name, {})
    rubric = spec.get("rubric", [])
    max_score = int(spec.get("max_score", 5) or 5)
    pass_score = int(spec.get("pass_score", 4) or 4)

    try:
        from autogen import ConversableAgent
        from multi_agent import _llm_config

        evaluator = ConversableAgent(
            name="GroundTruthEvaluator",
            system_message=(
                "คุณคือ external ground-truth evaluator ที่ตรวจคำตอบสุดท้ายเท่านั้น "
                "ห้ามช่วยแก้งาน ห้ามสนทนาต่อกับ agent อื่น ให้ตัดสินจากโจทย์ rubric และคำตอบสุดท้าย "
                "ตอบเป็น JSON เท่านั้นตาม schema: "
                "{\"score\": 1-5, \"passed\": true/false, "
                "\"missing_points\": [string], \"rationale\": string}"
            ),
            llm_config=_llm_config(temperature=0.0),
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
            "score": None,
            "max_score": max_score,
            "pass_score": pass_score,
            "passed": None,
            "missing_points": ["LLM evaluator failed"],
            "rationale": str(exc)[:300],
            "error_type": type(exc).__name__,
        }


def evaluate_answer(task_name: str, task_prompt: str, final_answer: str) -> Dict:
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
        result = _llm_evaluate(task_name, task_prompt, final_answer)
        result["heuristic_reference"] = heuristic
    else:
        llm_result = _llm_evaluate(task_name, task_prompt, final_answer)
        result = llm_result
        result["mode"] = "both"
        result["heuristic_reference"] = heuristic

    result["elapsed_seconds"] = round(time.time() - start, 2)
    return result
