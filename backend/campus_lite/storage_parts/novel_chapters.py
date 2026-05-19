from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from .common import JSON_LIMITS, RUNTIME_SCENE_CARD_FIELDS, STATE_SCENE_CARD_FIELDS, UNTRUSTED_VERSION_SOURCES


class NovelChapterStorageMixin:
    def create_novel_chapter(
        self,
        project_id: str,
        title: str,
        goal: str = "",
        summary: str = "",
        body: str = "",
        status: str = "planned",
        scene_card: dict[str, Any] | None = None,
        source_material_ids: list[str] | None = None,
        chapter_order: int | None = None,
    ) -> str:
        chapter_id = f"chapter_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            if chapter_order is None:
                row = conn.execute(
                    "SELECT coalesce(max(chapter_order), 0) + 1 AS next_order FROM novel_chapters WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                next_order = int(row["next_order"] if row else 1)
            else:
                next_order = max(1, int(chapter_order))
            conn.execute(
                """
                INSERT INTO novel_chapters (
                    id, project_id, chapter_order, title, goal, summary, body,
                    status, scene_card_json, source_material_ids_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    project_id,
                    next_order,
                    title.strip()[:120] or f"第 {next_order} 章",
                    goal.strip()[:1000],
                    summary.strip()[:1200],
                    body.strip()[:20000],
                    status,
                    self._dump_json(scene_card or {}, "scene_card_json", JSON_LIMITS["scene_card_json"]),
                    self._dump_json(source_material_ids or [], "source_material_ids_json"),
                ),
            )
            conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
        if body:
            row = self.get_novel_chapter(chapter_id)
            planning_snapshot = self._novel_planning_snapshot(
                row,
                title,
                goal,
                summary,
                status,
                scene_card or {},
                source_material_ids or [],
            ) if row else {}
            self.add_novel_version(project_id, chapter_id, "draft", title, body, summary, "create", planning_snapshot=planning_snapshot)
        return chapter_id

    def get_novel_chapter(self, chapter_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_chapters WHERE id = ?", (chapter_id,)).fetchone()

    def list_novel_chapters(self, project_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_chapters
                WHERE project_id = ?
                ORDER BY chapter_order ASC
                """,
                (project_id,),
            ).fetchall()

    def delete_novel_chapter(self, chapter_id: str) -> sqlite3.Row | None:
        existing = self.get_novel_chapter(chapter_id)
        if not existing:
            return None
        project_id = existing["project_id"]
        deleted_order = int(existing["chapter_order"])
        with self.connect() as conn:
            conn.execute("DELETE FROM novel_chapters WHERE id = ?", (chapter_id,))
            conn.execute(
                """
                UPDATE novel_chapters
                SET chapter_order = -chapter_order
                WHERE project_id = ? AND chapter_order > ?
                """,
                (project_id, deleted_order),
            )
            conn.execute(
                """
                UPDATE novel_chapters
                SET chapter_order = abs(chapter_order) - 1,
                    updated_at = datetime('now')
                WHERE project_id = ? AND chapter_order < 0
                """,
                (project_id,),
            )
            conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
        return existing

    def update_novel_chapter(
        self,
        chapter_id: str,
        updates: dict[str, Any],
        version_source: str = "manual",
        create_version: bool = True,
    ) -> bool:
        existing = self.get_novel_chapter(chapter_id)
        if not existing:
            return False
        with self.connect() as conn:
            changed = self._apply_novel_chapter_update(conn, existing, updates, version_source, create_version)
            if changed:
                conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (existing["project_id"],))
            return True

    def update_novel_chapter_draft(
        self,
        project_id: str,
        chapter_id: str,
        project_updates: dict[str, Any],
        chapter_updates: dict[str, Any],
        version_source: str = "manual",
    ) -> bool:
        project_fields, project_values = self._novel_project_update_fields(project_updates)
        with self.connect() as conn:
            project = conn.execute("SELECT id FROM novel_projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return False
            existing = conn.execute("SELECT * FROM novel_chapters WHERE id = ? AND project_id = ?", (chapter_id, project_id)).fetchone()
            if not existing:
                return False
            changed = False
            if project_fields:
                conn.execute(
                    f"UPDATE novel_projects SET {', '.join(project_fields)}, updated_at = datetime('now') WHERE id = ?",
                    [*project_values, project_id],
                )
                changed = True
            changed = self._apply_novel_chapter_update(conn, existing, chapter_updates, version_source, True) or changed
            if changed and not project_fields:
                conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
            return True

    def _novel_chapter_update_fields(self, updates: dict[str, Any]) -> tuple[list[str], list[Any]]:
        allowed = {
            "title": 120,
            "goal": 1000,
            "summary": 1200,
            "body": 20000,
            "status": 40,
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, limit in allowed.items():
            if key in updates and updates[key] is not None:
                fields.append(f"{key} = ?")
                values.append(str(updates[key]).strip()[:limit])
        if "source_material_ids" in updates and updates["source_material_ids"] is not None:
            fields.append("source_material_ids_json = ?")
            values.append(self._dump_json(updates["source_material_ids"][:24], "source_material_ids_json"))
        if "scene_card" in updates and updates["scene_card"] is not None:
            fields.append("scene_card_json = ?")
            values.append(self._dump_json(updates["scene_card"], "scene_card_json", JSON_LIMITS["scene_card_json"]))
        return fields, values

    def _apply_novel_chapter_update(
        self,
        conn: sqlite3.Connection,
        existing: sqlite3.Row,
        updates: dict[str, Any],
        version_source: str,
        create_version: bool,
    ) -> bool:
        fields, values = self._novel_chapter_update_fields(updates)
        if not fields:
            return False
        fields.append("updated_at = datetime('now')")
        values.append(existing["id"])
        conn.execute(f"UPDATE novel_chapters SET {', '.join(fields)} WHERE id = ?", values)
        if create_version and "body" in updates and updates["body"] is not None and str(updates["body"]).strip():
            self._create_active_chapter_version(conn, existing, updates, version_source)
        return True

    def _create_active_chapter_version(
        self,
        conn: sqlite3.Connection,
        existing: sqlite3.Row,
        updates: dict[str, Any],
        version_source: str,
    ) -> str:
        next_title = str(updates.get("title") if updates.get("title") is not None else existing["title"])
        next_goal = str(updates.get("goal") if updates.get("goal") is not None else existing["goal"])
        next_summary = str(updates.get("summary") if updates.get("summary") is not None else existing["summary"])
        next_status = str(updates.get("status") if updates.get("status") is not None else existing["status"])
        next_scene_card = updates.get("scene_card") if isinstance(updates.get("scene_card"), dict) else self._json_dict(existing["scene_card_json"] if "scene_card_json" in existing.keys() else "{}")
        if version_source in UNTRUSTED_VERSION_SOURCES:
            next_scene_card = self._strip_novel_state_fields(next_scene_card)
        next_source_material_ids = updates.get("source_material_ids") if isinstance(updates.get("source_material_ids"), list) else self._json_list(existing["source_material_ids_json"] if "source_material_ids_json" in existing.keys() else "[]")
        state_delta = self._novel_version_state_delta(existing, next_title, str(updates["body"]), next_summary, version_source, next_scene_card)
        if version_source == "mock" and not state_delta.get("handoff_source"):
            state_delta["handoff_source"] = "skipped_mock"
        planning_snapshot = self._novel_planning_snapshot(
            existing,
            next_title,
            next_goal,
            next_summary,
            next_status,
            next_scene_card,
            next_source_material_ids,
        )
        version_id = self._insert_novel_version(
            conn,
            existing["project_id"],
            existing["id"],
            "draft",
            next_title,
            str(updates["body"]),
            next_summary,
            version_source,
            state_delta,
            planning_snapshot,
        )
        state_delta = {**state_delta, "chapter_version_id": version_id}
        active_scene_card = {
            **next_scene_card,
            "active_version_id": version_id,
            "active_state_delta": state_delta,
        }
        if state_delta.get("handoff_source"):
            active_scene_card["handoff_source"] = state_delta["handoff_source"]
        if state_delta.get("chapter_handoff"):
            active_scene_card["chapter_handoff"] = state_delta["chapter_handoff"]
        conn.execute(
            "UPDATE novel_chapters SET scene_card_json = ?, updated_at = datetime('now') WHERE id = ?",
            (
                self._dump_json(active_scene_card, "scene_card_json", JSON_LIMITS["scene_card_json"]),
                existing["id"],
            ),
        )
        return version_id

    def _strip_novel_state_fields(self, scene_card: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(scene_card) if isinstance(scene_card, dict) else {}
        for key in STATE_SCENE_CARD_FIELDS:
            cleaned.pop(key, None)
        return cleaned

    def _strip_runtime_scene_card_fields(self, scene_card: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(scene_card) if isinstance(scene_card, dict) else {}
        for key in RUNTIME_SCENE_CARD_FIELDS:
            cleaned.pop(key, None)
        return cleaned
