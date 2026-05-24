from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...schemas import (
    CharacterCard,
    MemoryItem,
    NovelProjectCreateRequest,
    NovelProjectDraftGenerateRequest,
    NovelProjectDraftGenerateResponse,
    StoryItem,
)

logger = logging.getLogger(__name__)

PROJECT_DRAFT_SYSTEM_PROMPT = (
    "你是小说项目策划助手。把用户的一句话粗设定扩写成可编辑的长篇小说项目 JSON。"
    "只返回 JSON object，不要 Markdown，不要解释。"
    "允许字段只有：title, genre, tone, protagonist, worldview, relationship_setup, outline。"
    "用户粗设定是最高优先级；如果当前草稿、聊天素材或剧情标签与用户粗设定冲突，必须服从用户粗设定。"
    "当前草稿只能作为低优先级参考，不能沿用与用户粗设定不一致的旧标题、旧类型、旧世界观。"
    "genre 要像作品类型契约，tone 要比几个形容词更具体，写出叙事节奏、冲突强度和文风边界。"
    "worldview 写故事发生的日常规则、地点质感和可持续展开的限制。"
    "relationship_setup 写主角与角色的起点、互动张力、推进边界和不能突然越过的关系线。"
    "outline 用 5 到 8 条短段落，给出长篇开端、递进、转折和阶段性回收。"
    "必须尊重聊天素材，不要编造已经发生的亲密关系或私人事实。"
)


class NovelProjectDraftMixin:
    async def generate_project_draft(
        self,
        llm: Any,
        character: CharacterCard,
        messages: list[dict[str, Any]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        payload: NovelProjectDraftGenerateRequest,
    ) -> NovelProjectDraftGenerateResponse:
        current = payload.current or NovelProjectCreateRequest()
        diagnostics: dict[str, Any] = {
            "llm_configured": bool(llm.configured()),
            "source": "fallback",
            "prompt_chars": len(payload.prompt.strip()),
        }
        genre_hint = self._genre_hint_from_prompt(payload.prompt)
        if genre_hint:
            diagnostics["genre_hint"] = genre_hint
        if not llm.configured():
            return NovelProjectDraftGenerateResponse(
                project=self._fallback_project_draft(payload.prompt, current, character),
                diagnostics={**diagnostics, "reason": "llm_not_configured"},
            )
        try:
            text = await llm.chat_complete(
                [
                    {"role": "system", "content": PROJECT_DRAFT_SYSTEM_PROMPT},
                    {"role": "user", "content": self._project_draft_prompt(character, messages, memories, story_items, payload)},
                ],
                timeout_ms=24_000,
                response_format={"type": "json_object"},
                temperature=0.45,
            )
            raw = self._load_llm_json_object(text, "novel_project_draft")
            project = self._normalize_project_draft(raw, current, payload.prompt, character)
            return NovelProjectDraftGenerateResponse(
                project=project,
                diagnostics={**diagnostics, "source": "remote", "fields": self._filled_project_fields(project)},
            )
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            logger.warning("novel project draft generation failed: %s", exc)
            return NovelProjectDraftGenerateResponse(
                project=self._fallback_project_draft(payload.prompt, current, character),
                diagnostics={**diagnostics, "reason": type(exc).__name__},
            )

    def _project_draft_prompt(
        self,
        character: CharacterCard,
        messages: list[dict[str, Any]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        payload: NovelProjectDraftGenerateRequest,
    ) -> str:
        recent_messages = [
            {
                "role": str(item.get("role") or ""),
                "content": str(item.get("content") or "")[:280],
            }
            for item in messages[-14:]
            if str(item.get("content") or "").strip()
        ]
        compact_memories = [
            {
                "type": item.memory_type,
                "content": item.content[:220],
            }
            for item in memories[:10]
        ]
        compact_story = [
            {
                "kind": item.kind,
                "label": item.label,
                "content": item.content[:220],
            }
            for item in story_items[:10]
        ]
        return "\n".join(
            [
                f"用户粗设定：{payload.prompt.strip()}",
                "优先级规则：用户粗设定 > 角色材料 > 聊天/记忆/剧情标签 > 当前草稿。",
                "如果用户粗设定写了题材，例如修仙、武侠、玄幻、科幻、悬疑，就必须让 title/genre/worldview/outline 明显服务这个题材。",
                f"低优先级当前草稿：{json.dumps((payload.current or NovelProjectCreateRequest()).model_dump(exclude={'story_canvas'}), ensure_ascii=False)}",
                f"角色：{json.dumps(character.model_dump(), ensure_ascii=False)[:3000]}",
                f"最近聊天：{json.dumps(recent_messages, ensure_ascii=False)[:5000]}",
                f"关系/记忆素材：{json.dumps(compact_memories, ensure_ascii=False)[:3000]}",
                f"剧情标签素材：{json.dumps(compact_story, ensure_ascii=False)[:3000]}",
                "请输出完整项目草稿 JSON。",
            ]
        )

    def _normalize_project_draft(
        self,
        raw: dict[str, Any],
        current: NovelProjectCreateRequest,
        prompt: str,
        character: CharacterCard,
    ) -> NovelProjectCreateRequest:
        source = raw.get("project") if isinstance(raw.get("project"), dict) else raw
        fallback = self._fallback_project_draft(prompt, current, character)
        genre = self._text_field(source.get("genre"), fallback.genre, 80) or fallback.genre
        genre_hint = self._genre_hint_from_prompt(prompt)
        if genre_hint and not self._genre_matches_hint(genre, genre_hint):
            genre = genre_hint
        return NovelProjectCreateRequest(
            title=self._text_field(source.get("title"), fallback.title or "", 120) or fallback.title,
            genre=genre,
            tone=self._text_field(source.get("tone"), fallback.tone, 120) or fallback.tone,
            protagonist=self._text_field(source.get("protagonist"), fallback.protagonist, 120) or fallback.protagonist,
            worldview=self._text_field(source.get("worldview"), fallback.worldview, 2000) or fallback.worldview,
            relationship_setup=self._text_field(source.get("relationship_setup"), fallback.relationship_setup, 2000)
            or fallback.relationship_setup,
            outline=self._outline_field(source.get("outline"), fallback.outline, 4000) or fallback.outline,
        )

    def _fallback_project_draft(
        self,
        prompt: str,
        current: NovelProjectCreateRequest,
        character: CharacterCard,
    ) -> NovelProjectCreateRequest:
        seed = prompt.strip()
        title_seed = seed.split("，")[0].split(",")[0].split("。")[0].strip()[:32]
        title = current.title or (f"{title_seed}计划" if title_seed else f"{character.name}的长篇计划")
        protagonist = current.protagonist or character.name
        genre = current.genre or "校园日常长篇"
        genre_hint = self._genre_hint_from_prompt(seed)
        if genre_hint and not self._genre_matches_hint(genre, genre_hint):
            genre = genre_hint
        tone = current.tone or "温柔、克制、日常"
        worldview = current.worldview or (
            f"故事从当前聊天积累出的日常关系出发，以{protagonist}与{character.name}的校园生活、共同话题和未完成约定为核心。"
            "场景保持可感知、低悬浮，事件推进依赖真实互动而不是突发巧合。"
        )
        relationship_setup = current.relationship_setup or (
            f"{protagonist}与{character.name}的关系从熟悉但仍需要确认边界的状态开始。"
            "推进节奏以已发生的对话、明确偏好和被尊重的边界为依据，不突然制造亲密结论。"
        )
        outline = current.outline or "\n".join(
            [
                "1. 从一次具体的日常交集切入，确认两人的当前距离和未完成话题。",
                "2. 通过共同任务或约定让关系自然延展，埋下后续选择的伏笔。",
                "3. 引入轻微分歧或误会，测试双方表达、倾听和边界感。",
                "4. 让角色用行动回应此前的记忆点，形成关系上的小幅推进。",
                "5. 在阶段性事件后回收前文伏笔，为下一卷或下一组章节留下开放线索。",
            ]
        )
        return NovelProjectCreateRequest(
            title=title,
            genre=genre,
            tone=tone,
            protagonist=protagonist,
            worldview=worldview,
            relationship_setup=relationship_setup,
            outline=outline,
        )

    def _text_field(self, value: Any, fallback: str, max_chars: int) -> str:
        text = str(value if value is not None else fallback or "").strip()
        text = " ".join(text.split()) if "\n" not in text else "\n".join(line.strip() for line in text.splitlines()).strip()
        return text[:max_chars]

    def _outline_field(self, value: Any, fallback: str, max_chars: int) -> str:
        if isinstance(value, list):
            text = "\n".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value if value is not None else fallback or "").strip()
        text = self._normalize_outline_wraps(text)
        return text[:max_chars]

    def _normalize_outline_wraps(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) <= 1:
            return text.strip()
        list_like_count = sum(1 for line in lines if re.match(r"^(\d+[\).、]|[-*•]|第[一二三四五六七八九十\d]+[章节幕阶段])\s*", line))
        if list_like_count >= 2:
            return "\n".join(lines)
        return re.sub(r"\s{2,}", " ", "".join(lines)).strip()

    def _filled_project_fields(self, project: NovelProjectCreateRequest) -> list[str]:
        data = project.model_dump(exclude={"story_canvas"})
        return [key for key, value in data.items() if str(value or "").strip()]

    def _genre_hint_from_prompt(self, prompt: str) -> str:
        text = str(prompt or "")
        hints = [
            ("修仙", "修仙"),
            ("仙侠", "仙侠"),
            ("武侠", "武侠"),
            ("玄幻", "玄幻"),
            ("奇幻", "奇幻"),
            ("科幻", "科幻"),
            ("赛博", "赛博朋克"),
            ("悬疑", "悬疑"),
            ("推理", "推理"),
            ("都市", "都市"),
            ("校园", "校园"),
            ("古风", "古风"),
            ("历史", "历史"),
            ("末世", "末世"),
            ("群像", "群像"),
        ]
        found: list[str] = []
        for keyword, label in hints:
            if keyword in text and label not in found:
                found.append(label)
        return f"{''.join(found)}长篇" if found else ""

    def _genre_matches_hint(self, genre: str, hint: str) -> bool:
        tokens = [
            "修仙",
            "仙侠",
            "武侠",
            "玄幻",
            "奇幻",
            "科幻",
            "赛博朋克",
            "悬疑",
            "推理",
            "都市",
            "校园",
            "古风",
            "历史",
            "末世",
            "群像",
        ]
        tokens = [token for token in tokens if token in hint]
        return any(token and token in genre for token in tokens)
