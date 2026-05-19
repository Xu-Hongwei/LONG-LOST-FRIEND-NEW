from __future__ import annotations

from typing import Any

import httpx


class LlmChatMixin:
    async def chat_complete(
        self,
        messages: list[dict[str, str]],
        timeout_ms: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        if not self.provider:
            raise RuntimeError("No remote LLM provider configured")
        body = {
            "model": self.provider["model"],
            "temperature": 0.82,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.provider['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = (timeout_ms or self.provider["timeout_ms"]) / 1000
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.provider['base_url'].rstrip('/')}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        self.last_chat_error = None
        return payload["choices"][0]["message"]["content"].strip()
