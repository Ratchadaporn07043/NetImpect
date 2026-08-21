"""
AutoGen Multi-Agent System
==========================
Planner -> Worker -> Reviewer คุยกันผ่าน GroupChat (Round-based communication)
ตรงตาม diagram: docker/AutoGen Multi-Agent System

ใช้งาน:
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

# จำนวนรอบสนทนา "สูงสุด" (safety cap กันไม่ให้ loop ไม่จบเมื่อ network แย่มาก
# หรือ Reviewer ไม่ยอม APPROVED สักที) ปกติบทสนทนาจะจบเร็วกว่านี้อยู่แล้ว
# เพราะมี early-termination เมื่อ Reviewer พูด APPROVED (ดู _is_reviewer_approved)
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", 6))

# จำนวนครั้งที่ retry ทั้ง task ใหม่ ถ้าเจอ timeout/connection error (ไม่นับ attempt แรก)
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
        # timeout ระดับ request เดียว (วินาที) — สำคัญมากตอนจำลอง network แย่
        # ปรับผ่าน env LLM_TIMEOUT ถ้าโมเดลตอบช้ากว่านี้ (เช่นเครื่องรันช้า)
        "timeout": int(os.environ.get("LLM_TIMEOUT", 120)),
        # ปิด cache เด็ดขาด! ถ้าไม่ปิด AutoGen จะ cache คำตอบไว้ตาม (prompt+model+temperature)
        # แล้วครั้งถัดไปถ้า prompt เดิม (เช่น task เดียวกันคนละ scenario) จะไม่ยิง
        # request ไปหา LLM จริงเลย แต่ดึงคำตอบเก่าจาก disk มาใช้แทน (เร็วผิดปกติ,
        # token/quality เหมือนเป๊ะทุกครั้ง) ทำให้ผลการทดลองเรื่อง network ไม่มีความหมาย
        "cache_seed": None,
    }


def build_agents():
    """สร้าง 3 agent ตาม diagram: Planner, Worker, Reviewer"""

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
    """ดึงคะแนน 1-5 จากข้อความ Reviewer เช่น 'SCORE: 4' -> คืน 4 หรือ None ถ้าไม่เจอ"""
    match = re.search(r"SCORE\s*[:：]\s*(\d)", reviewer_text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 5:
            return score
    return None


def _is_reviewer_approved(msg) -> bool:
    """
    ใช้เป็น is_termination_msg ของ GroupChatManager

    แก้บั๊ก: เดิม speaker_selection_method="round_robin" วนไปจนครบ
    max_round เสมอ ไม่มี logic ให้หยุดทันทีที่ Reviewer อนุมัติงานแล้ว
    ผลคือ "rounds" ที่ log ไว้เป็นค่าคงที่ (=MAX_ROUNDS) ทุก trial ไม่ได้
    สะท้อนอะไรจากการทดลองจริง แถมยังเสียเวลา/token คุยต่อทั้งที่งานเสร็จแล้ว

    ตอนนี้เช็คว่าข้อความล่าสุดมาจาก Reviewer และขึ้นต้นด้วย "APPROVED"
    หรือไม่ ถ้าใช่ -> ให้ GroupChatManager หยุดบทสนทนาทันที
    """
    if not isinstance(msg, dict):
        return False
    if msg.get("name") != "Reviewer":
        return False
    content = (msg.get("content") or "").strip().upper()
    return content.startswith("APPROVED")


def _attempt_once(task_prompt: str, max_rounds: int, logger=None):
    """
    รัน 1 ครั้ง (1 attempt) ของ Planner -> Worker -> Reviewer
    ใช้ agent ชุดใหม่ทุกครั้ง เพื่อไม่ให้ state เก่าค้างข้ามรอบ retry

    คืนค่า: (success, final_answer, rounds_seen, rejections, quality_score, error_or_None)
    """
    planner, worker, reviewer = build_agents()

    # แก้บั๊ก: เดิม logger.log_message() ถูกเรียกใน loop `for msg in
    # groupchat.messages` หลังบทสนทนาทั้งหมดจบแล้วเท่านั้น (ใน finally block)
    # ทำให้ timestamp ของทุก message ในบทสนทนาเกาะติดกันเป็นก้อนเดียว
    # (ต่างกันแค่เสี้ยววินาที ซึ่งคือเวลาที่ใช้ loop เขียน log ไม่ใช่เวลาจริง
    # ที่แต่ละ message ถูกส่ง) ทำให้วัด latency ต่อ message จาก network delay
    # ไม่ได้เลย
    #
    # ตอนนี้ hook เข้า "process_message_before_send" ของแต่ละ agent เพื่อ
    # บันทึกเวลาจริง ณ ตอนที่ agent นั้นส่งข้อความออกไปจริงๆ แล้วค่อยจับคู่
    # กับ groupchat.messages ทีหลังตามลำดับ (index ต่อ index)
    message_timestamps = []

    def _record_send_timestamp(sender, message, recipient, silent):
        message_timestamps.append(time.time())
        return message  # ต้องคืนค่า message เดิม ไม่แก้ไขเนื้อหา

    for agent in (planner, worker, reviewer):
        try:
            agent.register_hook("process_message_before_send", _record_send_timestamp)
        except AttributeError:
            # autogen เวอร์ชันเก่าบางเวอร์ชันอาจไม่มี register_hook นี้
            # ถ้าไม่มี ให้ข้ามไป (fallback: message_timestamps จะว่างเปล่า
            # ทุก message จะ fallback ไปใช้ time.time() ตอน log แทน เหมือน
            # พฤติกรรมเดิมก่อนแก้ ไม่ทำให้โปรแกรม crash)
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
        # สำคัญ: log message ที่เกิดขึ้นจริงเสมอ ไม่ว่าจะจบปกติหรือ error กลางทาง
        # (แก้บั๊กเดิมที่ messages ว่างเปล่าเมื่อเกิด timeout กลางทาง)
        for idx, msg in enumerate(groupchat.messages):
            speaker = msg.get("name", "")
            content = msg.get("content", "") or ""

            # จับคู่ timestamp จริงตามลำดับ ถ้าจำนวนไม่ตรงกัน (เช่น hook ไม่ทำงาน
            # เพราะ autogen เวอร์ชันเก่าไม่รองรับ register_hook) ให้ fallback
            # เป็นเวลาปัจจุบัน กันโปรแกรม crash แต่ผลลัพธ์จะกลับไปเป็นแบบเดิม
            real_timestamp = message_timestamps[idx] if idx < len(message_timestamps) else time.time()

            if logger is not None:
                logger.log_message(from_agent=speaker, to_agent="group", content=content,
                                    timestamp=real_timestamp)

            if speaker == "Reviewer":
                score = _parse_quality_score(content)
                if score is not None:
                    quality_score = score

                # success = คำตัดสิน "ล่าสุด" ของ Reviewer เสมอ (overwrite ทุกครั้ง
                # เหมือน quality_score) แก้บั๊กเดิมที่ success ค้างเป็น True แม้
                # Reviewer จะ REVISE ในรอบหลัง
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
    รัน 1 task ผ่าน Planner -> Worker -> Reviewer
    มี retry อัตโนมัติถ้าเจอ timeout/connection error (สูงสุด MAX_RETRIES ครั้ง)

    Args:
        task_prompt: โจทย์งานที่จะให้ทีม agent ทำ
        logger: instance ของ ExperimentLogger (ถ้ามี จะ log ทุก message อัตโนมัติ)
        max_rounds: override MAX_ROUNDS ถ้าต้องการ (safety cap เท่านั้น
                    บทสนทนาจะหยุดเร็วกว่านี้ถ้า Reviewer APPROVED ก่อนถึง cap)
        task_name: ชื่อ benchmark task สำหรับ ground-truth evaluator

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
            break  # สำเร็จ (ไม่มี exception) ไม่ต้อง retry ต่อ

        # แยกประเภท error ให้ถูกต้อง (แก้บั๊กเดิมที่ TimeoutError ไม่ถูกนับเป็น timeout)
        is_timeout = "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower()

        if logger is not None:
            if is_timeout:
                logger.log_timeout(detail=str(error)[:300])
            else:
                logger.log_error(error_type=type(error).__name__, detail=str(error)[:300])

        retries_used = attempt - 1  # จำนวนครั้งที่ retry ไปแล้ว (ไม่นับ attempt แรก)

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
    # ทดสอบเดี่ยวๆ โดยไม่มี logger (รันตรงจาก: python3 multi_agent.py)
    r = run_multi_agent_task("เขียนฟังก์ชัน python คำนวณเลข fibonacci ตัวที่ N")
    print(r)