from __future__ import annotations

import re
from typing import Any

from .event_pool import apply_story_event_pool_delta, bind_story_event_pool_to_chapters, normalize_story_event_pool
from .progression import chapter_progression_defaults, normalize_progression_protocol, normalize_story_promise


class NovelCanvasParsingMixin:
    def _looks_like_english_slug(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9_\\-\\s]+", text)) and bool(re.search(r"[A-Za-z]", text))

    def _scene_slug_to_chinese(self, value: Any, fallback: str = "") -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        if not self._looks_like_english_slug(text):
            return text[:500]
        lowered = text.lower()
        if lowered in {"third_person", "third person"}:
            return "第三人称限知"
        token_map = {
            "company": "公司",
            "building": "大楼",
            "front": "门口",
            "office": "办公室",
            "street": "街道",
            "road": "路边",
            "lake": "湖边",
            "cafe": "咖啡店",
            "shop": "店门口",
            "station": "车站",
            "school": "学校",
            "library": "图书馆",
            "room": "房间",
            "door": "门口",
            "hall": "走廊",
        }
        pieces = re.split(r"[_\\-\\s]+", lowered)
        translated = "".join(token_map.get(piece, "") for piece in pieces if piece)
        if translated:
            return translated[:500]
        return fallback[:500]

    def _normalize_scene_display_value(self, value: Any, fallback: Any, chapter: dict[str, Any], key: str) -> str:
        raw = str(value or "").strip()
        fallback_text = str(fallback or "").strip()
        if key == "pov":
            if self._looks_like_english_slug(raw):
                return "第三人称限知"
            return (raw or "第三人称限知")[:260]
        if key == "current_scene":
            if self._looks_like_english_slug(raw):
                translated = self._scene_slug_to_chinese(raw, "")
                if translated:
                    return translated[:500]
                return str(chapter.get("external_event") or chapter.get("trigger_event") or fallback_text or "")[:500]
        return (raw or fallback_text)[:500]

    def _parse_event_pool_delta_response(self, text: str) -> dict[str, Any]:
        raw = self._load_llm_json_object(text, "event_pool_delta")
        delta = raw.get("event_pool_delta") if isinstance(raw.get("event_pool_delta"), dict) else raw
        if not isinstance(delta, dict):
            return {}
        cleaned: dict[str, Any] = {}
        for key in ["add", "update", "retire"]:
            value = delta.get(key)
            if not isinstance(value, list):
                continue
            if key == "retire":
                cleaned[key] = [
                    item for item in value
                    if isinstance(item, (str, int, float)) or (isinstance(item, dict) and str(item.get("id") or "").strip())
                ][:10]
            else:
                cleaned[key] = [item for item in value if isinstance(item, dict)][:10]
        return cleaned

    def _merge_event_pool_deltas(self, first: Any, second: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in ["add", "update", "retire"]:
            items: list[Any] = []
            for source in [first, second]:
                if isinstance(source, dict) and isinstance(source.get(key), list):
                    items.extend(source.get(key) or [])
            if items:
                merged[key] = items[:20]
        return merged

    def _parse_canvas_response(self, text: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raw = self._load_llm_json_object(text, "canvas")
        if not isinstance(raw, dict):
            raise ValueError("Canvas payload is not an object")
        canvas = raw.get("story_canvas") if isinstance(raw.get("story_canvas"), dict) else raw
        if not isinstance(canvas, dict):
            raise ValueError("Canvas payload is not an object")
        chapters_raw = canvas.get("chapters")
        scenes_raw = canvas.get("scenes")
        if not isinstance(chapters_raw, list) or not chapters_raw:
            raise ValueError("Canvas missing chapters")
        if not isinstance(scenes_raw, list):
            scenes_raw = []

        fallback_chapters = self._canvas_chapters(fallback)
        fallback_scenes = self._canvas_scenes(fallback)
        acts_raw = canvas.get("acts") if isinstance(canvas.get("acts"), list) else fallback.get("acts", [])
        acts: list[dict[str, Any]] = []
        for index, item in enumerate(acts_raw[:8]):
            source = item if isinstance(item, dict) else {"title": item}
            acts.append({
                "id": str(source.get("id") or f"act_{index + 1}"),
                "order": self._coerce_int(source.get("order"), index + 1, 1, 99),
                "title": str(source.get("title") or f"阶段 {index + 1}")[:80],
                "purpose": str(source.get("purpose") or "")[:240],
                "chapter_ids": [str(value) for value in source.get("chapter_ids", [])] if isinstance(source.get("chapter_ids"), list) else [],
            })

        chapters: list[dict[str, Any]] = []
        for index, item in enumerate(chapters_raw[:12]):
            if not isinstance(item, dict):
                continue
            base = fallback_chapters[min(index, len(fallback_chapters) - 1)] if fallback_chapters else {}
            chapter_id = str(item.get("id") or base.get("id") or f"canvas_ch_{index + 1}")
            chapter_status = self._normalize_remote_canvas_chapter_status(item.get("status"), base.get("status"))
            chapter = {
                "id": chapter_id,
                "act_id": str(item.get("act_id") or base.get("act_id") or "act_1"),
                "chapter_order": index + 1,
                "event_pool_id": str(item.get("event_pool_id") or base.get("event_pool_id") or ""),
                "title": self._normalize_chapter_title(str(item.get("title") or base.get("title") or ""), index + 1),
                "goal": str(item.get("goal") or base.get("goal") or "")[:500],
                "external_event": str(item.get("external_event") or base.get("external_event") or "")[:500],
                "trigger_event": str(item.get("trigger_event") or item.get("external_event") or base.get("trigger_event") or "")[:500],
                "immediate_reaction": str(item.get("immediate_reaction") or base.get("immediate_reaction") or "")[:500],
                "obstacle_escalation": str(item.get("obstacle_escalation") or base.get("obstacle_escalation") or "")[:500],
                "counterpart_reaction": str(item.get("counterpart_reaction") or base.get("counterpart_reaction") or "")[:500],
                "character_choice": str(item.get("character_choice") or base.get("character_choice") or "")[:500],
                "scene_consequence": str(item.get("scene_consequence") or base.get("scene_consequence") or "")[:500],
                "relationship_shift": str(item.get("relationship_shift") or base.get("relationship_shift") or "")[:260],
                "ending_hook": str(item.get("ending_hook") or base.get("ending_hook") or "")[:500],
                "target_length": self._coerce_int(item.get("target_length") or base.get("target_length"), 1800, 300, 12000),
                "status": chapter_status,
                "emotion_curve": str(item.get("emotion_curve") or base.get("emotion_curve") or "")[:260],
                "scene_ids": [str(value) for value in item.get("scene_ids", [])] if isinstance(item.get("scene_ids"), list) else [],
                "chapter_drive": str(item.get("chapter_drive") or base.get("chapter_drive") or "")[:500],
                "progression_role": str(item.get("progression_role") or base.get("progression_role") or "")[:80],
                "promise_targets": [str(value)[:160] for value in item.get("promise_targets", [])] if isinstance(item.get("promise_targets"), list) else (base.get("promise_targets", []) if isinstance(base.get("promise_targets"), list) else []),
            }
            chapters.append(chapter)

        chapter_ids = {chapter["id"] for chapter in chapters}
        first_chapter_id = chapters[0]["id"]
        derived_scenes = False
        if not scenes_raw:
            scenes_raw = self._derive_canvas_scenes_from_chapters(chapters)
            derived_scenes = True
        scenes: list[dict[str, Any]] = []
        invalid_scene_tension_count = 0
        for index, item in enumerate(scenes_raw[:20]):
            if not isinstance(item, dict):
                continue
            base = fallback_scenes[min(index, len(fallback_scenes) - 1)] if fallback_scenes else {}
            chapter_id = str(item.get("chapter_id") or base.get("chapter_id") or first_chapter_id)
            if chapter_id not in chapter_ids:
                chapter_id = first_chapter_id
            chapter_for_scene = next((chapter for chapter in chapters if chapter["id"] == chapter_id), {})
            raw_tension = item.get("tension") if item.get("tension") is not None else base.get("tension")
            if self._is_numeric_conflict_marker(raw_tension):
                invalid_scene_tension_count += 1
            tension = self._normalize_scene_tension(
                raw_tension,
                chapter_for_scene,
                base,
            )
            scenes.append({
                "id": str(item.get("id") or base.get("id") or f"scene_{index + 1}"),
                "chapter_id": chapter_id,
                "scene_order": self._coerce_int(item.get("scene_order"), index + 1, 1, 99),
                "current_scene": self._normalize_scene_display_value(item.get("current_scene"), base.get("current_scene"), chapter_for_scene, "current_scene"),
                "pov": self._normalize_scene_display_value(item.get("pov"), base.get("pov"), chapter_for_scene, "pov")[:260],
                "present_characters": (
                    "、".join(str(value).strip() for value in item.get("present_characters", []) if str(value).strip())[:260]
                    if isinstance(item.get("present_characters"), list)
                    else str(item.get("present_characters") or base.get("present_characters") or "")[:260]
                ),
                "surface_event": str(item.get("surface_event") or base.get("surface_event") or "")[:500],
                "character_desire": str(item.get("character_desire") or base.get("character_desire") or "")[:500],
                "tension": tension,
                "required_facts": [str(value)[:260] for value in item.get("required_facts", [])] if isinstance(item.get("required_facts"), list) else [],
                "forbidden_progress": [str(value)[:260] for value in item.get("forbidden_progress", [])] if isinstance(item.get("forbidden_progress"), list) else [],
                "ending_beat": str(item.get("ending_beat") or base.get("ending_beat") or "")[:500],
                "linked_material_ids": [str(value) for value in item.get("linked_material_ids", [])] if isinstance(item.get("linked_material_ids"), list) else [],
            })

        threads_raw = canvas.get("threads") if isinstance(canvas.get("threads"), list) else []
        threads: list[dict[str, Any]] = []
        for index, item in enumerate(threads_raw[:12]):
            if not isinstance(item, dict):
                continue
            threads.append({
                "id": str(item.get("id") or f"thread_{index + 1}"),
                "kind": str(item.get("kind") or "foreshadowing")[:60],
                "label": str(item.get("label") or "")[:120],
                "setup_chapter_id": str(item.get("setup_chapter_id") or first_chapter_id),
                "payoff_chapter_id": str(item.get("payoff_chapter_id") or chapters[-1]["id"]),
                "status": str(item.get("status") or "seed")[:60],
                "notes": str(item.get("notes") or "")[:500],
            })

        quality_rules = canvas.get("quality_rules") if isinstance(canvas.get("quality_rules"), list) else fallback.get("quality_rules", [])
        diagnostics = self._json_dict(canvas.get("diagnostics"))
        fallback_diagnostics = self._json_dict(fallback.get("diagnostics"))
        setting_type = str(diagnostics.get("setting_type") or fallback_diagnostics.get("setting_type") or "modern_daily")
        story_promise = normalize_story_promise(canvas.get("story_promise") if isinstance(canvas.get("story_promise"), dict) else fallback.get("story_promise"))
        progression_protocol = normalize_progression_protocol(canvas.get("progression_protocol") if isinstance(canvas.get("progression_protocol"), dict) else fallback.get("progression_protocol"))
        progression_canvas = {"story_promise": story_promise, "progression_protocol": progression_protocol}
        for chapter in chapters:
            chapter.update(chapter_progression_defaults(chapter, progression_canvas))
        event_pool_source = canvas.get("event_pool") if isinstance(canvas.get("event_pool"), dict) else fallback.get("event_pool")
        event_pool = normalize_story_event_pool(event_pool_source, setting_type)
        event_pool = apply_story_event_pool_delta(event_pool, canvas.get("event_pool_delta"), setting_type)
        event_pool = bind_story_event_pool_to_chapters(event_pool, chapters, setting_type)
        if derived_scenes:
            diagnostics = {**diagnostics, "scene_source": "derived_from_chapters"}
        if invalid_scene_tension_count:
            diagnostics = {
                **diagnostics,
                "scene_tension_repaired": invalid_scene_tension_count,
                "scene_tension_repair_reason": "remote_returned_number_instead_of_obstacle_text",
            }
        return {
            "version": self._coerce_int(canvas.get("version"), 1, 1, 99),
            "mode": str(canvas.get("mode") or "story_canvas"),
            "story_promise": story_promise,
            "progression_protocol": progression_protocol,
            "acts": acts or fallback.get("acts", []),
            "chapters": chapters,
            "scenes": scenes,
            "threads": threads or fallback.get("threads", []),
            "quality_rules": [str(value)[:240] for value in quality_rules],
            "event_pool": event_pool,
            "diagnostics": diagnostics,
        }

    def _normalize_remote_canvas_chapter_status(self, raw_status: Any, base_status: Any = "") -> str:
        raw = str(raw_status or "").strip().lower()
        base = str(base_status or "").strip().lower()
        allowed = {"planned", "drafting", "draft", "revised", "locked", "affected", "not_started", "in_progress"}
        complete_statuses = {"complete", "completed"}
        if base in complete_statuses and raw in {"", *complete_statuses}:
            return "complete"
        if raw in complete_statuses:
            return "planned"
        if raw in allowed:
            return raw
        if base in allowed:
            return base
        return "planned"

    def _derive_canvas_scenes_from_chapters(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for index, chapter in enumerate(chapters):
            scene_ids = chapter.get("scene_ids") if isinstance(chapter.get("scene_ids"), list) else []
            scene_id = str(scene_ids[0]) if scene_ids else f"scene_{index + 1}"
            scenes.append({
                "id": scene_id,
                "chapter_id": chapter["id"],
                "scene_order": 1,
                "current_scene": chapter.get("external_event") or chapter.get("trigger_event") or chapter.get("title") or "",
                "pov": "第三人称限知",
                "present_characters": "",
                "surface_event": chapter.get("trigger_event") or chapter.get("external_event") or "",
                "character_desire": chapter.get("immediate_reaction") or chapter.get("goal") or "",
                "tension": chapter.get("obstacle_escalation") or "",
                "required_facts": [],
                "forbidden_progress": [],
                "ending_beat": chapter.get("ending_hook") or chapter.get("scene_consequence") or "",
                "linked_material_ids": [],
            })
        return scenes

    def _normalize_scene_tension(
        self,
        value: Any,
        chapter: dict[str, Any] | None = None,
        fallback: dict[str, Any] | None = None,
    ) -> str:
        text = str(value or "").strip()
        if text and not self._is_numeric_conflict_marker(text):
            return text[:500]
        chapter = chapter or {}
        for key in ["obstacle_escalation", "counterpart_reaction", "trigger_event", "external_event"]:
            candidate = self._clean_material_text(str(chapter.get(key) or ""))
            if candidate and not self._is_numeric_conflict_marker(candidate):
                return candidate[:500]
        fallback_text = str((fallback or {}).get("tension") or "").strip()
        if fallback_text and not self._is_numeric_conflict_marker(fallback_text):
            return fallback_text[:500]
        return "阻碍尚未写清：需要补充一个会打断人物目标的具体外部事件。"

    def _is_numeric_conflict_marker(self, value: Any) -> bool:
        text = str(value or "").strip()
        return bool(re.fullmatch(r"[1-5１-５]", text))
