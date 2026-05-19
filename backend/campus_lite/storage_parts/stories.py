from __future__ import annotations

import json
import sqlite3
import uuid


class StoryStorageMixin:
    def upsert_story_item(
        self,
        session_id: str,
        kind: str,
        label: str,
        content: str,
        evidence: str = "",
        evidence_level: str = "inferred",
        status: str = "active",
        source_message_ids: list[str] | None = None,
    ) -> str | None:
        clean_label = label.strip()[:80]
        clean_content = content.strip()[:500]
        if not clean_label or not clean_content:
            return None
        story_id = f"story_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO story_items (
                    id, session_id, kind, label, content, evidence,
                    evidence_level, status, source_message_ids_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, kind, label) DO UPDATE SET
                    content = excluded.content,
                    evidence = excluded.evidence,
                    evidence_level = excluded.evidence_level,
                    status = excluded.status,
                    source_message_ids_json = excluded.source_message_ids_json,
                    updated_at = datetime('now')
                """,
                (
                    story_id,
                    session_id,
                    kind,
                    clean_label,
                    clean_content,
                    evidence.strip()[:500],
                    evidence_level,
                    status,
                    json.dumps(source_message_ids or [], ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT id FROM story_items WHERE session_id = ? AND kind = ? AND label = ?",
                (session_id, kind, clean_label),
            ).fetchone()
        return str(row["id"]) if row else None

    def list_story_items(self, session_id: str, include_archived: bool = False) -> list[sqlite3.Row]:
        with self.connect() as conn:
            where = "session_id = ?" if include_archived else "session_id = ? AND status != 'archived'"
            return conn.execute(
                f"""
                SELECT * FROM story_items
                WHERE {where}
                ORDER BY
                    CASE kind
                        WHEN 'story_beat' THEN 0
                        WHEN 'open_thread' THEN 1
                        WHEN 'motif' THEN 2
                        WHEN 'relationship_texture' THEN 3
                        WHEN 'boundary' THEN 4
                        ELSE 5
                    END,
                    updated_at DESC
                """,
                (session_id,),
            ).fetchall()
