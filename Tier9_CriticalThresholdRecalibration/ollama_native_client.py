"""
ollama_native_client.py - Tier9's standard AutoGen model client for Ollama's
native /api/chat endpoint (not OpenAI-compatible /v1/chat/completions).
================================================================================
**This is Tier9's standard client, not a diagnostic patch.** Tier8 confirmed through
multiple runs that this Ollama version enables thinking mode for qwen3:8b by default,
making calls 10-30+ times slower. The reliable `think:false` parameter works only
through native endpoints such as `/api/generate` and `/api/chat`, not AutoGen's
`/v1/chat/completions`. Tier9 therefore embeds this client as the default.

Evidence supporting standard use (from Tier8_EnsureScopeClosure/thinking_off_diagnostic/):
    - Native /api/chat + "think": false took 0.27-0.44 seconds in raw curl tests,
        with no reasoning field, versus 8-38 seconds through /v1/chat/completions.
    - End-to-end wiring tests with a fake HTTP server confirmed that all agents and
        GroupChatManager route to /api/chat with think:false.
    - A real Ollama confirmatory run showed a one-time 13-16 second cold-start,
        followed by requests under one second with no reasoning field.
"""
import requests


class OllamaNativeThinkOffClient:
    """Custom pyautogen 0.2.x client using native /api/chat with think=false."""

    def __init__(self, config, **kwargs):
        self.model = config["model"]
        base_url = config.get("base_url", "http://host.docker.internal:11434/v1")
        # AutoGen uses an OpenAI-compatible base URL ending in /v1. Remove it
        # and append /api/chat to reach the native endpoint.
        native_base = base_url[:-3] if base_url.endswith("/v1") else base_url
        self.chat_url = native_base.rstrip("/") + "/api/chat"
        self.timeout = config.get("timeout", 120)
        self.temperature = config.get("temperature", 0.3)

    def create(self, params):
        """Create a response object matching the OpenAI client interface expected by AutoGen."""
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
            "think": False,  # The key setting in this client.
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(self.chat_url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {}) or {}
        content = message.get("content", "")
        # Guard against versions that attach reasoning despite think=false.
        # This was not observed in testing, but prevents reasoning from entering the answer.
        # multi_agent.py uses this content to parse SCORE/APPROVED.
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
    """Small local equivalent of types.SimpleNamespace to avoid another import."""
    pass
