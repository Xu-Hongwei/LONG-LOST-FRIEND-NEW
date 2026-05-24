from __future__ import annotations

import json
import logging
from typing import Any

from ..schemas import CharacterCard, MemoryItem


logger = logging.getLogger(__name__)

RELATIONSHIP_STAGE_TIMEOUT_MS = 12_000
BOND_STAGE_TIMEOUT_MS = 24_000
RELATIONSHIP_EVENT_STRUCTURED_PROMPT = (
    "Extract relationship events between the user and the current character from the provided chat context. "
    "Return one JSON object only: {\"events\":[...]}. Use {\"events\":[]} only when no relationship event is present. "
    "Each event may contain only event_type, evidence_grade, and evidence_text. "
    "Allowed event_type values are shared_context, preference_confirmed, trust_signal, emotional_disclosure, "
    "boundary_respected, negative_feedback, boundary_violation, and repair. "
    "Allowed evidence_grade values are explicit, strong, contextual, and weak. "
    "Evidence text must be an exact contiguous substring copied from the supplied user message whenever the evidence "
    "comes from the user. Do not summarize, paraphrase, normalize, shorten, translate, or prefix it with phrases such "
    "as 'the user said' or '用户表示'. If no exact user-message substring supports the event, return contextual/weak "
    "or omit the event. "
    "Never output relationship stages, scores, score deltas, resonance values, or free numeric confidence. "
    "Use explicit when the user directly confirms trust, a boundary, a relationship-facing preference, "
    "a concrete shared pact, a violation, or an accepted repair. "
    "Use strong only for direct text evidence with very little inference. "
    "Use contextual or weak for indirect hints. "
    "Assistant-only reassurance, ordinary acknowledgements, topic switches, scheduling, and casual chat are not enough. "
    "For overlapping evidence keep the single highest-priority event: boundary_violation before negative_feedback, "
    "and repair before shared_context or trust_signal."
)

CHARACTER_DRAFT_STRUCTURED_PROMPT = (
    "You expand a short user idea into a safe fictional AI chat character card. "
    "Return one JSON object only with key \"character\". The character object must use these keys: "
    "name, archetype, tagline, gender, bio, personality, scenario, speech_style, relationship_pace, "
    "opening_line, likes, dislikes, boundaries, mes_example, creator_notes, system_prompt, "
    "post_history_instructions, interaction_policy, anti_patterns, voice, visual. "
    "interaction_policy must include initiative_level, action_density, action_style, comfort_style, "
    "question_style, memory_style. voice must include sentence_rhythm, signature_moves, avoid, sample_lines. "
    "visual must include accent and portrait_hint. "
    "Make the examples rich enough to be useful: sample_lines should contain 4 to 6 short reusable lines; "
    "mes_example should contain 2 to 3 user/character exchanges showing greeting, emotional support, memory use, "
    "and boundary or relationship pacing where relevant. "
    "likes, dislikes, boundaries, anti_patterns, and signature_moves should usually contain 3 to 6 concrete items. "
    "Do not create a real-person impersonation, do not include private personal data, and keep the role fictional. "
    "Write natural Chinese fields unless the user explicitly asks otherwise. "
    "The card should be usable for a campus companion chat and should avoid forcing intimacy or fixed actions every turn."
)


class LlmAnalysisMixin:
    async def generate_character_draft(
        self,
        prompt: str,
        template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user = (
            f"用户粗设定：{prompt}\n"
            f"可参考模板：{json.dumps(template or {}, ensure_ascii=False)}\n"
            "请扩写成完整角色卡 JSON。不要保存角色，只返回草稿。"
        )
        if not self.provider:
            return self._fallback_character_draft(prompt, template)
        try:
            text = await self.chat_complete(
                [
                    {"role": "system", "content": CHARACTER_DRAFT_STRUCTURED_PROMPT},
                    {"role": "user", "content": user},
                ],
                timeout_ms=24_000,
                response_format={"type": "json_object"},
                temperature=0.55,
            )
            parsed = self._parse_character_draft_json(text)
            if parsed:
                return parsed
            self.last_analysis_error = "InvalidCharacterDraftJson"
        except Exception as exc:
            self.last_analysis_error = type(exc).__name__
            logger.warning("character draft generation failed: %s", exc)
        return self._fallback_character_draft(prompt, template)

    def _fallback_character_draft(self, prompt: str, template: dict[str, Any] | None = None) -> dict[str, Any]:
        base = template if isinstance(template, dict) else {}
        seed = (prompt or "").strip()
        name = str(base.get("name") or "").strip() or "自定义角色"
        archetype = str(base.get("archetype") or "").strip() or "自定义人格"
        raw = {
            **base,
            "name": name,
            "archetype": archetype,
            "tagline": str(base.get("tagline") or f"由设定「{seed[:40] or '自定义'}」扩写出的角色"),
            "bio": str(base.get("bio") or f"这个角色围绕用户设定展开：{seed}"),
            "personality": str(base.get("personality") or f"核心设定：{seed}。保持稳定、具体、不过度表演。"),
            "scenario": str(base.get("scenario") or "当前关系处在轻陪伴聊天中，地点和动作跟随上下文自然生成。"),
            "speech_style": str(base.get("speech_style") or "自然、具体、少说教，优先回应用户当下的话。"),
            "likes": base.get("likes") or ["清楚表达", "稳定回应", "自然的共同记忆"],
            "dislikes": base.get("dislikes") or ["突然越界", "空泛说教", "固定动作循环"],
            "boundaries": base.get("boundaries") or ["不强行推进亲密关系", "不冒充真人", "遇到危险或违法话题时温和拒绝"],
            "relationship_pace": str(base.get("relationship_pace") or "根据聊天自然推进，不突然越界。"),
            "opening_line": str(base.get("opening_line") or f"你好，我是{name}。你刚刚那个设定，我已经记住了。"),
            "mes_example": str(base.get("mes_example") or "\n".join([
                "用户：今天有点不知道从哪里开始。",
                f"{name}：那就先不用急着讲完整。你给我一个最小的开头就好，我会接住。",
                "",
                "用户：你会记得我之前说过的事吗？",
                f"{name}：会。但我不会像读档案一样念出来，只会在刚好需要的时候轻轻提一下。",
                "",
                "用户：我不太喜欢被催着表态。",
                f"{name}：明白。那我会放慢一点，先确认你的节奏，不替你做决定。",
            ])),
            "creator_notes": str(base.get("creator_notes") or "这是本地 fallback 草稿；远程模型不可用或返回格式无效时生成。"),
            "anti_patterns": base.get("anti_patterns") or ["不要突然告白", "不要每轮重复同一个动作", "不要把安慰写成训话"],
            "interaction_policy": {
                "initiative_level": 0.45,
                "action_density": "low",
                "action_style": "动作轻量、跟随语境，不固定道具或场景。",
                "comfort_style": "先回应用户感受，再给一个具体落点。",
                "question_style": "少量追问，优先接住用户已经说出的内容。",
                "memory_style": "自然提起相关记忆，不像读档案。",
            },
            "voice": {
                "sentence_rhythm": "句子自然，有节奏但不过度文学化。",
                "signature_moves": ["顺着用户当前话题回应", "把抽象感受落成具体态度", "在合适时自然提起旧话题"],
                "avoid": ["系统腔", "固定动作循环", "突然推进亲密", "长篇说教"],
                "sample_lines": [
                    f"我大概懂你想要的感觉：{seed[:60] or '稳定、自然、具体'}。",
                    "我们可以先从最小的那句话开始，不用一下子讲完。",
                    "这件事我会记得，但不会拿它压着你。",
                    "如果你不想现在回答，我就先陪你停在这里。",
                    "我会慢一点靠近，不抢你的节奏。",
                ],
            },
            "visual": {"accent": "#9fb6d7", "portrait_hint": "自定义角色"},
        }
        return self._clean_character_draft(raw)

    async def extract_memories(self, user_message: str, assistant_reply: str) -> list[dict[str, Any]]:
        if not self.provider:
            return []
        system = self.memory_extraction_system_prompt()
        user = f"用户消息：{user_message}\n角色回复：{assistant_reply}"
        try:
            text = await self.chat_complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], timeout_ms=RELATIONSHIP_STAGE_TIMEOUT_MS)
            return self._parse_memory_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("memory extraction failed: %s", exc)
            return []

    async def score_character_state(
        self,
        character: CharacterCard,
        previous_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any] | None:
        if not self.provider:
            return None
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧状态：{json.dumps(previous_state, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": self.character_state_system_prompt()},
                {"role": "user", "content": user},
            ], timeout_ms=RELATIONSHIP_STAGE_TIMEOUT_MS)
            return self._parse_state_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("character state scoring failed: %s", exc)
            return None

    async def extract_relationship_events(
        self,
        character: CharacterCard,
        previous_bond: dict[str, Any],
        current_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any] | None:
        if not self.provider:
            return None
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧长期关系档案：{json.dumps(previous_bond, ensure_ascii=False)}\n"
            f"当前短期状态：{json.dumps(current_state, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": RELATIONSHIP_EVENT_STRUCTURED_PROMPT},
                {
                    "role": "system",
                    "content": (
                        'Structured output contract: return one JSON object only, shaped as {"events":[...]}. '
                        'Use {"events":[]} when there is no relationship event. '
                        "Each event may contain only event_type, evidence_grade, and evidence_text. "
                        "The evidence_text must be copied exactly from the current user message as a contiguous "
                        "substring. Do not output summaries like 'the user said ...' or '用户表示...'. "
                        "Do not return an empty events array when the user explicitly says they trust this character, "
                        "names a boundary violation, states a relationship-facing interaction preference, "
                        "accepts a repair after harm, or names a concrete shared pact. "
                        'Example trust output: {"events":[{"event_type":"trust_signal","evidence_grade":"explicit",'
                        '"evidence_text":"I trust you to take what I say seriously."}]}. '
                        'Example boundary output: {"events":[{"event_type":"boundary_violation","evidence_grade":"explicit",'
                        '"evidence_text":"You crossed a line just now; do not keep questioning me like that."}]}.'
                    ),
                },
                {"role": "user", "content": user},
            ],
                timeout_ms=BOND_STAGE_TIMEOUT_MS,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return self._parse_relationship_events_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("relationship event extraction failed: %s", exc)
            return []

    async def score_character_bond(
        self,
        character: CharacterCard,
        previous_bond: dict[str, Any],
        current_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> list[dict[str, Any]]:
        return await self.extract_relationship_events(
            character,
            previous_bond,
            current_state,
            recent_messages,
            user_message,
            assistant_reply,
            recalled_memories,
        )

    async def analyze_turn(
        self,
        character: CharacterCard,
        previous_state: dict[str, Any],
        previous_bond: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any]:
        if not self.provider:
            return {"state": None, "bond": None, "memories": []}
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧短期状态：{json.dumps(previous_state, ensure_ascii=False)}\n"
            f"旧长期关系档案：{json.dumps(previous_bond, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": self.turn_analysis_system_prompt()},
                {"role": "user", "content": user},
            ])
            self.last_analysis_error = None
            return self._parse_turn_analysis_json(text)
        except Exception as exc:
            self.last_analysis_error = type(exc).__name__
            logger.warning("turn analysis failed: %s", exc)
            return {"state": None, "bond": None, "memories": []}
