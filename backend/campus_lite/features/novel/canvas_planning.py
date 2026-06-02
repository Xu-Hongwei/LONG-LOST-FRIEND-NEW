from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .event_pool import (
    advance_story_event_pool,
    apply_story_event_pool_delta,
    bind_story_event_pool_to_chapters,
    normalize_story_event_pool,
    story_event_for_order,
)
from .progression import chapter_progression_defaults, normalize_story_progression
from .setting_profiles import infer_novel_setting_type, novel_setting_profile


class NovelCanvasPlanningMixin:
    def _default_extension_canvas(
        self,
        project: Any,
        current_canvas: dict[str, Any],
        from_order: int,
        count: int,
    ) -> dict[str, Any]:
        novel_state = self._novel_state_until(project, from_order)
        start = from_order + 1
        act_id = f"rolling_act_{start}_{start + count - 1}"
        open_threads = [str(item) for item in novel_state.get("open_threads", []) if str(item).strip()]
        anchor = open_threads[0] if open_threads else "上一次被打断的话题还没有真正说完。"
        setting_type = infer_novel_setting_type(project)
        profile = novel_setting_profile(setting_type)
        progression_canvas = normalize_story_progression(current_canvas, project)
        event_pool = normalize_story_event_pool(current_canvas.get("event_pool"), setting_type)
        chapters: list[dict[str, Any]] = []
        scenes: list[dict[str, Any]] = []
        titles = profile["titles"]
        for offset in range(count):
            order = start + offset
            chapter_id = f"canvas_ch_{order}"
            scene_id = f"scene_{order}"
            title = titles[offset % len(titles)]
            pool_event = story_event_for_order(event_pool, order, setting_type)
            place = pool_event.get("place") or profile["places"][offset % len(profile["places"])]
            event = pool_event.get("event") or profile["events"][offset % len(profile["events"])]
            ending = pool_event.get("hook") or profile["endings"][offset % len(profile["endings"])]
            chapters.append({
                "id": chapter_id,
                "act_id": act_id,
                "chapter_order": order,
                "event_pool_id": str(pool_event.get("id") or ""),
                "title": f"第{order}章 {title}",
                "goal": f"承接“{anchor[:70]}”，本章把场面放在{place}：{event}主角需要先处理眼前麻烦，却被时间、旁人或信息差打断；主角做出一个不越界的小选择，让两人多一件可回望的共同经历。",
                "external_event": event,
                "trigger_event": event,
                "immediate_reaction": "主角先处理眼前的小麻烦，没有急着解释自己的在意。",
                "obstacle_escalation": "旁人的催促、时间限制或突发变化让他们不能把话说完整。",
                "counterpart_reaction": "对方没有追问，只用一个具体动作帮她把场面接住。",
                "character_choice": "主角没有立刻退开，而是主动完成一个小选择。",
                "scene_consequence": "两人多了一件只有彼此知道的小事。",
                "relationship_shift": "从可以聊天推进到能一起处理小麻烦。",
                "ending_hook": ending,
                "target_length": 1800,
                "status": "planned",
                "emotion_curve": "克制 -> 小混乱 -> 被接住 -> 留下未完问题",
                "scene_ids": [scene_id],
            })
            chapters[-1].update(chapter_progression_defaults(chapters[-1], progression_canvas, project, order))
            scenes.append({
                "id": scene_id,
                "chapter_id": chapter_id,
                "scene_order": 1,
                "current_scene": place,
                "pov": f"第三人称限知，{project['protagonist']}感受靠前。",
                "present_characters": f"{project['protagonist']}、对方、路过同学",
                "surface_event": event,
                "character_desire": "她想把眼前的小麻烦处理得自然一点，也想确认对方是否还记得上一章留下的话。",
                "tension": "时间限制和旁人打断让她不能直接问出口。",
                "required_facts": [anchor[:220]],
                "forbidden_progress": ["不突然表白", "不跳过慢速靠近", "不重复已写的初次偶遇"],
                "ending_beat": ending,
                "linked_material_ids": [],
            })
        return {
            "version": 1,
            "mode": "story_canvas",
            "story_promise": progression_canvas.get("story_promise", {}),
            "progression_protocol": progression_canvas.get("progression_protocol", {}),
            "event_pool": event_pool,
            "acts": [{"id": act_id, "order": start, "title": f"第{start}-{start + count - 1}章滚动小弧线", "purpose": "承接已写正文，规划下一组局部关系推进。", "chapter_ids": [item["id"] for item in chapters]}],
            "chapters": chapters,
            "scenes": scenes,
            "threads": [
                {
                    "id": f"thread_rolling_{start}",
                    "kind": "relationship",
                    "label": "未说完的话继续靠近",
                    "setup_chapter_id": chapters[0]["id"],
                    "payoff_chapter_id": chapters[-1]["id"],
                    "status": "active",
                    "notes": anchor[:300],
                }
            ],
            "quality_rules": ["后续章节必须承接上一章交接单，不重复已发生事件。"],
            "diagnostics": {"source": "local", "mode": "rolling_extend"},
        }

    def _update_canvas_from_completed_chapter(
        self,
        project_id: str,
        chapter: Any,
        scene_card: dict[str, Any],
        parsed: dict[str, Any],
    ) -> None:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            return
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        if not canvas:
            return
        order = int(chapter["chapter_order"])
        next_canvas = json.loads(json.dumps(canvas, ensure_ascii=False))
        canvas_chapter = next((item for item in self._canvas_chapters(next_canvas) if int(item.get("chapter_order") or 0) == order), None)
        if not canvas_chapter:
            canvas_chapter = {
                "id": f"canvas_ch_{order}",
                "act_id": (next_canvas.get("acts") or [{}])[0].get("id", "act_1") if isinstance(next_canvas.get("acts"), list) else "act_1",
                "chapter_order": order,
                "title": str(parsed.get("title") or chapter["title"] or f"第{order}章"),
                "goal": str(chapter["goal"] or parsed.get("summary") or ""),
                "scene_ids": [],
            }
            next_canvas.setdefault("chapters", []).append(canvas_chapter)
        canvas_chapter["title"] = str(parsed.get("title") or canvas_chapter.get("title") or chapter["title"])
        canvas_chapter["goal"] = str(chapter["goal"] or canvas_chapter.get("goal") or parsed.get("summary") or "")
        canvas_chapter["status"] = "complete"
        canvas_chapter["completed_summary"] = str(parsed.get("summary") or "")[:1200]
        canvas_chapter["actual_word_count"] = self._count_cjk_words(str(parsed.get("body") or ""))
        canvas_chapter["completed_at"] = datetime.now(timezone.utc).isoformat()

        scene = self._canvas_scene_for_canvas_chapter(next_canvas, str(canvas_chapter.get("id", "")))
        if not scene:
            scene = {
                "id": f"scene_{order}_1",
                "chapter_id": str(canvas_chapter.get("id") or f"canvas_ch_{order}"),
                "scene_order": 1,
                "linked_material_ids": [],
            }
            next_canvas.setdefault("scenes", []).append(scene)
            canvas_chapter["scene_ids"] = [scene["id"]]
        for key in [
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
        ]:
            if key in scene_card and scene_card.get(key) not in (None, "", []):
                scene[key] = scene_card[key]
        setting_type = self._json_dict(next_canvas.get("diagnostics")).get("setting_type") or infer_novel_setting_type(project)
        next_canvas["event_pool"] = advance_story_event_pool(
            next_canvas.get("event_pool"),
            str(setting_type),
            order,
            str(canvas_chapter.get("event_pool_id") or ""),
            canvas_chapter,
        )
        compacted = self._compact_story_canvas(next_canvas)
        storage.update_novel_project(project_id, {"story_canvas": compacted, "outline": self._canvas_outline(compacted)})

    def _merge_extended_canvas(
        self,
        current: dict[str, Any],
        extension: dict[str, Any],
        from_order: int,
        scoring_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kept_chapters = [item for item in self._canvas_chapters(current) if int(item.get("chapter_order") or 0) <= from_order]
        kept_ids = {str(item.get("id")) for item in kept_chapters}
        kept_scenes = [item for item in self._canvas_scenes(current) if str(item.get("chapter_id")) in kept_ids]
        extension_chapters = self._canvas_chapters(extension)
        extension_scenes = self._canvas_scenes(extension)
        remap: dict[str, str] = {}
        normalized_chapters: list[dict[str, Any]] = []
        for index, item in enumerate(extension_chapters):
            order = from_order + index + 1
            old_id = str(item.get("id") or f"canvas_ch_ext_{index + 1}")
            new_id = f"canvas_ch_{order}"
            remap[old_id] = new_id
            scene_ids = [f"scene_{order}_{scene_index + 1}" for scene_index, _scene in enumerate([s for s in extension_scenes if str(s.get("chapter_id")) == old_id] or [{}])]
            normalized_chapters.append({
                **item,
                "id": new_id,
                "chapter_order": order,
                "title": self._normalize_chapter_title(str(item.get("title") or ""), order),
                "scene_ids": scene_ids,
            })
        normalized_scenes: list[dict[str, Any]] = []
        scene_counts: dict[str, int] = {}
        for item in extension_scenes:
            old_chapter_id = str(item.get("chapter_id") or "")
            new_chapter_id = remap.get(old_chapter_id)
            if not new_chapter_id:
                continue
            scene_counts[new_chapter_id] = scene_counts.get(new_chapter_id, 0) + 1
            order = int(new_chapter_id.rsplit("_", 1)[-1])
            chapter_for_scene = next((chapter for chapter in normalized_chapters if chapter["id"] == new_chapter_id), {})
            normalized_scenes.append({
                **item,
                "id": f"scene_{order}_{scene_counts[new_chapter_id]}",
                "chapter_id": new_chapter_id,
                "scene_order": scene_counts[new_chapter_id],
                "tension": self._normalize_scene_tension(item.get("tension"), chapter_for_scene, {}),
            })
        if not normalized_scenes:
            normalized_scenes = self._derive_canvas_scenes_from_chapters(normalized_chapters)
        kept_threads = current.get("threads") if isinstance(current.get("threads"), list) else []
        extension_threads = extension.get("threads") if isinstance(extension.get("threads"), list) else []
        normalized_threads = []
        for index, item in enumerate(extension_threads[:12]):
            if not isinstance(item, dict):
                continue
            normalized_threads.append({
                **item,
                "id": f"thread_{from_order + 1}_{index + 1}",
                "setup_chapter_id": remap.get(str(item.get("setup_chapter_id")), normalized_chapters[0]["id"] if normalized_chapters else ""),
                "payoff_chapter_id": remap.get(str(item.get("payoff_chapter_id")), normalized_chapters[-1]["id"] if normalized_chapters else ""),
            })
        diagnostics = {
            **self._json_dict(current.get("diagnostics")),
            **self._json_dict(extension.get("diagnostics")),
            "extended_from_order": from_order,
            "extended_count": len(normalized_chapters),
        }
        progression_canvas = normalize_story_progression(current, scoring_context.get("project") if isinstance(scoring_context, dict) else None)
        if isinstance(extension.get("story_promise"), dict) and not progression_canvas.get("progression_protocol", {}).get("manual_edited"):
            progression_canvas["story_promise"] = extension.get("story_promise")
        if isinstance(extension.get("progression_protocol"), dict) and not progression_canvas.get("progression_protocol", {}).get("manual_edited"):
            progression_canvas["progression_protocol"] = extension.get("progression_protocol")
        progression_canvas = normalize_story_progression(progression_canvas, scoring_context.get("project") if isinstance(scoring_context, dict) else None)
        merged_chapters = [*kept_chapters, *normalized_chapters]
        for chapter in merged_chapters:
            chapter.update(chapter_progression_defaults(chapter, progression_canvas, scoring_context.get("project") if isinstance(scoring_context, dict) else None))
        merged_scenes = [*kept_scenes, *normalized_scenes]
        merged_threads = [*kept_threads, *normalized_threads][-24:]
        event_pool_source = extension.get("event_pool") if isinstance(extension.get("event_pool"), dict) else current.get("event_pool")
        event_pool = normalize_story_event_pool(event_pool_source, str(diagnostics.get("setting_type") or "modern_daily"))
        event_pool = apply_story_event_pool_delta(event_pool, extension.get("event_pool_delta"), str(diagnostics.get("setting_type") or "modern_daily"))
        return self._compact_story_canvas({
            **current,
            "version": self._coerce_int(current.get("version"), 1, 1, 99),
            "mode": "story_canvas",
            "story_promise": progression_canvas.get("story_promise", {}),
            "progression_protocol": progression_canvas.get("progression_protocol", {}),
            "event_pool": event_pool,
            "acts": [*(current.get("acts") if isinstance(current.get("acts"), list) else []), *(extension.get("acts") if isinstance(extension.get("acts"), list) else [])],
            "chapters": merged_chapters,
            "scenes": merged_scenes,
            "threads": merged_threads,
            "quality_rules": self._unique_short_list([*(current.get("quality_rules") if isinstance(current.get("quality_rules"), list) else []), *(extension.get("quality_rules") if isinstance(extension.get("quality_rules"), list) else [])], 20),
            "diagnostics": diagnostics,
        }, scoring_context)

    def _compact_story_canvas(self, canvas: dict[str, Any], scoring_context: dict[str, Any] | None = None) -> dict[str, Any]:
        if not canvas:
            return {}
        next_canvas = json.loads(json.dumps(canvas, ensure_ascii=False))
        next_canvas = normalize_story_progression(next_canvas)
        chapters = self._canvas_chapters(next_canvas)
        for index, chapter in enumerate(chapters):
            order = self._coerce_int(chapter.get("chapter_order"), index + 1, 1, 999)
            chapter["title"] = self._normalize_chapter_title(str(chapter.get("title") or ""), order)
            chapter.update(chapter_progression_defaults(chapter, next_canvas, order=order))
        chapter_ids = {str(item.get("id") or "") for item in chapters if str(item.get("id") or "")}
        next_canvas["acts"] = self._dedupe_canvas_acts(
            next_canvas.get("acts") if isinstance(next_canvas.get("acts"), list) else [],
            chapter_ids,
        )
        next_canvas["scenes"] = [
            item for item in self._canvas_scenes(next_canvas)
            if str(item.get("chapter_id") or "") in chapter_ids
        ]
        next_canvas["threads"] = [
            item for item in next_canvas.get("threads", []) if isinstance(item, dict)
            and (not str(item.get("setup_chapter_id") or "") or str(item.get("setup_chapter_id") or "") in chapter_ids)
            and (not str(item.get("payoff_chapter_id") or "") or str(item.get("payoff_chapter_id") or "") in chapter_ids)
        ][-24:] if isinstance(next_canvas.get("threads"), list) else []
        diagnostics = self._json_dict(next_canvas.get("diagnostics"))
        next_canvas["event_pool"] = bind_story_event_pool_to_chapters(
            next_canvas.get("event_pool"),
            chapters,
            str(diagnostics.get("setting_type") or "modern_daily"),
            scoring_context,
        )
        self._sync_bound_event_contracts(next_canvas)
        next_canvas["diagnostics"] = {
            **diagnostics,
            "compact_acts": len(next_canvas["acts"]),
        }
        return next_canvas

    def _sync_bound_event_contracts(self, canvas: dict[str, Any]) -> None:
        pool = canvas.get("event_pool") if isinstance(canvas.get("event_pool"), dict) else {}
        events = [
            *(pool.get("active") if isinstance(pool.get("active"), list) else []),
            *(pool.get("retired") if isinstance(pool.get("retired"), list) else []),
        ]
        by_id = {str(item.get("id") or ""): item for item in events if isinstance(item, dict)}
        for chapter in self._canvas_chapters(canvas):
            event_id = str(chapter.get("event_pool_id") or "").strip()
            if not event_id:
                continue
            current_contract = chapter.get("event_contract") if isinstance(chapter.get("event_contract"), dict) else {}
            if str(current_contract.get("event_id") or "") == event_id:
                continue
            event = by_id.get(event_id)
            if not event:
                continue
            source = str(event.get("source") or "").strip().lower()
            if source not in {"remote", "llm", "project", "manual"}:
                continue
            self._sync_event_contract_to_chapter(canvas, chapter, event, None, use_mode=event.get("use_mode") or "guide")

    def _dedupe_canvas_acts(self, acts: list[Any], chapter_ids: set[str]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in reversed(acts):
            if not isinstance(item, dict):
                continue
            act_id = str(item.get("id") or "").strip()
            order = self._coerce_int(item.get("order"), len(deduped) + 1, 1, 99)
            key = act_id or f"order:{order}"
            if key in seen:
                continue
            seen.add(key)
            chapter_refs = item.get("chapter_ids")
            if isinstance(chapter_refs, list):
                item = {**item, "chapter_ids": [ref for ref in chapter_refs if str(ref) in chapter_ids]}
            deduped.append(item)
        deduped.reverse()
        return deduped[-8:]
