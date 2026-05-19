from __future__ import annotations

from typing import Any

from ...schemas import NovelProjectResponse
from .config import NOVEL_CANVAS_TIMEOUT_MS


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
        canvas = self._default_extension_canvas(project, {}, 0, 4)
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._canvas_extend_system_prompt()},
                {"role": "user", "content": self._initial_canvas_source(project, story_bible, materials)},
            ], timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"})
            canvas = self._parse_canvas_response(text, canvas)
            canvas["diagnostics"] = {**self._json_dict(canvas.get("diagnostics")), "source": "remote", "mode": "initial_rolling"}
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            canvas["diagnostics"] = {
                **self._json_dict(canvas.get("diagnostics")),
                "source": "local",
                "mode": "initial_rolling",
                "fallback_reason": type(exc).__name__,
                "fallback_detail": str(exc)[:240],
            }
        canvas = self._story_canvas_with_materials(canvas, materials)
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        self._prune_empty_chapters_outside_canvas(project_id, canvas)
        self._sync_chapters_from_canvas(project_id, canvas)
        return self.project_response(project_id)

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
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._canvas_extend_system_prompt()},
                {"role": "user", "content": self._canvas_extend_source(project, current_canvas, db_chapters, from_order, count, instruction)},
            ], timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"})
            extension = self._parse_canvas_response(text, fallback)
            extension["diagnostics"] = {**self._json_dict(extension.get("diagnostics")), "source": "remote", "mode": "rolling_extend"}
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
                },
            }
        canvas = self._merge_extended_canvas(current_canvas, extension, from_order)
        canvas = self._story_canvas_with_materials(canvas, storage.list_novel_materials(project_id))
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        self._prune_empty_chapters_outside_canvas(project_id, canvas)
        self._sync_chapters_from_canvas(project_id, canvas, start_order=from_order + 1)
        return self.project_response(project_id)
