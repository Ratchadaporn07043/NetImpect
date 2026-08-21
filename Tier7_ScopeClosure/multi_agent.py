"""
Multi-Agent Runner — Tier 7 (Scope Closure)
============================================
สำเนาสะสมของ Tier5/Tier6 (`strict_reviewer` + `mitigation` + `network_condition`)
บวกสองสิ่งที่ Tier 7 ต้องใช้:

TIER7 CHANGE 1 — mitigation ตัวใหม่: "fixed_long_timeout"
    เหตุผล: ผลของ Tier5 แสดงว่า condition-aware timeout เพิ่ม completion ที่ 75%
    configured loss จาก 14/20 เป็น 20/20 (Fisher p = 0.0202) — แต่ **ไม่เคย
    เทียบกับการตั้ง timeout ยาวคงที่** จึงแยกไม่ได้ว่าสิ่งที่ช่วยคือ "การปรับ
    timeout ตามสภาพเครือข่าย" (condition-awareness) หรือแค่ "ให้เวลามากขึ้น"
    เฉยๆ arm นี้ตั้ง timeout คงที่เท่ากับค่าที่สูตร adaptive ให้ที่จุดวิกฤต
    (loss=75%  ->  120 + int(75*3) = 345 วินาที) กับ **ทุก** scenario เพื่อให้
    ต่างจาก adaptive arm เพียงมิติเดียวคือความ condition-aware

TIER7 CHANGE 2 — บันทึก agent ที่ error เกิดขึ้น
    เดิม error log ไม่มี field บอกว่า LLM call ของ agent ตัวไหน timeout ทำให้
    คำอธิบายผลลบของ context caching เป็นเพียงสมมติฐาน ตอนนี้จำ speaker ล่าสุด
    จาก transcript แล้วอนุมาน agent ที่ถึงคิวถัดไปตาม round-robin ส่งเข้า
    logger.log_error(..., agent=...)

หมายเหตุสำคัญเรื่องสถาปัตยกรรมที่ตรวจพบระหว่างทำ Tier 7 (ไม่ได้แก้โค้ด โดยตั้งใจ):
    `planner.initiate_chat(manager, message=...)` ทำให้ข้อความแรกที่ติดป้ายว่า
    "Planner" คือ **seed message ที่เป็นตัว prompt เอง ไม่ใช่ผลลัพธ์จากโมเดล**
    จากนั้น round-robin ไป Worker ทันที ผลคือใน 95.8% ของ trial ที่ตรวจ Planner
    **ไม่ได้เรียก LLM เลยสักครั้ง** — 1 trial ที่สำเร็จมี 2 LLM call ไม่ใช่ 3
    และ `cached_plan` ที่ context caching เก็บไว้ก็คือตัว prompt เดิม ไม่ใช่แผน
    พฤติกรรมนี้ **คงไว้ตามเดิมโดยเจตนา** เพื่อให้ Tier 7 เทียบกับข้อมูลเดิมทั้ง
    5,300 trials ได้ และรายงานระบบตามที่เป็นจริงในเปเปอร์แทนการเปลี่ยนระบบกลางคัน
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

# TIER7: timeout คงที่ของ arm "fixed_long_timeout"
# ค่าเริ่มต้น = ค่าที่ _adaptive_timeout_seconds() คืนที่จุดวิกฤต loss=75%
#   120 (base) + int(75 * 3) = 345 วินาที
# ตั้งเท่ากันทุก scenario โดยเจตนา เพื่อให้ต่างจาก adaptive arm มิติเดียว
FIXED_LONG_TIMEOUT = int(os.environ.get("FIXED_LONG_TIMEOUT", 345))

ROUND_ROBIN_ORDER = ("Planner", "Worker", "Reviewer")


def _next_speaker(last_speaker: str):
    """agent ที่ถึงคิวถัดจาก last_speaker ตาม round-robin (None ถ้าระบุไม่ได้)"""
    if last_speaker not in ROUND_ROBIN_ORDER:
        return None
    idx = ROUND_ROBIN_ORDER.index(last_speaker)
    return ROUND_ROBIN_ORDER[(idx + 1) % len(ROUND_ROBIN_ORDER)]


def _blame_agent(groupchat_messages, use_cached_plan: bool = False):
    """อนุมานว่า LLM call ของ agent ตัวไหนล้มเหลว

    transcript บันทึกเฉพาะเทิร์นที่ผลิตข้อความสำเร็จ เทิร์นที่ error จึงไม่มี
    ข้อความ -> agent ที่ล้มเหลวคือตัวที่ถึงคิวถัดจากข้อความล่าสุด
    เมื่อ use_cached_plan=True ห้องแชทมีแค่ (Worker, Reviewer) จึงสลับสองตัวนี้
    """
    if not groupchat_messages:
        return "Worker" if use_cached_plan else None
    last = groupchat_messages[-1].get("name", "")
    if use_cached_plan:
        return "Reviewer" if last == "Worker" else "Worker"
    return _next_speaker(last)

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


# TIER5 CHANGE: คำนวณ timeout แบบปรับตาม network condition
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
    """TIER5 CHANGE: เพิ่ม timeout_seconds (ส่งต่อจาก _adaptive_timeout_seconds
    เมื่อเปิด mitigation='adaptive_timeout'/'both' — ถ้าไม่ส่ง = BASE_LLM_TIMEOUT
    เหมือนเดิม)"""

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

    TIER5 CHANGE:
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
            # TIER5 CHANGE (Mitigation B): ข้าม Planner ไปเลย ฝังแผนที่ cache
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

    # TIER7: อนุมาน agent ที่ LLM call ล้มเหลว จาก transcript ที่ค้างอยู่ ณ จุดที่ error
    blamed_agent = _blame_agent(groupchat.messages, use_cached_plan) if caught_error is not None else None

    return (success, final_answer, len(groupchat.messages), rejections, quality_score,
            caught_error, planner_output, blamed_agent)


def run_multi_agent_task(task_prompt: str, logger=None, max_rounds: int = None, task_name: str = None,
                          strict_reviewer: bool = False, mitigation: str = "none",
                          network_condition: dict = None):
    """รัน 1 task ผ่าน Planner -> Worker -> Reviewer

    TIER5 CHANGE: เพิ่มพารามิเตอร์ mitigation (default "none" = พฤติกรรมเดิม
    100%) และ network_condition (dict ของ scenario ปัจจุบัน ใช้กับ
    adaptive_timeout เท่านั้น)
    """
    if mitigation not in VALID_MITIGATIONS:
        raise ValueError(f"mitigation ต้องเป็นหนึ่งใน {VALID_MITIGATIONS} แต่ได้ {mitigation!r}")

    use_adaptive_timeout = mitigation in ("adaptive_timeout", "both")
    use_context_cache = mitigation in ("context_cache", "both")
    use_fixed_long_timeout = mitigation == "fixed_long_timeout"

    if use_adaptive_timeout:
        timeout_seconds = _adaptive_timeout_seconds(network_condition)
    elif use_fixed_long_timeout:
        # TIER7: ค่าเดียวกันทุก scenario โดยไม่ดู network_condition เลย
        # นี่คือจุดที่ทำให้ arm นี้ต่างจาก adaptive arm เพียงมิติเดียว
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
        # TIER5 CHANGE (Mitigation B): ใช้ cached_plan ตั้งแต่ attempt ที่ 2 เป็นต้นไป
        # ถ้าเปิด context_cache และมี plan จาก attempt ก่อนหน้าอยู่แล้ว
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
            # TIER7: บันทึก agent ที่ล้มเหลวลง log โดยตรง ไม่ต้องอนุมานย้อนหลังอีก
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
        "mitigation": mitigation,  # TIER5 CHANGE: บันทึกไว้ว่า attempt นี้ใช้ mitigation อะไร
        "timeout_seconds": timeout_seconds,  # TIER7: timeout ที่ใช้จริงใน trial นี้
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
