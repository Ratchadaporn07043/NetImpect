"""
ทดสอบว่า:
1. Container คุยกับ Ollama บน macOS host ได้ (ผ่าน host.docker.internal:11434)
2. AutoGen เรียกโมเดล Qwen3 (local) ผ่าน OpenAI-compatible endpoint ของ Ollama ได้

รันจากใน container:
    python3 scripts/test_connection.py
"""
import os
import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
OLLAMA_ROOT = OLLAMA_BASE_URL.replace("/v1", "")


def test_ollama_reachable():
    print(f"[1/2] เช็คว่า Ollama server ตอบสนองที่ {OLLAMA_ROOT} ...")
    resp = requests.get(f"{OLLAMA_ROOT}/api/tags", timeout=5)
    resp.raise_for_status()
    models = [m["name"] for m in resp.json().get("models", [])]
    print("    เชื่อมต่อสำเร็จ, โมเดลที่มีอยู่:", models)
    return models


def test_autogen_chat(model_name: str):
    print(f"[2/2] ทดสอบเรียก {model_name} ผ่าน AutoGen ...")
    from autogen import ConversableAgent

    config_list = [
        {
            "model": model_name,
            "base_url": OLLAMA_BASE_URL,
            "api_key": "ollama",  # ไม่ใช้จริง แต่ AutoGen ต้องการ field นี้
        }
    ]

    agent = ConversableAgent(
        name="test_agent",
        llm_config={"config_list": config_list, "temperature": 0},
        human_input_mode="NEVER",
    )

    reply = agent.generate_reply(
        messages=[{"role": "user", "content": "ตอบสั้นๆ ว่า 'ระบบพร้อมทำงาน'"}]
    )
    print("    ตอบกลับจากโมเดล:", reply)


if __name__ == "__main__":
    models = test_ollama_reachable()
    if not models:
        print("!! ยังไม่มีโมเดลถูก pull เข้ามาใน Ollama เลย รัน `ollama pull qwen3:8b` บน host ก่อน")
    else:
        # ใช้โมเดลตัวแรกที่เจอในการทดสอบ (ปรับชื่อให้ตรงกับที่ pull ไว้จริง เช่น qwen3:8b)
        test_autogen_chat(models[0])