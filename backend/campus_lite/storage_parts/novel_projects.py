from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from .common import JSON_LIMITS


class NovelProjectStorageMixin:
    def create_novel_project(
        self,
        session_id: str,
        visitor_id: str,
        character_id: str,
        title: str,
        genre: str,
        tone: str,
        protagonist: str,
        worldview: str,
        relationship_setup: str,
        outline: str,
        story_bible: dict[str, Any],
        story_canvas: dict[str, Any] | None = None,
        novel_state: dict[str, Any] | None = None,
    ) -> str:
        project_id = f"novel_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO novel_projects (
                    id, session_id, visitor_id, character_id, title, genre, tone,
                    protagonist, worldview, relationship_setup, outline, story_bible_json,
                    story_canvas_json, novel_state_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    visitor_id,
                    character_id,
                    title.strip()[:120],
                    genre.strip()[:80],
                    tone.strip()[:120],
                    protagonist.strip()[:120],
                    worldview.strip()[:2000],
                    relationship_setup.strip()[:2000],
                    outline.strip()[:4000],
                    self._dump_json(story_bible, "story_bible_json"),
                    self._dump_json(story_canvas or {}, "story_canvas_json", JSON_LIMITS["story_canvas_json"]),
                    self._dump_json(novel_state or {}, "novel_state_json", JSON_LIMITS["novel_state_json"]),
                ),
            )
        return project_id

    def get_novel_project(self, project_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_projects WHERE id = ?", (project_id,)).fetchone()

    def list_novel_projects(self, session_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_projects
                WHERE session_id = ? AND status != 'archived'
                ORDER BY updated_at DESC
                """,
                (session_id,),
            ).fetchall()

    def update_novel_project(self, project_id: str, updates: dict[str, Any]) -> bool:
        fields, values = self._novel_project_update_fields(updates)
        if not fields:
            return bool(self.get_novel_project(project_id))
        fields.append("updated_at = datetime('now')")
        values.append(project_id)
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE novel_projects SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            return cur.rowcount > 0

    def delete_novel_project(self, project_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE novel_projects
                SET status = 'archived', updated_at = datetime('now')
                WHERE id = ? AND status != 'archived'
                """,
                (project_id,),
            )
            return cur.rowcount > 0

    def _novel_project_update_fields(self, updates: dict[str, Any]) -> tuple[list[str], list[Any]]:
        allowed = {
            "title": 120,
            "genre": 80,
            "tone": 120,
            "protagonist": 120,
            "worldview": 2000,
            "relationship_setup": 2000,
            "outline": 4000,
            "status": 40,
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, limit in allowed.items():
            if key in updates and updates[key] is not None:
                fields.append(f"{key} = ?")
                values.append(str(updates[key]).strip()[:limit])
        if "story_bible" in updates and updates["story_bible"] is not None:
            fields.append("story_bible_json = ?")
            values.append(self._dump_json(updates["story_bible"], "story_bible_json"))
        if "story_canvas" in updates and updates["story_canvas"] is not None:
            fields.append("story_canvas_json = ?")
            values.append(self._dump_json(updates["story_canvas"], "story_canvas_json", JSON_LIMITS["story_canvas_json"]))
        if "novel_state" in updates and updates["novel_state"] is not None:
            fields.append("novel_state_json = ?")
            values.append(self._dump_json(updates["novel_state"], "novel_state_json", JSON_LIMITS["novel_state_json"]))
        return fields, values

    def upsert_novel_material(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        category: str,
        label: str,
        content: str,
        evidence_level: str = "inferred",
    ) -> str | None:
        clean_label = label.strip()[:100]
        clean_content = content.strip()[:1000]
        if not clean_label or not clean_content:
            return None
        material_id = f"mat_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO novel_materials (
                    id, project_id, source_type, source_id, category,
                    label, content, evidence_level
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_type, source_id, label) DO UPDATE SET
                    category = excluded.category,
                    content = excluded.content,
                    evidence_level = excluded.evidence_level
                """,
                (
                    material_id,
                    project_id,
                    source_type,
                    source_id.strip()[:120],
                    category,
                    clean_label,
                    clean_content,
                    evidence_level,
                ),
            )
            row = conn.execute(
                """
                SELECT id FROM novel_materials
                WHERE project_id = ? AND source_type = ? AND source_id = ? AND label = ?
                """,
                (project_id, source_type, source_id.strip()[:120], clean_label),
            ).fetchone()
        return str(row["id"]) if row else None

    def list_novel_materials(self, project_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_materials
                WHERE project_id = ?
                ORDER BY
                    CASE category
                        WHEN 'fact' THEN 0
                        WHEN 'boundary' THEN 1
                        WHEN 'relationship' THEN 2
                        WHEN 'foreshadowing' THEN 3
                        WHEN 'open_thread' THEN 4
                        ELSE 5
                    END,
                    created_at ASC
                """,
                (project_id,),
            ).fetchall()
