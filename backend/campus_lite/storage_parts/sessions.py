from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any


class SessionStorageMixin:
    def resolve_visitor(self, visitor_id: str | None) -> tuple[str, bool]:
        normalized = (visitor_id or "").strip() or f"visitor_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM visitors WHERE id = ?", (normalized,)).fetchone()
            created = row is None
            if created:
                conn.execute("INSERT INTO visitors (id) VALUES (?)", (normalized,))
            else:
                conn.execute("UPDATE visitors SET last_active_at = datetime('now') WHERE id = ?", (normalized,))
        return normalized, created

    def create_or_get_session(self, visitor_id: str, character_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM sessions
                WHERE visitor_id = ? AND character_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (visitor_id, character_id),
            ).fetchone()
            if row:
                conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (row["id"],))
                return str(row["id"])
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO sessions (id, visitor_id, character_id) VALUES (?, ?, ?)",
                (session_id, visitor_id, character_id),
            )
            return session_id

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def add_message(self, session_id: str, visitor_id: str, character_id: str, role: str, content: str) -> str:
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, session_id, visitor_id, character_id, role, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, visitor_id, character_id, role, content),
            )
            conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
        return message_id

    def get_message(self, message_id: str) -> dict[str, str] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, role, content, created_at FROM messages
                WHERE id = ?
                LIMIT 1
                """,
                (message_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}

    def recent_messages(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE session_id = ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [{"role": row["role"], "content": row["content"], "created_at": row["created_at"]} for row in rows]

    def session_messages(self, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        with self.connect() as conn:
            if limit:
                rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT rowid AS message_order, id, role, content, created_at FROM messages
                        WHERE session_id = ?
                        ORDER BY rowid DESC
                        LIMIT ?
                    )
                    ORDER BY message_order ASC
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, role, content, created_at FROM messages
                    WHERE session_id = ?
                    ORDER BY rowid ASC
                    """,
                    (session_id,),
                ).fetchall()
        return [
            {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}
            for row in rows
        ]

    def update_session_memory(self, session_id: str, frozen: bool | None = None, manual_note: str | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if frozen is not None:
            fields.append("frozen = ?")
            values.append(1 if frozen else 0)
        if manual_note is not None:
            fields.append("manual_note = ?")
            values.append(manual_note[:1000])
        if not fields:
            return
        values.append(session_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", values)

    def set_summary(self, session_id: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET recent_summary = ?, updated_at = datetime('now') WHERE id = ?", (content[:1600], session_id))
            conn.execute(
                "INSERT INTO summaries (id, session_id, summary_type, content) VALUES (?, ?, 'recent', ?)",
                (f"sum_{uuid.uuid4().hex[:12]}", session_id, content[:1600]),
            )

    def set_prompt_slots(self, session_id: str, slots: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET last_prompt_slots = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(slots, ensure_ascii=False), session_id),
            )

    def set_postprocess_diagnostics(self, session_id: str, diagnostics: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET postprocess_diagnostics_json = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (json.dumps(diagnostics, ensure_ascii=False), session_id),
            )

    def set_character_state(self, session_id: str, state: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET character_state_json = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(state, ensure_ascii=False), session_id),
            )
