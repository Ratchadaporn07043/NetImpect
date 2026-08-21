"""
Multi-Agent Runner — Tier 8 (Scope Closure, fresh-environment build)
========================================================================
Nearly complete copy of `Tier7_ScopeClosure/multi_agent.py` (conversation logic,
retries, and mitigation modes are already verified and unchanged). The key
difference from Tier 7 is:

**`logger.log_timeout(..., agent=...)` now works** because Tier8 runners pass the
Tier8 logger, whose methods accept `agent=None`. This fixes the Tier7 7A bug
where the unexpected keyword argument caused timeout handling and retries to fail.
The behavior is covered by tests_tier8/test_logger_agent_param.py.

Preserved unchanged from Tier 7:
  - mitigation modes: none / adaptive_timeout / context_cache / both / fixed_long_timeout
    - FIXED_LONG_TIMEOUT = 345s (the adaptive value at loss=75%: 120+int(75*3))
    - The Planner seed message is not counted as an LLM call, preserving comparison
        with the original 5,300 trials.
"""
import os
import re
import time
from autogen import ConversableAgent, GroupChat, GroupChatManager
from experiment.evaluator import evaluate_answer

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen3:8b")

MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", 6))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 2))
BASE_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", 120))

VALID_MITIGATIONS = ("none", "adaptive_timeout", "context_cache", "both", "fixed_long_timeout")

# Default: the value returned by _adaptive_timeout_seconds() at loss=75%.
# 120 (base) + int(75 * 3) = 345 seconds, deliberately equal across scenarios.
# This isolates condition awareness from the adaptive arm.
FIXED_LONG_TIMEOUT = int(os.environ.get("FIXED_LONG_TIMEOUT", 345))

ROUND_ROBIN_ORDER = ("Planner", "Worker", "Reviewer")


def _next_speaker(last_speaker: str):
    """Return the next round-robin agent after last_speaker, or None if unknown."""
    if last_speaker not in ROUND_ROBIN_ORDER:
        return None
    idx = ROUND_ROBIN_ORDER.index(last_speaker)
    return ROUND_ROBIN_ORDER[(idx + 1) % len(ROUND_ROBIN_ORDER)]


def _blame_agent(groupchat_messages, use_cached_plan: bool = False):
    """Infer the failed agent from the transcript and round-robin order."""
    if not groupchat_messages:
        return "Worker" if use_cached_plan else None
    last = groupchat_messages[-1].get("name", "")
    if use_cached_plan:
        return "Reviewer" if last == "Worker" else "Worker"
    return _next_speaker(last)


REVIEWER_SYSTEM_MESSAGE_DEFAULT = (
    "You are a Reviewer agent. Check whether the Worker's output follows the plan and is correct. "
    "Reply in exactly two lines:\n"
    "Line 1: 'APPROVED' or 'REVISE' followed by a brief reason.\n"
    "Line 2: 'SCORE: X', where X is a quality score from 1 to 5. "
    "Score the actual quality; give 5 only for genuinely complete work."
)

REVIEWER_SYSTEM_MESSAGE_STRICT = (
    "You are a very strict Reviewer. Check the Worker's output point by point "
    "before deciding. Follow these steps internally (do not write them out):\n"
    "1. Break the task into every stated requirement.\n"
    "2. Check the Worker's answer against each requirement.\n"
    "3. If any requirement fails, return REVISE; do not approve incomplete work.\n"
    "Reply in exactly two lines:\n"
    "Line 1: 'APPROVED' or 'REVISE' followed by a brief reason.\n"
    "Line 2: 'SCORE: X', where X is a strict quality score from 1 to 5."
)


def _adaptive_timeout_seconds(network_condition: dict = None) -> int:
    """Scale BASE_LLM_TIMEOUT from delay_ms, loss_pct, and jitter_ms, capped at 10x."""
    if not network_condition:
        return BASE_LLM_TIMEOUT

    delay_ms = network_condition.get("delay_ms", 0) or 0
    loss_pct = network_condition.get("loss_pct", 0) or 0
    jitter_ms = network_condition.get("jitter_ms", 0) or 0

    extra = int(delay_ms / 100 * 10) + int(loss_pct * 3) + int(jitter_ms / 10 * 5)
    timeout = BASE_LLM_TIMEOUT + extra
    return min(timeout, BASE_LLM_TIMEOUT * 10)


def _llm_config(temperature: float = 0.3, timeout_override: int = None):
    return {
        "config_list": [
            {
                "model": MODEL_NAME,
                "base_url": OLLAMA_BASE_URL,
                "api_key": "ollama",
            }
        ],
        "temperature": temperature,
        "timeout": timeout_override if timeout_override is not None else BASE_LLM_TIMEOUT,
        "cache_seed": None,
    }


def build_agents(strict_reviewer: bool = False, timeout_seconds: int = None):
    planner = ConversableAgent(
        name="Planner",
        system_message=(
            "คุณคือ Planner agent มีหน้าที่แตกงานที่ได้รับเป็นแผนขั้นตอนสั้นๆ "
            "(3-5 ข้อ) ให้ Worker เอาไปทำต่อ ห้ามลงมือทำงานเอง แค่วางแผน"
        ),
        llm_config=_llm_config(temperature=0.2, timeout_override=timeout_seconds),
        human_input_mode="NEVER",
    )

    worker = ConversableAgent(
        name="Worker",
        system_message=(
            "คุณคือ Worker agent มีหน้าที่ทำงานจริงตามแผนที่ Planner ให้มา "
            "ตอบคำตอบสุดท้ายให้ชัดเจน ถ้า Reviewer ติงกลับมา ให้แก้ไขและตอบใหม่"
        ),
        llm_config=_llm_config(temperature=0.4, timeout_override=timeout_seconds),
        human_input_mode="NEVER",
    )

    reviewer_system_message = (
        REVIEWER_SYSTEM_MESSAGE_STRICT if strict_reviewer else REVIEWER_SYSTEM_MESSAGE_DEFAULT
    )
    reviewer = ConversableAgent(
        name="Reviewer",
        system_message=reviewer_system_message,
        llm_config=_llm_config(temperature=0.2, timeout_override=timeout_seconds),
        human_input_mode="NEVER",
    )

    return planner, worker, reviewer


def _parse_quality_score(reviewer_text: str):
    match = re.search(r"SCORE\s*[:：]\s*(\d)", reviewer_text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 5:
            return score
    return None


def _is_reviewer_approved(msg) -> bool:
    if not isinstance(msg, dict):
        return False
    if msg.get("name") != "Reviewer":
        return False
    content = (msg.get("content") or "").strip().upper()
    return content.startswith("APPROVED")


def _extract_first_planner_message(groupchat_messages):
    for msg in groupchat_messages:
        if msg.get("name") == "Planner":
            return msg.get("content", "") or ""
    return None


def _attempt_once(task_prompt: str, max_rounds: int, logger=None, strict_reviewer: bool = False,
                   timeout_seconds: int = None, cached_plan: str = None):
    """รัน 1 attempt ของ Planner -> Worker -> Reviewer
    cached_plan: ถ้าไม่ใช่ None ให้ข้าม Planner ไปเลย ส่งแผนที่ cache ไว้ให้ Worker
    เริ่มทำงานต่อทันที (Mitigation B)"""
    planner, worker, reviewer = build_agents(strict_reviewer=strict_reviewer,
                                              timeout_seconds=timeout_seconds)

    message_timestamps = []

    def _record_send_timestamp(sender, message, recipient, silent):
        message_timestamps.append(time.time())
        return message

    use_cached_plan = cached_plan is not None
    active_agents = (worker, reviewer) if use_cached_plan else (planner, worker, reviewer)

    for agent in active_agents:
        try:
            agent.register_hook("process_message_before_send", _record_send_timestamp)
        except AttributeError:
            break

    groupchat = GroupChat(
        agents=list(active_agents),
        messages=[],
        max_round=max_rounds,
        speaker_selection_method="round_robin",
    )
    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=_llm_config(timeout_override=timeout_seconds),
        is_termination_msg=_is_reviewer_approved,
    )

    rejections = 0
    success = False
    final_answer = ""
    quality_score = None
    caught_error = None

    try:
        if use_cached_plan:
            seed_message = (
                f"[แผนจาก Planner ที่ cache ไว้จาก attempt ก่อนหน้า ไม่ต้องขอแผนใหม่]\n"
                f"{cached_plan}\n\nงานที่ต้องทำ: {task_prompt}"
            )
            worker.initiate_chat(manager, message=seed_message)
        else:
            planner.initiate_chat(manager, message=f"งานที่ต้องทำ: {task_prompt}")
    except Exception as e:
        caught_error = e
    finally:
        for idx, msg in enumerate(groupchat.messages):
            speaker = msg.get("name", "")
            content = msg.get("content", "") or ""

            real_timestamp = message_timestamps[idx] if idx < len(message_timestamps) else time.time()

            if logger is not None:
                logger.log_message(from_agent=speaker, to_agent="group", content=content,
                                    timestamp=real_timestamp)

            if speaker == "Reviewer":
                score = _parse_quality_score(content)
                if score is not None:
                    quality_score = score

                if content.strip().upper().startswith("REVISE"):
                    rejections += 1
                    success = False
                    if logger is not None:
                        logger.log_error(error_type="reviewer_rejection", detail=content[:200])
                elif content.strip().upper().startswith("APPROVED"):
                    success = True

            if speaker == "Worker":
                final_answer = content

    planner_output = cached_plan if use_cached_plan else _extract_first_planner_message(groupchat.messages)

    # อนุมาน agent ที่ LLM call ล้มเหลว จาก transcript ที่ค้างอยู่ ณ จุดที่ error
    blamed_agent = _blame_agent(groupchat.messages, use_cached_plan) if caught_error is not None else None

    return (success, final_answer, len(groupchat.messages), rejections, quality_score,
            caught_error, planner_output, blamed_agent)


def run_multi_agent_task(task_prompt: str, logger=None, max_rounds: int = None, task_name: str = None,
                          strict_reviewer: bool = False, mitigation: str = "none",
                          network_condition: dict = None):
    """รัน 1 task ผ่าน Planner -> Worker -> Reviewer
    mitigation: "none" (default = พฤติกรรมเดิม 100%) / "adaptive_timeout" /
      "context_cache" / "both" / "fixed_long_timeout"
    network_condition: dict ของ scenario ปัจจุบัน ใช้กับ adaptive_timeout เท่านั้น"""
    if mitigation not in VALID_MITIGATIONS:
        raise ValueError(f"mitigation ต้องเป็นหนึ่งใน {VALID_MITIGATIONS} แต่ได้ {mitigation!r}")

    use_adaptive_timeout = mitigation in ("adaptive_timeout", "both")
    use_context_cache = mitigation in ("context_cache", "both")
    use_fixed_long_timeout = mitigation == "fixed_long_timeout"

    if use_adaptive_timeout:
        timeout_seconds = _adaptive_timeout_seconds(network_condition)
    elif use_fixed_long_timeout:
        # ค่าเดียวกันทุก scenario โดยไม่ดู network_condition เลย — นี่คือจุดที่
        # ทำให้ arm นี้ต่างจาก adaptive arm เพียงมิติเดียว
        timeout_seconds = FIXED_LONG_TIMEOUT
    else:
        timeout_seconds = None

    max_rounds = max_rounds or MAX_ROUNDS
    start_ts = time.time()

    attempt = 0
    retries_used = 0
    cached_plan = None
    success, final_answer, rounds, rejections, quality_score = False, "", 0, 0, None

    while attempt <= MAX_RETRIES:
        attempt += 1
        plan_to_use = cached_plan if (use_context_cache and attempt > 1 and cached_plan) else None

        (success, final_answer, rounds, rejections, quality_score, error,
         planner_output, blamed_agent) = _attempt_once(
            task_prompt, max_rounds, logger, strict_reviewer=strict_reviewer,
            timeout_seconds=timeout_seconds, cached_plan=plan_to_use,
        )
        if planner_output:
            cached_plan = planner_output

        if error is None:
            break

        is_timeout = "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower()

        if logger is not None:
            # TIER8: บันทึก agent ที่ล้มเหลวลง log โดยตรง — logger.py ของ Tier8
            # รองรับ agent= จริงแล้ว (ตรวจยืนยันก่อนเขียนไฟล์นี้)
            if is_timeout:
                logger.log_timeout(detail=str(error)[:300], agent=blamed_agent)
            else:
                logger.log_error(error_type=type(error).__name__,
                                 detail=str(error)[:300], agent=blamed_agent)

        retries_used = attempt - 1

        if attempt <= MAX_RETRIES:
            if logger is not None:
                logger.log_retry(
                    reason=f"attempt {attempt} failed with {type(error).__name__}, retrying",
                    agent=blamed_agent)
            print(f"    !! เกิด {type(error).__name__} ลอง retry ครั้งที่ {attempt}/{MAX_RETRIES}")
        else:
            print(f"    !! เกิน MAX_RETRIES ({MAX_RETRIES}) แล้ว ยอมแพ้")

    evaluation = evaluate_answer(task_name or "unknown", task_prompt, final_answer)
    elapsed = time.time() - start_ts

    result = {
        "success": success,
        "final_answer": final_answer,
        "rounds": rounds,
        "rejections": rejections,
        "quality_score": quality_score,
        "ground_truth_score": evaluation.get("score"),
        "ground_truth_passed": evaluation.get("passed"),
        "evaluation": evaluation,
        "retries": retries_used,
        "elapsed_seconds": round(elapsed, 2),
        "mitigation": mitigation,
        "timeout_seconds": timeout_seconds,
    }

    if logger is not None:
        logger.log_outcome(
            success=success,
            rounds=rounds,
            rejections=rejections,
            elapsed_seconds=elapsed,
            quality_score=quality_score,
            retries=retries_used,
            evaluation=evaluation,
        )

    return result


if __name__ == "__main__":
    r = run_multi_agent_task("เขียนฟังก์ชัน python คำนวณเลข fibonacci ตัวที่ N")
    print(r)
