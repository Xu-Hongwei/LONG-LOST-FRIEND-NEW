from __future__ import annotations

import json
import re
from typing import Any

from .config import NOVEL_PLANNING_TIMEOUT_MS


class NovelHandoffMixin:
    async def _build_chapter_handoff(
        self,
        llm: Any,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        fallback = self._mock_chapter_handoff(chapter, scene_card, parsed)
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._handoff_system_prompt()},
                {"role": "user", "content": self._handoff_source(project, chapter, scene_card, scene_beats, parsed)},
            ], timeout_ms=NOVEL_PLANNING_TIMEOUT_MS, response_format={"type": "json_object"})
            handoff = self._parse_chapter_handoff(text, fallback)
            return self._sanitize_chapter_handoff(project, chapter, scene_card, parsed, handoff, fallback), "remote"
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            return fallback, "mock"

    def _handoff_system_prompt(self) -> str:
        return (
            "你是长篇小说连续性编辑。你的任务是从已生成章节中提取交接单，不写正文。"
            "只记录已发生事实、关系变化、结尾钩子和下一章必须承接的内容。"
            "不要添加正文里没有发生的事件，不要把猜测写成事实。"
            "只输出 JSON 对象。字段：happened, relationship_delta, ending_hook, next_must_continue, avoid_repeating, open_threads。"
            "每个字段都是字符串数组，最多 5 条。"
        )

    def _handoff_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
    ) -> str:
        body = str(parsed.get("body") or "")
        return "\n\n".join([
            "[作品]",
            f"{project['title']}｜{project['genre']}｜{project['tone']}",
            "[章节]",
            f"第{chapter['chapter_order']}章《{parsed.get('title') or chapter['title']}》",
            "[章节摘要]",
            str(parsed.get("summary") or "")[:1200],
            "[当前章节场景卡：只作为本章提示]",
            self._handoff_scene_card_prompt(scene_card),
            "[Scene Beats]",
            self._scene_beats_prompt(scene_beats),
            "[正文尾段]",
            body[-2200:] if body else "无",
            "[输出要求]",
            "提取交接单，供下一章承接。happened 只能写本章正文里新发生的事实；"
            "required_facts 和上一章背景只用于连续性，不能复制进 happened。"
            "不要评价文笔，不要写创作建议，只写已经发生和必须承接的事项。",
        ])

    def _handoff_scene_card_prompt(self, scene_card: dict[str, Any]) -> str:
        current_only = {
            "current_scene": scene_card.get("current_scene", ""),
            "present_characters": scene_card.get("present_characters", []),
            "surface_event": scene_card.get("surface_event", ""),
            "character_desire": scene_card.get("character_desire", ""),
            "tension": scene_card.get("tension", ""),
            "ending_beat": scene_card.get("ending_beat", ""),
        }
        context_only = {
            "required_facts_context_only": scene_card.get("required_facts", []),
            "forbidden_progress_context_only": scene_card.get("forbidden_progress", []),
        }
        return json.dumps(
            {
                "current_chapter_hints": current_only,
                "continuity_context_do_not_copy_to_happened": context_only,
            },
            ensure_ascii=False,
        )

    def _parse_chapter_handoff(self, text: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raw = self._load_llm_json_object(text, "chapter_handoff")
        result = dict(fallback)
        for key in ["happened", "relationship_delta", "ending_hook", "next_must_continue", "avoid_repeating", "open_threads"]:
            value = raw.get(key)
            if isinstance(value, list):
                cleaned = [self._clean_material_text(str(item))[:220] for item in value if str(item).strip()]
            elif str(value or "").strip():
                cleaned = [self._clean_material_text(str(value))[:220]]
            else:
                cleaned = []
            result[key] = cleaned[:5] or result.get(key, [])
        return result

    def _sanitize_chapter_handoff(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        parsed: dict[str, Any],
        handoff: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        order = int(chapter["chapter_order"])
        previous_state = self._novel_state_until(project, order - 1)
        stale_sources: list[Any] = []
        for item in previous_state.get("chapter_handoffs", []) if isinstance(previous_state.get("chapter_handoffs"), list) else []:
            if not isinstance(item, dict):
                continue
            for key in ["happened", "relationship_delta", "ending_hook", "next_must_continue", "open_threads"]:
                value = item.get(key)
                if isinstance(value, list):
                    stale_sources.extend(value)
        required_facts = scene_card.get("required_facts")
        if isinstance(required_facts, list):
            stale_sources.extend(required_facts)
        elif str(required_facts or "").strip():
            stale_sources.extend(part for part in re.split(r"[；;]\s*", str(required_facts)) if part.strip())
        stale_norms = {self._norm_handoff_text(value) for value in stale_sources if self._norm_handoff_text(value)}

        result = dict(handoff)
        for key in ["happened", "relationship_delta"]:
            values = result.get(key)
            if not isinstance(values, list):
                continue
            filtered = [
                self._clean_material_text(str(item))[:220]
                for item in values
                if str(item).strip() and self._norm_handoff_text(item) not in stale_norms
            ]
            if key == "happened" and not filtered:
                filtered = [str(item) for item in fallback.get("happened", []) if str(item).strip()]
                if not filtered and str(parsed.get("summary") or "").strip():
                    filtered = [self._clean_material_text(str(parsed.get("summary")))[:220]]
            result[key] = self._unique_short_list(filtered, 5)
        result["chapter_order"] = order
        result["chapter_title"] = str(parsed.get("title") or chapter["title"])[:120]
        return result

    def _norm_handoff_text(self, value: Any) -> str:
        text = self._clean_material_text(str(value or "")).lower()
        return re.sub(r"[\s,，。.!！?？:：;；、\"'“”‘’（）()\[\]【】]+", "", text)

    def _mock_chapter_handoff(self, chapter: Any, scene_card: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        ending = self._clean_material_text(str(scene_card.get("ending_beat") or parsed.get("summary") or ""))[:220]
        happened = self._clean_material_text(str(scene_card.get("surface_event") or parsed.get("summary") or ""))[:220]
        return {
            "chapter_order": int(chapter["chapter_order"]),
            "chapter_title": str(parsed.get("title") or chapter["title"])[:120],
            "happened": [happened] if happened else [],
            "relationship_delta": [self._clean_material_text(str(scene_card.get("character_desire") or ""))[:220]] if scene_card.get("character_desire") else [],
            "ending_hook": [ending] if ending else [],
            "next_must_continue": [ending] if ending else [],
            "avoid_repeating": [happened] if happened else [],
            "open_threads": [ending] if ending else [],
        }

