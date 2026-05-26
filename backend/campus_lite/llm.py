from __future__ import annotations

from .llm_parts.analysis import LlmAnalysisMixin
from .llm_parts.chat import LlmChatMixin
from .llm_parts.embeddings import LlmEmbeddingMixin
from .llm_parts.mock import LlmMockMixin
from .llm_parts.parsing import LlmParsingMixin
from .llm_parts.prompts import LlmPromptMixin
from .llm_parts.providers import LlmProviderMixin


class LlmClient(
    LlmProviderMixin,
    LlmPromptMixin,
    LlmChatMixin,
    LlmAnalysisMixin,
    LlmEmbeddingMixin,
    LlmMockMixin,
    LlmParsingMixin,
):
    def __init__(self) -> None:
        self.provider = self._select_provider()
        self.embedding_provider = self._select_embedding_provider()
        self.last_chat_error: str | None = None
        self.last_analysis_error: str | None = None
        self.last_character_draft_diagnostics: dict[str, object] = {}
        self.last_embedding_error: str | None = None
