"""
AutoGen Multi-Agent System
==========================
Planner -> Worker -> Reviewer communicate through GroupChat (round-based communication).
Matches the diagram: docker/AutoGen Multi-Agent System.

Usage:
    from multi_agent import run_multi_agent_task
    result = run_multi_agent_task("เขียนฟังก์ชัน python สำหรับ..." )
"""
import os
import re
import time
from autogen import ConversableAgent, GroupChat, GroupChatManager
from experiment.evaluator import evaluate_answer

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen3:8b")

# Maximum conversation rounds. This safety cap prevents an endless loop when the
# network is poor or the Reviewer never returns APPROVED. Conversations normally
# end earlier through early termination in _is_reviewer_approved.
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", 6))

# Number of full-task retries after a timeout or connection error, excluding the first attempt.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 2))


def _llm_config(temperature: float = 0.3):
    return {
        "config_list": [
            {
                "model": MODEL_NAME,
                "base_url": OLLAMA_BASE_URL,
                "api_key": "ollama",
            }
        ],
        "temperature": temperature,
        # Timeout for one request, in seconds. This matters when simulating poor networks.
        # Override it with LLM_TIMEOUT when the model responds more slowly.
        "timeout": int(os.environ.get("LLM_TIMEOUT", 120)),
        # Disable caching completely. Otherwise AutoGen may reuse a response for the
        # same prompt, model, and temperature instead of sending a real LLM request,
        # making network results invalid.
        "cache_seed": None,
    }


def build_agents():
    """Create three agents according to the diagram: Planner, Worker, and Reviewer."""

    planner = ConversableAgent(
        name="Planner",
        system_message=(
            "คุณคือ Planner agent มีหน้าที่แตกงานที่ได้รับเป็นแผนขั้นตอนสั้นๆ "
            "(3-5 ข้อ) ให้ Worker เอาไปทำต่อ ห้ามลงมือทำงานเอง แค่วางแผน"
        ),
        llm_config=_llm_config(temperature=0.2),
        human_input_mode="NEVER",
    )

    worker = ConversableAgent(
        name="Worker",
        system_message=(
            "คุณคือ Worker agent มีหน้าที่ทำงานจริงตามแผนที่ Planner ให้มา "
            "ตอบคำตอบสุดท้ายให้ชัดเจน ถ้า Reviewer ติงกลับมา ให้แก้ไขและตอบใหม่"
        ),
        llm_config=_llm_config(temperature=0.4),
        human_input_mode="NEVER",
    )

    reviewer = ConversableAgent(
        name="Reviewer",
        system_message=(
            "คุณคือ Reviewer agent ตรวจงานจาก Worker ว่าตรงตามแผนและถูกต้องไหม "
            "ตอบตามรูปแบบนี้เท่านั้น (2 บรรทัด):\n"
            "บรรทัดที่ 1: 'APPROVED' หรือ 'REVISE' ตามด้วยเหตุผลสั้นๆ\n"
            "บรรทัดที่ 2: 'SCORE: X' โดย X คือคะแนนคุณภาพงาน 1-5 "
            "(5=ดีมาก สมบูรณ์ครบถ้วน, 1=แย่มาก ผิดหรือไม่ตรงโจทย์เลย) "
            "ให้คะแนนตามคุณภาพจริง แม้ว่าจะ APPROVED ก็อาจได้คะแนนไม่เต็ม 5 ได้ "
            "ถ้างานสมบูรณ์จริงๆ ค่อยให้ 5"
        ),
        llm_config=_llm_config(temperature=0.2),
        human_input_mode="NEVER",
    )

    return planner, worker, reviewer


def _parse_quality_score(reviewer_text: str):
    """Extract a score from 1 to 5 from Reviewer text, or None if absent."""
    match = re.search(r"SCORE\s*[:：]\s*(\d)", reviewer_text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 5:
            return score
    return None


def _is_reviewer_approved(msg) -> bool:
    """
    Used as the is_termination_msg callback for GroupChatManager.

    Previously, round_robin always continued until max_round because there was
    no immediate stop when the Reviewer approved the work. This made the logged
    round count constant and wasted time and tokens after completion.

    Now stop when the latest message is from the Reviewer and starts with
    "APPROVED".
    """
    if not isinstance(msg, dict):
        return False
    if msg.get("name") != "Reviewer":
        return False
    content = (msg.get("content") or "").strip().upper()
    return content.startswith("APPROVED")


def _attempt_once(task_prompt: str, max_rounds: int, logger=None):
    """
    Run one attempt of Planner -> Worker -> Reviewer using fresh agents so that
    state does not leak across retries.

    Returns: (success, final_answer, rounds_seen, rejections, quality_score, error_or_None)
    """
    planner, worker, reviewer = build_agents()

    # Record timestamps when messages are sent rather than after the conversation
    # finishes. Logging all messages in a final loop would give them nearly
    # identical timestamps and would make per-message network latency unmeasurable.
    #
    # Hook each agent's process_message_before_send event, then pair timestamps
    # with groupchat.messages by index.
    message_timestamps = []

    def _record_send_timestamp(sender, message, recipient, silent):
        message_timestamps.append(time.time())
        return message  # Return the original message unchanged.

    for agent in (planner, worker, reviewer):
        try:
            agent.register_hook("process_message_before_send", _record_send_timestamp)
        except AttributeError:
            # Older AutoGen versions may not provide register_hook. In that case,
            # leave timestamps empty and fall back to time.time() during logging.
            break

    groupchat = GroupChat(
        agents=[planner, worker, reviewer],
        messages=[],
        max_round=max_rounds,
        speaker_selection_method="round_robin",
    )
    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=_llm_config(),
        is_termination_msg=_is_reviewer_approved,
    )

    rejections = 0
    success = False
    final_answer = ""
    quality_score = None
    caught_error = None

    try:
        planner.initiate_chat(manager, message=f"งานที่ต้องทำ: {task_prompt}")
    except Exception as e:
        caught_error = e
    finally:
        # Always log messages produced before normal completion or an error.
        for idx, msg in enumerate(groupchat.messages):
            speaker = msg.get("name", "")
            content = msg.get("content", "") or ""

            # Pair timestamps by order. If the hook is unavailable in an older
            # AutoGen version, fall back to the current time.
            real_timestamp = message_timestamps[idx] if idx < len(message_timestamps) else time.time()

            if logger is not None:
                logger.log_message(from_agent=speaker, to_agent="group", content=content,
                                    timestamp=real_timestamp)

            if speaker == "Reviewer":
                score = _parse_quality_score(content)
                if score is not None:
                    quality_score = score

                # success always reflects the Reviewer's latest decision, just
                # like quality_score, so a later REVISE clears an earlier approval.
                if content.strip().upper().startswith("REVISE"):
                    rejections += 1
                    success = False
                    if logger is not None:
                        logger.log_error(error_type="reviewer_rejection", detail=content[:200])
                elif content.strip().upper().startswith("APPROVED"):
                    success = True

            if speaker == "Worker":
                final_answer = content

    return success, final_answer, len(groupchat.messages), rejections, quality_score, caught_error


def run_multi_agent_task(task_prompt: str, logger=None, max_rounds: int = None, task_name: str = None):
    """
    Run one task through Planner -> Worker -> Reviewer.
    Retry automatically after timeout or connection errors.

    Args:
        task_prompt: Task prompt for the agent team.
        logger: Optional ExperimentLogger that records every message.
        max_rounds: Optional MAX_ROUNDS override used only as a safety cap.
        task_name: Benchmark task name for the ground-truth evaluator.

    Returns:
        dict: {"success", "final_answer", "rounds", "rejections", "quality_score",
               "ground_truth_score", "ground_truth_passed", "evaluation",
               "retries", "elapsed_seconds"}
    """
    max_rounds = max_rounds or MAX_ROUNDS
    start_ts = time.time()

    attempt = 0
    retries_used = 0
    success, final_answer, rounds, rejections, quality_score = False, "", 0, 0, None

    while attempt <= MAX_RETRIES:
        attempt += 1
        success, final_answer, rounds, rejections, quality_score, error = _attempt_once(
            task_prompt, max_rounds, logger
        )

        if error is None:
            break  # No exception; no retry is needed.

        # Classify timeout errors explicitly so TimeoutError is counted correctly.
        is_timeout = "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower()

        if logger is not None:
            if is_timeout:
                logger.log_timeout(detail=str(error)[:300])
            else:
                logger.log_error(error_type=type(error).__name__, detail=str(error)[:300])

        retries_used = attempt - 1  # Number of retries completed, excluding the first attempt.

        if attempt <= MAX_RETRIES:
            if logger is not None:
                logger.log_retry(reason=f"attempt {attempt} failed with {type(error).__name__}, retrying")
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
    # Run a standalone smoke test without a logger.
    r = run_multi_agent_task("เขียนฟังก์ชัน python คำนวณเลข fibonacci ตัวที่ N")
    print(r)