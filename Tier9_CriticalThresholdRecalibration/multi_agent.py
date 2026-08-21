"""
Multi-Agent Runner — Tier 9 (Critical Threshold Recalibration)
========================================================================
สำเนาของ `Tier8_EnsureScopeClosure/multi_agent.py` ทั้งหมด **ยกเว้นจุดเดียว
ที่ตั้งใจเปลี่ยน**: LLM call ทุกตัวคุย Ollama ผ่าน native `/api/chat` +
`"think": false` (ผ่าน `OllamaNativeThinkOffClient`) เป็น**ค่าเริ่มต้นมาตรฐาน
ของไฟล์นี้เลย** ไม่ใช่ monkey-patch จากภายนอกแบบที่
`Tier8_EnsureScopeClosure/thinking_off_diagnostic/multi_agent_thinking_off.py`
ทำ (ไฟล์นั้นเป็นเครื่องมือวินิจฉัยชั่วคราว จงใจไม่แก้ไฟล์ต้นฉบับ — ไฟล์นี้คือ
"ต้นฉบับ" ของ Tier 9 เองที่เขียนให้ถูกต้องตั้งแต่แรกไปเลย)

เหตุผลที่ต้องฝัง native client เป็นค่าเริ่มต้น (สรุปจาก Tier 8, ตรวจสอบซ้ำแล้ว
หลายรอบก่อนสรุปเป็น Tier 9):
  1. Ollama เวอร์ชันของเครื่องนี้เปิด "thinking" mode เป็นค่าเริ่มต้นให้ qwen3:8b
     ทำให้ทุก LLM call ผ่าน `/v1/chat/completions` (ที่ AutoGen ใช้ปกติ) ช้าลง
     10-30+ เท่า โดยพารามิเตอร์ "think": false ผ่าน endpoint นั้นถูก Ollama
     เพิกเฉยเงียบๆ (ยืนยันด้วยการทดสอบจริงหลายรอบใน Tier 8)
  2. วิธีเดียวที่ยืนยันแล้วว่าปิด thinking ได้จริงคือเรียก native `/api/chat`
     พร้อม `"think": false` ตรงๆ — ต้องใช้ custom AutoGen model client
     (`ollama_native_client.py` ในโฟลเดอร์นี้)
  3. **สำคัญที่สุด**: การรัน confirmatory จริงใน Tier 8 พบว่า thinking mode
     ไม่ใช่สาเหตุของ ceiling effect ที่ข้อ 1/2/3 (ปิดแล้ว completion ยังสูง
     เท่าเดิม) — สาเหตุจริงคือ inference โดยรวม (ไม่นับ thinking) เร็วขึ้นเอง
     ~2 เท่าเมื่อเทียบกับตอน Tier 5 รัน (ดู Tier 9 README.md หัวข้อ "ที่มา")
     ดังนั้นการฝัง thinking-off เป็นค่าเริ่มต้นใน Tier 9 **ไม่ใช่การแก้ปัญหา
     ceiling effect** (นั่นคือเป้าหมายของการหา critical loss ใหม่ต่างหาก)
     แต่เป็นการรับประกันว่าอย่างน้อย "ตัวแปรที่ควบคุมได้" (thinking mode) จะไม่
     ปนเข้ามาเป็น confound อีกในผลของ Tier 9 — ส่วน "ตัวแปรที่ควบคุมไม่ได้"
     (inference เร็วขึ้นเอง) คือเหตุผลที่ต้องหา critical loss ใหม่แทนที่จะใช้
     75% เดิม

คงไว้ตามเดิมจาก Tier 8 ทั้งหมด (ไม่เปลี่ยน):
  - mitigation modes: none / adaptive_timeout / context_cache / both / fixed_long_timeout
  - retry logic, agent-blame logic, evaluator call, logger call — ทุกอย่าง
    เหมือน Tier8_EnsureScopeClosure/multi_agent.py เป๊ะ ยกเว้นจุดที่สร้าง/
    ใช้งาน LLM client (ดู _llm_config()/build_agents()/_attempt_once() ด้านล่าง
    ที่มีคอมเมนต์ "TIER9 CHANGE" กำกับจุดที่ต่างจาก Tier 8 ไว้ชัดเจน)
  - FIXED_LONG_TIMEOUT: ยังคำนวณจากสูตรเดียวกัน (BASE_LLM_TIMEOUT + int(loss*3))
    แต่ Tier 9 ตั้งค่าให้ตรงกับ critical loss ที่พบใหม่ (ไม่ใช่ 75% ตายตัวแบบ
    Tier 8) — ค่าเริ่มต้น 345 ด้านล่างเป็นแค่ fallback เฉยๆ ของจริง
    run_tier9_critical_comparison.py จะ import โมดูลนี้ก่อน แล้ว **ตั้งค่า
    `multi_agent.FIXED_LONG_TIMEOUT` ทับตรงๆ หลัง import** (ไม่ใช่ผ่าน
    environment variable) เพราะฟังก์ชันที่ใช้ค่านี้ (ดู _attempt_once() ด้านล่าง)
    อ่านชื่อ global ของโมดูลตอนถูกเรียกจริงเสมอ ไม่ใช่ตอน import ครั้งแรก
    การตั้งค่าทับหลัง import จึงมีผลจริงเหมือนตั้ง env var ก่อน import ทุกประการ
"""
import os
import re
import time
from autogen import ConversableAgent, GroupChat, GroupChatManager
from tier9_evaluator import evaluate_answer  # สำเนา standalone ของ Tier 9 (ไม่ผูกกับ experiment/ ที่ root)
from ollama_native_client import OllamaNativeThinkOffClient  # TIER9 CHANGE

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen3:8b")

MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", 6))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 2))
BASE_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", 120))

VALID_MITIGATIONS = ("none", "adaptive_timeout", "context_cache", "both", "fixed_long_timeout")

# ค่าเริ่มต้น 345 (= ค่าที่ Tier 8 ใช้ที่จุดวิกฤตเดิม loss=75%) เก็บไว้เป็น
# fallback เฉยๆ ไม่ได้ใช้จริงตอนรัน Tier 9 — run_tier9_critical_comparison.py
# จะตั้งค่า multi_agent.FIXED_LONG_TIMEOUT ทับตรงๆ หลัง import เสมอ (ดู main()
# ในไฟล์นั้น บรรทัดที่เรียก multi_agent_module._adaptive_timeout_seconds()
# แล้ว assign ทับ) ให้ตรงกับ critical loss ที่พบใหม่จริง ไม่ใช่ 345 นี้
FIXED_LONG_TIMEOUT = int(os.environ.get("FIXED_LONG_TIMEOUT", 345))

ROUND_ROBIN_ORDER = ("Planner", "Worker", "Reviewer")


def _next_speaker(last_speaker: str):
    """agent ที่ถึงคิวถัดจาก last_speaker ตาม round-robin (None ถ้าระบุไม่ได้)"""
    if last_speaker not in ROUND_ROBIN_ORDER:
        return None
    idx = ROUND_ROBIN_ORDER.index(last_speaker)
    return ROUND_ROBIN_ORDER[(idx + 1) % len(ROUND_ROBIN_ORDER)]


def _blame_agent(groupchat_messages, use_cached_plan: bool = False):
    """อนุมานว่า LLM call ของ agent ตัวไหนล้มเหลว: transcript บันทึกเฉพาะเทิร์นที่
    ผลิตข้อความสำเร็จ เทิร์นที่ error จึงไม่มีข้อความ -> agent ที่ล้มเหลวคือตัวที่
    ถึงคิวถัดจากข้อความล่าสุด เมื่อ use_cached_plan=True ห้องแชทมีแค่
    (Worker, Reviewer) จึงสลับสองตัวนี้"""
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
    +10s ต่อทุก 100ms delay, +3s ต่อทุก 1% loss, +5s ต่อทุก 10ms jitter,
    cap ที่ 10 เท่าของ base"""
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
                # TIER9 CHANGE: บอก AutoGen ว่า config entry นี้ต้องใช้ custom
                # client (ค่านี้เป็น string ต้องตรงกับ __name__ ของคลาสเป๊ะ —
                # ดู autogen.oai.client.OpenAIWrapper._register_default_client
                # ที่ผูก placeholder ไว้รอ register_model_client() เรียกจริง)
                "model_client_cls": "OllamaNativeThinkOffClient",
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

    # TIER9 CHANGE: ผูก custom client เข้ากับทั้ง 3 agent ทันทีหลังสร้าง (ต้อง
    # สร้าง agent ก่อนถึงจะเรียก register_model_client ได้ ตามรูปแบบมาตรฐานของ
    # AutoGen custom model client — ดู ollama_native_client.py)
    for agent in (planner, worker, reviewer):
        agent.register_model_client(model_client_cls=OllamaNativeThinkOffClient)

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
    # TIER9 CHANGE: _attempt_once() สร้าง manager เองตรงๆ ไม่ผ่าน build_agents()
    # ต้องผูก custom client ให้ manager ด้วย เพราะ manager ก็เรียก LLM เหมือนกัน
    # (เลือก speaker / จัดการบทสนทนา) ถ้าลืมจุดนี้ manager จะยังคุยผ่าน
    # /v1/chat/completions เดิมอยู่ ทั้งที่ agent อื่นคุยผ่าน native แล้ว
    manager.register_model_client(model_client_cls=OllamaNativeThinkOffClient)

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
