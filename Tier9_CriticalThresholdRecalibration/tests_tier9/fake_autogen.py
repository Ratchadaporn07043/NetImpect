"""
fake_autogen.py — stub เลียนแบบ pyautogen สำหรับ unit test ของ Tier9_CriticalThresholdRecalibration
================================================================================
สำเนาจาก Tier8_EnsureScopeClosure/tests_tier8/fake_autogen.py เพิ่มเพียงจุดเดียว:
`register_model_client()` เป็น no-op บน ConversableAgent และ GroupChatManager
(Tier 9's multi_agent.py เรียกเมธอดนี้จริงตอน build_agents()/_attempt_once()
เพื่อผูก OllamaNativeThinkOffClient — fake ตัวนี้ต้องมีเมธอดนี้ไว้ ไม่งั้นเทส
จะพังด้วย AttributeError ทันทีที่ import multi_agent.py ของ Tier 9)

เป้าหมาย: ทดสอบ logic ของ multi_agent.py (การนับ round, การ parse score, retry/
timeout handling, mitigation dispatch, agent-blame, และตอนนี้รวม "ผูก custom
client ให้ครบทุก agent/manager จริงไหม") โดยไม่ต้องมี Ollama/GPU/โมเดลจริงรันอยู่เลย

วิธีใช้ (จาก conftest.py):
    sys.modules["autogen"] = fake_autogen

ควบคุมบทสนทนาจำลองผ่าน set_script(agent_name, list_of_replies):
    set_script("Reviewer", ["REVISE เหตุผล...\\nSCORE: 2", "APPROVED ครบถ้วน\\nSCORE: 5"])

ถ้าไม่ได้ set_script ไว้ล่วงหน้า จะใช้ default: Reviewer ตอบ "APPROVED\\nSCORE: 5"
เสมอ (จบใน 1 รอบแบบ happy-path)

ถ้าอยากจำลอง exception (เช่น timeout) ให้ใส่ Exception instance ไว้ใน script list:
    set_script("Worker", [TimeoutError("simulated timeout")])
"""
from collections import deque

_SCRIPTS = {}
_DEFAULT_REPLIES = {
    "Planner": "1. ทำสิ่งนี้ 2. ทำสิ่งนั้น 3. สรุปผล",
    "Worker": "นี่คือคำตอบสุดท้ายของ Worker",
    "Reviewer": "APPROVED เหตุผลสั้นๆ\nSCORE: 5",
    "GroundTruthEvaluator": '{"score": 4, "passed": true, "missing_points": [], "rationale": "ok"}',
}

# TIER9: บันทึกไว้ว่า agent/manager ตัวไหนเรียก register_model_client() ไปแล้ว
# บ้าง ด้วยคลาสอะไร — ใช้ assert ในเทสว่าผูก client ครบทุกตัวจริง (ไม่ใช่แค่
# เขียนโค้ดไว้เฉยๆ แต่ลืมเรียกจริง)
REGISTERED_MODEL_CLIENTS = []


def reset_registered_model_clients():
    REGISTERED_MODEL_CLIENTS.clear()


def set_script(agent_name: str, replies: list):
    _SCRIPTS[agent_name] = deque(replies)


def reset_scripts():
    _SCRIPTS.clear()


def _next_reply(agent_name: str):
    script = _SCRIPTS.get(agent_name)
    if script:
        reply = script.popleft()
        if isinstance(reply, BaseException):
            raise reply
        return reply
    return _DEFAULT_REPLIES.get(agent_name, "ok")


class ConversableAgent:
    def __init__(self, name, system_message="", llm_config=None, human_input_mode="NEVER"):
        self.name = name
        self.system_message = system_message
        self.llm_config = llm_config
        self.human_input_mode = human_input_mode
        self._hooks = []

    def register_hook(self, hook_name, fn):
        self._hooks.append((hook_name, fn))

    def register_model_client(self, model_client_cls, **kwargs):
        """TIER9: no-op แต่บันทึกไว้ให้เทส assert ได้ว่าเรียกจริง"""
        REGISTERED_MODEL_CLIENTS.append((self.name, model_client_cls))

    def _fire_send_hooks(self, content):
        for hook_name, fn in self._hooks:
            if hook_name == "process_message_before_send":
                fn(self, content, None, False)

    def generate_reply(self, messages=None, sender=None):
        return _next_reply(self.name)

    def initiate_chat(self, manager, message):
        """จำลอง GroupChat round-robin แบบง่าย: self ส่งข้อความแรก แล้ววนถามทีละ
        agent ตามลำดับใน manager.groupchat.agents จนกว่า is_termination_msg()
        จะ True หรือครบ max_round"""
        groupchat = manager.groupchat
        self._fire_send_hooks(message)
        groupchat.messages.append({"name": self.name, "content": message})

        agents = groupchat.agents
        try:
            idx = agents.index(self)
        except ValueError:
            idx = -1

        rounds_done = 0
        while rounds_done < groupchat.max_round:
            idx = (idx + 1) % len(agents)
            speaker = agents[idx]
            reply = speaker.generate_reply()
            speaker._fire_send_hooks(reply)
            msg = {"name": speaker.name, "content": reply}
            groupchat.messages.append(msg)
            rounds_done += 1
            if manager.is_termination_msg is not None and manager.is_termination_msg(msg):
                break


class GroupChat:
    def __init__(self, agents, messages, max_round, speaker_selection_method="round_robin"):
        self.agents = list(agents)
        self.messages = messages if messages is not None else []
        self.max_round = max_round
        self.speaker_selection_method = speaker_selection_method


class GroupChatManager:
    def __init__(self, groupchat, llm_config=None, is_termination_msg=None):
        self.groupchat = groupchat
        self.llm_config = llm_config
        self.is_termination_msg = is_termination_msg
        self.name = "chat_manager"

    def register_model_client(self, model_client_cls, **kwargs):
        """TIER9: no-op แต่บันทึกไว้ให้เทส assert ได้ว่า manager ก็ถูกผูกด้วย
        (จุดที่ Tier 8's monkey-patch เดิมต้องใช้ subclass พิเศษเพื่อทำสิ่งนี้
        แต่ Tier 9 เขียนตรงๆ ใน _attempt_once() เลยได้)"""
        REGISTERED_MODEL_CLIENTS.append((self.name, model_client_cls))
