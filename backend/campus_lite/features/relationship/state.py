from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...schemas import CharacterCard, MemoryItem
from ...storage import Storage


MIN_RESONANCE_DELTA = -0.03
MAX_RESONANCE_DELTA = 0.05


class CharacterStateService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def default_state(self, character: CharacterCard | None = None) -> dict[str, Any]:
        energy = self._default_energy(character)
        resonance = 0.30
        return {
            "mood": self._default_mood(character),
            "tone": self._default_tone(character),
            "distance": self._default_distance(character),
            "focus": self._default_focus(character),
            "energy": energy,
            "resonance": resonance,
            "behavior": self._behavior_from_character(character, energy, resonance),
            "last_shift": self._default_evidence(character),
            "evidence": self._default_evidence(character),
            "updated_at": self._now_iso(),
        }

    def get_state(self, session_id: str, character: CharacterCard | None = None) -> dict[str, Any]:
        session = self.storage.get_session(session_id)
        if not session:
            return self.default_state(character)
        try:
            raw = json.loads(session["character_state_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            raw = {}
        return self.normalize_state(raw, character)

    def ensure_state(self, session_id: str, character: CharacterCard | None = None) -> dict[str, Any]:
        state = self.get_state(session_id, character)
        session = self.storage.get_session(session_id)
        if session and self._should_seed_state(session["character_state_json"]):
            self.storage.set_character_state(session_id, state)
        return state

    async def update_after_turn(
        self,
        llm: Any,
        session_id: str,
        character: CharacterCard,
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any]:
        previous = self.get_state(session_id, character)
        scored = await llm.score_character_state(
            character,
            previous,
            recent_messages,
            user_message,
            assistant_reply,
            recalled_memories,
        )
        if not scored:
            return previous
        next_state = self.apply_model_score(previous, scored, character)
        self.storage.set_character_state(session_id, next_state)
        return next_state

    def apply_model_score(
        self,
        previous: dict[str, Any],
        scored: dict[str, Any],
        character: CharacterCard | None = None,
    ) -> dict[str, Any]:
        previous = self.normalize_state(previous, character)
        energy = self._clamp(self._safe_float(scored.get("energy"), previous["energy"]), 0.0, 1.0)
        delta = self._clamp(self._safe_float(scored.get("resonance_delta"), 0.0), MIN_RESONANCE_DELTA, MAX_RESONANCE_DELTA)
        resonance = self._clamp(self._safe_float(previous["resonance"], 0.30) + delta, 0.0, 1.0)
        behavior = self._clean_behavior(scored.get("behavior"))
        if not behavior:
            behavior = self._behavior_from_character(character, energy, resonance)
        return {
            "mood": self._short_text(scored.get("mood"), previous["mood"]),
            "tone": self._short_text(scored.get("tone"), previous["tone"]),
            "distance": self._short_text(scored.get("distance"), previous["distance"]),
            "focus": self._short_text(scored.get("focus"), previous["focus"], 120),
            "energy": energy,
            "resonance": resonance,
            "behavior": behavior,
            "last_shift": self._short_text(scored.get("evidence") or scored.get("last_shift"), previous["last_shift"], 180),
            "evidence": self._short_text(scored.get("evidence"), previous.get("evidence", ""), 180),
            "updated_at": self._now_iso(),
        }

    def update_from_score(
        self,
        session_id: str,
        previous: dict[str, Any],
        scored: dict[str, Any] | None,
        character: CharacterCard | None = None,
    ) -> dict[str, Any]:
        if not scored:
            return self.normalize_state(previous, character)
        next_state = self.apply_model_score(previous, scored, character)
        self.storage.set_character_state(session_id, next_state)
        return next_state

    def normalize_state(self, raw: dict[str, Any], character: CharacterCard | None = None) -> dict[str, Any]:
        default = self.default_state(character)
        energy = self._clamp(self._safe_float(raw.get("energy"), default["energy"]), 0.0, 1.0)
        resonance = self._clamp(self._safe_float(raw.get("resonance"), default["resonance"]), 0.0, 1.0)
        behavior = self._clean_behavior(raw.get("behavior")) or self._behavior_from_character(character, energy, resonance)
        return {
            "mood": self._short_text(raw.get("mood"), default["mood"]),
            "tone": self._short_text(raw.get("tone"), default["tone"]),
            "distance": self._short_text(raw.get("distance"), default["distance"]),
            "focus": self._short_text(raw.get("focus"), default["focus"], 120),
            "energy": energy,
            "resonance": resonance,
            "behavior": behavior,
            "last_shift": self._short_text(raw.get("last_shift"), default["last_shift"], 180),
            "evidence": self._short_text(raw.get("evidence"), default["evidence"], 180),
            "updated_at": self._short_text(raw.get("updated_at"), default["updated_at"], 40),
        }

    def state_to_prompt(self, state: dict[str, Any]) -> str:
        state = self.normalize_state(state)
        behavior = state["behavior"]
        return "\n".join([
            f"当前互动心境：{state['mood']}；语气倾向：{state['tone']}；互动距离：{state['distance']}。",
            f"当前关注点：{state['focus']}",
            "本轮行为指导："
            f"回复节奏={behavior['pace']}；"
            f"主动程度={behavior['initiative']}；"
            f"温度={behavior['warmth']}；"
            f"记忆使用={behavior['memory_use']}；"
            f"避免={behavior['avoid']}。",
            f"状态变化依据：{state['last_shift']}",
            "只把这些当作语气和节奏参考，不要提到状态条、成长值、默契度、分数或内部评分。",
        ])

    def _behavior_from_scores(self, energy: float, resonance: float) -> dict[str, str]:
        if energy < 0.34:
            pace = "放慢，回复更短更稳"
            initiative = "少主动展开，少连续追问"
        elif energy < 0.67:
            pace = "正常承接，保持清晰"
            initiative = "适度提问，优先回应用户已经说出的内容"
        else:
            pace = "更轻快，可以多一点主动承接"
            initiative = "可以提供一两个自然选项，但不要抢话"

        if resonance < 0.34:
            warmth = "保持礼貌和温和，不默认过度熟悉"
            memory_use = "只使用高度相关且明确的记忆"
        elif resonance < 0.67:
            warmth = "自然熟悉，但不突然亲密"
            memory_use = "可以轻轻承接相关共同记忆"
        else:
            warmth = "更顺手地接住共同语境，仍保留边界"
            memory_use = "可以自然引用高可信共同记忆和用户偏好"

        return {
            "pace": pace,
            "initiative": initiative,
            "warmth": warmth,
            "memory_use": memory_use,
            "avoid": "不要把系统状态、评分或关系数值说给用户听",
        }

    def _behavior_from_character(
        self,
        character: CharacterCard | None,
        energy: float,
        resonance: float,
    ) -> dict[str, str]:
        behavior = self._behavior_from_scores(energy, resonance)
        if not character:
            return behavior
        policy = character.interaction_policy or {}
        voice = character.voice or {}
        anti_patterns = character.anti_patterns or []
        behavior["pace"] = self._short_text(voice.get("sentence_rhythm"), behavior["pace"], 100)
        behavior["initiative"] = self._short_text(policy.get("question_style"), behavior["initiative"], 100)
        behavior["warmth"] = self._short_text(character.relationship_pace, behavior["warmth"], 100)
        behavior["memory_use"] = self._short_text(policy.get("memory_style"), behavior["memory_use"], 100)
        avoid = "；".join(anti_patterns[:2]) if anti_patterns else behavior["avoid"]
        behavior["avoid"] = self._short_text(avoid, behavior["avoid"], 100)
        return behavior

    def _default_energy(self, character: CharacterCard | None) -> float:
        policy = character.interaction_policy if character else {}
        initiative = self._safe_float((policy or {}).get("initiative_level"), 0.45)
        return self._clamp(0.25 + initiative * 0.5, 0.25, 0.75)

    def _default_mood(self, character: CharacterCard | None) -> str:
        if not character:
            return "安静接住"
        return self._short_text(f"保持{character.archetype}底色", "角色基准状态")

    def _default_tone(self, character: CharacterCard | None) -> str:
        if not character:
            return "自然、温和"
        return self._short_text(character.speech_style, "自然回应", 80)

    def _default_distance(self, character: CharacterCard | None) -> str:
        if not character:
            return "初步熟悉"
        return self._short_text(character.relationship_pace, "按角色节奏慢慢熟悉", 80)

    def _default_focus(self, character: CharacterCard | None) -> str:
        if not character:
            return "优先回应用户当前这句话"
        policy = character.interaction_policy or {}
        return self._short_text(policy.get("comfort_style"), "优先回应用户当前这句话", 120)

    def _default_evidence(self, character: CharacterCard | None) -> str:
        if not character:
            return "新会话默认状态，尚未形成明显互动变化。"
        return f"来自角色卡的初始互动基准：{character.name} / {character.archetype}。"

    def _should_seed_state(self, raw_json: str) -> bool:
        if not (raw_json or "").strip("{} "):
            return True
        try:
            raw = json.loads(raw_json)
        except (TypeError, json.JSONDecodeError):
            return True
        return raw.get("evidence") == "暂无状态评分证据。"

    def _clean_behavior(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        cleaned = {
            key: self._short_text(value.get(key), "", 100)
            for key in ["pace", "initiative", "warmth", "memory_use", "avoid"]
        }
        return cleaned if all(cleaned.values()) else {}

    def _short_text(self, value: Any, fallback: str, limit: int = 80) -> str:
        text = str(value or "").strip()
        return (text or fallback)[:limit]

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _safe_float(self, value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
