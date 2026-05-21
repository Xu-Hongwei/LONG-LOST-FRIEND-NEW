from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class NovelGenerationPostprocessMixin:
    async def finalize_chapter_postprocess(self, llm: Any, project_id: str, chapter_id: str) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        chapter = storage.get_novel_chapter(chapter_id)
        if not project or not chapter:
            return
        scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
        postprocess = self._json_dict(scene_card.get("postprocess"))
        if postprocess.get("status") in {"done", "skipped"}:
            return
        scene_card["postprocess"] = {
            **postprocess,
            "status": "running",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        scene_card["generation_progress"] = {
            "stage": "handoff",
            "percent": 88,
            "detail": "后台生成章节交接单并更新全局状态",
            "source": "backend",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        storage.update_novel_chapter(chapter_id, {"scene_card": scene_card}, "system")
        try:
            project = storage.get_novel_project(project_id)
            chapter = storage.get_novel_chapter(chapter_id)
            if not project or not chapter:
                return
            scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
            scene_beats = scene_card.get("scene_beats") if isinstance(scene_card.get("scene_beats"), list) else []
            parsed = {
                "title": chapter["title"],
                "summary": chapter["summary"],
                "body": chapter["body"],
                "source_material_ids": self._json_list(chapter["source_material_ids_json"] if "source_material_ids_json" in chapter.keys() else "[]"),
            }
            handoff, handoff_source = await self._build_chapter_handoff(llm, project, chapter, scene_card, scene_beats, parsed)
            scene_card = {
                **scene_card,
                "chapter_handoff": handoff,
                "handoff_source": handoff_source,
                "postprocess": {
                    "status": "handoff_done",
                    "mode": "background",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "generation_progress": {
                    "stage": "handoff",
                    "percent": 92,
                    "detail": "章节交接单已生成，正在更新 Novel State",
                    "source": "backend",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            storage.update_novel_chapter(
                chapter_id,
                {
                    "title": parsed["title"],
                    "summary": parsed["summary"],
                    "body": parsed["body"],
                    "scene_card": scene_card,
                    "source_material_ids": parsed["source_material_ids"],
                },
                "remote",
            )
            self._mark_following_chapters_affected(project_id, int(chapter["chapter_order"]))
            await self._update_novel_state_after_chapter(project_id, llm, project, chapter, parsed, handoff)
            self._update_canvas_from_completed_chapter(project_id, chapter, scene_card, parsed)
            latest_for_replan = storage.get_novel_chapter(chapter_id)
            if latest_for_replan:
                latest_scene_card = self._json_dict(latest_for_replan["scene_card_json"] if "scene_card_json" in latest_for_replan.keys() else "{}")
                latest_scene_card["generation_progress"] = {
                    "stage": "replan",
                    "percent": 96,
                    "detail": "后台滚动重规划后续两章画布和场景卡",
                    "source": "backend",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                storage.update_novel_chapter(chapter_id, {"scene_card": latest_scene_card}, "system")
            await self.extend_canvas(
                llm,
                project_id,
                int(chapter["chapter_order"]),
                2,
                "当前章节已经完成。请基于最新 Novel State 和本章交接单，只滚动重规划后续两章。",
            )
            latest = storage.get_novel_chapter(chapter_id)
            if latest:
                latest_scene_card = self._json_dict(latest["scene_card_json"] if "scene_card_json" in latest.keys() else "{}")
                latest_scene_card["postprocess"] = {
                    "status": "done",
                    "mode": "background",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                latest_scene_card["generation_progress"] = {
                    "stage": "done",
                    "percent": 100,
                    "detail": "正文、状态和后续画布已更新",
                    "source": "backend",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                storage.update_novel_chapter(chapter_id, {"scene_card": latest_scene_card}, "system")
        except Exception as exc:
            latest = storage.get_novel_chapter(chapter_id)
            if latest:
                latest_scene_card = self._json_dict(latest["scene_card_json"] if "scene_card_json" in latest.keys() else "{}")
                latest_scene_card["postprocess"] = {
                    **self._json_dict(latest_scene_card.get("postprocess")),
                    "status": "failed",
                    "error": type(exc).__name__,
                    "detail": str(exc)[:240],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                latest_scene_card["generation_progress"] = {
                    "stage": "failed",
                    "percent": 100,
                    "detail": f"后台交接或滚动画布失败：{type(exc).__name__}",
                    "source": "backend",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                storage.update_novel_chapter(chapter_id, {"scene_card": latest_scene_card}, "system")
            llm.last_chat_error = type(exc).__name__
