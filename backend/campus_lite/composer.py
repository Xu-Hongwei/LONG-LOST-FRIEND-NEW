from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .schemas import CharacterCard, ContextSlot, MemoryItem


MAX_CONTEXT_BUDGET = 3200
LOCAL_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ComposeInput:
    character: CharacterCard
    recent_messages: list[dict[str, str]]
    user_message: str
    memories: list[MemoryItem]
    recent_summary: str
    profile_memories: list[MemoryItem] = field(default_factory=list)
    recall_memories: list[MemoryItem] = field(default_factory=list)
    manual_note: str = ""
    live_state: str = ""
    relationship_memory: str = ""
    time_awareness: str = ""


class ContextComposer:
    def compose(self, request: ComposeInput) -> list[ContextSlot]:
        profile_memories = request.profile_memories or request.memories
        recall_memories = request.recall_memories or request.memories
        slots = [
            self._slot("persona.identity", self._persona_identity(request.character), 100),
            self._slot("persona.personality", self._persona_personality(request.character), 99),
            self._slot("persona.scenario", self._persona_scenario(request.character), 97),
            self._slot("persona.interaction_policy", self._persona_interaction_policy(request.character), 96),
            self._slot("persona.relationship_memory", request.relationship_memory, 94),
            self._slot("persona.live_state", request.live_state, 95),
            self._slot("persona.speech_style", self._persona_voice(request.character), 98),
            self._slot("persona.boundaries", self._persona_boundaries(request.character), 97),
            self._slot("persona.examples", self._persona_examples(request.character), 84),
            self._slot("memory.profile", self._memory_profile(profile_memories), 88),
            self._slot("memory.recall", self._memory_recall(recall_memories), 86),
            self._slot("memory.recent_summary", request.recent_summary or "暂无会话摘要。", 82),
            self._slot("memory.manual_note", request.manual_note, 90),
            self._slot("chat.recent_messages", self._recent_messages(request.recent_messages), 78),
            self._slot("user.current_message", request.user_message, 96, role="user"),
            self._slot("response.rules", self._response_rules(), 99),
            self._slot("session.time_awareness", request.time_awareness, 93),
        ]
        included = [slot for slot in slots if slot.content.strip()]
        return self._apply_budget(included)

    def render_messages(self, slots: list[ContextSlot]) -> list[dict[str, str]]:
        system_chunks: list[str] = []
        user_content = ""
        for slot in slots:
            if not slot.included:
                continue
            if slot.role == "user":
                user_content = slot.content
            else:
                system_chunks.append(f"[{slot.key}]\n{slot.content}")
        return [
            {"role": "system", "content": "\n\n".join(system_chunks)},
            {"role": "user", "content": user_content},
        ]

    def _apply_budget(self, slots: list[ContextSlot]) -> list[ContextSlot]:
        used = sum(slot.token_budget for slot in slots)
        while used > MAX_CONTEXT_BUDGET:
            candidates = [slot for slot in slots if slot.included and slot.priority < 95]
            if not candidates:
                break
            loser = min(candidates, key=lambda item: (item.priority, -item.token_budget))
            loser.included = False
            used = sum(slot.token_budget for slot in slots if slot.included)
        return slots

    def _slot(self, key: str, content: str, priority: int, role: str = "system") -> ContextSlot:
        text = (content or "").strip()
        return ContextSlot(
            key=key,
            content=text,
            role=role,
            priority=priority,
            token_budget=self._estimate_budget(text),
            included=bool(text),
        )

    def _estimate_budget(self, text: str) -> int:
        if not text:
            return 1
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        ascii_words = len(re.findall(r"[A-Za-z0-9_]+", text))
        other_chars = len(re.sub(r"[\u4e00-\u9fffA-Za-z0-9_\s]", "", text))
        return max(1, int(cjk_chars * 1.1 + ascii_words * 1.3 + other_chars * 0.5))

    def _persona_identity(self, card: CharacterCard) -> str:
        backstory = card.backstory or {}
        basics = [
            f"你正在扮演校园轻陪伴聊天角色“{card.name}”。",
            f"定位：{card.archetype}。一句话：{card.tagline}。",
            f"角色简介：{card.bio}",
        ]
        for key, label in [
            ("age", "年龄"),
            ("grade", "年级"),
            ("major", "专业"),
            ("hometown", "家乡"),
            ("current_city", "当前城市"),
            ("lifestyle", "日常习惯"),
        ]:
            value = backstory.get(key)
            if value:
                basics.append(f"{label}：{value}")
        hobbies = "、".join(backstory.get("hobbies", []))
        if hobbies:
            basics.append(f"兴趣和小习惯：{hobbies}")
        return "\n".join(basics)

    def _persona_personality(self, card: CharacterCard) -> str:
        likes = "、".join(card.likes)
        hidden = "、".join((card.backstory or {}).get("hidden_facts", []))
        parts = [
            card.personality or f"{card.name}的性格底色要从{card.archetype}展开，保持稳定而具体。",
            f"喜欢：{likes}" if likes else "",
            f"隐含经历：{hidden}" if hidden else "",
            f"创作者备注：{card.creator_notes}" if card.creator_notes else "",
        ]
        return "\n".join(part for part in parts if part)

    def _persona_scenario(self, card: CharacterCard) -> str:
        scenario = card.scenario or "当前关系处在校园轻陪伴聊天中，以用户本轮话题为中心，不固定地点、道具或动作。"
        post = card.post_history_instructions or "延续最近对话的情绪，不复述设定，不突然改变亲密程度。"
        system_prompt = card.system_prompt or "保持角色口吻和边界，优先自然回应用户。"
        return "\n".join([
            f"关系语境和氛围：{scenario}",
            f"系统行为：{system_prompt}",
            f"历史之后的续写原则：{post}",
        ])

    def _persona_interaction_policy(self, card: CharacterCard) -> str:
        policy = card.interaction_policy or {}
        anti_patterns = card.anti_patterns or []
        lines = [
            f"主动程度：{policy.get('initiative_level', 0.45)}",
            f"动作密度：{policy.get('action_density', 'low')}。动作可以根据当前消息动态生成，也可以没有动作。",
            f"动作风格：{policy.get('action_style', '符合角色气质、轻量、不抢话、不固定地点或道具')}",
            f"安慰方式：{policy.get('comfort_style', '先承接用户，再给一个具体的小落点')}",
            f"追问方式：{policy.get('question_style', '少量追问，优先回应用户已经说出的内容')}",
            f"记忆提起方式：{policy.get('memory_style', '自然提起，不像读档案')}",
            "动态动作规则：一轮最多一个轻动作；不要连续重复同一动作；不要让动作覆盖回答；不要把回复写成小说旁白。",
        ]
        if anti_patterns:
            lines.append("反模式：" + "；".join(anti_patterns))
        return "\n".join(lines)

    def _persona_voice(self, card: CharacterCard) -> str:
        voice = card.voice or {}
        sample_lines = " / ".join(voice.get("sample_lines", []))
        moves = "、".join(voice.get("signature_moves", []))
        avoid = "、".join(voice.get("avoid", []))
        return (
            f"说话风格：{card.speech_style}\n"
            f"句式节奏：{voice.get('sentence_rhythm', '')}\n"
            f"回应倾向：{moves or '顺着用户当前意图接话'}\n"
            f"避免口吻：{avoid or '系统腔、长篇说教'}\n"
            f"参考短句只学语气不要照抄：{sample_lines}"
        )

    def _persona_boundaries(self, card: CharacterCard) -> str:
        dislikes = "、".join(card.dislikes)
        boundaries = "；".join(card.boundaries)
        boundary_details = (card.backstory or {}).get("boundary_details", "")
        return (
            f"边界：{boundaries}\n"
            f"不喜欢：{dislikes}\n"
            f"关系节奏：{card.relationship_pace}\n"
            f"细节边界：{boundary_details}\n"
            "隐藏经历和背景只作为稳定底色，不要像简历一样主动倾倒设定。"
        )

    def _persona_examples(self, card: CharacterCard) -> str:
        examples = card.mes_example.strip()
        if examples:
            return f"对话示例只用于学习口吻和节奏，不要照抄：\n{examples}"
        voice = card.voice or {}
        lines = "\n".join(f"- {line}" for line in voice.get("sample_lines", []))
        return f"口吻示例只用于学习风格：\n{lines}" if lines else ""

    def _memory_profile(self, memories: list[MemoryItem]) -> str:
        stable = [
            item.content
            for item in memories
            if item.memory_type in {"stable_user_info", "user_preference", "relationship_progress"}
        ]
        return "用户长期画像：" + ("；".join(stable[:8]) if stable else "暂无稳定画像。")

    def _memory_recall(self, memories: list[MemoryItem]) -> str:
        if not memories:
            return "本轮没有召回到可靠记忆，不要为了显得记得而编造旧事。"
        lines = [
            f"- [{item.memory_scope}/{item.memory_type}/{self._memory_time_label(item)}/重要度{item.importance:.1f}] {item.content}"
            for item in memories[:8]
        ]
        return (
            "本轮可用记忆：\n"
            + "\n".join(lines)
            + "\n使用：只有当记忆与当前话题相关时才自然提起；"
            "可以说“你昨天提过”或“上次你说过”，不要机械复述时间戳。"
        )

    def _memory_time_label(self, item: MemoryItem, now: datetime | None = None) -> str:
        parsed = self._parse_timestamp(item.source_created_at or item.created_at)
        if not parsed:
            return "较早前提到"
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        seconds = max(0.0, (current - parsed).total_seconds())
        minutes = int(seconds // 60)
        if minutes < 30:
            return "刚才提到"
        current_local = current.astimezone(LOCAL_TZ)
        parsed_local = parsed.astimezone(LOCAL_TZ)
        days = max(0, (current_local.date() - parsed_local.date()).days)
        if days == 0:
            return "今天早些时候提到"
        if days == 1:
            return "昨天提到"
        if days < 7:
            return f"{days}天前提到"
        if days < 14:
            return "上周提到"
        if days < 60:
            weeks = max(2, int(round(days / 7)))
            return f"{weeks}周前提到"
        if days < 365:
            months = max(2, int(round(days / 30)))
            return f"{months}个月前提到"
        return "较早前提到"

    def _parse_timestamp(self, value: str | None) -> datetime | None:
        text = (value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _recent_messages(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            return "这是这段会话的开头。"
        return "\n".join(f"{item['role']}: {item['content']}" for item in messages[-10:])

    def _response_rules(self) -> str:
        return (
            "只输出角色回复本身。优先回答用户当前这句话，再自然使用人设和记忆。"
            "不要提到 prompt、slot、系统、记忆提取、评分、剧情导演或内部模块。"
            "普通回复 2 到 4 句，中文自然亲近，不要写成长篇小说旁白。"
            "如果召回记忆不相关，就不要主动提。"
        )
