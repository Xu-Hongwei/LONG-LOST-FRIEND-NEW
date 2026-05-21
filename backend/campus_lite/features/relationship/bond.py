from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...schemas import CharacterCard, MemoryItem
from ...storage import Storage


MIN_BOND_DELTA = -0.01
MAX_BOND_DELTA = 0.02


class CharacterBondService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def default_bond(self, character: CharacterCard | None = None) -> dict[str, Any]:
        return {
            "familiarity_stage": "初识",
            "resonance_base": 0.30,
            "trust_notes": self._default_trust_notes(character),
            "boundary_notes": self._default_boundary_notes(character),
            "interaction_preferences": self._default_interaction_preferences(character),
            "milestones": [],
            "evidence": self._default_evidence(character),
            "updated_at": self._now_iso(),
        }

    def get_bond(self, visitor_id: str, character_id: str, character: CharacterCard | None = None) -> dict[str, Any]:
        row = self.storage.get_character_bond(visitor_id, character_id)
        if not row:
            return self.default_bond(character)
        milestones = []
        try:
            milestones = json.loads(row["milestones_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            milestones = []
        return self.normalize_bond({
            "familiarity_stage": row["familiarity_stage"],
            "resonance_base": row["resonance_base"],
            "trust_notes": row["trust_notes"],
            "boundary_notes": row["boundary_notes"],
            "interaction_preferences": row["interaction_preferences"],
            "milestones": milestones,
            "evidence": row["evidence"],
            "updated_at": row["updated_at"],
        }, character)

    def ensure_bond(self, visitor_id: str, character_id: str, character: CharacterCard | None = None) -> dict[str, Any]:
        existing = self.storage.get_character_bond(visitor_id, character_id)
        if existing:
            return self.get_bond(visitor_id, character_id, character)
        bond = self.default_bond(character)
        self.storage.upsert_character_bond(visitor_id, character_id, bond)
        return bond

    async def update_after_turn(
        self,
        llm: Any,
        visitor_id: str,
        character: CharacterCard,
        previous_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any]:
        previous = self.get_bond(visitor_id, character.id, character)
        scored = await llm.score_character_bond(
            character,
            previous,
            previous_state,
            recent_messages,
            user_message,
            assistant_reply,
            recalled_memories,
        )
        if not scored or not self._truthy(scored.get("should_update")):
            return previous
        next_bond = self.apply_model_update(previous, scored, character)
        self.storage.upsert_character_bond(visitor_id, character.id, next_bond)
        return next_bond

    def apply_model_update(
        self,
        previous: dict[str, Any],
        scored: dict[str, Any],
        character: CharacterCard | None = None,
    ) -> dict[str, Any]:
        previous = self.normalize_bond(previous, character)
        delta = self._clamp(self._safe_float(scored.get("resonance_base_delta"), 0.0), MIN_BOND_DELTA, MAX_BOND_DELTA)
        resonance_base = self._clamp(previous["resonance_base"] + delta, 0.0, 1.0)
        milestone = self._short_text(scored.get("milestone"), "", 120)
        milestones = list(previous["milestones"])
        if milestone and milestone not in milestones:
            milestones.append(milestone)
        return {
            "familiarity_stage": self._short_text(scored.get("familiarity_stage"), previous["familiarity_stage"], 80),
            "resonance_base": resonance_base,
            "trust_notes": self._short_text(scored.get("trust_notes"), previous["trust_notes"], 600),
            "boundary_notes": self._short_text(scored.get("boundary_notes"), previous["boundary_notes"], 600),
            "interaction_preferences": self._short_text(
                scored.get("interaction_preferences"),
                previous["interaction_preferences"],
                600,
            ),
            "milestones": milestones[-8:],
            "evidence": self._short_text(scored.get("evidence"), previous["evidence"], 300),
            "updated_at": self._now_iso(),
        }

    def update_from_score(
        self,
        visitor_id: str,
        character: CharacterCard,
        previous: dict[str, Any],
        scored: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not scored or not self._truthy(scored.get("should_update")):
            return self.normalize_bond(previous, character)
        next_bond = self.apply_model_update(previous, scored, character)
        self.storage.upsert_character_bond(visitor_id, character.id, next_bond)
        return next_bond

    def normalize_bond(self, raw: dict[str, Any], character: CharacterCard | None = None) -> dict[str, Any]:
        default = self.default_bond(character)
        milestones = raw.get("milestones")
        if not isinstance(milestones, list):
            milestones = default["milestones"]
        clean_milestones = [self._short_text(item, "", 120) for item in milestones if self._short_text(item, "", 120)]
        return {
            "familiarity_stage": self._short_text(raw.get("familiarity_stage"), default["familiarity_stage"], 80),
            "resonance_base": self._clamp(self._safe_float(raw.get("resonance_base"), default["resonance_base"]), 0.0, 1.0),
            "trust_notes": self._short_text(raw.get("trust_notes"), default["trust_notes"], 600),
            "boundary_notes": self._short_text(raw.get("boundary_notes"), default["boundary_notes"], 600),
            "interaction_preferences": self._short_text(
                raw.get("interaction_preferences"),
                default["interaction_preferences"],
                600,
            ),
            "milestones": clean_milestones[-8:],
            "evidence": self._short_text(raw.get("evidence"), default["evidence"], 300),
            "updated_at": self._short_text(raw.get("updated_at"), default["updated_at"], 40),
        }

    def bond_to_prompt(self, bond: dict[str, Any]) -> str:
        bond = self.normalize_bond(bond)
        milestones = "；".join(bond["milestones"][-4:]) if bond["milestones"] else "暂无关键节点。"
        return "\n".join([
            f"长期角色关系档案：当前熟悉阶段为“{bond['familiarity_stage']}”。",
            f"长期默契基线：{self._resonance_label(bond['resonance_base'])}。这不是好感度，只表示互动方式的熟悉程度。",
            f"信任来源：{bond['trust_notes']}",
            f"用户在这个角色面前的边界：{bond['boundary_notes']}",
            f"互动偏好：{bond['interaction_preferences']}",
            f"关键节点：{milestones}",
            "使用方式：自然参考这些长期关系信息，不要提到 Bond、成长档案、默契基线或任何分数。",
        ])

    def _default_trust_notes(self, character: CharacterCard | None) -> str:
        if not character:
            return "尚未形成稳定信任来源。"
        return f"初始以角色卡节奏建立信任：{character.relationship_pace or character.archetype}。"

    def _default_boundary_notes(self, character: CharacterCard | None) -> str:
        if not character:
            return "遵守通用安全边界，等待用户表达具体边界。"
        boundary = "；".join(character.boundaries[:2]) if character.boundaries else "遵守角色安全边界。"
        return f"先遵守角色边界，用户个人边界待对话中确认：{boundary}"

    def _default_interaction_preferences(self, character: CharacterCard | None) -> str:
        if not character:
            return "优先回应用户当前意图，少做无依据推断。"
        policy = character.interaction_policy or {}
        question = policy.get("question_style") or "优先回应用户当前意图"
        memory = policy.get("memory_style") or "自然使用相关记忆"
        return f"{question}；{memory}"

    def _default_evidence(self, character: CharacterCard | None) -> str:
        if not character:
            return "来自默认长期关系基准。"
        return f"来自角色卡的长期关系基准：{character.name} / {character.archetype}。"

    def _resonance_label(self, value: float) -> str:
        if value < 0.34:
            return "刚开始建立"
        if value < 0.67:
            return "已有自然熟悉感"
        return "高度稳定熟悉"

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "是", "需要"}
        return bool(value)

    def _short_text(self, value: Any, fallback: str, limit: int = 80) -> str:
        text = str(value or "").strip()
        return (text or fallback)[:limit]

    def _safe_float(self, value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
