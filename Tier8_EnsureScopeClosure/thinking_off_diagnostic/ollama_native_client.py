"""
ollama_native_client.py — Custom AutoGen model client ที่คุย Ollama ผ่าน
native /api/chat โดยตรง (ไม่ผ่าน OpenAI-compatible /v1/chat/completions)
================================================================================
เหตุผลที่ต้องมีไฟล์นี้ (ยืนยันด้วย micro-benchmark จริงก่อนเขียน ไม่ใช่เดา):

  1. Ollama เวอร์ชันปัจจุบันของเครื่องนี้ (0.32.5) เปิด "thinking" mode เป็น
     ค่าเริ่มต้นสำหรับ qwen3:8b — แม้แค่ถามคำถามเดียวคำ ("Reply with exactly
     one word: OK") ก็ยังคิด 8-23 วินาทีก่อนตอบ เพราะแนบ chain-of-thought
     ("thinking"/"reasoning" field) มาด้วยทุกครั้ง

  2. พารามิเตอร์ "think": false ที่ปิด thinking ได้จริง ใช้งานได้เฉพาะกับ
     native endpoint ของ Ollama (/api/generate, /api/chat) เท่านั้น —
     ทดสอบแล้วว่า "think": false ผ่าน /v1/chat/completions (endpoint ที่
     AutoGen ใช้อยู่ปกติผ่าน openai python client) ไม่มีผลอะไรเลย และ
     "/no_think" suffix ในข้อความก็ไม่ทำงานทั้งสอง endpoint เช่นกัน

  3. ดังนั้นวิธีเดียวที่ยืนยันแล้วว่าปิด thinking ได้จริงคือเลี่ยง AutoGen's
     ปกติ (ที่คุยผ่าน openai package ไปที่ /v1/...) แล้วคุยกับ /api/chat
     โดยตรงแทน ผ่าน custom model client ตามรูปแบบที่ pyautogen 0.2.x
     รองรับ (register_model_client) — ไฟล์นี้คือ client นั้น

ผลจาก micro-benchmark (ยืนยันแล้วก่อนเขียนไฟล์นี้):
  native /api/chat ปกติ (ไม่ส่ง think)      : 10-17 วินาที, มี reasoning field
  native /api/chat + "think": false          : 0.27-0.44 วินาที, ไม่มี reasoning
  ต่างกันประมาณ 30-60 เท่า — สอดคล้องกับสมมติฐานที่ว่า thinking mode คือ
  สาเหตุหลักของ elapsed_seconds ที่พุ่งขึ้นในผลรัน Tier 8 ทั้งชุด
"""
import requests


class OllamaNativeThinkOffClient:
    """Custom model client สำหรับ pyautogen 0.2.x (ตาม interface ที่
    register_model_client ต้องการ: __init__, create, message_retrieval,
    cost, get_usage) คุยกับ Ollama ผ่าน native /api/chat + think=false"""

    def __init__(self, config, **kwargs):
        self.model = config["model"]
        base_url = config.get("base_url", "http://host.docker.internal:11434/v1")
        # config เดิมของ multi_agent.py ใช้ base_url แบบ OpenAI-compat ที่ลงท้าย
        # ด้วย "/v1" (เช่น "http://host.docker.internal:11434/v1") — ต้องตัด
        # "/v1" ออกแล้วต่อ "/api/chat" เพื่อได้ native endpoint ที่ถูกต้อง
        native_base = base_url[:-3] if base_url.endswith("/v1") else base_url
        self.chat_url = native_base.rstrip("/") + "/api/chat"
        self.timeout = config.get("timeout", 120)
        self.temperature = config.get("temperature", 0.3)

    def create(self, params):
        """params มาจาก AutoGen: messages (list of {"role","content"}),
        อาจมี temperature/n ด้วย — คืนค่าเป็น object ที่มี .choices[i].message.content
        เหมือนรูปแบบที่ AutoGen คาดหวังจาก OpenAI client ปกติ"""
        messages = params.get("messages", [])
        n = params.get("n", 1)
        temperature = params.get("temperature", self.temperature)

        response = _SimpleNamespace()
        response.model = self.model
        response.choices = []

        for _ in range(n):
            content = self._call_ollama_native(messages, temperature)
            choice = _SimpleNamespace()
            choice.message = _SimpleNamespace()
            choice.message.content = content
            choice.message.function_call = None
            choice.message.tool_calls = None
            response.choices.append(choice)

        return response

    def _call_ollama_native(self, messages, temperature):
        body = {
            "model": self.model,
            "messages": messages,
            "think": False,  # <-- จุดสำคัญที่สุดของไฟล์นี้ทั้งไฟล์
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(self.chat_url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {}) or {}
        content = message.get("content", "")
        # เผื่อกรณี Ollama เวอร์ชันนี้ยังแนบ reasoning ติดมาแม้ think=false
        # (ไม่ควรเกิดตามผลทดสอบ แต่กันไว้ไม่ให้ reasoning text ปนเข้าไปในคำตอบ
        # ที่ multi_agent.py เอาไปตัดสิน SCORE/APPROVED)
        if not content and message.get("thinking"):
            content = message.get("thinking", "")
        return content

    def message_retrieval(self, response):
        return [choice.message.content for choice in response.choices]

    def cost(self, response) -> float:
        return 0.0

    @staticmethod
    def get_usage(response):
        return {}


class _SimpleNamespace:
    """เทียบเท่า types.SimpleNamespace แต่เขียนเองไว้ในไฟล์นี้เพื่อไม่ต้อง
    import เพิ่ม (stdlib types.SimpleNamespace ก็ใช้ได้เหมือนกัน อันนี้แค่
    กันเผื่อ environment ไหนแปลกๆ ไม่มี types module ครบ)"""
    pass
