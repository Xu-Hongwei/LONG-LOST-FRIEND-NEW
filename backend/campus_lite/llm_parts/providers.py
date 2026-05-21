from __future__ import annotations

import os
from typing import Any


class LlmProviderMixin:
    def configured(self) -> bool:
        return self.provider is not None

    def provider_name(self) -> str | None:
        if not self.provider:
            return None
        return self.provider["name"]

    def _select_provider(self) -> dict[str, Any] | None:
        configs = [
            {
                "name": "router",
                "api_key": os.getenv("LLM_ROUTER_API_KEY"),
                "base_url": os.getenv("LLM_ROUTER_BASE_URL") or "",
                "model": os.getenv("LLM_ROUTER_MODEL") or "auto",
                "timeout_ms": int(os.getenv("LLM_ROUTER_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "dashscope",
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "base_url": os.getenv("DASHSCOPE_BASE_URL") or os.getenv("DASHSCOPE_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": os.getenv("DASHSCOPE_MODEL") or "qwen-plus-character",
                "timeout_ms": int(os.getenv("DASHSCOPE_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "deepseek",
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com",
                "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
                "timeout_ms": int(os.getenv("DEEPSEEK_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "ark",
                "api_key": os.getenv("ARK_API_KEY"),
                "base_url": os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3",
                "model": os.getenv("ARK_MODEL") or "",
                "timeout_ms": int(os.getenv("ARK_TIMEOUT_MS") or "12000"),
            },
        ]
        for config in configs:
            if config["api_key"] and config["base_url"] and config["model"]:
                return config
        return None

    def _select_embedding_provider(self) -> dict[str, Any] | None:
        configs = [
            {
                "name": "router",
                "api_key": os.getenv("LLM_ROUTER_EMBEDDING_API_KEY") or os.getenv("LLM_ROUTER_API_KEY"),
                "base_url": os.getenv("LLM_ROUTER_EMBEDDING_BASE_URL") or os.getenv("LLM_ROUTER_BASE_URL") or "",
                "model": os.getenv("LLM_ROUTER_EMBEDDING_MODEL") or "",
                "timeout_ms": int(os.getenv("LLM_ROUTER_EMBEDDING_TIMEOUT_MS") or os.getenv("LLM_ROUTER_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "dashscope",
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "base_url": os.getenv("DASHSCOPE_EMBEDDING_BASE_URL")
                or os.getenv("DASHSCOPE_BASE_URL")
                or os.getenv("DASHSCOPE_BASE")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": os.getenv("DASHSCOPE_EMBEDDING_MODEL") or "text-embedding-v4",
                "timeout_ms": int(os.getenv("DASHSCOPE_EMBEDDING_TIMEOUT_MS") or os.getenv("DASHSCOPE_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "ark",
                "api_key": os.getenv("ARK_API_KEY"),
                "base_url": os.getenv("ARK_EMBEDDING_BASE_URL") or os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3",
                "model": os.getenv("ARK_EMBEDDING_MODEL") or "",
                "timeout_ms": int(os.getenv("ARK_EMBEDDING_TIMEOUT_MS") or os.getenv("ARK_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "deepseek",
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": os.getenv("DEEPSEEK_EMBEDDING_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com",
                "model": os.getenv("DEEPSEEK_EMBEDDING_MODEL") or "",
                "timeout_ms": int(os.getenv("DEEPSEEK_EMBEDDING_TIMEOUT_MS") or os.getenv("DEEPSEEK_TIMEOUT_MS") or "12000"),
            },
        ]
        for config in configs:
            if config["api_key"] and config["model"]:
                return config
        return None
