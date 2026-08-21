"""
AutoGen Multi-Agent System — Tier2 REPLACEMENT
==================================================
ไฟล์นี้แทนที่ multi_agent.py ต้นฉบับที่ root ของโปรเจกต์ (สำรองไฟล์เดิมไว้ก่อน!)

การเปลี่ยนแปลงจากต้นฉบับ (ค้นหาคำว่า "TIER2 CHANGE" เพื่อดูจุดที่แก้ทั้งหมด):
  - เพิ่มพารามิเตอร์ `strict_reviewer: bool = False` ใน build_agents(),
    _attempt_once(), และ run_multi_agent_task()
  - เมื่อ strict_reviewer=False (ค่า default) พฤติกรรมเหมือนต้นฉบับ 100%
    ทุกประการ (Reviewer ใช้ system_message เดิมเป๊ะ) — ไม่กระทบ
    experiment เดิม (logs_three_day/) หรือ Tier1 เลย
  - เมื่อ strict_reviewer=True: Reviewer จะใช้ system_message ที่เข้มงวดขึ้น
    (ต้องเช็ค rubric ทีละข้อก่อนอนุมัติ, ห้าม APPROVED ถ้ายังมีข้อบกพร่อง)
    ใช้คู่กับ tier2_tasks_multiround.py เพื่อเพิ่มโอกาสให้เกิดการคุยหลายรอบ
    (multi-round) ในชุดข้อมูล ซึ่งชุดข้อมูลเดิมแทบไม่มีเลย (ดู
    NetImpact_ผลการทดลองเชิงลึก.md ส่วนที่พูดถึง "distribution ของ rounds")

ใช้งาน:
    from multi_agent import run_multi_agent_task
    result = run_multi_agent_task("...", strict_reviewer=True)
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

REVIEWER_SYSTEM_MESSAGE_DEFAULT = (
    "คุณคือ Reviewer agent ตรวจงานจาก Worker ว่าตรงตามแผนและถูกต้องไหม "
    "ตอบตามรูปแบบนี้เท่านั้น (2 บรรทัด):\n"
    "บรรทัดที่ 1: 'APPROVED' หรือ 'REVISE' ตามด้วยเหตุผลสั้นๆ\n"
    "บรรทัดที่ 2: 'SCORE: X' โดย X คือคะแนนคุณภาพงาน 1-5 "
    "(5=ดีมาก สมบูรณ์ครบถ้วน, 1=แย่มาก ผิดหรือไม่ตรงโจทย์เลย) "
    "ให้คะแนนตามคุณภาพจริง แม้ว่าจะ APPROVED ก็อาจได้คะแนนไม่เต็ม 5 ได้ "
    "ถ้างานสมบูรณ์จริงๆ ค่อยให้ 5"
)

# TIER2 CHANGE: Reviewer เวอร์ชันเข้มงวด — บังคับเช็คทีละเงื่อนไขก่อนอนุมัติ
# เป้าหมาย: เพิ่มโอกาสเกิด REVISE รอบแรก (multi-round) กับ task ที่ซับซ้อน
# (tier2_tasks_multiround.py) เพื่อให้มีข้อมูล "บทสนทนาหลายรอบภายใต้ network
# ที่แย่" มากพอจะวิเคราะห์ ต่างจาก default reviewer ที่มักอนุมัติง่ายเกินไป
REVIEWER_SYSTEM_MESSAGE_STRICT = (
    "คุณคือ Reviewer agent ที่เข้มงวดมาก ตรวจงานจาก Worker แบบละเอียดทีละจุด "
    "ก่อนตัดสินใจ ให้ทำตามขั้นตอนนี้ในใจ (ไม่ต้องเขียนขั้นตอนออกมา):\n"
    "1. แตกโจทย์เป็นเงื่อนไขย่อยทั้งหมดที่โจทย์ระบุ (เช่น ต้องมี key ครบไหม, "
    "ต้องมีตัวอย่างไหม, ต้องตอบครบทุกข้อย่อยไหม)\n"
    "2. เช็คคำตอบของ Worker ทีละเงื่อนไขว่าผ่านหรือไม่ผ่าน\n"
    "3. ถ้ามีเงื่อนไขใดไม่ผ่านแม้แต่ข้อเดียว ต้องตอบ REVISE เท่านั้น ห้าม APPROVED "
    "จนกว่า Worker จะแก้ครบทุกเงื่อนไข\n"
    "ตอบตามรูปแบบนี้เท่านั้น (2 บรรทัด):\n"
    "บรรทัดที่ 1: 'APPROVED' หรือ 'REVISE' ตามด้วยเหตุผลสั้นๆ ระบุเงื่อนไขที่ยังขาด (ถ้ามี)\n"
    "บรรทัดที่ 2: 'SCORE: X' โดย X คือคะแนนคุณภาพงาน 1-5 ให้คะแนนอย่างเข้มงวดตามความครบถ้วน"
)


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
        "timeout": int(os.environ.get("LLM_TIMEOUT", 120)),
        "cache_seed": None,
    }


def build_agents(strict_reviewer: bool = False):
    """สร้าง 3 agent ตาม diagram: Planner, Worker, Reviewer

    TIER2 CHANGE: เพิ่มพารามิเตอร์ strict_reviewer (default False = พฤติกรรม
    เดิมเป๊ะ). เมื่อ True จะสลับ system_message ของ Reviewer เป็นเวอร์ชัน
    เข้มงวด (REVIEWER_SYSTEM_MESSAGE_STRICT)
    """

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

    reviewer_system_message = (
        REVIEWER_SYSTEM_MESSAGE_STRICT if strict_reviewer else REVIEWER_SYSTEM_MESSAGE_DEFAULT
    )
    reviewer = ConversableAgent(
        name="Reviewer",
        system_message=reviewer_system_message,
        llm_config=_llm_config(temperature=0.2),
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


def _attempt_once(task_prompt: str, max_rounds: int, logger=None, strict_reviewer: bool = False):
    """รัน 1 ครั้ง (1 attempt) ของ Planner -> Worker -> Reviewer

    TIER2 CHANGE: ส่งต่อ strict_reviewer ไปยัง build_agents()
    """
    planner, worker, reviewer = build_agents(strict_reviewer=strict_reviewer)

    message_timestamps = []

    def _record_send_timestamp(sender, message, recipient, silent):
        message_timestamps.append(time.time())
        return message

    for agent in (planner, worker, reviewer):
        try:
            agent.register_hook("process_message_before_send", _record_send_timestamp)
        except AttributeError:
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

    return success, final_answer, len(groupchat.messages), rejections, quality_score, caught_error


def run_multi_agent_task(task_prompt: str, logger=None, max_rounds: int = None, task_name: str = None,
                          strict_reviewer: bool = False):
    """รัน 1 task ผ่าน Planner -> Worker -> Reviewer

    TIER2 CHANGE: เพิ่มพารามิเตอร์ strict_reviewer (default False = เหมือน
    ต้นฉบับ 100%) ส่งต่อไปยัง _attempt_once() -> build_agents()
    """
    max_rounds = max_rounds or MAX_ROUNDS
    start_ts = time.time()

    attempt = 0
    retries_used = 0
    success, final_answer, rounds, rejections, quality_score = False, "", 0, 0, None

    while attempt <= MAX_RETRIES:
        attempt += 1
        success, final_answer, rounds, rejections, quality_score, error = _attempt_once(
            task_prompt, max_rounds, logger, strict_reviewer=strict_reviewer
        )

        if error is None:
            break

        is_timeout = "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower()

        if logger is not None:
            if is_timeout:
                logger.log_timeout(detail=str(error)[:300])
            else:
                logger.log_error(error_type=type(error).__name__, detail=str(error)[:300])

        retries_used = attempt - 1

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
    r = run_multi_agent_task("เขียนฟังก์ชัน python คำนวณเลข fibonacci ตัวที่ N")
    print(r)
