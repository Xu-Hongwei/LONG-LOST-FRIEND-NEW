from __future__ import annotations

import json
import re
from typing import Any

from ...schemas import NovelInstructionOptimizeRequest, NovelInstructionOptimizeResponse
from .config import NOVEL_GENERATION_TIMEOUT_MS
from .event_pool import normalize_story_event_pool, story_event_for_chapter, sync_story_event_pool_display_bindings


class NovelInstructionOptimizerMixin:
    async def optimize_chapter_instruction(
        self,
        llm: Any,
        project_id: str,
        payload: NovelInstructionOptimizeRequest,
    ) -> NovelInstructionOptimizeResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        chapter = storage.get_novel_chapter(payload.chapter_id) if payload.chapter_id else None
        if payload.chapter_id and (not chapter or chapter["project_id"] != project_id):
            raise ValueError("Novel chapter not found")
        fallback = self._usable_instruction(payload.base_instruction) or self._usable_instruction(payload.goal) or "承接前文，写出一个有事件、有对白、有选择和结尾钩子的连续场景。"
        diagnostics: dict[str, Any] = {
            "llm_configured": bool(llm.configured()),
            "fallback_length": len(fallback),
            "target_length": payload.target_length,
        }
        event_pool_context = self._instruction_event_pool_context(project, chapter, payload)
        if event_pool_context:
            selected_event = event_pool_context.get("selected_event") if isinstance(event_pool_context.get("selected_event"), dict) else {}
            diagnostics = {
                **diagnostics,
                "event_pool_linked": True,
                "event_pool_id": selected_event.get("id") or "",
                "event_pool_time_anchor": selected_event.get("time_anchor") or "",
            }
        if not llm.configured():
            return NovelInstructionOptimizeResponse(instruction=fallback, source="fallback", diagnostics={**diagnostics, "reason": "llm_not_configured"})
        try:
            text = await llm.chat_complete([
                {"role": "system", "content": self._instruction_optimizer_system_prompt()},
                {"role": "user", "content": self._instruction_optimizer_source(project, chapter, payload, fallback, event_pool_context)},
            ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
            raw = self._load_llm_json_object(text, "instruction_optimization")
            instruction = self._usable_instruction(str(raw.get("instruction", "")))
            diagnostics = {
                **diagnostics,
                "raw_keys": sorted(raw.keys()),
                "remote_length": len(instruction),
            }
            if instruction:
                return NovelInstructionOptimizeResponse(instruction=instruction, source="remote", diagnostics=diagnostics)
            return NovelInstructionOptimizeResponse(instruction=fallback, source="fallback", diagnostics={**diagnostics, "reason": "empty_remote_instruction"})
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            return NovelInstructionOptimizeResponse(instruction=fallback, source="fallback", diagnostics={**diagnostics, "reason": type(exc).__name__})

    def _instruction_optimizer_system_prompt(self) -> str:
        return (
            "你是小说创作导演，只优化写作指令，不写正文。"
            "你必须返回 JSON 对象：{\"instruction\":\"...\"}。"
            "instruction 用中文，面向后续正文生成模型，必须可执行、具体、分段清晰，建议 450-900 字。"
            "保留本地骨架里的硬约束：目标字数、最低长度、禁止越界、禁止元叙述、不得重复正文。"
            "把场景卡转成写作任务：可见事件、人物欲望、具体阻碍、动作链、对白、结尾钩子。"
            "优先按这些小节组织：生成模式、剧情承接、场景展开、长度与节奏、质量补救、禁止事项。"
            "不要输出评分、等级、解释、Markdown 代码块或正文片段。"
        )

    def _instruction_event_pool_context(
        self,
        project: Any,
        chapter: Any,
        payload: NovelInstructionOptimizeRequest,
    ) -> dict[str, Any]:
        try:
            canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        except Exception:
            canvas = {}
        if not isinstance(canvas.get("event_pool"), dict):
            return {}
        diagnostics = self._json_dict(canvas.get("diagnostics"))
        setting_type = str(diagnostics.get("setting_type") or "modern_daily")
        pool = sync_story_event_pool_display_bindings(
            normalize_story_event_pool(canvas.get("event_pool"), setting_type),
            self._canvas_chapters(canvas),
            setting_type,
        )
        canvas_chapter = payload.canvas_chapter if isinstance(payload.canvas_chapter, dict) else {}
        event_contract = canvas_chapter.get("event_contract") if isinstance(canvas_chapter.get("event_contract"), dict) else {}
        order = self._coerce_int(
            canvas_chapter.get("chapter_order") or (chapter["chapter_order"] if chapter else 0),
            0,
            0,
            999,
        )
        event_id = str(canvas_chapter.get("event_pool_id") or "").strip()
        selected = story_event_for_chapter(
            pool,
            {**canvas_chapter, "chapter_order": order, "event_pool_id": event_id},
            setting_type,
        ) if order else {}
        if not selected and not event_contract:
            return {}
        selected_orders = [str(value) for value in selected.get("bound_chapter_orders", [])] if selected else []
        selected_id = str(selected.get("id") or "")
        contract_id = str(event_contract.get("event_id") or "")
        if not event_contract and not ((event_id and selected_id == event_id) or (order and str(order) in selected_orders)):
            return {}
        tags = selected.get("tags") if isinstance(selected.get("tags"), dict) else {}
        selected_source = selected if selected else {}
        return {
            "role": "current_chapter_event_pool_binding",
            "rule": "事件池决定本章发生什么；场景卡只补镜头、视角、欲望和边界。",
            "event_contract": event_contract,
            "selected_event": {
                "id": selected_source.get("id") or contract_id or "",
                "source": selected_source.get("source") or event_contract.get("source") or "",
                "status": selected_source.get("status") or event_contract.get("status") or "",
                "use_mode": selected_source.get("use_mode") or event_contract.get("use_mode") or "guide",
                "place": event_contract.get("place") or selected_source.get("place") or "",
                "time_anchor": event_contract.get("time_anchor") or selected_source.get("time_anchor") or "",
                "event": event_contract.get("external_event") or selected_source.get("event") or "",
                "hook": event_contract.get("hook") or selected_source.get("hook") or "",
                "motifs": event_contract.get("motifs") or selected_source.get("motifs") or [],
                "theme_markers": tags.get("theme_markers") or [],
                "tone_markers": tags.get("tone_markers") or [],
                "relationship_motion": tags.get("relationship_motion") or [],
                "selection_score": event_contract.get("score") or selected_source.get("selection_score") or canvas_chapter.get("event_pool_score") or 0,
                "selection_reasons": event_contract.get("reasons") or selected_source.get("selection_reasons") or canvas_chapter.get("event_pool_reasons") or [],
                "selection_penalties": event_contract.get("penalties") or selected_source.get("selection_penalties") or canvas_chapter.get("event_pool_penalties") or [],
            },
            "chapter_binding": {
                "chapter_order": order,
                "chapter_event_pool_id": event_id,
                "chapter_event_pool_score": canvas_chapter.get("event_pool_score") or 0,
                "chapter_event_pool_reasons": canvas_chapter.get("event_pool_reasons") or [],
                "chapter_event_pool_penalties": canvas_chapter.get("event_pool_penalties") or [],
            },
        }

    def _instruction_optimizer_source(
        self,
        project: Any,
        chapter: Any,
        payload: NovelInstructionOptimizeRequest,
        fallback: str,
        event_pool_context: dict[str, Any] | None = None,
    ) -> str:
        body = str(payload.body or "")
        body_excerpt = body[:900]
        body_tail = body[-900:] if len(body) > 900 else ""
        scene_card = payload.scene_card or {}
        canvas_chapter = payload.canvas_chapter or {}
        previous_handoff = payload.previous_handoff or {}
        prior_novel_state = payload.prior_novel_state or {}
        quality_diagnosis = payload.quality_diagnosis or {}
        current_words = self._count_cjk_words(body)
        min_words = max(400, int(payload.target_length * 0.7))
        lines = [
            f"作品：{project['title']}",
            f"类型/基调：{project['genre']} / {project['tone']}",
            f"章节：{payload.title or (chapter['title'] if chapter else '')}",
            f"目标字数：{payload.target_length}",
            f"最低可接受长度：{min_words}",
            f"当前正文字数：{current_words}",
            "",
            "本地硬约束骨架：",
            fallback,
            "",
            "章节目标：",
            str(payload.goal or (chapter["goal"] if chapter else "") or ""),
            "",
            "章节摘要：",
            str(payload.summary or (chapter["summary"] if chapter else "") or ""),
            "",
            "当前章节画布节点：",
            json.dumps(canvas_chapter, ensure_ascii=False, indent=2)[:2400] if canvas_chapter else "无",
            "",
            "项目事件池绑定：",
            json.dumps(event_pool_context, ensure_ascii=False, indent=2)[:2400] if event_pool_context else "无",
            "",
            "场景卡：",
            json.dumps(scene_card, ensure_ascii=False, indent=2)[:3000],
            "",
            "上一章交接单：",
            json.dumps(previous_handoff, ensure_ascii=False, indent=2)[:2200] if previous_handoff else "无",
            "",
            "截至上一章 Novel State 精简版：",
            json.dumps(prior_novel_state, ensure_ascii=False, indent=2)[:2200] if prior_novel_state else "无",
            "",
            "当前正文质量诊断：",
            json.dumps(quality_diagnosis, ensure_ascii=False, indent=2)[:1600] if quality_diagnosis else "无",
            "",
            "当前正文开头：",
            body_excerpt,
        ]
        if body_tail and body_tail != body_excerpt:
            lines.extend(["", "当前正文结尾：", body_tail])
        lines.extend([
            "",
            "请生成优化后的 instruction。要求：",
            "- 不写正文，只写给生成模型的操作指令。",
            "- 信息优先级固定：已写正文/Novel State > 当前章节画布 > 项目事件池绑定 > 场景卡 > 用户写作偏好。",
            "- 项目事件池绑定决定这一章的可见事件、时间锚点、主题标记和结尾钩子；不能另起一个与事件池无关的事件。",
            "- 事件 use_mode 规则：strict 必须采用核心地点/时间/事件/钩子；guide 作为主要方向；flavor 只借地点、意象或钩子；free 只作灵感，允许自由发挥。",
            "- 场景卡只决定镜头落点、视角、在场人物、人物欲望、边界和禁止推进；如果场景卡与事件池冲突，保留事件池发生什么，调整场景卡的写法。",
            "- 如果当前正文明显短于目标，指令必须强调扩写同一章而不是另起新章。",
            "- 指令必须要求增加具体事件、动作、对白、选择和结尾钩子。",
            "- 指令必须提醒字段名、分析句和内部标签不能进入正文。",
            "- 必须参考章节画布、项目事件池、场景卡、上一章交接单和 Novel State，保证承接关系和边界不漂移。",
            "- 必须针对质量诊断给出具体补救策略，例如补对白、补动作、补结尾钩子或压缩重复抒情。",
            "- 优化结果要比本地骨架更具体，但不要超过 900 字；优先给出 4-6 个可执行写作动作，而不是抽象审美要求。",
        ])
        return "\n".join(lines)

    def _instruction_optimizer_source_legacy(
        self,
        project: Any,
        chapter: Any,
        payload: NovelInstructionOptimizeRequest,
        fallback: str,
        event_pool_context: dict[str, Any] | None = None,
    ) -> str:
        body = str(payload.body or "")
        body_excerpt = body[:900]
        body_tail = body[-900:] if len(body) > 900 else ""
        scene_card = payload.scene_card or {}
        canvas_chapter = payload.canvas_chapter or {}
        previous_handoff = payload.previous_handoff or {}
        prior_novel_state = payload.prior_novel_state or {}
        quality_diagnosis = payload.quality_diagnosis or {}
        current_words = self._count_cjk_words(body)
        min_words = max(400, int(payload.target_length * 0.7))
        lines = [
            f"作品：{project['title']}",
            f"类型/基调：{project['genre']} / {project['tone']}",
            f"章节：{payload.title or (chapter['title'] if chapter else '')}",
            f"目标字数：{payload.target_length}",
            f"最低可接受长度：{min_words}",
            f"当前正文长度：{current_words}",
            "",
            "本地硬约束骨架：",
            fallback,
            "",
            "章节目标：",
            str(payload.goal or (chapter["goal"] if chapter else "") or ""),
            "",
            "章节摘要：",
            str(payload.summary or (chapter["summary"] if chapter else "") or ""),
            "",
            "当前章节画布节点：",
            json.dumps(canvas_chapter, ensure_ascii=False, indent=2)[:2400] if canvas_chapter else "无",
            "",
            "场景卡：",
            json.dumps(scene_card, ensure_ascii=False, indent=2)[:3000],
            "",
            "上一章交接单：",
            json.dumps(previous_handoff, ensure_ascii=False, indent=2)[:2200] if previous_handoff else "无",
            "",
            "截至上一章 Novel State 精简版：",
            json.dumps(prior_novel_state, ensure_ascii=False, indent=2)[:2200] if prior_novel_state else "无",
            "",
            "当前正文质量诊断：",
            json.dumps(quality_diagnosis, ensure_ascii=False, indent=2)[:1600] if quality_diagnosis else "无",
            "",
            "当前正文开头：",
            body_excerpt,
        ]
        if body_tail and body_tail != body_excerpt:
            lines.extend(["", "当前正文结尾：", body_tail])
        lines.extend([
            "",
            "请生成优化后的 instruction。要求：",
            "- 不写正文，只写给生成模型的操作指令。",
            "- 如果当前正文明显短于目标，指令必须强调扩写同一章而不是另起新章。",
            "- 指令必须要求增加具体事件、动作、对白、选择和结尾钩子。",
            "- 指令必须提醒场景卡只作为指导，字段名和分析句不能进入正文。",
            "- 必须参考章节画布节点、上一章交接单和截至上一章 Novel State，保证承接关系和边界不漂移。",
            "- 必须针对质量诊断给出具体补救策略，例如补对白、补动作、补结尾钩子或压缩重复抒情。",
            "- 请把优化结果写得比本地骨架更具体，但不要超过 900 字；优先给出 4-6 个可执行写作动作，而不是抽象审美要求。",
        ])
        return "\n".join(lines)

    def _validate_optimized_instruction(
        self,
        instruction: str,
        fallback: str,
        payload: NovelInstructionOptimizeRequest,
    ) -> tuple[bool, str]:
        if not instruction:
            return False, "empty_instruction"
        if len(instruction) < 120:
            return False, "too_short"
        if len(instruction) > 4000:
            return False, "too_long"
        compact = re.sub(r"\s+", "", instruction)
        if not compact:
            return False, "empty_compact_instruction"
        if str(payload.target_length) not in instruction and "目标" not in instruction:
            return False, "missing_target_length"
        if not any(term in instruction for term in ("不要", "禁止", "不得", "避免", "不能", "不可")):
            return False, "missing_constraints"
        if payload.goal:
            goal_text = self._clean_material_text(payload.goal)
            goal_keywords = [item for item in re.split(r"[\s，。；、,.!?！？：:]+", goal_text) if len(item) >= 3]
            has_goal_signal = "章节目标" in instruction or "目标" in instruction or any(keyword[:12] in instruction for keyword in goal_keywords[:4])
            if not has_goal_signal:
                return False, "missing_goal"
        scene_card = payload.scene_card or {}
        scene_values = [
            str(scene_card.get(key, "")).strip()
            for key in ("current_scene", "surface_event", "character_desire", "tension", "ending_beat")
            if str(scene_card.get(key, "")).strip()
        ]
        if scene_values:
            matched = any(self._clean_material_text(value)[:16] and self._clean_material_text(value)[:16] in instruction for value in scene_values)
            if not matched and "场景" not in instruction:
                return False, "missing_scene_card"
        if instruction.strip() == fallback.strip():
            return False, "same_as_fallback"
        return True, "ok"

    def _count_cjk_words(self, text: str) -> int:
        cjk = re.findall(r"[\u4e00-\u9fff]", text or "")
        latin = re.findall(r"[A-Za-z0-9]+", text or "")
        return len(cjk) + len(latin)
