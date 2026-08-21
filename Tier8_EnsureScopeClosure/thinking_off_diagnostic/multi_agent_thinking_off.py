"""
multi_agent_thinking_off.py — Tier8 multi_agent.py แบบเดียวกันทุกประการ
แต่ monkey-patch ให้ทุก LLM call ผ่าน OllamaNativeThinkOffClient (native
/api/chat + "think": false) แทน default OpenAI-compatible client
================================================================================
เจตนา: ห้ามแก้ Tier8_EnsureScopeClosure/multi_agent.py ตัวจริงโดยเด็ดขาด
(ไฟล์นั้นตรวจสอบ/ยืนยันความถูกต้องแล้ว และ Tier 8 จริงยังใช้มันอยู่) ไฟล์นี้จึง
import multi_agent module ตัวจริงมา แล้ว "ปะ" (monkey-patch) เฉพาะ 3 จุดที่จำเป็น
เพื่อสลับ LLM client โดยไม่แตะ logic การสนทนา/retry/evaluation ใดๆ เลย —
พฤติกรรมอื่นทั้งหมด (mitigation modes, retry, evaluator, logger) เหมือนเดิม
100% เพราะเรียกฟังก์ชันเดิมของ multi_agent.py จริงๆ ไม่ได้ copy โค้ดมาเขียนใหม่

3 จุดที่ patch (ทำไมต้องแก้ 3 จุดนี้ ไม่ใช่จุดเดียว):
  1. multi_agent._llm_config()
     เพิ่มคีย์ "model_client_cls": "OllamaNativeThinkOffClient" เข้าไปใน
     config_list entry — pyautogen 0.2.x ต้องเห็นคีย์นี้ก่อนถึงจะรู้ว่า config
     entry นี้ไม่ใช่ config แบบ OpenAI/Azure ปกติ (ไม่งั้น OpenAIWrapper จะ
     พยายามสร้าง openai.OpenAI client ไปเรียก /v1/chat/completions ตามเดิม)

  2. multi_agent.build_agents()
     หลังสร้าง Planner/Worker/Reviewer (3 ตัว) ต้องเรียก
     agent.register_model_client(model_client_cls=OllamaNativeThinkOffClient)
     ทีละตัว — นี่คือขั้นตอนที่ผูกคีย์ string "OllamaNativeThinkOffClient" จาก
     ข้อ 1 เข้ากับ class object จริง (ทำตอนนี้เพราะ agent ต้องถูกสร้างเสร็จก่อน
     ถึงจะเรียก register_model_client ได้ ตามรูปแบบมาตรฐานของ AutoGen custom
     model client)

  3. multi_agent.GroupChatManager
     _attempt_once() ใน multi_agent.py สร้าง GroupChatManager เองโดยตรง (ไม่ผ่าน
     build_agents()) จึงต้องแทนที่ class นี้ด้วย subclass ที่ auto-register
     ตัวเองใน __init__ — ไม่งั้น manager (ซึ่งก็เรียก LLM เหมือนกันตอนเลือก
     speaker/สรุปบทสนทนา) จะยังคุยผ่าน default client อยู่

ทำไม monkey-patch ถึงใช้ได้จริง (ไม่ใช่แค่ปะแล้วไม่มีผล):
  ฟังก์ชันใน Python มองหาชื่อที่ไม่ใช่ local variable จาก "module namespace"
  ของโมดูลที่ฟังก์ชันนั้นถูกนิยามไว้ ณ ตอนที่ถูกเรียก (ไม่ใช่ ณ ตอนที่ถูกนิยาม)
  ดังนั้นเมื่อเรา reassign `multi_agent._llm_config`, `multi_agent.build_agents`,
  `multi_agent.GroupChatManager` แล้ว โค้ดข้างในของ `_attempt_once()` และ
  `run_multi_agent_task()` (ที่เรียกชื่อพวกนี้แบบ global lookup อยู่แล้ว) จะ
  หยิบเวอร์ชันที่ patch แล้วไปใช้เองโดยอัตโนมัติ ไม่ต้อง copy/แก้โค้ดภายในเลย

การใช้งาน:
    import multi_agent_thinking_off  # แค่ import ก็ patch ทันที (side effect)
    import multi_agent               # module เดียวกับที่ patch ไปแล้ว
    result = multi_agent.run_multi_agent_task(...)  # เรียกปกติ ได้ thinking-off แล้ว
"""
import sys
import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import multi_agent  # noqa: E402  (Tier8 local — ต้อง import "ก่อน" ไฟล์นี้เสมอ
# ผ่านการตั้ง sys.path ของสคริปต์ runner ที่เรียกไฟล์นี้ เหมือนที่
# run_tier8_fixed_timeout.py ทำ — ไฟล์นี้ไม่ตั้ง sys.path ให้เพราะไม่ใช่ entrypoint)
from autogen import GroupChatManager  # noqa: E402
from ollama_native_client import OllamaNativeThinkOffClient  # noqa: E402

_PATCHED_FLAG = "_thinking_off_patch_applied"


def _patch_llm_config():
    original_llm_config = multi_agent._llm_config

    def _llm_config_thinking_off(temperature: float = 0.3, timeout_override: int = None):
        config = original_llm_config(temperature, timeout_override)
        for entry in config["config_list"]:
            entry["model_client_cls"] = "OllamaNativeThinkOffClient"
        return config

    multi_agent._llm_config = _llm_config_thinking_off


def _patch_build_agents():
    original_build_agents = multi_agent.build_agents

    def build_agents_thinking_off(strict_reviewer: bool = False, timeout_seconds: int = None):
        planner, worker, reviewer = original_build_agents(strict_reviewer, timeout_seconds)
        for agent in (planner, worker, reviewer):
            agent.register_model_client(model_client_cls=OllamaNativeThinkOffClient)
        return planner, worker, reviewer

    multi_agent.build_agents = build_agents_thinking_off


class _AutoRegisteringGroupChatManager(GroupChatManager):
    """เหมือน GroupChatManager ทุกประการ แต่ register custom client ให้ตัวเอง
    ทันทีหลังสร้างเสร็จ เพราะ _attempt_once() ใน multi_agent.py สร้าง manager
    ตรงๆ ไม่ผ่าน build_agents() (ดูคำอธิบายจุดที่ 3 ด้านบนไฟล์)"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_model_client(model_client_cls=OllamaNativeThinkOffClient)


def _patch_group_chat_manager():
    multi_agent.GroupChatManager = _AutoRegisteringGroupChatManager


def apply_patches():
    """เรียกครั้งเดียวตอน import (idempotent — เรียกซ้ำได้ไม่พัง)"""
    if getattr(multi_agent, _PATCHED_FLAG, False):
        return
    _patch_llm_config()
    _patch_build_agents()
    _patch_group_chat_manager()
    setattr(multi_agent, _PATCHED_FLAG, True)
    print("[multi_agent_thinking_off] patched multi_agent._llm_config / "
          "build_agents / GroupChatManager -> ใช้ OllamaNativeThinkOffClient แล้ว")


apply_patches()
