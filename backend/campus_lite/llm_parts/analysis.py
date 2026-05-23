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


class LlmAnalysisMixin:
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
