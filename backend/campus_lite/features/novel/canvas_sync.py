from __future__ import annotations

from typing import Any


class NovelCanvasSyncMixin:
    def sync_story_canvas_to_chapters(self, project_id: str, start_order: int = 1) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        if not canvas:
            return
        normalized = self._compact_story_canvas(canvas)
        if normalized != canvas:
            storage.update_novel_project(project_id, {"story_canvas": normalized, "outline": self._canvas_outline(normalized)})
        self._sync_chapters_from_canvas(project_id, normalized, start_order=start_order)

    def _sync_chapters_from_canvas(self, project_id: str, canvas: dict[str, Any], start_order: int = 1) -> None:
        storage = self._require_storage()
        existing = list(storage.list_novel_chapters(project_id))
        existing_by_order = {int(row["chapter_order"]): row for row in existing}
        material_ids = [str(row["id"]) for row in storage.list_novel_materials(project_id)[:6]]
        for canvas_chapter in self._canvas_chapters(canvas):
            order = self._coerce_int(canvas_chapter.get("chapter_order"), len(existing_by_order) + 1, 1, 99)
            if order < start_order:
                continue
            scene = self._scene_card_planning_from_canvas(canvas_chapter, self._canvas_scene_for_canvas_chapter(canvas, str(canvas_chapter.get("id", ""))) or {})
            updates = {
                "title": canvas_chapter.get("title") or f"第{order}章",
                "goal": canvas_chapter.get("goal") or canvas_chapter.get("external_event") or "",
                "source_material_ids": material_ids,
            }
            row = existing_by_order.get(order)
            if row:
                existing_scene_card = self._json_dict(row["scene_card_json"] if "scene_card_json" in row.keys() else "{}")
                updates["scene_card"] = self._merge_scene_card_planning(existing_scene_card, scene)
                storage.update_novel_chapter(row["id"], updates, "canvas")
            else:
                chapter_id = storage.create_novel_chapter(
                    project_id,
                    str(updates["title"]),
                    str(updates["goal"]),
                    "",
                    "",
                    "planned",
                    scene,
                    material_ids,
                    order,
                )
                created = storage.get_novel_chapter(chapter_id)
                if created:
                    existing_by_order[int(created["chapter_order"])] = created

    def _scene_card_planning_from_canvas(self, canvas_chapter: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
        if not canvas_chapter and not scene:
            return {}
        action_pairs = [
            ("触发事件", canvas_chapter.get("trigger_event") or canvas_chapter.get("external_event")),
            ("即时反应", canvas_chapter.get("immediate_reaction")),
            ("阻碍升级", canvas_chapter.get("obstacle_escalation")),
            ("对方反应", canvas_chapter.get("counterpart_reaction")),
            ("人物选择", canvas_chapter.get("character_choice")),
            ("场景后果", canvas_chapter.get("scene_consequence") or canvas_chapter.get("relationship_shift")),
            ("结尾钩子", canvas_chapter.get("ending_hook")),
        ]
        planning = dict(scene)
        if canvas_chapter:
            planning["surface_event"] = (
                str(canvas_chapter.get("trigger_event") or canvas_chapter.get("external_event") or "").strip()
                or str(scene.get("surface_event") or "").strip()
            )
            planning["tension"] = (
                str(canvas_chapter.get("obstacle_escalation") or "").strip()
                or str(scene.get("tension") or "").strip()
            )
            planning["ending_beat"] = (
                str(canvas_chapter.get("ending_hook") or "").strip()
                or str(scene.get("ending_beat") or "").strip()
            )
        planning.update({
            "canvas_chapter_id": str(canvas_chapter.get("id") or ""),
            "canvas_scene_id": str(scene.get("id") or ""),
            "canvas_chapter_order": self._coerce_int(canvas_chapter.get("chapter_order"), 0, 0, 999),
            "canvas_chapter_status": str(canvas_chapter.get("status") or ""),
            "canvas_action_chain": [
                {"label": label, "text": str(value).strip()}
                for label, value in action_pairs
                if str(value or "").strip()
            ],
        })
        return planning

    def _merge_scene_card_planning(self, existing: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
        if not scene:
            return existing
        planning_keys = {
            "id",
            "chapter_id",
            "scene_order",
            "current_scene",
            "pov",
            "present_characters",
            "surface_event",
            "character_desire",
            "tension",
            "required_facts",
            "forbidden_progress",
            "ending_beat",
            "linked_material_ids",
            "canvas_chapter_id",
            "canvas_scene_id",
            "canvas_chapter_order",
            "canvas_chapter_status",
            "canvas_action_chain",
        }
        merged = dict(existing)
        for key in planning_keys:
            if key in scene:
                merged[key] = scene[key]
        return merged

    def _prune_empty_chapters_outside_canvas(self, project_id: str, canvas: dict[str, Any]) -> None:
        storage = self._require_storage()
        max_canvas_order = max([int(item.get("chapter_order") or 0) for item in self._canvas_chapters(canvas)] or [0])
        for row in sorted(storage.list_novel_chapters(project_id), key=lambda item: int(item["chapter_order"]), reverse=True):
            if int(row["chapter_order"]) <= max_canvas_order:
                continue
            if str(row["body"] or "").strip():
                continue
            if storage.list_novel_versions(row["id"]):
                continue
            storage.delete_novel_chapter(row["id"])
