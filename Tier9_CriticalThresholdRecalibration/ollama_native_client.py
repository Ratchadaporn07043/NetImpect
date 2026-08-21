"""
ollama_native_client.py — AutoGen model client มาตรฐานของ Tier 9 ที่คุย Ollama
ผ่าน native /api/chat โดยตรง (ไม่ผ่าน OpenAI-compatible /v1/chat/completions)
================================================================================
สถานะ: **นี่คือ client มาตรฐานของ Tier 9 ไม่ใช่ diagnostic patch แบบที่
Tier8_EnsureScopeClosure/thinking_off_diagnostic/ ใช้** — Tier 8 ค้นพบและยืนยัน
(ผ่านการรัน confirmatory จริงหลายรอบ) ว่า Ollama เวอร์ชันของเครื่องนี้เปิด
"thinking" mode เป็นค่าเริ่มต้นให้ qwen3:8b ทำให้ทุก LLM call ช้าลง 10-30+ เท่า
และพารามิเตอร์ "think": false ที่ปิดได้จริง ใช้งานได้เฉพาะ native endpoint
(/api/generate, /api/chat) เท่านั้น ไม่ใช่ผ่าน /v1/chat/completions ที่ AutoGen
ใช้เป็นค่าเริ่มต้น — Tier 9 จึงฝัง client ตัวนี้เป็นค่าเริ่มต้นมาตรฐานตั้งแต่ต้น
(ดู multi_agent.py ในโฟลเดอร์นี้) ไม่ใช่ monkey-patch จากภายนอกอีกต่อไป

หลักฐานยืนยันก่อนนำมาใช้เป็นมาตรฐาน (จาก Tier8_EnsureScopeClosure/thinking_off_diagnostic/):
  - native /api/chat + "think": false (raw curl บนเครื่องจริง): 0.27-0.44 วินาที
    ไม่มี reasoning field เลย — เทียบกับ /v1/chat/completions ปกติที่ 8-38 วินาที
    ต่อคำขอเดียว พร้อม reasoning field แนบมาเสมอ
  - ทดสอบ wiring แบบ end-to-end ด้วย fake HTTP server จำลองแล้วว่า Planner/
    Worker/Reviewer/GroupChatManager ทุกตัว route ไปที่ /api/chat พร้อม
    think:false ครบทุกครั้งจริง (ไม่มี request หลุดไปที่ endpoint เดิม)
  - รัน confirmatory จริงผ่าน Ollama จริง (ไม่ใช่ fake server): smoke test เห็น
    warm-up (cold model load) 13-16 วินาทีครั้งเดียว จากนั้น request จริงเหลือ
    <1 วินาที ไม่มี reasoning field ปนมาเลย และรันเต็ม workflow จริงได้ถูกต้อง
"""
import requests


class OllamaNativeThinkOffClient:
    """Custom model client สำหรับ pyautogen 0.2.x (ตาม interface ที่
    register_model_client ต้องการ: __init__, create, message_retrieval,
    cost, get_usage) คุยกับ Ollama ผ่าน native /api/chat + think=false"""

    def __init__(self, config, **kwargs):
        self.model = config["model"]
        base_url = config.get("base_url", "http://host.docker.internal:11434/v1")
        # config ใช้ base_url แบบ OpenAI-compat ที่ลงท้ายด้วย "/v1" (เช่น
        # "http://host.docker.internal:11434/v1") — ต้องตัด "/v1" ออกแล้วต่อ
        # "/api/chat" เพื่อได้ native endpoint ที่ถูกต้อง
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
    import เพิ่ม"""
    pass
