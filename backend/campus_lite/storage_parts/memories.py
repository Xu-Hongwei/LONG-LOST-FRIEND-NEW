from __future__ import annotations

import json
import re
import sqlite3
import uuid


class MemoryStorageMixin:
    def _normalize_memory_key(self, text: str) -> str:
        compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())
        return compact[:160] or uuid.uuid4().hex

    def _memory_scope(self, memory_type: str) -> str:
        if memory_type in {"stable_user_info", "user_preference"}:
            return "global"
        if memory_type == "relationship_progress":
            return "character"
        return "session"

    def memory_visible_in_session(self, memory_id: str, visitor_id: str, character_id: str, session_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE id = ?
                  AND {self._memory_scope_where()}
                LIMIT 1
                """,
                (memory_id, visitor_id, character_id, session_id, session_id),
            ).fetchone()

    def add_memory(
        self,
        visitor_id: str,
        session_id: str,
        character_id: str,
        memory_type: str,
        content: str,
        confidence: float,
        source_message_id: str | None,
        importance: float = 0.5,
    ) -> str | None:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        memory_scope = self._memory_scope(memory_type)
        normalized_key = self._normalize_memory_key(content)
        with self.connect() as conn:
            existing = self._find_existing_memory(
                conn,
                visitor_id,
                session_id,
                character_id,
                memory_scope,
                memory_type,
                normalized_key,
                content,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE memories SET
                        content = ?,
                        confidence = max(confidence, ?),
                        importance = max(importance, ?),
                        source_message_id = coalesce(?, source_message_id),
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (content, confidence, importance, source_message_id, existing["id"]),
                )
                row = conn.execute("SELECT id FROM memories WHERE id = ?", (existing["id"],)).fetchone()
            else:
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, visitor_id, session_id, character_id, memory_type, memory_scope,
                        content, confidence, importance, normalized_key, source_message_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        visitor_id,
                        session_id,
                        character_id,
                        memory_type,
                        memory_scope,
                        content,
                        confidence,
                        importance,
                        normalized_key,
                        source_message_id,
                    ),
                )
                row = conn.execute("SELECT id FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row:
                conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (row["id"],))
                conn.execute(
                    "INSERT INTO memory_fts (content, memory_id, session_id, visitor_id) VALUES (?, ?, ?, ?)",
                    (content, row["id"], session_id, visitor_id),
                )
                return str(row["id"])
        return None

    def upsert_embedding(self, owner_type: str, owner_id: str, provider: str, vector: list[float]) -> None:
        if not vector:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (id, owner_type, owner_id, provider, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(owner_type, owner_id, provider) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    created_at = datetime('now')
                """,
                (
                    f"emb_{uuid.uuid4().hex[:12]}",
                    owner_type,
                    owner_id,
                    provider,
                    json.dumps(vector),
                ),
            )

    def vector_memory_candidates(
        self,
        visitor_id: str,
        character_id: str,
        session_id: str,
        provider: str,
        limit: int = 200,
    ) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT memories.*, embeddings.vector_json
                FROM memories
                JOIN embeddings
                  ON embeddings.owner_type = 'memory'
                 AND embeddings.owner_id = memories.id
                 AND embeddings.provider = ?
                WHERE {self._memory_scope_where()}
                ORDER BY memories.importance DESC, memories.confidence DESC, memories.updated_at DESC
                LIMIT ?
                """,
                (provider, visitor_id, character_id, session_id, session_id, limit),
            ).fetchall()

    def update_memory_item(
        self,
        memory_id: str,
        visitor_id: str,
        character_id: str,
        session_id: str,
        memory_type: str | None = None,
        memory_scope: str | None = None,
        content: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
    ) -> bool:
        existing = self.memory_visible_in_session(memory_id, visitor_id, character_id, session_id)
        if not existing:
            return False
        next_content = (content if content is not None else existing["content"]).strip()
        next_type = memory_type or existing["memory_type"]
        next_scope = memory_scope or existing["memory_scope"] or self._memory_scope(next_type)
        next_confidence = max(0.0, min(1.0, float(confidence if confidence is not None else existing["confidence"] or 0)))
        next_importance = max(0.0, min(1.0, float(importance if importance is not None else existing["importance"] or 0.5)))
        if not next_content:
            return False
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE memories SET
                    memory_type = ?,
                    memory_scope = ?,
                    content = ?,
                    confidence = ?,
                    importance = ?,
                    normalized_key = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    next_type,
                    next_scope,
                    next_content[:280],
                    next_confidence,
                    next_importance,
                    self._normalize_memory_key(next_content),
                    memory_id,
                ),
            )
            conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            conn.execute(
                "INSERT INTO memory_fts (content, memory_id, session_id, visitor_id) VALUES (?, ?, ?, ?)",
                (next_content[:280], memory_id, session_id, visitor_id),
            )
        return True

    def delete_memory_item(self, memory_id: str, visitor_id: str, character_id: str, session_id: str) -> bool:
        existing = self.memory_visible_in_session(memory_id, visitor_id, character_id, session_id)
        if not existing:
            return False
        with self.connect() as conn:
            conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            conn.execute("DELETE FROM embeddings WHERE owner_type = 'memory' AND owner_id = ?", (memory_id,))
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return True

    def _find_existing_memory(
        self,
        conn: sqlite3.Connection,
        visitor_id: str,
        session_id: str,
        character_id: str,
        memory_scope: str,
        memory_type: str,
        normalized_key: str,
        content: str,
    ) -> sqlite3.Row | None:
        if memory_scope == "global":
            return conn.execute(
                """
                SELECT id FROM memories
                WHERE visitor_id = ? AND memory_scope = 'global'
                  AND memory_type = ? AND normalized_key = ?
                LIMIT 1
                """,
                (visitor_id, memory_type, normalized_key),
            ).fetchone()
        if memory_scope == "character":
            return conn.execute(
                """
                SELECT id FROM memories
                WHERE visitor_id = ? AND character_id = ? AND memory_scope = 'character'
                  AND memory_type = ? AND normalized_key = ?
                LIMIT 1
                """,
                (visitor_id, character_id, memory_type, normalized_key),
            ).fetchone()
        return conn.execute(
            """
            SELECT id FROM memories
            WHERE session_id = ? AND memory_type = ?
              AND (normalized_key = ? OR content = ?)
            LIMIT 1
            """,
            (session_id, memory_type, normalized_key, content),
        ).fetchone()

    def _memory_scope_where(self) -> str:
        return """
            visitor_id = ? AND (
                memory_scope = 'global'
                OR (memory_scope = 'character' AND character_id = ?)
                OR (memory_scope = 'session' AND session_id = ?)
                OR (memory_scope = '' AND session_id = ?)
            )
        """

    def list_memories(self, visitor_id: str, character_id: str, session_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                ORDER BY
                    CASE memory_scope
                        WHEN 'global' THEN 0
                        WHEN 'character' THEN 1
                        WHEN 'session' THEN 2
                        ELSE 3
                    END,
                    CASE memory_type
                        WHEN 'stable_user_info' THEN 0
                        WHEN 'user_preference' THEN 1
                        WHEN 'relationship_progress' THEN 2
                        WHEN 'open_thread' THEN 3
                        WHEN 'recent_emotion' THEN 4
                        ELSE 5
                    END,
                    importance DESC,
                    updated_at DESC
                """,
                (visitor_id, character_id, session_id, session_id),
            ).fetchall()

    def profile_memories(self, visitor_id: str, character_id: str, session_id: str, limit: int = 12) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                  AND memory_type IN ('stable_user_info', 'user_preference', 'relationship_progress')
                ORDER BY
                    CASE memory_scope
                        WHEN 'global' THEN 0
                        WHEN 'character' THEN 1
                        ELSE 2
                    END,
                    importance DESC,
                    confidence DESC,
                    updated_at DESC
                LIMIT ?
                """,
                (visitor_id, character_id, session_id, session_id, limit),
            ).fetchall()

    def search_memories(self, visitor_id: str, character_id: str, session_id: str, query: str, limit: int = 8) -> list[sqlite3.Row]:
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query)
        terms = " ".join(part for part in cleaned.split() if len(part) >= 2)
        with self.connect() as conn:
            if terms:
                try:
                    rows = conn.execute(
                        f"""
                        SELECT memories.* FROM memory_fts
                        JOIN memories ON memories.id = memory_fts.memory_id
                        WHERE memory_fts MATCH ?
                          AND memories.visitor_id = ? AND (
                            memories.memory_scope = 'global'
                            OR (memories.memory_scope = 'character' AND memories.character_id = ?)
                            OR (memories.memory_scope = 'session' AND memories.session_id = ?)
                            OR (memories.memory_scope = '' AND memories.session_id = ?)
                          )
                        ORDER BY memories.importance DESC, memories.confidence DESC, memories.updated_at DESC
                        LIMIT ?
                        """,
                        (terms, visitor_id, character_id, session_id, session_id, limit),
                    ).fetchall()
                    if rows:
                        return rows
                except sqlite3.Error:
                    pass
            candidates = conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                ORDER BY importance DESC, confidence DESC, updated_at DESC
                """,
                (visitor_id, character_id, session_id, session_id),
            ).fetchall()
        return self._rank_text_memory_candidates(query, candidates, limit)

    def _rank_text_memory_candidates(self, query: str, rows: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
        query_terms = set(self._memory_relevance_terms(query))
        if not query_terms:
            return []
        scored: list[tuple[float, sqlite3.Row]] = []
        query_compact = self._normalize_memory_key(query)
        for row in rows:
            content = str(row["content"] or "")
            content_terms = set(self._memory_relevance_terms(content))
            overlap = len(query_terms & content_terms)
            compact = self._normalize_memory_key(content)
            substring_boost = 2 if query_compact and (query_compact in compact or compact in query_compact) else 0
            score = overlap + substring_boost
            if score <= 0:
                continue
            score += float(row["importance"] or 0) * 0.4 + float(row["confidence"] or 0) * 0.2
            scored.append((score, row))
        scored.sort(key=lambda item: (item[0], float(item[1]["importance"] or 0), float(item[1]["confidence"] or 0), str(item[1]["updated_at"] or "")), reverse=True)
        return [row for _, row in scored[:limit]]

    def _memory_relevance_terms(self, text: str) -> list[str]:
        stop_terms = {"用户", "角色", "当前", "会话", "询问", "是否", "什么", "一个", "这个", "那个"}
        value = (text or "").lower()
        terms: list[str] = []
        for chunk in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", value):
            if len(chunk) < 2:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
                terms.append(chunk)
                terms.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
            else:
                terms.append(chunk)
        return [term for term in terms if len(term) >= 2 and term not in stop_terms]
