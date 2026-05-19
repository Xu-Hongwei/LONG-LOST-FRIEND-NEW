from __future__ import annotations

import json
import math
from typing import Any

from .schemas import MemoryItem
from .storage import Storage


class MemoryService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def row_to_memory(self, row: Any) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            memory_type=row["memory_type"],
            memory_scope=row["memory_scope"] or "session",
            content=row["content"],
            confidence=float(row["confidence"] or 0),
            importance=float(row["importance"] or 0.5),
            source_message_id=row["source_message_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_memories(self, session_id: str) -> list[MemoryItem]:
        session = self.storage.get_session(session_id)
        if not session:
            return []
        return [
            self.row_to_memory(row)
            for row in self.storage.list_memories(session["visitor_id"], session["character_id"], session_id)
        ]

    def recall(
        self,
        session_id: str,
        user_message: str,
        limit: int = 8,
        query_vector: list[float] | None = None,
        embedding_provider: str | None = None,
    ) -> list[MemoryItem]:
        session = self.storage.get_session(session_id)
        if not session:
            return []
        profile_rows = self.storage.profile_memories(session["visitor_id"], session["character_id"], session_id, 10)
        recall_rows = self.storage.search_memories(
            session["visitor_id"],
            session["character_id"],
            session_id,
            user_message,
            limit,
        )
        semantic_rows = []
        semantic_scores: dict[str, float] = {}
        if query_vector and embedding_provider:
            semantic_rows = self.storage.vector_memory_candidates(
                session["visitor_id"],
                session["character_id"],
                session_id,
                embedding_provider,
            )
            semantic_scores = self._semantic_scores(semantic_rows, query_vector)
            semantic_rows = [row for row in semantic_rows if semantic_scores.get(row["id"], 0) >= 0.18]
        memories = self._dedupe([self.row_to_memory(row) for row in [*profile_rows, *recall_rows, *semantic_rows]])
        return self._rank_hybrid(memories, user_message, semantic_scores)[:limit]

    def add_extracted(
        self,
        visitor_id: str,
        session_id: str,
        character_id: str,
        source_message_id: str,
        extracted: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        stored: list[tuple[str, str]] = []
        for item in extracted:
            content = str(item.get("content") or "").strip()
            memory_type = str(item.get("memory_type") or "").strip()
            if not content or not memory_type:
                continue
            confidence = float(item.get("confidence") or 0.6)
            importance = float(item.get("importance") or 0.5)
            memory_id = self.storage.add_memory(
                visitor_id,
                session_id,
                character_id,
                memory_type,
                content,
                confidence,
                source_message_id,
                importance,
            )
            if memory_id:
                stored.append((memory_id, content))
        return stored

    def store_embeddings(self, memory_records: list[tuple[str, str]], vectors: list[list[float]], provider: str | None) -> None:
        if not provider:
            return
        for (memory_id, _), vector in zip(memory_records, vectors):
            self.storage.upsert_embedding("memory", memory_id, provider, vector)

    def build_pane(self, session_id: str, last_recall: list[MemoryItem] | None = None) -> dict[str, Any]:
        session = self.storage.get_session(session_id)
        memories = self.list_memories(session_id)
        diagnostics = {}
        if session:
            try:
                diagnostics = json.loads(session["postprocess_diagnostics_json"] or "{}")
            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                diagnostics = {}
        return {
            "session_id": session_id,
            "frozen": bool(session["frozen"]) if session else False,
            "manual_note": session["manual_note"] if session else "",
            "summary": session["recent_summary"] if session else "",
            "memories": [item.model_dump() for item in memories],
            "last_recall": [item.model_dump() for item in (last_recall or [])],
            "prompt_slots": json.loads(session["last_prompt_slots"] or "[]") if session else [],
            "diagnostics": diagnostics,
        }

    def update_recent_summary(self, session_id: str) -> str:
        messages = self.storage.recent_messages(session_id, 10)
        if not messages:
            return ""
        lines = []
        for item in messages[-6:]:
            role = "用户" if item["role"] == "user" else "角色"
            lines.append(f"{role}: {item['content'][:80]}")
        summary = "最近对话摘要：" + " / ".join(lines)
        self.storage.set_summary(session_id, summary)
        return summary

    def _rank_hybrid(
        self,
        memories: list[MemoryItem],
        query: str,
        semantic_scores: dict[str, float] | None = None,
    ) -> list[MemoryItem]:
        compact = set(self._terms(query))
        semantic_scores = semantic_scores or {}

        def score(item: MemoryItem) -> float:
            content_terms = set(self._terms(item.content))
            overlap = len(compact & content_terms)
            type_boost = {
                "stable_user_info": 4,
                "user_preference": 3,
                "relationship_progress": 2,
                "open_thread": 2,
                "recent_emotion": 1,
            }.get(item.memory_type, 0)
            scope_boost = {"global": 3, "character": 2, "session": 1}.get(item.memory_scope, 0)
            semantic = semantic_scores.get(item.id, 0.0)
            return (
                semantic * 12
                + overlap * 10
                + type_boost
                + scope_boost
                + item.importance * 4
                + item.confidence * 2
            )

        return sorted(memories, key=score, reverse=True)

    def _semantic_scores(self, rows: list[Any], query_vector: list[float]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for row in rows:
            try:
                vector = json.loads(row["vector_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            score = self._cosine(query_vector, vector)
            if score > 0:
                scores[row["id"]] = score
        return scores

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _dedupe(self, memories: list[MemoryItem]) -> list[MemoryItem]:
        seen: set[str] = set()
        result: list[MemoryItem] = []
        for item in memories:
            key = f"{item.memory_scope}:{item.memory_type}:{item.content}"
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _terms(self, text: str) -> list[str]:
        text = (text or "").strip().lower()
        pieces = [part for part in text.replace("，", " ").replace("。", " ").replace("？", " ").split() if len(part) >= 2]
        if pieces:
            return pieces
        return [text[i : i + 2] for i in range(max(0, len(text) - 1)) if text[i : i + 2].strip()]
