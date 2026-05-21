from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException

from ...llm import LlmClient
from ...schemas import MemoryItemPatchRequest, MemoryPaneResponse, MemoryPatchRequest
from ...storage import Storage
from .memory import MemoryService


class RelationshipService:
    def __init__(
        self,
        *,
        storage: Storage,
        memory: MemoryService,
        llm: LlmClient,
    ) -> None:
        self.storage = storage
        self.memory = memory
        self.llm = llm

    def get_memory(self, session_id: str) -> MemoryPaneResponse:
        self._require_session(session_id)
        return self._pane_response(session_id)

    async def wait_memory(
        self,
        session_id: str,
        user_message_id: str = "",
        timeout_seconds: float = 45.0,
    ) -> MemoryPaneResponse:
        deadline = time.perf_counter() + max(1.0, min(timeout_seconds, 90.0))
        terminal_statuses = {"succeeded", "failed", "skipped", "partial"}
        while True:
            pane = self.get_memory(session_id)
            diagnostics = pane.diagnostics or {}
            status = str(diagnostics.get("status") or "")
            diagnostic_message_id = str(diagnostics.get("user_message_id") or "")
            matches_message = not user_message_id or diagnostic_message_id == user_message_id
            if matches_message and status in terminal_statuses:
                return pane
            if time.perf_counter() >= deadline:
                return pane
            await asyncio.sleep(0.5)

    def patch_memory(self, session_id: str, payload: MemoryPatchRequest) -> MemoryPaneResponse:
        self._require_session(session_id)
        self.storage.update_session_memory(session_id, payload.frozen, payload.manual_note)
        return self._pane_response(session_id)

    async def patch_memory_item(
        self,
        session_id: str,
        memory_id: str,
        payload: MemoryItemPatchRequest,
    ) -> MemoryPaneResponse:
        session = self._require_session(session_id)
        updated = self.storage.update_memory_item(
            memory_id,
            session["visitor_id"],
            session["character_id"],
            session_id,
            payload.memory_type,
            payload.memory_scope,
            payload.content,
            payload.confidence,
            payload.importance,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Memory not found")
        if payload.content:
            vectors = await self.llm.embed_texts([payload.content])
            self.memory.store_embeddings(
                [(memory_id, payload.content)],
                vectors,
                self.llm.embedding_provider_name() if vectors else None,
            )
        return self._pane_response(session_id)

    def delete_memory_item(self, session_id: str, memory_id: str) -> MemoryPaneResponse:
        session = self._require_session(session_id)
        deleted = self.storage.delete_memory_item(memory_id, session["visitor_id"], session["character_id"], session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        return self._pane_response(session_id)

    def _require_session(self, session_id: str) -> dict[str, object]:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return dict(session)

    def _pane_response(self, session_id: str) -> MemoryPaneResponse:
        pane = self.memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=self.memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
            diagnostics=pane.get("diagnostics", {}),
        )
