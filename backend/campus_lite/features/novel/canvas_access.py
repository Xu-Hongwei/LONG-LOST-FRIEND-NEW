from __future__ import annotations

import json
from typing import Any


class NovelCanvasAccessMixin:
    def _story_canvas_with_materials(self, canvas: dict[str, Any], materials: list[Any]) -> dict[str, Any]:
        material_ids = [str(row["id"]) for row in materials[:6]]
        next_canvas = json.loads(json.dumps(canvas, ensure_ascii=False))
        for scene in self._canvas_scenes(next_canvas):
            if not scene.get("linked_material_ids"):
                scene["linked_material_ids"] = material_ids[:4]
        return next_canvas

    def _canvas_outline(self, canvas: dict[str, Any]) -> str:
        lines: list[str] = []
        for chapter in self._canvas_chapters(canvas):
            order = chapter.get("chapter_order") or len(lines) + 1
            title = chapter.get("title") or f"第{order}章"
            trigger = chapter.get("trigger_event") or chapter.get("external_event") or chapter.get("goal") or ""
            choice = chapter.get("character_choice") or chapter.get("relationship_shift") or ""
            hook = chapter.get("ending_hook") or ""
            lines.append(f"{order}. {title}：{trigger} → {choice} → {hook}")
        return "\n".join(lines)[:4000] or ""

    def _canvas_chapters(self, canvas: dict[str, Any]) -> list[dict[str, Any]]:
        chapters = canvas.get("chapters", [])
        return chapters if isinstance(chapters, list) else []

    def _canvas_scenes(self, canvas: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = canvas.get("scenes", [])
        return scenes if isinstance(scenes, list) else []

    def _canvas_scene_for_canvas_chapter(self, canvas: dict[str, Any], canvas_chapter_id: str) -> dict[str, Any] | None:
        for scene in self._canvas_scenes(canvas):
            if str(scene.get("chapter_id", "")) == canvas_chapter_id:
                return scene
        return None

    def _canvas_for_chapter(self, project: Any, chapter: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        matched_chapter: dict[str, Any] = {}
        chapter_order = int(chapter["chapter_order"])
        for item in self._canvas_chapters(canvas):
            if int(item.get("chapter_order") or 0) == chapter_order:
                matched_chapter = item
                break
        matched_scene = self._canvas_scene_for_canvas_chapter(canvas, str(matched_chapter.get("id", ""))) or {}
        return matched_chapter, matched_scene
