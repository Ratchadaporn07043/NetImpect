"""
fake_autogen.py — stub เลียนแบบ pyautogen สำหรับ unit test
================================================================
เป้าหมาย: ทดสอบ logic ของ multi_agent.py (การนับ round, การ parse score,
retry/timeout handling, mitigation dispatch ฯลฯ) โดย "ไม่ต้อง" มี Ollama/GPU/
โมเดลจริงรันอยู่เลย — เร็ว, deterministic, รันได้ทุกเครื่อง (CI ก็รันได้)

วิธีใช้ (จาก conftest.py):
    sys.modules["autogen"] = fake_autogen
    # ก่อน import multi_agent.py ตัวไหนก็ตาม (from autogen import ... จะได้ stub นี้แทน)

ควบคุมบทสนทนาจำลองผ่าน set_script(agent_name, list_of_replies):
    set_script("Reviewer", ["REVISE เหตุผล...\nSCORE: 2", "APPROVED ครบถ้วน\nSCORE: 5"])
    # ครั้งแรกที่ Reviewer ถูกถาม -> ตอบ REVISE, ครั้งที่สอง -> ตอบ APPROVED

ถ้าไม่ได้ set_script ไว้ล่วงหน้า จะใช้ default: Reviewer ตอบ "APPROVED\nSCORE: 5"
เสมอ (จบใน 1 รอบแบบ happy-path), Planner/Worker ตอบข้อความ placeholder เฉยๆ

ถ้าอยากจำลอง exception (เช่น timeout) ให้ใส่ Exception instance ไว้ใน script list
ตรงตำแหน่งที่ต้องการให้ raise:
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


def set_script(agent_name: str, replies: list):
    """ตั้ง script คำตอบของ agent ชื่อ agent_name (เรียงตามลำดับที่จะถูกถาม)"""
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

    def _fire_send_hooks(self, content):
        for hook_name, fn in self._hooks:
            if hook_name == "process_message_before_send":
                fn(self, content, None, False)

    def generate_reply(self, messages=None, sender=None):
        """ใช้โดย evaluator._llm_evaluate (GroundTruthEvaluator ไม่ผ่าน GroupChat)"""
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
            reply = speaker.generate_reply()  # อาจ raise exception ถ้า script ตั้งไว้แบบนั้น
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
