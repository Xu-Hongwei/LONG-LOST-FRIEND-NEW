from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...schemas import CharacterCard, MemoryItem
from ...storage import Storage


EVENT_WEIGHTS: dict[str, dict[str, float]] = {
    "shared_context": {"trust_level": 0.01, "closeness_level": 0.02, "boundary_safety": 0.0},
    "preference_confirmed": {"trust_level": 0.01, "closeness_level": 0.01, "boundary_safety": 0.01},
    "trust_signal": {"trust_level": 0.04, "closeness_level": 0.01, "boundary_safety": 0.0},
    "emotional_disclosure": {"trust_level": 0.03, "closeness_level": 0.03, "boundary_safety": 0.0},
    "boundary_respected": {"trust_level": 0.02, "closeness_level": 0.0, "boundary_safety": 0.04},
    "negative_feedback": {"trust_level": -0.03, "closeness_level": -0.02, "boundary_safety": -0.02},
    "boundary_violation": {"trust_level": -0.05, "closeness_level": -0.03, "boundary_safety": -0.08},
    "repair": {"trust_level": 0.02, "closeness_level": 0.01, "boundary_safety": 0.03},
}
EVIDENCE_CONFIDENCE = {"explicit": 0.95, "strong": 0.85}
STAGE_LABELS = {
    "initial": "初识",
    "familiar": "逐渐熟悉",
    "trusted": "建立信任",
    "close": "稳定靠近",
}
CONDITION_LABELS = {
    "steady": "稳定",
    "warming": "升温中",
    "guarded": "有保留",
    "strained": "关系受损",
    "repairing": "修复中",
}
FAMILIARITY_STAGE_CODES = {
    "初识": "initial",
    "逐渐熟悉": "familiar",
    "稳定熟悉": "trusted",
    "形成默契": "close",
    "建立信任": "trusted",
    "稳定靠近": "close",
}
POSITIVE_EVENT_TYPES = {
    "shared_context",
    "preference_confirmed",
    "trust_signal",
    "emotional_disclosure",
    "boundary_respected",
    "repair",
}
NEGATIVE_EVENT_TYPES = {"negative_feedback", "boundary_violation"}
DELTA_CAPS = {
    "trust_level": (-0.08, 0.05),
    "closeness_level": (-0.06, 0.05),
    "boundary_safety": (-0.10, 0.04),
}
EVENT_PRIORITY = {
    "boundary_violation": 90,
    "repair": 80,
    "boundary_respected": 70,
    "trust_signal": 60,
    "emotional_disclosure": 50,
    "preference_confirmed": 40,
    "shared_context": 30,
    "negative_feedback": 20,
}


class CharacterBondService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def default_bond(self, character: CharacterCard | None = None) -> dict[str, Any]:
        return {
            "familiarity_stage": STAGE_LABELS["initial"],
            "stage_code": "initial",
            "condition_code": "steady",
            "condition_settle_turns": 0,
            "relationship_condition": CONDITION_LABELS["steady"],
            "resonance_base": 0.30,
            "trust_level": 0.30,
            "closeness_level": 0.20,
            "boundary_safety": 0.60,
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
        try:
            milestones = json.loads(row["milestones_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            milestones = []
        keys = set(row.keys())
        return self.normalize_bond({
            "familiarity_stage": row["familiarity_stage"],
            "stage_code": row["stage_code"] if "stage_code" in keys else "",
            "condition_code": row["condition_code"] if "condition_code" in keys else "",
            "condition_settle_turns": row["condition_settle_turns"] if "condition_settle_turns" in keys else 0,
            "resonance_base": row["resonance_base"],
            "trust_level": row["trust_level"] if "trust_level" in keys else None,
            "closeness_level": row["closeness_level"] if "closeness_level" in keys else None,
            "boundary_safety": row["boundary_safety"] if "boundary_safety" in keys else None,
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
        extracted = await llm.extract_relationship_events(
            character,
            previous,
            previous_state,
            recent_messages,
            user_message,
            assistant_reply,
            recalled_memories,
        )
        next_bond, _ = self.update_from_events(
            visitor_id=visitor_id,
            session_id="",
            source_message_ids=[],
            character=character,
            previous=previous,
            extracted=extracted,
            evidence_context=self._evidence_context(recent_messages, user_message, assistant_reply),
        )
        return next_bond

    def update_from_events(
        self,
        *,
        visitor_id: str,
        session_id: str,
        source_message_ids: list[str],
        character: CharacterCard,
        previous: dict[str, Any],
        extracted: list[dict[str, Any]] | None,
        evidence_context: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        previous = self.normalize_bond(previous, character)
        accepted, rejected = self._prepare_events(extracted or [], evidence_context, source_message_ids)
        historical = self.storage.list_relationship_events(visitor_id, character.id, 24)
        delta = self._reduce_delta(accepted)
        next_bond, stage_changed, frozen = self.apply_events(previous, accepted, historical, delta, character)

        bond_changed = accepted or next_bond["condition_code"] != previous["condition_code"] or (
            next_bond["condition_settle_turns"] != previous["condition_settle_turns"]
        )
        if bond_changed:
            self.storage.upsert_character_bond(visitor_id, character.id, next_bond)
        if accepted:
            if session_id:
                for event in accepted:
                    event["applied_delta"] = dict(EVENT_WEIGHTS[event["event_type"]])
                    self.storage.add_relationship_event(
                        visitor_id=visitor_id,
                        character_id=character.id,
                        session_id=session_id,
                        event=event,
                    )

        rejected_reasons: dict[str, int] = {}
        for item in rejected:
            reason = str(item.get("reason") or "rejected")
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
        return next_bond, {
            "extracted_events_count": len(extracted or []),
            "accepted_events_count": len(accepted),
            "rejected_events_count": len(rejected),
            "extracted_events": [self._event_preview(item) for item in (extracted or [])[:8]],
            "accepted_events": [self._event_preview(item) for item in accepted[:8]],
            "rejected_events": [self._event_preview(item) for item in rejected[:8]],
            "rejected_event_reasons": rejected_reasons,
            "applied_delta": delta,
            "stage_changed": stage_changed,
            "stage_code": next_bond["stage_code"],
            "condition_changed": next_bond["condition_code"] != previous["condition_code"],
            "condition_code": next_bond["condition_code"],
            "condition_settle_turns": next_bond["condition_settle_turns"],
            "progression_frozen": frozen,
        }

    def apply_events(
        self,
        previous: dict[str, Any],
        accepted: list[dict[str, Any]],
        historical: list[dict[str, Any]],
        delta: dict[str, float],
        character: CharacterCard | None = None,
    ) -> tuple[dict[str, Any], bool, bool]:
        previous = self.normalize_bond(previous, character)
        evidence = [*historical, *accepted]
        frozen = self._progression_frozen(evidence)
        if not accepted:
            next_condition, settle_turns = self._next_condition(previous, accepted, frozen)
            if next_condition == previous["condition_code"] and settle_turns == previous["condition_settle_turns"]:
                return previous, False, frozen
            settled = dict(previous)
            settled.update({
                "condition_code": next_condition,
                "condition_settle_turns": settle_turns,
                "relationship_condition": CONDITION_LABELS[next_condition],
                "updated_at": self._now_iso(),
            })
            return settled, False, frozen

        trust_level = self._clamp(previous["trust_level"] + delta["trust_level"], 0.0, 1.0)
        closeness_level = self._clamp(previous["closeness_level"] + delta["closeness_level"], 0.0, 1.0)
        boundary_safety = self._clamp(previous["boundary_safety"] + delta["boundary_safety"], 0.0, 1.0)
        next_stage = self._next_stage(
            previous["stage_code"],
            trust_level,
            closeness_level,
            boundary_safety,
            evidence,
            frozen,
        )
        next_condition, settle_turns = self._next_condition(previous, accepted, frozen)
        stage_changed = next_stage != previous["stage_code"]
        milestones = list(previous["milestones"])
        if stage_changed:
            milestones.append(f"关系阶段进入{STAGE_LABELS[next_stage]}。")
        return {
            "familiarity_stage": STAGE_LABELS[next_stage],
            "stage_code": next_stage,
            "condition_code": next_condition,
            "condition_settle_turns": settle_turns,
            "relationship_condition": CONDITION_LABELS[next_condition],
            "resonance_base": previous["resonance_base"],
            "trust_level": trust_level,
            "closeness_level": closeness_level,
            "boundary_safety": boundary_safety,
            "trust_notes": self._update_note(
                previous["trust_notes"],
                accepted,
                {"trust_signal", "emotional_disclosure", "boundary_respected", "repair"},
            ),
            "boundary_notes": self._update_note(
                previous["boundary_notes"],
                accepted,
                {"boundary_respected", "negative_feedback", "boundary_violation", "repair"},
            ),
            "interaction_preferences": self._update_note(
                previous["interaction_preferences"],
                accepted,
                {"preference_confirmed"},
            ),
            "milestones": milestones[-8:],
            "evidence": self._latest_evidence(accepted, previous["evidence"]),
            "updated_at": self._now_iso(),
        }, stage_changed, frozen

    def normalize_bond(self, raw: dict[str, Any], character: CharacterCard | None = None) -> dict[str, Any]:
        default = self.default_bond(character)
        milestones = raw.get("milestones")
        if not isinstance(milestones, list):
            milestones = default["milestones"]
        clean_milestones = [self._short_text(item, "", 120) for item in milestones if self._short_text(item, "", 120)]
        stage_code = self._stage_code(raw.get("stage_code"), raw.get("familiarity_stage"))
        condition_code = self._condition_code(raw.get("condition_code"))
        return {
            "familiarity_stage": STAGE_LABELS[stage_code],
            "stage_code": stage_code,
            "condition_code": condition_code,
            "condition_settle_turns": self._safe_int(
                raw.get("condition_settle_turns"),
                default["condition_settle_turns"],
                0,
                2,
            ),
            "relationship_condition": CONDITION_LABELS[condition_code],
            "resonance_base": self._clamp(self._safe_float(raw.get("resonance_base"), default["resonance_base"]), 0.0, 1.0),
            "trust_level": self._clamp(self._safe_float(raw.get("trust_level"), default["trust_level"]), 0.0, 1.0),
            "closeness_level": self._clamp(self._safe_float(raw.get("closeness_level"), default["closeness_level"]), 0.0, 1.0),
            "boundary_safety": self._clamp(self._safe_float(raw.get("boundary_safety"), default["boundary_safety"]), 0.0, 1.0),
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
            f"最近关系状态：{bond['relationship_condition']}。长期阶段不因短期波动直接回退。",
            f"长期默契基线：{self._resonance_label(bond['resonance_base'])}。这不是好感度，只表示互动方式的熟悉程度。",
            f"信任来源：{bond['trust_notes']}",
            f"用户在这个角色面前的边界：{bond['boundary_notes']}",
            f"互动偏好：{bond['interaction_preferences']}",
            f"关键节点：{milestones}",
            "使用方式：自然参考这些长期关系信息，不要提到 Bond、成长档案、默契基线或任何分数。",
        ])

    def _prepare_events(
        self,
        extracted: list[dict[str, Any]],
        evidence_context: str,
        source_message_ids: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        seen: set[str] = set()
        evidence_event_indexes: dict[str, int] = {}
        for item in extracted:
            if not isinstance(item, dict):
                rejected.append({"reason": "invalid_payload"})
                continue
            event_type = str(item.get("event_type") or "").strip()
            evidence_grade = str(item.get("evidence_grade") or "").strip()
            evidence_text = self._short_text(item.get("evidence_text"), "", 420)
            if event_type not in EVENT_WEIGHTS or not evidence_text:
                rejected.append(self._rejected_event(item, "invalid_payload"))
                continue
            if evidence_grade not in EVIDENCE_CONFIDENCE:
                rejected.append(self._rejected_event(item, f"grade_{evidence_grade or 'missing'}"))
                continue
            if event_type == "boundary_respected" and not self._has_boundary_signal(evidence_text):
                rejected.append(self._rejected_event(item, "boundary_without_signal"))
                continue
            if not self._matches_context(evidence_text, evidence_context):
                rejected.append(self._rejected_event(item, "evidence_not_in_context"))
                continue
            dedupe_key = f"{event_type}:{self._context_key(evidence_text)}"
            if dedupe_key in seen:
                rejected.append(self._rejected_event(item, "duplicate"))
                continue
            seen.add(dedupe_key)
            accepted_event = {
                "event_type": event_type,
                "evidence_grade": evidence_grade,
                "evidence_text": evidence_text,
                "source_message_ids": [item for item in source_message_ids if item],
                "local_confidence": EVIDENCE_CONFIDENCE[evidence_grade],
                "accepted": True,
            }
            evidence_key = self._context_key(evidence_text)
            previous_index = evidence_event_indexes.get(evidence_key)
            if previous_index is not None:
                previous_event = accepted[previous_index]
                if EVENT_PRIORITY[event_type] > EVENT_PRIORITY[previous_event["event_type"]]:
                    rejected.append(self._rejected_event(previous_event, "duplicate_evidence"))
                    accepted[previous_index] = accepted_event
                else:
                    rejected.append(self._rejected_event(accepted_event, "duplicate_evidence"))
                continue
            evidence_event_indexes[evidence_key] = len(accepted)
            accepted.append(accepted_event)
        return accepted, rejected

    def _rejected_event(self, item: dict[str, Any], reason: str) -> dict[str, str]:
        return {
            **self._event_preview(item),
            "reason": reason,
        }

    def _event_preview(self, item: Any) -> dict[str, str]:
        if not isinstance(item, dict):
            return {"reason": "invalid_payload"}
        preview = {
            "event_type": self._short_text(item.get("event_type"), "", 60),
            "evidence_grade": self._short_text(item.get("evidence_grade"), "", 24),
            "evidence_text": self._short_text(item.get("evidence_text"), "", 220),
        }
        reason = self._short_text(item.get("reason"), "", 80)
        if reason:
            preview["reason"] = reason
        return preview

    def _reduce_delta(self, accepted: list[dict[str, Any]]) -> dict[str, float]:
        raw = {key: 0.0 for key in DELTA_CAPS}
        for item in accepted:
            weights = EVENT_WEIGHTS[item["event_type"]]
            for key in raw:
                raw[key] += weights[key]
        return {
            key: round(self._clamp(value, DELTA_CAPS[key][0], DELTA_CAPS[key][1]), 4)
            for key, value in raw.items()
        }

    def _next_stage(
        self,
        current: str,
        trust_level: float,
        closeness_level: float,
        boundary_safety: float,
        evidence: list[dict[str, Any]],
        frozen: bool,
    ) -> str:
        if frozen:
            return current
        if current == "initial":
            positive_count = sum(self._is_positive_event(item) for item in evidence)
            if trust_level >= 0.38 and closeness_level >= 0.28 and positive_count >= 2:
                return "familiar"
            return current
        if current == "familiar":
            has_trust_evidence = any(
                item.get("event_type") in {"trust_signal", "boundary_respected"}
                for item in evidence
                if item.get("accepted", True)
            )
            if trust_level >= 0.52 and boundary_safety >= 0.62 and has_trust_evidence:
                return "trusted"
            return current
        if current == "trusted":
            if (
                trust_level >= 0.68
                and closeness_level >= 0.60
                and boundary_safety >= 0.68
                and self._has_recent_positive_turns(evidence)
            ):
                return "close"
        return current

    def _progression_frozen(self, events: list[dict[str, Any]]) -> bool:
        frozen = False
        for event in events:
            event_type = event.get("event_type")
            if not event.get("accepted", True):
                continue
            if event_type in NEGATIVE_EVENT_TYPES:
                frozen = True
            elif event_type == "repair":
                frozen = False
        return frozen

    def _next_condition(
        self,
        previous: dict[str, Any],
        accepted: list[dict[str, Any]],
        frozen: bool,
    ) -> tuple[str, int]:
        previous_code = previous["condition_code"]
        previous_settle_turns = previous["condition_settle_turns"]
        event_types = {str(event.get("event_type") or "") for event in accepted}
        if "boundary_violation" in event_types:
            return "strained", 0
        if "negative_feedback" in event_types:
            return "guarded", 0
        if "repair" in event_types:
            return "repairing", 0
        if frozen:
            return previous_code, 0
        if previous_code == "warming":
            if accepted:
                return "warming", 0
            settle_turns = previous_settle_turns + 1
            return ("steady", 0) if settle_turns >= 2 else ("warming", settle_turns)
        if previous_code == "repairing":
            settle_turns = previous_settle_turns + 1
            return ("steady", 0) if settle_turns >= 2 else ("repairing", settle_turns)
        if any(event_type in POSITIVE_EVENT_TYPES for event_type in event_types):
            return "warming", 0
        return previous_code, 0

    def _has_recent_positive_turns(self, events: list[dict[str, Any]]) -> bool:
        recent_positive = [event for event in events[-12:] if self._is_positive_event(event)]
        message_ids = {
            str(event.get("source_message_ids", [""])[0])
            for event in recent_positive
            if event.get("source_message_ids")
        }
        return len(recent_positive) >= 4 and len(message_ids) >= 2

    def _is_positive_event(self, event: dict[str, Any]) -> bool:
        return bool(event.get("accepted", True)) and event.get("event_type") in POSITIVE_EVENT_TYPES

    def _update_note(self, previous: str, accepted: list[dict[str, Any]], event_types: set[str]) -> str:
        candidates = [
            self._short_text(item.get("evidence_text"), "", 220)
            for item in accepted
            if item.get("event_type") in event_types
        ]
        return self._short_text(candidates[-1], previous, 600) if candidates else previous

    def _latest_evidence(self, accepted: list[dict[str, Any]], fallback: str) -> str:
        evidence = [self._short_text(item.get("evidence_text"), "", 180) for item in accepted]
        return self._short_text("；".join(item for item in evidence if item), fallback, 300)

    def _stage_code(self, raw_code: Any, raw_stage: Any) -> str:
        code = str(raw_code or "").strip()
        if code in STAGE_LABELS:
            return code
        return FAMILIARITY_STAGE_CODES.get(str(raw_stage or "").strip(), "initial")

    def _condition_code(self, raw_code: Any) -> str:
        code = str(raw_code or "").strip()
        return code if code in CONDITION_LABELS else "steady"

    def _evidence_context(
        self,
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
    ) -> str:
        recent = "\n".join(
            str(item.get("content") or "")
            for item in recent_messages[-8:]
            if str(item.get("role") or "") == "user"
        )
        return "\n".join([recent, user_message])

    def _has_boundary_signal(self, evidence_text: str) -> bool:
        normalized = self._context_key(evidence_text)
        signals = (
            "边界",
            "界限",
            "越界",
            "尊重",
            "停下",
            "别问",
            "不问",
            "不要追问",
            "不再追问",
            "能接受",
            "可以接受",
        )
        return any(self._context_key(signal) in normalized for signal in signals)

    def _matches_context(self, evidence_text: str, evidence_context: str) -> bool:
        evidence_key = self._context_key(evidence_text)
        return bool(evidence_key) and evidence_key in self._context_key(evidence_context)

    def _context_key(self, value: Any) -> str:
        return "".join(str(value or "").lower().split())

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

    def _short_text(self, value: Any, fallback: str, limit: int = 80) -> str:
        text = str(value or "").strip()
        return (text or fallback)[:limit]

    def _safe_float(self, value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _safe_int(self, value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return fallback

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
