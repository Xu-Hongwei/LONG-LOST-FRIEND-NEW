from __future__ import annotations

import json
import logging
from typing import Any

from ..schemas import CharacterCard, MemoryItem


logger = logging.getLogger(__name__)


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
            ])
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
            ])
            return self._parse_state_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("character state scoring failed: %s", exc)
            return None

    async def score_character_bond(
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
                {"role": "system", "content": self.character_bond_system_prompt()},
                {"role": "user", "content": user},
            ])
            return self._parse_bond_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("character bond scoring failed: %s", exc)
            return None

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
