from __future__ import annotations

import uuid
import json
import re
from datetime import datetime, timezone
from typing import Any

from ...schemas import StoryEventPoolBindingRequest, StoryEventPoolEventWriteRequest
from .config import NOVEL_EVENT_BINDING_TIMEOUT_MS
from .continuity import continuity_hits, continuity_ledger_terms
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
from .progression import progression_prompt
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
        storage = self._require_storage()
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        event = self._find_event(pool, event_id)
        if not event:
            raise ValueError("Event not found")
        fallback = dict(event)
        event.update(self._event_entry_from_payload(payload, setting_type, 0, fallback=fallback, event_id=event_id))
        event["updated_at"] = datetime.now(timezone.utc).isoformat()
        db_chapters = storage.list_novel_chapters(project_id)
        for canvas_chapter in self._canvas_chapters(canvas):
            if str(canvas_chapter.get("event_pool_id") or "") != event_id:
                continue
            chapter = next((row for row in db_chapters if int(row["chapter_order"]) == int(canvas_chapter.get("chapter_order") or 0)), None)
            self._sync_event_contract_to_chapter(canvas, canvas_chapter, event, chapter, project=project)
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
            canvas_chapter.pop("event_contract", None)
            canvas_chapter.pop("event_sync", None)
            scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
            scene_card.pop("event_contract", None)
            scene_card.pop("event_sync", None)
            storage.update_novel_chapter(chapter_id, {"scene_card": scene_card}, "system", create_version=False)
            return self._save_event_pool(project["id"], canvas, pool, setting_type)
        event = self._find_event(pool, event_id)
        if not event:
            raise ValueError("Event not found")
        use_mode = normalize_event_use_mode(payload.use_mode or event.get("use_mode"))
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
        self._sync_event_contract_to_chapter(canvas, canvas_chapter, event, chapter, use_mode=use_mode, project=project)
        return self._save_event_pool(project["id"], canvas, pool, setting_type)

    async def bind_event_pool_event_to_chapter_remote(
        self,
        llm: Any,
        project_id: str,
        chapter_id: str,
        payload: StoryEventPoolBindingRequest,
    ) -> Any:
        local_response = self.bind_event_pool_event_to_chapter(project_id, chapter_id, payload)
        event_id = str(payload.event_id or "").strip()
        if not event_id:
            return local_response
        try:
            configured = bool(llm and llm.configured())
        except Exception:
            configured = False
        if not configured:
            self._mark_event_contract_remote_status(project_id, chapter_id, "skipped", "llm_not_configured")
            return self.project_response(project_id)

        storage = self._require_storage()
        chapter = storage.get_novel_chapter(chapter_id)
        scene_card = self._json_dict(chapter["scene_card_json"] if chapter and "scene_card_json" in chapter.keys() else "{}")
        contract = scene_card.get("event_contract") if isinstance(scene_card.get("event_contract"), dict) else {}
        if normalize_event_use_mode(contract.get("use_mode")) == "free":
            self._mark_event_contract_remote_status(project_id, chapter_id, "skipped", "free_mode")
            return self.project_response(project_id)

        try:
            remote_response = await self._remote_event_contract_sync(llm, project_id, chapter_id)
            if remote_response:
                return remote_response
        except Exception as exc:
            try:
                llm.last_chat_error = type(exc).__name__
            except Exception:
                pass
            self._mark_event_contract_remote_status(project_id, chapter_id, "failed", type(exc).__name__)
        return self.project_response(project_id)

    def _event_contract_from_event(
        self,
        event: dict[str, Any],
        canvas_chapter: dict[str, Any],
        use_mode: str | None = None,
        project: Any | None = None,
    ) -> dict[str, Any]:
        tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
        previous_contract = canvas_chapter.get("event_contract") if isinstance(canvas_chapter.get("event_contract"), dict) else {}
        continuity = self._event_continuity_marks(project, event)
        return {
            "version": 1,
            "event_id": str(event.get("id") or ""),
            "use_mode": normalize_event_use_mode(use_mode or previous_contract.get("use_mode") or event.get("use_mode")),
            "source": str(event.get("source") or ""),
            "status": str(event.get("status") or ""),
            "place": str(event.get("place") or ""),
            "time_anchor": str(event.get("time_anchor") or ""),
            "external_event": str(event.get("event") or ""),
            "hook": str(event.get("hook") or ""),
            "motifs": event.get("motifs") if isinstance(event.get("motifs"), list) else [],
            "theme_markers": tags.get("theme_markers") if isinstance(tags.get("theme_markers"), list) else [],
            "tone_markers": tags.get("tone_markers") if isinstance(tags.get("tone_markers"), list) else [],
            "progression_role": str(tags.get("progression_role") or canvas_chapter.get("progression_role") or ""),
            "progression_markers": tags.get("progression_markers") if isinstance(tags.get("progression_markers"), list) else [],
            "promise_markers": tags.get("promise_markers") if isinstance(tags.get("promise_markers"), list) else [],
            "drift_guard_risks": tags.get("drift_guard_risks") if isinstance(tags.get("drift_guard_risks"), list) else [],
            "chapter_drive": str(canvas_chapter.get("chapter_drive") or ""),
            "promise_targets": canvas_chapter.get("promise_targets") if isinstance(canvas_chapter.get("promise_targets"), list) else [],
            "score": int(canvas_chapter.get("event_pool_score") or event.get("selection_score") or 0),
            "reasons": canvas_chapter.get("event_pool_reasons") if isinstance(canvas_chapter.get("event_pool_reasons"), list) else [],
            "penalties": canvas_chapter.get("event_pool_penalties") if isinstance(canvas_chapter.get("event_pool_penalties"), list) else [],
            "source_reason": str(event.get("source_reason") or ""),
            "continuity_hits": continuity["hits"],
            "continuity_risks": continuity["risks"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _event_continuity_marks(self, project: Any | None, event: dict[str, Any]) -> dict[str, list[str]]:
        if not project:
            return {"hits": [], "risks": []}
        try:
            novel_state = self._json_dict(project["novel_state_json"] if "novel_state_json" in project.keys() else "{}")
        except Exception:
            novel_state = {}
        terms = continuity_ledger_terms(novel_state.get("continuity_ledger"))
        text = " ".join(
            str(value or "")
            for value in [
                event.get("place"),
                event.get("time_anchor"),
                event.get("event"),
                event.get("hook"),
                event.get("source_reason"),
                " ".join(str(item) for item in event.get("motifs", []) if str(item).strip()) if isinstance(event.get("motifs"), list) else "",
            ]
        )
        hits = [
            *continuity_hits(text, terms["ledger_must_continue"], 3),
            *continuity_hits(text, terms["ledger_open"], 2),
            *continuity_hits(text, terms["ledger_promises"], 2),
        ]
        risks = [
            *continuity_hits(text, terms["ledger_avoid"], 2),
            *continuity_hits(text, terms["ledger_resolved"], 2),
            *continuity_hits(text, terms["ledger_forbidden"], 2),
        ]
        return {"hits": hits[:6], "risks": risks[:6]}

    def _sync_event_contract_to_chapter(
        self,
        canvas: dict[str, Any],
        canvas_chapter: dict[str, Any],
        event: dict[str, Any],
        chapter: Any | None,
        use_mode: str | None = None,
        project: Any | None = None,
    ) -> None:
        contract = self._event_contract_from_event(event, canvas_chapter, use_mode=use_mode, project=project)
        mode = normalize_event_use_mode(contract.get("use_mode"))
        canvas_chapter["event_contract"] = contract
        if contract.get("progression_role") and not str(canvas_chapter.get("progression_role") or "").strip():
            canvas_chapter["progression_role"] = contract["progression_role"]
        if contract.get("progression_markers") and not str(canvas_chapter.get("chapter_drive") or "").strip():
            canvas_chapter["chapter_drive"] = " / ".join(str(item) for item in contract.get("progression_markers", []) if str(item).strip())[:500]
        if contract.get("promise_markers") and not isinstance(canvas_chapter.get("promise_targets"), list):
            canvas_chapter["promise_targets"] = contract.get("promise_markers", [])[:6]
        elif contract.get("promise_markers") and not canvas_chapter.get("promise_targets"):
            canvas_chapter["promise_targets"] = contract.get("promise_markers", [])[:6]
        if mode == "free":
            canvas_chapter["event_sync"] = {
                "source": "local",
                "remote_status": "skipped",
                "event_id": contract["event_id"],
                "mode": mode,
                "fields": {},
                "scene_fields": {},
                "updated_at": contract["updated_at"],
            }
            if chapter:
                scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
                scene_card["event_contract"] = contract
                scene_card["event_sync"] = canvas_chapter["event_sync"]
                self._require_storage().update_novel_chapter(chapter["id"], {"scene_card": scene_card}, "system", create_version=False)
            return

        previous_sync = self._json_dict(canvas_chapter.get("event_sync"))
        previous_fields = previous_sync.get("fields") if isinstance(previous_sync.get("fields"), dict) else {}
        previous_scene_fields = previous_sync.get("scene_fields") if isinstance(previous_sync.get("scene_fields"), dict) else {}
        force = mode == "strict"
        first_guide_sync = mode == "guide" and not previous_sync
        flavor = mode == "flavor"
        event_text = str(contract.get("external_event") or "")
        hook = str(contract.get("hook") or "")
        place = str(contract.get("place") or "")
        time_anchor = str(contract.get("time_anchor") or "")
        motif_text = "、".join(str(item) for item in contract.get("motifs", []) if str(item).strip())
        field_values = {
            "external_event": event_text,
            "trigger_event": event_text,
            "ending_hook": hook,
            "goal": f"{time_anchor + '，' if time_anchor else ''}{place}：{event_text}。{hook}" if (place or event_text or hook) else "",
            "obstacle_escalation": "事件带来的时间、信息或旁观压力让角色不能立刻把话说完。",
            "scene_consequence": hook or "事件留下一个可继续展开的选择。",
        }
        if flavor:
            field_values = {
                "ending_hook": hook,
            }
        written_fields: dict[str, Any] = {}
        for key, value in field_values.items():
            clean = str(value or "").strip()
            if not clean:
                continue
            current = str(canvas_chapter.get(key) or "").strip()
            previous = str(previous_fields.get(key) or "").strip()
            should_write = force or first_guide_sync or not current or (previous and current == previous)
            if flavor and key != "ending_hook":
                should_write = False
            if should_write:
                canvas_chapter[key] = clean
                written_fields[key] = clean
        scene = self._event_contract_canvas_scene(canvas, canvas_chapter)
        scene_values = {
            "current_scene": f"{time_anchor + '，' if time_anchor else ''}{place}" if place or time_anchor else "",
            "surface_event": event_text,
            "ending_beat": hook,
        }
        if motif_text and mode == "flavor":
            scene_values["surface_event"] = f"借用意象：{motif_text}"
        written_scene_fields: dict[str, Any] = {}
        for key, value in scene_values.items():
            clean = str(value or "").strip()
            if not clean:
                continue
            current = str(scene.get(key) or "").strip()
            previous = str(previous_scene_fields.get(key) or "").strip()
            should_write = force or first_guide_sync or not current or (previous and current == previous)
            if flavor and key == "surface_event":
                should_write = not current or (previous and current == previous)
            if should_write:
                scene[key] = clean
                written_scene_fields[key] = clean
        sync = {
            "source": "local",
            "remote_status": "skipped",
            "event_id": contract["event_id"],
            "mode": mode,
            "fields": written_fields,
            "scene_fields": written_scene_fields,
            "updated_at": contract["updated_at"],
        }
        canvas_chapter["event_sync"] = sync
        if chapter:
            scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
            scene_card["event_contract"] = contract
            scene_card["event_sync"] = sync
            for key, value in scene_values.items():
                clean = str(value or "").strip()
                if not clean:
                    continue
                current = str(scene_card.get(key) or "").strip()
                previous = str(previous_scene_fields.get(key) or "").strip()
                should_write = force or first_guide_sync or not current or (previous and current == previous)
                if flavor and key == "surface_event":
                    should_write = not current or (previous and current == previous)
                if should_write:
                    scene_card[key] = clean
            self._require_storage().update_novel_chapter(chapter["id"], {"scene_card": scene_card}, "system", create_version=False)

    async def _remote_event_contract_sync(self, llm: Any, project_id: str, chapter_id: str) -> Any:
        storage = self._require_storage()
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter or chapter["project_id"] != project_id:
            raise ValueError("Novel chapter not found")
        order = int(chapter["chapter_order"])
        canvas_chapter = next((item for item in self._canvas_chapters(canvas) if int(item.get("chapter_order") or 0) == order), None)
        if not canvas_chapter:
            raise ValueError("Canvas chapter not found")
        contract = canvas_chapter.get("event_contract") if isinstance(canvas_chapter.get("event_contract"), dict) else {}
        if not contract:
            return None
        mode = normalize_event_use_mode(contract.get("use_mode"))
        if mode == "free":
            return None
        scene = self._event_contract_canvas_scene(canvas, canvas_chapter)
        scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
        text = await llm.chat_complete(
            [
                {"role": "system", "content": self._event_contract_sync_system_prompt()},
                {"role": "user", "content": self._event_contract_sync_source(project, chapter, canvas_chapter, scene, scene_card, contract)},
            ],
            timeout_ms=NOVEL_EVENT_BINDING_TIMEOUT_MS,
            response_format={"type": "json_object"},
        )
        raw = self._load_llm_json_object(text, "event_contract_sync")
        applied = self._apply_remote_event_sync_patch(canvas, canvas_chapter, chapter, scene, scene_card, contract, raw)
        if not applied:
            self._mark_event_contract_remote_status(project_id, chapter_id, "empty", "empty_remote_patch")
            return self.project_response(project_id)
        storage.update_novel_chapter(chapter_id, {"scene_card": scene_card}, "system", create_version=False)
        return self._save_event_pool(project_id, canvas, pool, setting_type)

    def _event_contract_sync_system_prompt(self) -> str:
        return (
            "You are a long-form novel planning assistant. Return only a JSON object. "
            "Your task is to turn the selected event contract into a structured patch for the current chapter canvas and scene card. "
            "Do not write prose正文. Do not invent a different event. Do not output scores, confidence, markdown, or explanations outside JSON. "
            "Allowed top-level keys: canvas_chapter_patch, scene_card_patch, sync_note. "
            "Respect use_mode: strict must preserve the event core; guide treats the event as the main direction; flavor only borrows place, motifs, atmosphere, or hook; free should return empty patches. "
            "Respect story_promise and progression_protocol: they decide how this novel progresses; event_contract decides what this chapter does. "
            "If scene_card conflicts with event_contract, keep what happens from event_contract and adjust only staging details. "
            "Match the existing story canvas action-chain style: concrete, sequential, field-specific, and not summary-like. "
            "All returned field values must be natural Chinese. Never return English enum labels or snake_case values such as third_person or company_building_front. "
            "Never copy event-pool metadata such as variant labels, source_reason, score reasons, or '变体N' into output fields."
        )

    def _event_contract_sync_source(
        self,
        project: Any,
        chapter: Any,
        canvas_chapter: dict[str, Any],
        scene: dict[str, Any],
        scene_card: dict[str, Any],
        contract: dict[str, Any],
    ) -> str:
        project_context = {
            "title": project["title"],
            "genre": project["genre"],
            "tone": project["tone"],
            "protagonist": project["protagonist"],
            "worldview": project["worldview"],
            "relationship_setup": project["relationship_setup"],
            "outline": project["outline"],
        }
        chapter_context = {
            "id": chapter["id"],
            "chapter_order": chapter["chapter_order"],
            "title": chapter["title"],
            "goal": chapter["goal"],
            "summary": chapter["summary"],
            "status": chapter["status"],
        }
        expected = {
            "canvas_chapter_patch": {
                "goal": "具体章节目标，保留事件契约方向",
                "external_event": "本章可见外部事件",
                "trigger_event": "触发事件",
                "immediate_reaction": "角色当下反应",
                "obstacle_escalation": "阻碍或信息压力",
                "counterpart_reaction": "对方反应",
                "character_choice": "人物选择",
                "scene_consequence": "场景后果",
                "ending_hook": "结尾钩子",
            },
            "scene_card_patch": {
                "current_scene": "具体场景落点",
                "surface_event": "表层可见事件",
                "character_desire": "本场人物想要什么",
                "tension": "可演出的阻力或误差",
                "ending_beat": "本场最后一个动作/信息钩子",
                "required_facts": ["必须保留的事实"],
                "forbidden_progress": ["禁止提前推进的内容"],
            },
            "sync_note": "一句话说明这次如何把事件转成画布和场景卡",
        }
        lines = [
            "Return JSON in this exact shape:",
            self._json_dump(expected)[:1600],
            "",
            "Priority:",
            "1. Already written chapter/body and Novel State are highest; do not contradict them.",
            "2. event_contract decides what happens in this chapter.",
            "3. canvas_chapter carries chapter-level action chain.",
            "4. scene_card decides staging, desire, tension, and ending beat.",
            "5. generation instruction will later compile these results; do not write that instruction here.",
            "",
            "Canvas action-chain field semantics:",
            "- external_event: the visible outside event only; do not include pressure notes, score reasons, or variant labels.",
            "- trigger_event: the precise moment that forces interaction; it should not simply duplicate external_event.",
            "- immediate_reaction: the protagonist's first observable response.",
            "- obstacle_escalation: a concrete obstacle, time pressure, witness, missing information, or physical constraint.",
            "- counterpart_reaction: the other character's visible response, not an abstract relationship judgment.",
            "- character_choice: the protagonist's choice in this chapter.",
            "- scene_consequence: what changes by the end of the scene.",
            "- ending_hook: one clean next-scene hook, with no metadata.",
            "",
            "Scene-card field semantics:",
            "- current_scene: place plus time anchor when available.",
            "- surface_event: what the camera can see happening.",
            "- character_desire: what the protagonist wants right now.",
            "- tension: what makes the desire hard to satisfy.",
            "- ending_beat: the last visible beat or information hook.",
            "",
            "Project:",
            self._json_dump(project_context)[:2200],
            "",
            "Project progression protocol:",
            progression_prompt(self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}"), project)[:2200],
            "",
            "Current chapter row:",
            self._json_dump(chapter_context)[:1200],
            "",
            "Selected event_contract:",
            self._json_dump(contract)[:2200],
            "",
            "Current canvas_chapter:",
            self._json_dump(canvas_chapter)[:3000],
            "",
            "Current first canvas_scene:",
            self._json_dump(scene)[:2200],
            "",
            "Current editable scene_card:",
            self._json_dump(scene_card)[:2600],
            "",
            "Rules:",
            "- Use Chinese strings for generated field values.",
            "- Do not return English enum labels, pinyin, or snake_case; translate third_person to 第三人称限知 and rewrite location ids as Chinese scene text.",
            "- Keep the selected place/time/event/hook unless use_mode is flavor.",
            "- Do not use 用户/助手/AI as character names.",
            "- Rewrite event-pool candidate wording into natural chapter-planning prose; remove labels like 变体8, selection_score, source_reason, planned, fresh.",
            "- Keep patches concise and field-oriented; no markdown.",
            "- If a field should not change, omit it or use an empty string.",
        ]
        return "\n".join(lines)

    def _apply_remote_event_sync_patch(
        self,
        canvas: dict[str, Any],
        canvas_chapter: dict[str, Any],
        chapter: Any,
        scene: dict[str, Any],
        scene_card: dict[str, Any],
        contract: dict[str, Any],
        raw: dict[str, Any],
    ) -> bool:
        mode = normalize_event_use_mode(contract.get("use_mode"))
        previous_sync = self._json_dict(canvas_chapter.get("event_sync"))
        previous_fields = previous_sync.get("fields") if isinstance(previous_sync.get("fields"), dict) else {}
        previous_scene_fields = previous_sync.get("scene_fields") if isinstance(previous_sync.get("scene_fields"), dict) else {}
        force = mode == "strict"
        canvas_patch = self._json_dict(raw.get("canvas_chapter_patch") or raw.get("canvas_chapter") or raw.get("chapter_patch"))
        scene_patch = self._json_dict(raw.get("scene_card_patch") or raw.get("scene_card") or raw.get("scene_patch"))
        if mode == "flavor":
            canvas_allowed = {"ending_hook", "scene_consequence"}
            scene_allowed = {"current_scene", "tension", "ending_beat", "forbidden_progress"}
        else:
            canvas_allowed = {
                "goal",
                "external_event",
                "trigger_event",
                "immediate_reaction",
                "obstacle_escalation",
                "counterpart_reaction",
                "character_choice",
                "scene_consequence",
                "ending_hook",
            }
            scene_allowed = {
                "current_scene",
                "surface_event",
                "character_desire",
                "tension",
                "ending_beat",
                "required_facts",
                "forbidden_progress",
            }
        written_fields: dict[str, Any] = {}
        for key in canvas_allowed:
            clean = self._clean_remote_sync_value(canvas_patch.get(key), key)
            if clean in ("", [], None):
                continue
            current = str(canvas_chapter.get(key) or "").strip()
            previous = str(previous_fields.get(key) or "").strip()
            should_write = force or not current or (previous and current == previous)
            if should_write:
                canvas_chapter[key] = clean
                written_fields[key] = clean
        written_scene_fields: dict[str, Any] = {}
        for key in scene_allowed:
            clean = self._clean_remote_sync_value(scene_patch.get(key), key)
            if clean in ("", [], None):
                continue
            current = scene.get(key)
            current_text = "" if isinstance(current, list) and not current else (self._json_dump(current) if isinstance(current, list) else str(current or "").strip())
            previous = previous_scene_fields.get(key)
            previous_text = "" if isinstance(previous, list) and not previous else (self._json_dump(previous) if isinstance(previous, list) else str(previous or "").strip())
            should_write = force or not current_text or (previous_text and current_text == previous_text)
            if should_write:
                scene[key] = clean
                scene_card[key] = clean
                written_scene_fields[key] = clean
        if not written_fields and not written_scene_fields:
            return False
        now = datetime.now(timezone.utc).isoformat()
        note = str(raw.get("sync_note") or raw.get("source_note") or "").strip()[:360]
        sync = {
            "source": "remote",
            "remote_status": "succeeded",
            "event_id": str(contract.get("event_id") or ""),
            "mode": mode,
            "fields": written_fields,
            "scene_fields": written_scene_fields,
            "source_note": note,
            "updated_at": now,
        }
        contract["updated_at"] = now
        canvas_chapter["event_contract"] = contract
        canvas_chapter["event_sync"] = sync
        scene_card["event_contract"] = contract
        scene_card["event_sync"] = sync
        return True

    def _clean_remote_sync_value(self, value: Any, key: str) -> Any:
        if key in {"required_facts", "forbidden_progress"}:
            if not isinstance(value, list):
                return []
            items = [self._strip_event_pool_artifacts(str(item or "").strip()) for item in value if str(item or "").strip()]
            items = [item for item in items if item]
            return items[:8]
        text = self._strip_event_pool_artifacts(str(value or "").strip())
        if not text:
            return ""
        if key == "current_scene" and self._looks_like_english_slug(text):
            text = self._scene_slug_to_chinese(text) or ""
        if key == "pov" and self._looks_like_english_slug(text):
            text = "第三人称限知"
        limit = 900 if key in {"goal", "obstacle_escalation", "scene_consequence", "tension"} else 520
        return text[:limit]

    def _looks_like_english_slug(self, value: Any) -> bool:
        text = str(value or "").strip()
        return bool(text) and bool(re.fullmatch(r"[A-Za-z0-9_\\-\\s]+", text)) and bool(re.search(r"[A-Za-z]", text))

    def _scene_slug_to_chinese(self, value: Any) -> str:
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
        pieces = re.split(r"[_\\-\\s]+", str(value or "").strip().lower())
        return "".join(token_map.get(piece, "") for piece in pieces if piece)

    def _strip_event_pool_artifacts(self, text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return ""
        clean = re.sub(r"(?:^|[。；;，,\s])变体\s*\d+\s*[：:]\s*", "，", clean)
        clean = re.sub(r"^\s*[：:，,。；;\s]+", "", clean)
        clean = re.sub(r"\s+", " ", clean)
        clean = clean.replace("selection_score", "").replace("source_reason", "")
        return clean.strip(" ，,。；;")

    def _json_dump(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    def _mark_event_contract_remote_status(self, project_id: str, chapter_id: str, status: str, reason: str) -> None:
        storage = self._require_storage()
        project, canvas, pool, setting_type = self._editable_event_pool(project_id)
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter or chapter["project_id"] != project_id:
            return
        order = int(chapter["chapter_order"])
        canvas_chapter = next((item for item in self._canvas_chapters(canvas) if int(item.get("chapter_order") or 0) == order), None)
        if not canvas_chapter:
            return
        sync = self._json_dict(canvas_chapter.get("event_sync"))
        if not sync:
            return
        sync["remote_status"] = status
        sync["remote_reason"] = reason
        sync["updated_at"] = datetime.now(timezone.utc).isoformat()
        canvas_chapter["event_sync"] = sync
        scene_card = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
        if isinstance(scene_card.get("event_sync"), dict):
            scene_card["event_sync"] = {**scene_card["event_sync"], **sync}
            storage.update_novel_chapter(chapter_id, {"scene_card": scene_card}, "system", create_version=False)
        self._save_event_pool(project["id"], canvas, pool, setting_type)

    def _event_contract_canvas_scene(self, canvas: dict[str, Any], canvas_chapter: dict[str, Any]) -> dict[str, Any]:
        scenes = canvas.get("scenes") if isinstance(canvas.get("scenes"), list) else []
        scene_ids = canvas_chapter.get("scene_ids") if isinstance(canvas_chapter.get("scene_ids"), list) else []
        scene_id = str(scene_ids[0]) if scene_ids else ""
        scene = next(
            (
                item for item in scenes
                if isinstance(item, dict)
                and (str(item.get("id") or "") == scene_id or str(item.get("chapter_id") or "") == str(canvas_chapter.get("id") or ""))
            ),
            None,
        )
        if scene is not None:
            return scene
        order = int(canvas_chapter.get("chapter_order") or 1)
        scene = {
            "id": scene_id or f"scene_{order}_1",
            "chapter_id": str(canvas_chapter.get("id") or f"canvas_ch_{order}"),
            "scene_order": 1,
            "current_scene": "",
            "pov": "",
            "present_characters": "",
            "surface_event": "",
            "character_desire": "",
            "tension": "",
            "required_facts": [],
            "forbidden_progress": [],
            "ending_beat": "",
            "linked_material_ids": [],
        }
        canvas.setdefault("scenes", []).append(scene)
        canvas_chapter["scene_ids"] = [scene["id"]]
        return scene

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
