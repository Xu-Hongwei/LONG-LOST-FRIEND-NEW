from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ...schemas import StoryEventPoolBindingRequest, StoryEventPoolEventWriteRequest
from .event_pool import (
    STORY_EVENT_POOL_SIZE,
    _fallback_event,
    _normalize_event_entry,
    _record_event_binding,
    _replaceable_active_index,
    normalize_event_use_mode,
    normalize_story_event_pool,
    sync_story_event_pool_display_bindings,
)
from .setting_profiles import infer_novel_setting_type


class NovelEventPoolEditMixin:
    def create_event_pool_event(self, project_id: str, payload: StoryEventPoolEventWriteRequest) -> Any:
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        active = pool.get("active") or []
        entry = self._event_entry_from_payload(payload, setting_type, len(active))
        if len(active) >= STORY_EVENT_POOL_SIZE:
            replace_index = _replaceable_active_index(active)
            if replace_index < 0:
                raise ValueError("Event pool is full; retire or delete an unbound event first")
            active.pop(replace_index)
        active.append(entry)
        pool["active"] = active[:STORY_EVENT_POOL_SIZE]
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    def update_event_pool_event(self, project_id: str, event_id: str, payload: StoryEventPoolEventWriteRequest) -> Any:
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        event = self._find_event(pool, event_id)
        if not event:
            raise ValueError("Event not found")
        fallback = dict(event)
        event.update(self._event_entry_from_payload(payload, setting_type, 0, fallback=fallback, event_id=event_id))
        event["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    def retire_event_pool_event(self, project_id: str, event_id: str) -> Any:
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        active = pool.get("active") or []
        retired = pool.get("retired") or []
        index = next((idx for idx, item in enumerate(active) if str(item.get("id") or "") == event_id), -1)
        if index < 0:
            raise ValueError("Event not found in active pool")
        event = active.pop(index)
        event["status"] = "retired"
        event["retired_at"] = datetime.now(timezone.utc).isoformat()
        retired.append(event)
        pool["active"] = active
        pool["retired"] = retired[-40:]
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    def delete_event_pool_event(self, project_id: str, event_id: str) -> Any:
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        active = pool.get("active") or []
        retired = pool.get("retired") or []
        event = self._find_event(pool, event_id)
        if not event:
            raise ValueError("Event not found")
        if event.get("bound_chapter_orders") or event.get("used_chapter_ids"):
            raise ValueError("Bound or used events must be retired before they can be removed")
        pool["active"] = [item for item in active if str(item.get("id") or "") != event_id]
        pool["retired"] = [item for item in retired if str(item.get("id") or "") != event_id]
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    def bind_event_pool_event_to_chapter(self, project_id: str, chapter_id: str, payload: StoryEventPoolBindingRequest) -> Any:
        storage = self._require_storage()
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter or chapter["project_id"] != project_id:
            raise ValueError("Novel chapter not found")
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        order = int(chapter["chapter_order"])
        canvas_chapter = next((item for item in self._canvas_chapters(canvas) if int(item.get("chapter_order") or 0) == order), None)
        if not canvas_chapter:
            raise ValueError("Canvas chapter not found")
        event_id = str(payload.event_id or "").strip()
        if not event_id:
            canvas_chapter["event_pool_id"] = ""
            canvas_chapter["event_pool_score"] = 0
            canvas_chapter["event_pool_reasons"] = []
            canvas_chapter["event_pool_penalties"] = []
            return self._save_event_pool(project["id"], canvas, pool, setting_type)
        event = self._find_event(pool, event_id)
        if not event:
            raise ValueError("Event not found")
        if payload.use_mode:
            event["use_mode"] = normalize_event_use_mode(payload.use_mode)
        canvas_chapter["event_pool_id"] = event_id
        canvas_chapter["event_pool_score"] = int(event.get("selection_score") or 0)
        canvas_chapter["event_pool_reasons"] = event.get("selection_reasons") if isinstance(event.get("selection_reasons"), list) else []
        canvas_chapter["event_pool_penalties"] = event.get("selection_penalties") if isinstance(event.get("selection_penalties"), list) else []
        _record_event_binding(event, canvas_chapter, {
            "score": canvas_chapter["event_pool_score"],
            "reasons": canvas_chapter["event_pool_reasons"] or ["manual binding"],
            "penalties": canvas_chapter["event_pool_penalties"],
        })
        if event.get("status") == "fresh":
            event["status"] = "planned"
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    def _editable_event_pool(self, project_id: str) -> tuple[Any, dict[str, Any], dict[str, Any], str]:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        setting_type = str(self._json_dict(canvas.get("diagnostics")).get("setting_type") or infer_novel_setting_type(project))
        pool = normalize_story_event_pool(canvas.get("event_pool"), setting_type)
        canvas["event_pool"] = pool
        return project, canvas, pool, setting_type

    def _event_entry_from_payload(
        self,
        payload: StoryEventPoolEventWriteRequest,
        setting_type: str,
        index: int,
        *,
        fallback: dict[str, Any] | None = None,
        event_id: str = "",
    ) -> dict[str, Any]:
        fallback = fallback or _fallback_event(setting_type, index)
        raw = {
            **fallback,
            "id": event_id or f"evt_manual_{uuid.uuid4().hex[:10]}",
            "place": payload.place,
            "time_anchor": payload.time_anchor,
            "event": payload.event,
            "hook": payload.hook,
            "motifs": payload.motifs,
            "use_mode": payload.use_mode,
            "source": fallback.get("source") if event_id else "manual",
            "source_reason": payload.source_reason,
            "tags": payload.tags,
        }
        return _normalize_event_entry(raw, fallback, index)

    def _find_event(self, pool: dict[str, Any], event_id: str) -> dict[str, Any] | None:
        for item in [*(pool.get("active") or []), *(pool.get("retired") or [])]:
            if str(item.get("id") or "") == event_id:
                return item
        return None

    def _save_event_pool(self, project_id: str, canvas: dict[str, Any], pool: dict[str, Any], setting_type: str) -> Any:
        storage = self._require_storage()
        canvas["event_pool"] = sync_story_event_pool_display_bindings(pool, self._canvas_chapters(canvas), setting_type)
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        return self.project_response(project_id)
