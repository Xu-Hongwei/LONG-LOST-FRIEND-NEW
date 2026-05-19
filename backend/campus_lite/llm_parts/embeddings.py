from __future__ import annotations

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class LlmEmbeddingMixin:
    def embedding_configured(self) -> bool:
        return self.embedding_provider is not None

    def embedding_provider_name(self) -> str | None:
        if not self.embedding_provider:
            return None
        return f"{self.embedding_provider['name']}:{self.embedding_provider['model']}"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.strip() for text in texts if text and text.strip()]
        if not clean_texts:
            self.last_embedding_error = None
            return []
        if not self.embedding_provider:
            self.last_embedding_error = "not_configured"
            return []
        body = {
            "model": self.embedding_provider["model"],
            "input": clean_texts,
        }
        headers = {
            "Authorization": f"Bearer {self.embedding_provider['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = self.embedding_provider["timeout_ms"] / 1000
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.embedding_provider['base_url'].rstrip('/')}/embeddings",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
            payload = response.json()
            vectors = [item["embedding"] for item in sorted(payload.get("data", []), key=lambda item: item.get("index", 0))]
            self.last_embedding_error = None
            return [[float(value) for value in vector] for vector in vectors]
        except Exception as exc:
            self.last_embedding_error = type(exc).__name__
            logger.warning("embedding failed: %s", exc)
            return []
