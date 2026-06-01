from __future__ import annotations

import asyncio
from typing import Any

from ...schemas import NovelProjectResponse
from .config import NOVEL_CANVAS_TIMEOUT_MS
from .event_pool import apply_story_event_pool_delta, bind_story_event_pool_to_chapters


class NovelCanvasMixin:
    async def build_canvas(self, llm: Any, project_id: str) -> NovelProjectResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        initial_chapters = [row for row in storage.list_novel_chapters(project_id) if int(row["chapter_order"]) <= 4]
        if any(storage.list_novel_versions(row["id"]) for row in initial_chapters):
            raise ValueError("Cannot rebuild initial canvas while the first four chapters still have versions")
        story_bible = self._json_dict(project["story_bible_json"])
        materials = storage.list_novel_materials(project_id)
        reset_project = self._project_with_reset_canvas(project)
        fallback_canvas = self._default_extension_canvas(reset_project, {}, 0, 4)
        canvas = fallback_canvas
        event_pool_delta: dict[str, Any] = {}
        event_pool_delta_error = ""
        parallel_event_pool_update = False
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            canvas_messages = [
                {"role": "system", "content": self._canvas_extend_system_prompt()},
                {"role": "user", "content": self._initial_canvas_source(reset_project, story_bible, materials)},
            ]
            event_pool_messages = [
                {"role": "system", "content": self._event_pool_delta_system_prompt()},
                {
                    "role": "user",
                    "content": self._event_pool_delta_source(
                        reset_project,
                        fallback_canvas,
                        initial_chapters,
                        0,
                        4,
                        "Generate the initial project event pool. Return 6 to 10 concrete add candidates grounded in the project genre, tone, worldview, relationship setup, Story Bible, and opening chapter direction. Prefer replacing generic setting_profile placeholders while keeping character story_seed_pool only as translatable flavor.",
                    ),
                },
            ]
            parallel_event_pool_update = True
            canvas_result, event_pool_result = await asyncio.gather(
                llm.chat_complete(canvas_messages, timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"}),
                llm.chat_complete(event_pool_messages, timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"}),
                return_exceptions=True,
            )
            if isinstance(event_pool_result, Exception):
                event_pool_delta_error = type(event_pool_result).__name__
            else:
                try:
                    event_pool_delta = self._parse_event_pool_delta_response(str(event_pool_result))
                except Exception as delta_exc:
                    event_pool_delta_error = type(delta_exc).__name__
            if isinstance(canvas_result, Exception):
                raise canvas_result
            text = str(canvas_result)
            canvas = self._parse_canvas_response(text, canvas)
            if event_pool_delta:
                setting_type = str(
                    self._json_dict(canvas.get("diagnostics")).get("setting_type")
                    or self._json_dict(fallback_canvas.get("diagnostics")).get("setting_type")
                    or "modern_daily"
                )
                canvas["event_pool"] = bind_story_event_pool_to_chapters(
                    apply_story_event_pool_delta(canvas.get("event_pool"), event_pool_delta, setting_type),
                    self._canvas_chapters(canvas),
                    setting_type,
                )
            canvas["diagnostics"] = {
                **self._json_dict(canvas.get("diagnostics")),
                "source": "remote",
                "mode": "initial_rolling",
                "event_pool_reset": True,
                "event_pool_update_source": "remote" if event_pool_delta else "none",
                "event_pool_update_error": event_pool_delta_error,
                "parallel_event_pool_update": parallel_event_pool_update,
            }
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            if event_pool_delta:
                setting_type = str(self._json_dict(canvas.get("diagnostics")).get("setting_type") or "modern_daily")
                canvas["event_pool"] = bind_story_event_pool_to_chapters(
                    apply_story_event_pool_delta(canvas.get("event_pool"), event_pool_delta, setting_type),
                    self._canvas_chapters(canvas),
                    setting_type,
                )
            canvas["diagnostics"] = {
                **self._json_dict(canvas.get("diagnostics")),
                "source": "local",
                "mode": "initial_rolling",
                "event_pool_reset": True,
                "fallback_reason": type(exc).__name__,
                "fallback_detail": str(exc)[:240],
                "event_pool_update_source": "remote" if event_pool_delta else "none",
                "event_pool_update_error": event_pool_delta_error,
                "parallel_event_pool_update": parallel_event_pool_update,
            }
        canvas = self._story_canvas_with_materials(canvas, materials)
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        self._prune_empty_chapters_outside_canvas(project_id, canvas)
        self._sync_chapters_from_canvas(project_id, canvas)
        return self.project_response(project_id)

    def _project_with_reset_canvas(self, project: Any) -> Any:
        try:
            data = {key: project[key] for key in project.keys()}
        except Exception:
            data = dict(project) if isinstance(project, dict) else {}
        data["story_canvas_json"] = "{}"
        return data

    async def extend_canvas(
        self,
        llm: Any,
        project_id: str,
        from_chapter_order: int | None = None,
        count: int = 4,
        instruction: str = "",
    ) -> NovelProjectResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        current_canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        current_chapters = self._canvas_chapters(current_canvas)
        db_chapters = storage.list_novel_chapters(project_id)
        max_canvas_order = max([int(item.get("chapter_order") or 0) for item in current_chapters] or [0])
        max_written_order = max([
            int(row["chapter_order"])
            for row in db_chapters
            if str(row["body"] or "").strip()
        ] or [0])
        if from_chapter_order is not None:
            # Chapter generation is a rolling window anchored to the chapter the
            # user just wrote. Do not jump past stale future drafts that may be
            # present from earlier experiments or regenerations.
            from_order = from_chapter_order
        else:
            from_order = max(max_canvas_order, max_written_order)
        from_order = max(0, min(int(from_order), 999))
        count = max(2, min(int(count), 6))
        fallback = self._default_extension_canvas(project, current_canvas, from_order, count)
        event_pool_delta: dict[str, Any] = {}
        event_pool_delta_error = ""
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            canvas_messages = [
                {"role": "system", "content": self._canvas_extend_system_prompt()},
                {"role": "user", "content": self._canvas_extend_source(project, current_canvas, db_chapters, from_order, count, instruction)},
            ]
            event_pool_messages = [
                {"role": "system", "content": self._event_pool_delta_system_prompt()},
                {"role": "user", "content": self._event_pool_delta_source(project, current_canvas, db_chapters, from_order, count, instruction)},
            ]
            canvas_result, event_pool_result = await asyncio.gather(
                llm.chat_complete(canvas_messages, timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"}),
                llm.chat_complete(event_pool_messages, timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"}),
                return_exceptions=True,
            )
            if isinstance(event_pool_result, Exception):
                event_pool_delta_error = type(event_pool_result).__name__
            else:
                try:
                    event_pool_delta = self._parse_event_pool_delta_response(str(event_pool_result))
                except Exception as delta_exc:
                    event_pool_delta_error = type(delta_exc).__name__
            if isinstance(canvas_result, Exception):
                raise canvas_result
            text = str(canvas_result)
            extension = self._parse_canvas_response(text, fallback)
            if event_pool_delta:
                extension["event_pool_delta"] = self._merge_event_pool_deltas(extension.get("event_pool_delta"), event_pool_delta)
            extension["diagnostics"] = {
                **self._json_dict(extension.get("diagnostics")),
                "source": "remote",
                "mode": "rolling_extend",
                "event_pool_update_source": "remote" if event_pool_delta else "none",
                "event_pool_update_error": event_pool_delta_error,
                "parallel_event_pool_update": True,
            }
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            extension = {
                **fallback,
                "diagnostics": {
                    **self._json_dict(fallback.get("diagnostics")),
                    "source": "local",
                    "mode": "rolling_extend",
                    "fallback_reason": type(exc).__name__,
                    "fallback_detail": str(exc)[:240],
                    "event_pool_update_source": "none",
                    "event_pool_update_error": event_pool_delta_error,
                    "parallel_event_pool_update": False,
                },
            }
            if event_pool_delta:
                extension["event_pool_delta"] = event_pool_delta
                extension["diagnostics"]["event_pool_update_source"] = "remote"
        materials = storage.list_novel_materials(project_id)
        character_card = None
        try:
            character_id = str(project["character_id"] or "").strip()
            visitor_id = str(project["visitor_id"] or "").strip()
            if character_id:
                character_card = storage.get_character_card(character_id, visitor_id)
        except Exception:
            character_card = None
        scoring_context = {
            "project": {
                "title": project["title"],
                "genre": project["genre"],
                "tone": project["tone"],
                "protagonist": project["protagonist"],
                "worldview": project["worldview"],
                "relationship_setup": project["relationship_setup"],
                "outline": project["outline"],
            },
            "character": character_card or {},
            "story_bible": self._json_dict(project["story_bible_json"]),
            "materials": materials,
            "novel_state": self._novel_state_until(project, from_order),
            "recent_chapters": db_chapters,
            "bind_after_order": from_order,
        }
        canvas = self._merge_extended_canvas(current_canvas, extension, from_order, scoring_context)
        canvas = self._story_canvas_with_materials(canvas, materials)
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        self._prune_empty_chapters_outside_canvas(project_id, canvas)
        self._sync_chapters_from_canvas(project_id, canvas, start_order=from_order + 1)
        return self.project_response(project_id)
