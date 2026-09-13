from __future__ import annotations

import os
import tempfile
from typing import Protocol


class LLMProvider(Protocol):
    def generate(self, prompt: str, **kwargs) -> str: ...


class CursorComposerProvider:
    """One-shot Composer 2.5 via the official Cursor agent SDK."""

    def generate(self, prompt: str, **kwargs) -> str:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        sandbox = tempfile.mkdtemp(prefix="kryptolens-llm-")
        timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        options = AgentOptions(
            api_key=os.environ["CURSOR_API_KEY"],
            model=os.getenv("LLM_MODEL", "composer-2.5"),
            local=LocalAgentOptions(cwd=sandbox),
        )
        result = Agent.prompt(
            prompt
            + "\n\nReturn only the requested text or JSON. Do not use tools. Do not edit files.",
            options,
        )
        if getattr(result, "status", "ok") == "error":
            raise RuntimeError(f"Composer run failed: {getattr(result, 'id', '')}")
        text = getattr(result, "result", None) or getattr(result, "text", None)
        if text is None and hasattr(result, "wait"):
            waited = result.wait()
            text = getattr(waited, "result", None) or str(waited)
        if not text:
            raise RuntimeError("Composer returned empty output")
        return str(text)[:20000]


class OpenAICompatibleProvider:
    """Fallback HTTP chat-completions provider."""

    def generate(self, prompt: str, **kwargs) -> str:
        import httpx

        base = os.environ["LLM_BASE_URL"].rstrip("/")
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        response = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": "Return only the requested output."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class HeuristicProvider:
    """Offline compiler used when no LLM runtime is available."""

    def generate(self, prompt: str, **kwargs) -> str:
        from .compiler import HeuristicCompiler

        user = prompt.split("User intent:")[-1].strip()
        current = None
        if "Current policy JSON:" in prompt:
            import json

            from .policy import IntelligencePolicy

            blob = prompt.split("Current policy JSON:")[-1]
            start = blob.find("{")
            end = blob.rfind("}")
            if start != -1 and end != -1:
                current = IntelligencePolicy.model_validate(json.loads(blob[start : end + 1]))
        policy = HeuristicCompiler().compile(user, current_policy=current)
        return policy.model_dump_json()


def get_provider() -> LLMProvider:
    if os.getenv("CURSOR_API_KEY"):
        return CursorComposerProvider()
    if os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"):
        return OpenAICompatibleProvider()
    return HeuristicProvider()
