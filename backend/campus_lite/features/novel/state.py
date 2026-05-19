from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import NOVEL_PLANNING_TIMEOUT_MS


class NovelStateMixin:
    async def _update_novel_state_after_chapter(
        self,
        project_id: str,
        llm: Any,
        project: Any,
        chapter: Any,
        parsed: dict[str, Any],
        handoff: dict[str, Any],
    ) -> None:
        storage = self._require_storage()
        latest_project = storage.get_novel_project(project_id) or project
        chapter_order = int(chapter["chapter_order"])
        previous_state = self._novel_state_until(latest_project, chapter_order - 1)
        next_state = self._append_chapter_state_delta(previous_state, chapter, parsed, handoff)
        storage.update_novel_project(project_id, {"novel_state": next_state})

    def _empty_novel_state(self, title: str) -> dict[str, Any]:
        return {
            "version": 1,
            "title": title,
            "global_summary": "",
            "confirmed_facts": [],
            "character_states": [],
            "relationship_states": [],
            "open_threads": [],
            "resolved_threads": [],
            "chapter_handoffs": [],
            "last_completed_chapter_order": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _append_chapter_state_delta(
        self,
        previous_state: dict[str, Any],
        chapter: Any,
        parsed: dict[str, Any],
        handoff: dict[str, Any],
    ) -> dict[str, Any]:
        order = int(chapter["chapter_order"])
        chapter_title = str(parsed.get("title") or chapter["title"] or "")[:120]
        summary = self._clean_material_text(str(parsed.get("summary") or ""))[:1200]
        next_handoff = {
            **handoff,
            "chapter_order": order,
            "chapter_title": chapter_title,
        }

        def list_value(key: str) -> list[str]:
            value = next_handoff.get(key)
            if isinstance(value, list):
                return [self._clean_material_text(str(item))[:260] for item in value if str(item).strip()]
            return [self._clean_material_text(str(value))[:260]] if str(value or "").strip() else []

        previous_handoffs = [
            item for item in previous_state.get("chapter_handoffs", [])
            if isinstance(item, dict) and self._coerce_int(item.get("chapter_order"), 0, 0, 999) < order
        ]
        previous_summary = self._clean_material_text(str(previous_state.get("global_summary") or ""))
        summary_line = f"第{order}章：{summary}" if summary else ""
        return {
            **previous_state,
            "global_summary": self._clean_material_text(" ".join(item for item in [previous_summary, summary_line] if item))[:1400],
            "confirmed_facts": self._unique_short_list(list(previous_state.get("confirmed_facts", [])) + list_value("happened"), 16),
            "relationship_states": self._unique_short_list(list(previous_state.get("relationship_states", [])) + list_value("relationship_delta"), 16),
            "open_threads": self._unique_short_list(
                list(previous_state.get("open_threads", [])) + list_value("open_threads") + list_value("next_must_continue"),
                16,
            ),
            "resolved_threads": self._unique_short_list(list(previous_state.get("resolved_threads", [])) + list_value("resolved_threads"), 16),
            "chapter_handoffs": [*previous_handoffs, next_handoff][-8:],
            "last_completed_chapter_order": order,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _rebuild_novel_state_from_latest_chapters(self, project_id: str, llm: Any) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        base_state = self._empty_novel_state(project["title"])
        trusted_entries = self._latest_trusted_chapter_state_entries(project_id)
        next_state = self._merge_novel_state_entries(base_state, trusted_entries)
        try:
            if trusted_entries and llm.configured():
                text = await llm.chat_complete([
                    {"role": "system", "content": self._novel_state_system_prompt()},
                    {"role": "user", "content": self._novel_state_rebuild_source(project, base_state, trusted_entries)},
                ], timeout_ms=NOVEL_PLANNING_TIMEOUT_MS, response_format={"type": "json_object"})
                next_state = self._parse_novel_state(text, next_state)
                next_state["chapter_handoffs"] = [entry["handoff"] for entry in trusted_entries][-8:]
                next_state["last_completed_chapter_order"] = trusted_entries[-1]["chapter_order"]
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
        storage.update_novel_project(project_id, {"novel_state": next_state})

    def rebuild_novel_state_from_latest_chapters_sync(self, project_id: str) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        base_state = self._empty_novel_state(project["title"])
        entries = self._latest_trusted_chapter_state_entries(project_id)
        storage.update_novel_project(project_id, {"novel_state": self._merge_novel_state_entries(base_state, entries)})

    def mark_chapter_revision_boundary(self, project_id: str, chapter_order: int) -> None:
        self._mark_following_chapters_affected(project_id, chapter_order)
        self.rebuild_novel_state_from_latest_chapters_sync(project_id)

    def remove_chapter_from_story_canvas(self, project_id: str, deleted_order: int) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            return
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        if not canvas:
            return
        removed_chapter_ids = {
            str(item.get("id") or "")
            for item in self._canvas_chapters(canvas)
            if int(item.get("chapter_order") or 0) == deleted_order
        }
        if not removed_chapter_ids and not self._canvas_chapters(canvas):
            return
        next_canvas = json.loads(json.dumps(canvas, ensure_ascii=False))
        next_chapters: list[dict[str, Any]] = []
        for item in self._canvas_chapters(next_canvas):
            order = int(item.get("chapter_order") or 0)
            if order == deleted_order:
                continue
            if order > deleted_order:
                item["chapter_order"] = order - 1
            next_chapters.append(item)
        next_canvas["chapters"] = next_chapters
        next_canvas["scenes"] = [
            item for item in self._canvas_scenes(next_canvas)
            if str(item.get("chapter_id") or "") not in removed_chapter_ids
        ]
        for act in next_canvas.get("acts", []) if isinstance(next_canvas.get("acts"), list) else []:
            if isinstance(act, dict):
                chapter_ids = act.get("chapter_ids")
                if isinstance(chapter_ids, list):
                    act["chapter_ids"] = [item for item in chapter_ids if str(item) not in removed_chapter_ids]
        next_canvas["threads"] = [
            item for item in next_canvas.get("threads", []) if isinstance(item, dict)
            and str(item.get("setup_chapter_id") or "") not in removed_chapter_ids
            and str(item.get("payoff_chapter_id") or "") not in removed_chapter_ids
        ] if isinstance(next_canvas.get("threads"), list) else []
        diagnostics = self._json_dict(next_canvas.get("diagnostics"))
        next_canvas["diagnostics"] = {
            **diagnostics,
            "deleted_chapter_order": deleted_order,
            "deleted_canvas_chapter_ids": [item for item in removed_chapter_ids if item],
            "cleanup": "chapter_deleted",
        }
        storage.update_novel_project(project_id, {"story_canvas": next_canvas, "outline": self._canvas_outline(next_canvas)})

    def _mark_following_chapters_affected(self, project_id: str, chapter_order: int) -> None:
        storage = self._require_storage()
        for row in storage.list_novel_chapters(project_id):
            if int(row["chapter_order"]) <= chapter_order:
                continue
            if not str(row["body"] or "").strip():
                continue
            if str(row["status"] or "") == "locked":
                continue
            scene_card = self._json_dict(row["scene_card_json"] if "scene_card_json" in row.keys() else "{}")
            scene_card["affected_by_chapter_order"] = chapter_order
            scene_card["affected_reason"] = f"第{chapter_order}章已更新，后续章节需要重新确认连续性。"
            storage.update_novel_chapter(row["id"], {"status": "affected", "scene_card": scene_card}, "system")

    def _novel_state_until(self, project: Any, cutoff_order: int) -> dict[str, Any]:
        base_state = self._empty_novel_state(project["title"])
        if cutoff_order <= 0:
            return base_state
        entries = self._latest_trusted_chapter_state_entries(project["id"], cutoff_order)
        return self._merge_novel_state_entries(base_state, entries)

    def _latest_trusted_chapter_state_entries(self, project_id: str, cutoff_order: int | None = None) -> list[dict[str, Any]]:
        storage = self._require_storage()
        entries: list[dict[str, Any]] = []
        for row in sorted(storage.list_novel_chapters(project_id), key=lambda item: int(item["chapter_order"])):
            order = int(row["chapter_order"])
            if cutoff_order is not None and order > cutoff_order:
                break
            if order != len(entries) + 1:
                break
            if str(row["status"] or "") == "affected":
                break
            latest_versions = storage.list_novel_versions(row["id"])
            if not str(row["body"] or "").strip():
                break
            scene_card = self._json_dict(row["scene_card_json"] if "scene_card_json" in row.keys() else "{}")
            active_version_id = str(scene_card.get("active_version_id") or "").strip()
            active_version = storage.get_novel_version(active_version_id) if active_version_id else (latest_versions[0] if latest_versions else None)
            latest_source = str(active_version["source"] if active_version else "").strip()
            if latest_source in {"mock", "manual", "restore", "create", "system"}:
                break
            state_delta = self._json_dict(active_version["state_delta_json"] if active_version and "state_delta_json" in active_version.keys() else "{}")
            handoff = state_delta.get("chapter_handoff") if isinstance(state_delta.get("chapter_handoff"), dict) else {}
            if not handoff:
                handoff = scene_card.get("chapter_handoff") if isinstance(scene_card.get("chapter_handoff"), dict) else {}
            handoff_source = str(state_delta.get("handoff_source") or scene_card.get("handoff_source") or "").strip()
            if not handoff or handoff_source in {"skipped_mock", "cleaned_mock"}:
                break
            entries.append({
                "chapter_order": order,
                "chapter_title": str(row["title"] or "")[:120],
                "summary": str(row["summary"] or "")[:1200],
                "latest_source": latest_source,
                "handoff_source": handoff_source,
                "chapter_version_id": str(active_version["id"] if active_version else active_version_id),
                "state_delta": state_delta,
                "handoff": {
                    **handoff,
                    "chapter_order": order,
                    "chapter_title": str(row["title"] or "")[:120],
                    "chapter_version_id": str(active_version["id"] if active_version else active_version_id),
                },
            })
        return entries

    def _merge_novel_state_entries(self, base_state: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
        if not entries:
            return {
                **base_state,
                "chapter_handoffs": [],
                "last_completed_chapter_order": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        handoffs = [entry["handoff"] for entry in entries]
        summaries = [
            f"第{entry['chapter_order']}章：{entry.get('summary') or '已完成章节。'}"
            for entry in entries
            if str(entry.get("summary") or "").strip()
        ]
        confirmed = list(base_state.get("confirmed_facts", []))
        relationships = list(base_state.get("relationship_states", []))
        open_threads = list(base_state.get("open_threads", []))
        resolved = list(base_state.get("resolved_threads", []))
        for handoff in handoffs:
            confirmed.extend(handoff.get("happened", []) if isinstance(handoff.get("happened"), list) else [])
            relationships.extend(handoff.get("relationship_delta", []) if isinstance(handoff.get("relationship_delta"), list) else [])
            open_threads.extend(handoff.get("open_threads", []) if isinstance(handoff.get("open_threads"), list) else [])
            open_threads.extend(handoff.get("next_must_continue", []) if isinstance(handoff.get("next_must_continue"), list) else [])
            resolved.extend(handoff.get("resolved_threads", []) if isinstance(handoff.get("resolved_threads"), list) else [])
        return {
            **base_state,
            "global_summary": self._clean_material_text(" ".join(summaries))[:1400] or base_state.get("global_summary", ""),
            "confirmed_facts": self._unique_short_list(confirmed, 16),
            "relationship_states": self._unique_short_list(relationships, 16),
            "open_threads": self._unique_short_list(open_threads, 16),
            "resolved_threads": self._unique_short_list(resolved, 16),
            "chapter_handoffs": handoffs[-8:],
            "last_completed_chapter_order": entries[-1]["chapter_order"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _novel_state_rebuild_source(
        self,
        project: Any,
        base_state: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> str:
        return "\n\n".join([
            "[作品]",
            f"{project['title']}｜{project['genre']}｜{project['tone']}",
            "[基础 Story Bible 状态]",
            json.dumps({
                "confirmed_facts": base_state.get("confirmed_facts", []),
                "relationship_states": base_state.get("relationship_states", []),
                "open_threads": base_state.get("open_threads", []),
            }, ensure_ascii=False),
            "[最新可信章节版本]",
            json.dumps(entries, ensure_ascii=False)[:12000],
            "[更新规则]",
            "请只基于这些最新可信章节版本重建 Novel State；不要沿用旧状态里的重复或冲突内容。"
            "global_summary 用 500-900 字以内概括截至最后一个可信章节已经发生的主线。"
            "open_threads 只保留未解决线索；resolved_threads 只放明确回收的线索。"
            "chapter_handoffs 必须对应输入里的章节交接单，不要新增未发生剧情。",
        ])

    def _novel_state_system_prompt(self) -> str:
        return (
            "你是长篇小说全局状态管理员。根据最新可信章节版本、章节摘要和章节交接单，重建长期摘要。"
            "只保留已经发生的事实和仍需追踪的线索，不沿用旧状态里的重复或冲突内容，不写正文，不扩写剧情。"
            "输出 JSON 对象，字段：global_summary, confirmed_facts, character_states, relationship_states, open_threads, resolved_threads, chapter_handoffs, last_completed_chapter_order。"
        )

    def _parse_novel_state(self, text: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raw = self._load_llm_json_object(text, "novel_state")
        state = dict(fallback)
        state["global_summary"] = self._clean_material_text(str(raw.get("global_summary") or state.get("global_summary") or ""))[:1400]
        for key in ["confirmed_facts", "character_states", "relationship_states", "open_threads", "resolved_threads"]:
            value = raw.get(key)
            if isinstance(value, list):
                state[key] = [self._clean_material_text(str(item))[:260] for item in value if str(item).strip()][:16]
        if isinstance(raw.get("chapter_handoffs"), list):
            state["chapter_handoffs"] = raw["chapter_handoffs"][-8:]
        state["last_completed_chapter_order"] = self._coerce_int(raw.get("last_completed_chapter_order"), int(state.get("last_completed_chapter_order") or 0), 0, 999)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return state

    def _unique_short_list(self, values: list[Any], limit: int) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = self._clean_material_text(str(value))[:260]
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break
        return result

