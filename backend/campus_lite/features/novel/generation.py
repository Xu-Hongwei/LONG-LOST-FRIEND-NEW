from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...schemas import NovelChapter, NovelProjectResponse
from ...storage import Storage
from .config import NOVEL_GENERATION_TIMEOUT_MS


class NovelGenerationMixin:
    def _write_chapter_generation_progress(self, storage: Storage, chapter_id: str, progress: dict[str, Any]) -> None:
        try:
            chapter = storage.get_novel_chapter(chapter_id)
            if not chapter:
                return
            scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
            scene_card["generation_progress"] = progress
            storage.update_novel_chapter(chapter_id, {"scene_card": scene_card}, "system")
        except Exception:
            return

    async def generate_chapter(
        self,
        llm: Any,
        project_id: str,
        chapter_id: str | None,
        instruction: str,
        target_length: int,
        defer_postprocess: bool = False,
    ) -> tuple[NovelProjectResponse, NovelChapter]:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        if chapter_id:
            chapter = storage.get_novel_chapter(chapter_id)
            if not chapter or chapter["project_id"] != project_id:
                raise ValueError("Novel chapter not found")
            effective_instruction = self._usable_instruction(instruction) or str(chapter["goal"] or "").strip() or "承接前文，推进一个可验证的小目标。"
        else:
            effective_instruction = self._usable_instruction(instruction) or "承接前文，推进一个可验证的小目标。"
            chapter_id = storage.create_novel_chapter(project_id, "下一章", "承接前文，完成一个具体事件中的关系推进。", "", "", "drafting")
            chapter = storage.get_novel_chapter(chapter_id)
        assert chapter is not None
        scene_card: dict[str, Any] | None = None
        progress_payload: dict[str, Any] = {}

        def mark_progress(stage: str, percent: int, detail: str, source: str = "backend") -> None:
            nonlocal progress_payload, scene_card
            progress_payload = {
                "stage": stage,
                "percent": percent,
                "detail": detail,
                "source": source,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if isinstance(scene_card, dict):
                scene_card["generation_progress"] = progress_payload
            self._write_chapter_generation_progress(storage, chapter["id"], progress_payload)

        mark_progress("collecting", 10, "读取章节、画布、素材和上一章尾段")
        materials = storage.list_novel_materials(project_id)
        previous = storage.list_novel_chapters(project_id)
        mark_progress("state", 22, "本地重建截至上一章的 Novel State", "local")
        scene_card = self._chapter_scene_card(project, chapter, materials, previous, effective_instruction, target_length)
        scene_card["generation_progress"] = progress_payload
        mark_progress("beats", 32, "远程拆出 Scene Beats 和可见动作链", "remote")
        scene_beats, beat_source = await self._build_scene_beats(
            llm,
            project,
            chapter,
            materials,
            previous,
            effective_instruction,
            target_length,
            scene_card,
        )
        mark_progress(
            "beats",
            40,
            "场景节拍已返回" if beat_source == "remote" else "远程场景不可用，使用本地场景节拍",
            beat_source,
        )
        source = self._chapter_source(project, chapter, materials, previous, effective_instruction, target_length, scene_card, scene_beats)
        source_name = "remote"
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            mark_progress("drafting", 48, "远程生成当前章正文", "remote")
            text = await llm.chat_complete([
                {"role": "system", "content": self._chapter_system_prompt()},
                {"role": "user", "content": source},
            ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
            parsed = self._parse_chapter_response(text, target_length)
            mark_progress("local_check", 60, "本地检查内部字段、空正文和重复段落", "local")
            local_check = self._chapter_local_check(parsed.get("body", ""), target_length)
            if local_check["blockers"]:
                audit = {
                    "pass": False,
                    "hard_fail": True,
                    "rewrite_required": True,
                    "issues": local_check["blockers"],
                    "warnings": local_check["warnings"],
                    "rewrite_brief": "正文包含内部字段、内部编号、重复段落或明显元叙述，需要在保留事实的前提下重写为纯小说正文。",
                    "source": "local",
                }
            else:
                mark_progress("reviewing", 72, "远程审稿：检查事件、对白、选择和钩子", "remote")
                audit = await self._audit_chapter(llm, project, chapter, scene_card, scene_beats, parsed, target_length, local_check)
            rewrite_applied = False
            if self._audit_requires_rewrite(audit, target_length):
                mark_progress("rewriting", 82, "远程按审稿意见重写一次", "remote")
                rewrite_text = await llm.chat_complete([
                    {"role": "system", "content": self._chapter_system_prompt()},
                    {"role": "user", "content": self._rewrite_source(project, chapter, scene_card, scene_beats, parsed, audit, target_length)},
                ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
                parsed = self._parse_chapter_response(rewrite_text, target_length)
                rewrite_applied = True
                local_check = self._chapter_local_check(parsed.get("body", ""), target_length)
                if local_check["blockers"]:
                    raise ValueError("Chapter rewrite still failed local blockers: " + "; ".join(local_check["blockers"][:4]))
            else:
                mark_progress("rewriting", 82, "审稿通过，无需重写", "remote")
            audit = {**audit, "rewrite_applied": rewrite_applied}
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            source_name = "mock"
            mark_progress("fallback", 100, f"远程正文失败，已返回本地正文草稿：{type(exc).__name__}", "local")
            parsed = self._mock_chapter(project, chapter, materials, target_length, scene_card, scene_beats)
            audit = {"pass": False, "source": "fallback", "issues": [type(exc).__name__], "rewrite_applied": False}
        should_update_global_state = source_name != "mock"
        if should_update_global_state and not defer_postprocess:
            mark_progress("handoff", 88, "生成章节交接单并更新全局状态", "remote")
            handoff, handoff_source = await self._build_chapter_handoff(llm, project, chapter, scene_card, scene_beats, parsed)
            postprocess = {"status": "done", "mode": "sync", "updated_at": datetime.now(timezone.utc).isoformat()}
        elif should_update_global_state:
            handoff, handoff_source = {}, "pending"
            postprocess = {
                "status": "pending",
                "mode": "background",
                "steps": ["handoff", "novel_state", "rolling_canvas"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            mark_progress("handoff", 88, "正文已返回，后台交接排队中", "backend")
        else:
            handoff, handoff_source = {}, "skipped_mock"
            postprocess = {"status": "skipped", "reason": "mock_fallback", "updated_at": datetime.now(timezone.utc).isoformat()}
            audit = {
                **audit,
                "global_state_skipped": True,
                "skip_reason": "mock fallback is not trusted for Novel State, handoff, or rolling canvas",
            }
        next_scene_card = {
            **scene_card,
            "generation_instruction": effective_instruction,
            "scene_beats": scene_beats,
            "beat_source": beat_source,
            "chapter_audit": audit,
            "chapter_handoff": handoff,
            "handoff_source": handoff_source,
            "postprocess": postprocess,
            "generation_progress": progress_payload,
        }
        storage.update_novel_chapter(
            chapter["id"],
            {
                "title": parsed["title"],
                "summary": parsed["summary"],
                "body": parsed["body"],
                "status": "draft",
                "scene_card": next_scene_card,
                "source_material_ids": parsed["source_material_ids"],
            },
            source_name,
        )
        if should_update_global_state and not defer_postprocess:
            self._mark_following_chapters_affected(project_id, int(chapter["chapter_order"]))
            await self._update_novel_state_after_chapter(project_id, llm, project, chapter, parsed, handoff)
            self._update_canvas_from_completed_chapter(project_id, chapter, next_scene_card, parsed)
            mark_progress("replan", 96, "同步滚动重规划后续两章画布和场景卡", "remote")
            await self.extend_canvas(
                llm,
                project_id,
                int(chapter["chapter_order"]),
                2,
                "当前章节已经完成。请基于最新 Novel State 和本章交接单，只滚动重规划后续两章。",
            )
            mark_progress("done", 100, "正文、状态和后续画布已更新", "backend")
        else:
            self._mark_following_chapters_affected(project_id, int(chapter["chapter_order"]))
            self.rebuild_novel_state_from_latest_chapters_sync(project_id)
        updated = storage.get_novel_chapter(chapter["id"])
        assert updated is not None
        return self.project_response(project_id), self._chapter_from_row(updated, include_versions=True)

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
