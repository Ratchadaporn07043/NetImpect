#!/usr/bin/env python3
"""
smoke_test_thinking_off.py — ทดสอบเร็วๆ ว่า OllamaNativeThinkOffClient +
multi_agent_thinking_off.py ใช้งานได้จริง ก่อนรัน confirmatory re-run เต็มรูปแบบ
================================================================================
รันบน host/container เดียวกับที่รัน Tier8 จริง (ต้องมี pyautogen, requests,
เข้าถึง Ollama ที่ OLLAMA_BASE_URL ได้) ไม่แตะ tc/network เลย ไม่เขียน log ไฟล์
ถาวร ใช้เวลารวมไม่ควรเกิน ~1-2 นาที ถ้าทุกอย่างถูกต้อง (รวม cold-start model
load ครั้งเดียว ~15-30s ในรอบ warm-up ของ Stage 1 — เทียบกับหลายสิบวินาที/
หลายนาที "ต่อ 1 request" ถ้า thinking mode ยังเปิดอยู่)

ขั้นตอน:
  Stage 1 — เรียก OllamaNativeThinkOffClient โดยตรง (ไม่ผ่าน AutoGen เลย)
            ยิง "warm-up" call ก่อน 1 ครั้ง (ไม่จับเวลา, timeout กว้าง 180s)
            เพื่อให้ Ollama โหลดโมเดล qwen3:8b เข้า memory ก่อน (cold-start
            ครั้งแรกวัดจริงแล้วใช้เวลา ~15s ต่อครั้งที่ Ollama restart/evict
            โมเดล — ไม่เกี่ยวกับ thinking mode เลย เป็นค่าใช้จ่ายปกติของ Ollama)
            แล้วค่อยยิงรอบสองที่จับเวลาจริง ยืนยันว่า native /api/chat +
            think:false ทำงานเร็ว (<3s) และไม่มี reasoning field ปนมาในคำตอบ
  Stage 2 — เรียกผ่าน multi_agent_thinking_off.py เต็มรูปแบบ (Planner->Worker->
            Reviewer จริงผ่าน AutoGen GroupChat) ด้วย task สั้นๆ 1 ข้อ max_rounds
            ต่ำ ยืนยันว่า elapsed_seconds รวมทั้ง workflow อยู่ในหลักสิบวินาที
            (ไม่ใช่หลักร้อยเหมือนตอน thinking mode เปิด) — โมเดลอุ่นเครื่องจาก
            Stage 1 แล้ว จึงไม่ต้อง warm-up ซ้ำใน Stage 2

การใช้งาน:
    python3 smoke_test_thinking_off.py
"""
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # thinking_off_diagnostic/
_TIER8_DIR = os.path.dirname(_THIS_DIR)  # Tier8_EnsureScopeClosure/
_PROJECT_ROOT = os.path.dirname(_TIER8_DIR)  # โฟลเดอร์โปรเจกต์
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TIER8_DIR)
sys.path.insert(0, _THIS_DIR)  # insert ท้ายสุดเพื่อให้อยู่ตำแหน่ง 0 จริง

from ollama_native_client import OllamaNativeThinkOffClient  # noqa: E402


def stage1_direct_client_test():
    print("=" * 70)
    print("Stage 1: เรียก OllamaNativeThinkOffClient ตรงๆ (ไม่ผ่าน AutoGen)")
    print("=" * 70)

    model = os.environ.get("MODEL_NAME", "qwen3:8b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    # timeout กว้าง (180s) เผื่อ cold-start model load รอบ warm-up — ใช้ timeout
    # เดียวกันสำหรับรอบจับเวลาจริงด้วย (ไม่มีผลเพราะรอบนั้นควรจบใน <3s อยู่แล้ว
    # ถ้า think:false ทำงานถูกต้อง)
    config = {"model": model, "base_url": base_url, "timeout": 180, "temperature": 0.3}
    client = OllamaNativeThinkOffClient(config)
    print(f"  target native endpoint: {client.chat_url}")

    params = {
        "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}],
        "n": 1,
        "temperature": 0.3,
    }

    print("  warm-up call (ไม่จับเวลา, รอ Ollama โหลดโมเดลเข้า memory ถ้ายังไม่ได้โหลด)...")
    warmup_start = time.time()
    client.create(params)
    warmup_elapsed = time.time() - warmup_start
    print(f"  warm-up เสร็จใน {warmup_elapsed:.2f}s "
          f"({'มีการโหลดโมเดลจริง (cold start)' if warmup_elapsed > 3.0 else 'โมเดลอุ่นอยู่แล้ว'})")

    start = time.time()
    response = client.create(params)
    elapsed = time.time() - start

    content = response.choices[0].message.content
    print(f"  elapsed (หลัง warm-up แล้ว): {elapsed:.2f}s")
    print(f"  content: {content!r}")

    ok = True
    if elapsed >= 3.0:
        print(f"  [WARN] ช้ากว่าที่คาด (>= 3s) แม้อุ่นเครื่องแล้ว — thinking mode "
              f"อาจยังไม่ได้ปิดจริง (ลอง raw curl ยืนยัน: ดู README.md ในโฟลเดอร์นี้)")
        ok = False
    if not content:
        print("  [FAIL] content ว่างเปล่า — ตรวจ Ollama ว่ารันอยู่จริงและ model โหลดสำเร็จ")
        ok = False

    print(f"  -> Stage 1 {'ผ่าน' if ok else 'ไม่ผ่าน'}")
    print()
    return ok


def stage2_full_autogen_integration():
    print("=" * 70)
    print("Stage 2: run_multi_agent_task() เต็มรูปแบบผ่าน multi_agent_thinking_off")
    print("=" * 70)

    import multi_agent_thinking_off  # noqa: F401  (side effect: patch multi_agent)
    import multi_agent

    task = "เขียนฟังก์ชัน python คำนวณเลข fibonacci ตัวที่ N พร้อมอธิบายสั้นๆ"

    start = time.time()
    result = multi_agent.run_multi_agent_task(
        task, logger=None, max_rounds=4, task_name="smoke_test_fib",
        strict_reviewer=False, mitigation="none", network_condition=None,
    )
    elapsed = time.time() - start

    print(f"  elapsed รวมทั้ง workflow: {elapsed:.2f}s")
    print(f"  success={result['success']} rounds={result['rounds']} "
          f"retries={result['retries']} quality_score={result['quality_score']}")
    print(f"  final_answer (400 ตัวอักษรแรก): {result['final_answer'][:400]!r}")

    ok = True
    # เกณฑ์นี้เทียบกับ "ลายเซ็น" ของ thinking-on ที่วัดจริงจาก Tier 8 (item 2
    # elapsed median = 311s ต่อ trial เต็ม, single trivial one-word reply อย่าง
    # เดียวก็ 8-38s แล้ว) ไม่ใช่เทียบกับเวลาที่ "เร็วที่สุดในทางทฤษฎี" — บทสนทนา
    # จริง 3-4 รอบที่ต้องสร้างคำตอบยาว (โค้ด+คำอธิบาย) ใช้เวลาจริงหลักสิบวินาที
    # แม้ thinking ปิดแล้วก็ตาม ไม่ใช่หลักวินาทีเดียวเหมือน Stage 1 ที่ตอบแค่คำเดียว
    if elapsed >= 200.0:
        print("  [WARN] ช้ากว่าที่คาดมาก (>= 200s) ใกล้เคียงลายเซ็นของ thinking-on "
              "(item 2 เดิม median 311s/trial) — ตรวจว่า patch ทำงานจริง (ควรเห็น "
              "ข้อความ '[multi_agent_thinking_off] patched ...' พิมพ์ออกมาตอน import ด้านบน)")
        ok = False
    if not result["final_answer"]:
        print("  [FAIL] final_answer ว่างเปล่า — workflow อาจ error ทุก attempt")
        ok = False
    if result["success"] is False and result["final_answer"]:
        print("  [หมายเหตุ] success=False ที่นี่คือ Reviewer ตัดสินว่าคำตอบยังไม่ผ่าน "
              "(เนื้อหาโค้ดผิดจริง เช่น n=1 ควรได้ 0) เป็นเรื่องคุณภาพคำตอบของโมเดล "
              "ไม่เกี่ยวกับว่า patch/thinking-off ทำงานถูกต้องหรือไม่ ไม่ทำให้ Stage 2 ไม่ผ่าน")

    print(f"  -> Stage 2 {'ผ่าน' if ok else 'ไม่ผ่าน'}")
    print()
    return ok


def main():
    print("smoke_test_thinking_off.py — ทดสอบก่อนรัน confirmatory re-run เต็มรูปแบบ\n")
    ok1 = stage1_direct_client_test()
    ok2 = stage2_full_autogen_integration() if ok1 else False

    print("=" * 70)
    if ok1 and ok2:
        print("สรุป: ผ่านทั้ง 2 stage — พร้อมรัน run_confirm_thinking_off.py ต่อได้")
        sys.exit(0)
    else:
        print("สรุป: มี stage ที่ไม่ผ่าน — อย่าเพิ่งรัน run_confirm_thinking_off.py "
              "จนกว่าจะแก้ปัญหาข้างต้นได้ก่อน")
        sys.exit(1)


if __name__ == "__main__":
    main()
