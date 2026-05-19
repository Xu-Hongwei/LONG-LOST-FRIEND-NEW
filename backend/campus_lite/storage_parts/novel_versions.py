from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from .common import JSON_LIMITS, RUNTIME_SCENE_CARD_FIELDS, StoragePayloadError


class NovelVersionStorageMixin:
    def _dump_json(self, value: Any, label: str, max_chars: int | None = None) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False)
            json.loads(text)
        except (TypeError, ValueError) as exc:
            raise StoragePayloadError(f"{label} must be JSON serializable") from exc
        if max_chars is not None and len(text) > max_chars:
            raise StoragePayloadError(f"{label} is too large: {len(text)} chars, limit {max_chars}")
        return text

    def _json_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _json_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []

    def _novel_version_state_delta(
        self,
        chapter: sqlite3.Row,
        title: str,
        body: str,
        summary: str,
        source: str,
        scene_card: dict[str, Any],
    ) -> dict[str, Any]:
        handoff = scene_card.get("chapter_handoff") if isinstance(scene_card.get("chapter_handoff"), dict) else {}
        def handoff_list(key: str) -> list[str]:
            value = handoff.get(key) if isinstance(handoff, dict) else []
            if isinstance(value, list):
                return [str(item).strip()[:240] for item in value if str(item).strip()][:8]
            return [str(value).strip()[:240]] if str(value or "").strip() else []
        return {
            "chapter_id": chapter["id"],
            "chapter_order": int(chapter["chapter_order"]),
            "chapter_title": title.strip()[:120],
            "chapter_version_id": "",
            "body_hash": hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16],
            "summary_delta": summary.strip()[:1200],
            "facts_delta": handoff_list("happened"),
            "relationship_delta": handoff_list("relationship_delta"),
            "open_threads_delta": (handoff_list("open_threads") + handoff_list("next_must_continue"))[:12],
            "resolved_threads_delta": handoff_list("resolved_threads"),
            "chapter_handoff": handoff if isinstance(handoff, dict) else {},
            "handoff_source": str(scene_card.get("handoff_source") or "").strip(),
            "source": source.strip()[:120],
        }

    def _novel_planning_snapshot(
        self,
        chapter: sqlite3.Row | None,
        title: str,
        goal: str,
        summary: str,
        status: str,
        scene_card: dict[str, Any],
        source_material_ids: list[Any],
    ) -> dict[str, Any]:
        chapter_order = int(chapter["chapter_order"]) if chapter and "chapter_order" in chapter.keys() else 0
        chapter_id = str(chapter["id"]) if chapter and "id" in chapter.keys() else ""
        return {
            "chapter_id": chapter_id,
            "chapter_order": chapter_order,
            "title": title.strip()[:120],
            "goal": goal.strip()[:1000],
            "summary": summary.strip()[:1200],
            "status": status.strip()[:40] or "draft",
            "scene_card": self._strip_runtime_scene_card_fields(scene_card if isinstance(scene_card, dict) else {}),
            "source_material_ids": [str(item).strip() for item in source_material_ids if str(item).strip()][:24],
        }

    def add_novel_version(
        self,
        project_id: str,
        chapter_id: str,
        version_type: str,
        title: str,
        body: str,
        summary: str = "",
        source: str = "",
        state_delta: dict[str, Any] | None = None,
        planning_snapshot: dict[str, Any] | None = None,
    ) -> str:
        next_title = title.strip()[:120]
        next_body = body.strip()[:20000]
        next_summary = summary.strip()[:1200]
        next_source = source.strip()[:120]
        next_state_delta = state_delta if isinstance(state_delta, dict) else {}
        next_planning_snapshot = planning_snapshot if isinstance(planning_snapshot, dict) else {}
        with self.connect() as conn:
            return self._insert_novel_version(
                conn,
                project_id,
                chapter_id,
                version_type,
                next_title,
                next_body,
                next_summary,
                next_source,
                next_state_delta,
                next_planning_snapshot,
            )

    def _insert_novel_version(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        chapter_id: str,
        version_type: str,
        title: str,
        body: str,
        summary: str = "",
        source: str = "",
        state_delta: dict[str, Any] | None = None,
        planning_snapshot: dict[str, Any] | None = None,
    ) -> str:
        next_title = title.strip()[:120]
        next_body = body.strip()[:20000]
        next_summary = summary.strip()[:1200]
        next_source = source.strip()[:120]
        next_state_delta = state_delta if isinstance(state_delta, dict) else {}
        next_planning_snapshot = planning_snapshot if isinstance(planning_snapshot, dict) else {}
        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        next_state_delta = {**next_state_delta, "chapter_version_id": version_id}
        next_planning_snapshot = {**next_planning_snapshot, "chapter_version_id": version_id}
        conn.execute(
            """
            INSERT INTO novel_versions (
                id, project_id, chapter_id, version_type, title, body, summary, source, state_delta_json, planning_snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                project_id,
                chapter_id,
                version_type,
                next_title,
                next_body,
                next_summary,
                next_source,
                self._dump_json(next_state_delta, "state_delta_json", JSON_LIMITS["state_delta_json"]),
                self._dump_json(next_planning_snapshot, "planning_snapshot_json", JSON_LIMITS["planning_snapshot_json"]),
            ),
        )
        return version_id

    def list_novel_versions(self, chapter_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_versions
                WHERE chapter_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (chapter_id,),
            ).fetchall()

    def get_novel_version(self, version_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_versions WHERE id = ?", (version_id,)).fetchone()

    def delete_novel_version(self, version_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM novel_versions WHERE id = ?", (version_id,))
            return cur.rowcount > 0

    def restore_novel_version(self, version_id: str) -> bool:
        version = self.get_novel_version(version_id)
        if not version:
            return False
        chapter = self.get_novel_chapter(version["chapter_id"])
        if not chapter:
            return False
        scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
        state_delta = self._json_dict(version["state_delta_json"] if "state_delta_json" in version.keys() else "{}")
        planning_snapshot = self._json_dict(version["planning_snapshot_json"] if "planning_snapshot_json" in version.keys() else "{}")
        state_delta = {**state_delta, "chapter_version_id": version_id}
        snapshot_scene_card = planning_snapshot.get("scene_card") if isinstance(planning_snapshot.get("scene_card"), dict) else {}
        if snapshot_scene_card:
            scene_card = self._strip_runtime_scene_card_fields(snapshot_scene_card)
        else:
            scene_card = self._strip_runtime_scene_card_fields(scene_card)
        scene_card = {
            **scene_card,
            "active_version_id": version_id,
            "active_state_delta": state_delta,
        }
        handoff = state_delta.get("chapter_handoff") if isinstance(state_delta.get("chapter_handoff"), dict) else {}
        if handoff:
            scene_card["chapter_handoff"] = handoff
            scene_card["handoff_source"] = state_delta.get("handoff_source") or scene_card.get("handoff_source") or ""
        return self.update_novel_chapter(
            version["chapter_id"],
            {
                "title": version["title"],
                "goal": str(planning_snapshot.get("goal") or chapter["goal"] or ""),
                "body": version["body"],
                "summary": version["summary"],
                "status": str(planning_snapshot.get("status") or "revised"),
                "scene_card": scene_card,
                "source_material_ids": planning_snapshot.get("source_material_ids") if isinstance(planning_snapshot.get("source_material_ids"), list) else self._json_list(chapter["source_material_ids_json"] if "source_material_ids_json" in chapter.keys() else "[]"),
            },
            "restore",
            create_version=False,
        )
