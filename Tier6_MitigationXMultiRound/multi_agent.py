"""
AutoGen Multi-Agent System — Tier6 (ใช้ไฟล์เดียวกับ Tier5 โดยไม่แก้อะไรเลย)
====================================================================================================
ไฟล์นี้เป็นสำเนา 1:1 ของ `Tier5_Mitigation/multi_agent.py` (ไม่มีการแก้โค้ด
logic แม้แต่บรรทัดเดียว) — เก็บสำเนาไว้ในโฟลเดอร์นี้ด้วยเพื่อให้ Tier6
"self-contained" ตามธรรมเนียมเดียวกับทุก Tier ก่อนหน้า (แต่ละ Tier มี
multi_agent.py ของตัวเองพร้อม cp ไป root ได้ทันที ไม่ต้องไปงมหาไฟล์ข้าม Tier)

เหตุผลที่ใช้ไฟล์เดิมของ Tier5 ได้ทันทีโดยไม่ต้องแก้: ไฟล์นี้เป็น "เวอร์ชันสะสม"
ที่ Tier5 ออกแบบไว้ตั้งแต่แรกให้รองรับพารามิเตอร์ทั้งสองชุดพร้อมกันอยู่แล้ว:
  - `strict_reviewer: bool = False`  (มาจาก Tier2 — reviewer เข้มงวด บังคับเช็ค
    rubric ทีละข้อ ห้าม APPROVED จนกว่าจะครบทุกเงื่อนไข)
  - `mitigation: str = "none"`       (มาจาก Tier5 — "none"/"adaptive_timeout"/
    "context_cache"/"both")
  - `network_condition: dict = None` (ส่ง scenario ปัจจุบันเข้ามา ให้
    adaptive_timeout คำนวณ timeout ที่เหมาะสมได้)

สิ่งที่ Tier6 ทำคือ**เรียกใช้ทั้งสองพารามิเตอร์พร้อมกัน**เป็นครั้งแรก
(strict_reviewer=True + mitigation=<none|adaptive_timeout|context_cache>) กับ
scenario/task ของ Tier2 (moderate_delay ที่เป็นจุดอ่อนสุดของ multi-round ที่
Tier2 พบ) — ดูรายละเอียดการทดลองที่ `run_tier6_mitigation_multiround.py` และ
`README.md` ในโฟลเดอร์นี้ ยืนยันด้วย
`tests_extended/test_tier6_mitigation_multiround.py` ว่าเรียกสองพารามิเตอร์
พร้อมกันได้จริงโดยไม่ชนกัน (เช่น strict reviewer message ถูกใช้จริง +
adaptive timeout ถูกคำนวณจริง ในการเรียกเดียวกัน)

ทั้งสอง mitigation และ strict_reviewer ยังเป็น "opt-in" เหมือนเดิมทุกประการ —
ถ้าไม่ส่งพารามิเตอร์ใดเลย พฤติกรรมเหมือนต้นฉบับ 100% (ยืนยันซ้ำด้วย
tests/test_baseline_regression.py ที่มีอยู่แล้ว)

Mitigation A — Adaptive Timeout:
    ปัญหาที่พบ: LLM_TIMEOUT เดิมคงที่ 120 วินาทีทุก scenario แม้ delay/loss จะ
    ทำให้แต่ละ LLM call ช้าลงมากในสถานการณ์เลวร้าย (เช่น delay=1000ms x
    หลาย round) ทำให้เกิด timeout error "ปลอม" ที่จริงๆ แค่ต้องรอนานขึ้นเฉยๆ
    ไม่ใช่ระบบพัง ทำให้เสีย retry โดยไม่จำเป็น
    วิธีแก้: ขยาย timeout ตามสัดส่วนของ delay_ms/loss_pct/jitter_ms ในสถานการณ์
    นั้น (ดู _adaptive_timeout_seconds())

Mitigation B — Context Caching:
    ปัญหาที่พบ: เมื่อเกิด timeout/error กลางบทสนทนาแล้วต้อง retry ทั้ง task
    ใหม่ (_attempt_once เดิมสร้าง agent ชุดใหม่ทุกครั้ง) Planner ต้องคิดแผนใหม่
    จากศูนย์ทุกรอบ retry ทั้งที่แผนจากรอบก่อนอาจใช้ได้อยู่แล้ว เสีย LLM call
    ที่เสี่ยงเจอ network แย่ซ้ำอีกรอบโดยไม่จำเป็น
    วิธีแก้: cache ข้อความแรกของ Planner จาก attempt แรกไว้ ถ้าต้อง retry
    (attempt >= 2) และ mitigation เปิด context_cache ให้ข้ามการเรียก Planner
    ใหม่ ส่งแผนที่ cache ไว้ตรงให้ Worker เริ่มทำงานต่อได้เลย (ลดจำนวน LLM
    call ที่เสี่ยงเจอ network แย่ลง 1 ครั้งต่อ retry)
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
# TIER6 CHANGE: default is 600, not the project-wide 120 (see Tier5/base multi_agent.py),
# because the real Tier2 run that this Tier's `none` condition is meant to be a directly
# comparable control against was executed with LLM_TIMEOUT=600 (see
# Paper/NetImpact.md/Current/NetImpact_06_Tier6_Pending_Experiment.md §2.3 and
# Tier2_แกนใหม่/README.md). Running Tier6 with no special environment setup must
# automatically match the timeout regime Tier2 was actually measured under.
BASE_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", 600))

VALID_MITIGATIONS = ("none", "adaptive_timeout", "context_cache", "both")

REVIEWER_SYSTEM_MESSAGE_DEFAULT = (
    "คุณคือ Reviewer agent ตรวจงานจาก Worker ว่าตรงตามแผนและถูกต้องไหม "
    "ตอบตามรูปแบบนี้เท่านั้น (2 บรรทัด):\n"
    "บรรทัดที่ 1: 'APPROVED' หรือ 'REVISE' ตามด้วยเหตุผลสั้นๆ\n"
    "บรรทัดที่ 2: 'SCORE: X' โดย X คือคะแนนคุณภาพงาน 1-5 "
    "(5=ดีมาก สมบูรณ์ครบถ้วน, 1=แย่มาก ผิดหรือไม่ตรงโจทย์เลย) "
    "ให้คะแนนตามคุณภาพจริง แม้ว่าจะ APPROVED ก็อาจได้คะแนนไม่เต็ม 5 ได้ "
    "ถ้างานสมบูรณ์จริงๆ ค่อยให้ 5"
)

# (คงไว้จาก Tier2 — ใช้ร่วมกับ strict_reviewer=True ได้ตามปกติ)
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


def _adaptive_timeout_seconds(network_condition: dict = None) -> int:
    """ขยาย BASE_LLM_TIMEOUT ตาม delay_ms/loss_pct/jitter_ms ของ scenario
    สูตร (ปรับแต่งได้): +10s ต่อทุก 100ms delay, +3s ต่อทุก 1% loss,
    +5s ต่อทุก 10ms jitter, cap ที่ 10 เท่าของ base (กันหลุดไปยาวเกินจำเป็น)"""
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
    """timeout_seconds ส่งต่อจาก _adaptive_timeout_seconds เมื่อเปิด
    mitigation='adaptive_timeout'/'both' — ถ้าไม่ส่ง = BASE_LLM_TIMEOUT เหมือนเดิม"""

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
    """รัน 1 ครั้ง (1 attempt) ของ Planner -> Worker -> Reviewer

      - timeout_seconds: ส่งต่อไปยัง build_agents() (Mitigation A)
      - cached_plan: ถ้าไม่ใช่ None ให้ข้าม Planner ไปเลย ส่งแผนที่ cache ไว้
        ให้ Worker เริ่มทำงานต่อทันที (Mitigation B) — ใช้ GroupChat แค่
        [worker, reviewer] 2 agent แทน 3 agent ปกติ

    คืนค่าเพิ่มจากเดิม 1 อย่าง: planner_output (ข้อความแรกของ Planner จาก
    attempt นี้ หรือ cached_plan เดิมถ้าข้าม Planner ไป) เพื่อให้
    run_multi_agent_task นำไป cache สำหรับ attempt ถัดไปได้
    """
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
            # Mitigation B: ข้าม Planner ไปเลย ฝังแผนที่ cache
            # ไว้ลงในข้อความเริ่มต้นที่ Worker ได้รับโดยตรง
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

    return success, final_answer, len(groupchat.messages), rejections, quality_score, caught_error, planner_output


def run_multi_agent_task(task_prompt: str, logger=None, max_rounds: int = None, task_name: str = None,
                          strict_reviewer: bool = False, mitigation: str = "none",
                          network_condition: dict = None):
    """รัน 1 task ผ่าน Planner -> Worker -> Reviewer

    Tier6 เป็นจุดที่เรียก strict_reviewer=True และ mitigation=<...> พร้อมกัน
    เป็นครั้งแรก (ดู run_tier6_mitigation_multiround.py) — ทั้งสองพารามิเตอร์
    เป็น default "none"/"False" เสมอ จึง call site เดิมทั้งหมด (Tier1/Tier3/
    Tier4/experiment เดิม) ไม่ได้รับผลกระทบ
    """
    if mitigation not in VALID_MITIGATIONS:
        raise ValueError(f"mitigation ต้องเป็นหนึ่งใน {VALID_MITIGATIONS} แต่ได้ {mitigation!r}")

    use_adaptive_timeout = mitigation in ("adaptive_timeout", "both")
    use_context_cache = mitigation in ("context_cache", "both")

    timeout_seconds = _adaptive_timeout_seconds(network_condition) if use_adaptive_timeout else None

    max_rounds = max_rounds or MAX_ROUNDS
    start_ts = time.time()

    attempt = 0
    retries_used = 0
    cached_plan = None
    success, final_answer, rounds, rejections, quality_score = False, "", 0, 0, None

    while attempt <= MAX_RETRIES:
        attempt += 1
        # Mitigation B: ใช้ cached_plan ตั้งแต่ attempt ที่ 2 เป็นต้นไป
        # ถ้าเปิด context_cache และมี plan จาก attempt ก่อนหน้าอยู่แล้ว
        plan_to_use = cached_plan if (use_context_cache and attempt > 1 and cached_plan) else None

        success, final_answer, rounds, rejections, quality_score, error, planner_output = _attempt_once(
            task_prompt, max_rounds, logger, strict_reviewer=strict_reviewer,
            timeout_seconds=timeout_seconds, cached_plan=plan_to_use,
        )
        if planner_output:
            cached_plan = planner_output

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
        "mitigation": mitigation,  # บันทึกไว้ว่า attempt นี้ใช้ mitigation อะไร (ดูหมายเหตุ code gap ใน README)
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
