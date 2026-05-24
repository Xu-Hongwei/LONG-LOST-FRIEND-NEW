from __future__ import annotations

import json
import re
from typing import Any

from ..schemas import MemoryType


class LlmParsingMixin:
    def _parse_memory_json(self, text: str) -> list[dict[str, Any]]:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        raw = json.loads(match.group(0))
        return self._clean_memory_items(raw)

    def _clean_memory_items(self, raw: Any) -> list[dict[str, Any]]:
        allowed: set[MemoryType] = {
            "stable_user_info",
            "user_preference",
            "open_thread",
            "recent_emotion",
            "relationship_progress",
            "manual_note",
        }
        cleaned: list[dict[str, Any]] = []
        if not isinstance(raw, list):
            return []
        for item in raw:
            if not isinstance(item, dict):
                continue
            memory_type = item.get("memory_type")
            content = str(item.get("content") or "").strip()
            if memory_type not in allowed or not content:
                continue
            cleaned.append({
                "memory_type": memory_type,
                "content": content[:420],
                "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.6))),
                "importance": max(0.0, min(1.0, float(item.get("importance") or 0.5))),
            })
        return cleaned[:5]

    def _parse_state_json(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return None
        required = {"mood", "tone", "distance", "focus", "energy", "resonance_delta", "behavior", "evidence"}
        if not required.issubset(raw.keys()):
            return None
        if not isinstance(raw.get("behavior"), dict):
            return None
        return raw

    def _parse_relationship_events_json(self, text: str) -> list[dict[str, Any]]:
        raw: Any = None
        try:
            raw = json.loads(text.strip())
        except json.JSONDecodeError:
            object_match = re.search(r"\{[\s\S]*\}", text)
            array_match = re.search(r"\[[\s\S]*\]", text)
            match = object_match or array_match
            if not match:
                return []
            try:
                raw = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
        if isinstance(raw, dict):
            raw = raw.get("events")
        if not isinstance(raw, list):
            return []
        allowed_types = {
            "shared_context",
            "preference_confirmed",
            "trust_signal",
            "emotional_disclosure",
            "boundary_respected",
            "negative_feedback",
            "boundary_violation",
            "repair",
        }
        allowed_grades = {"explicit", "strong", "contextual", "weak"}
        forbidden = {"score", "delta", "confidence", "stage", "familiarity_stage", "resonance"}
        cleaned: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict) or forbidden.intersection(item):
                continue
            event_type = str(item.get("event_type") or "").strip()
            evidence_grade = str(item.get("evidence_grade") or "").strip()
            evidence_text = str(item.get("evidence_text") or "").strip()
            if event_type not in allowed_types or evidence_grade not in allowed_grades or not evidence_text:
                continue
            cleaned.append({
                "event_type": event_type,
                "evidence_grade": evidence_grade,
                "evidence_text": evidence_text[:420],
            })
        return cleaned[:8]

    def _parse_character_draft_json(self, text: str) -> dict[str, Any] | None:
        raw: Any = None
        try:
            raw = json.loads(text.strip())
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return None
            try:
                raw = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        if isinstance(raw, dict) and isinstance(raw.get("character"), dict):
            raw = raw["character"]
        if not isinstance(raw, dict):
            return None
        return self._clean_character_draft(raw)

    def _clean_character_draft(self, raw: dict[str, Any]) -> dict[str, Any]:
        def text(key: str, limit: int, default: str = "") -> str:
            return str(raw.get(key) or default).strip()[:limit]

        def string_list(key: str, limit: int, item_limit: int) -> list[str]:
            value = raw.get(key)
            if isinstance(value, str):
                candidates = re.split(r"[\n,，、]+", value)
            elif isinstance(value, list):
                candidates = value
            else:
                candidates = []
            result: list[str] = []
            for item in candidates:
                item_text = str(item or "").strip()
                if item_text:
                    result.append(item_text[:item_limit])
                if len(result) >= limit:
                    break
            return result

        def number(value: Any, default: float = 0.45) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                text_value = str(value or "").lower()
                if any(token in text_value for token in ["high", "strong", "高", "主动"]):
                    return 0.7
                if any(token in text_value for token in ["low", "weak", "低", "慢", "克制"]):
                    return 0.3
                return default

        interaction = raw.get("interaction_policy") if isinstance(raw.get("interaction_policy"), dict) else {}
        voice = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
        visual = raw.get("visual") if isinstance(raw.get("visual"), dict) else {}
        cleaned = {
            "name": text("name", 80, "自定义角色"),
            "archetype": text("archetype", 120, "自定义人格"),
            "tagline": text("tagline", 160),
            "gender": text("gender", 32, "unknown") or "unknown",
            "bio": text("bio", 1200),
            "speech_style": text("speech_style", 800),
            "likes": string_list("likes", 12, 80),
            "dislikes": string_list("dislikes", 12, 80),
            "boundaries": string_list("boundaries", 12, 160),
            "relationship_pace": text("relationship_pace", 800),
            "opening_line": text("opening_line", 800),
            "personality": text("personality", 2000),
            "scenario": text("scenario", 2000),
            "mes_example": text("mes_example", 3000),
            "creator_notes": text("creator_notes", 1600),
            "system_prompt": text("system_prompt", 2000),
            "post_history_instructions": text("post_history_instructions", 2000),
            "interaction_policy": {
                "initiative_level": number(interaction.get("initiative_level"), 0.45),
                "action_density": str(interaction.get("action_density") or "low")[:40],
                "action_style": str(interaction.get("action_style") or "").strip()[:800],
                "comfort_style": str(interaction.get("comfort_style") or "").strip()[:800],
                "question_style": str(interaction.get("question_style") or "").strip()[:800],
                "memory_style": str(interaction.get("memory_style") or "").strip()[:800],
            },
            "anti_patterns": string_list("anti_patterns", 12, 160),
            "voice": {
                "sentence_rhythm": str(voice.get("sentence_rhythm") or "").strip()[:800],
                "signature_moves": [
                    str(item or "").strip()[:120]
                    for item in (voice.get("signature_moves") if isinstance(voice.get("signature_moves"), list) else [])
                    if str(item or "").strip()
                ][:8],
                "avoid": [
                    str(item or "").strip()[:120]
                    for item in (voice.get("avoid") if isinstance(voice.get("avoid"), list) else [])
                    if str(item or "").strip()
                ][:8],
                "sample_lines": [
                    str(item or "").strip()[:240]
                    for item in (voice.get("sample_lines") if isinstance(voice.get("sample_lines"), list) else [])
                    if str(item or "").strip()
                ][:8],
            },
            "visual": {
                "accent": str(visual.get("accent") or "#9fb6d7").strip()[:32],
                "portrait_hint": str(visual.get("portrait_hint") or "").strip()[:240],
            },
        }
        if not cleaned["tagline"]:
            cleaned["tagline"] = f"{cleaned['name']}的自定义角色卡"
        if not cleaned["bio"]:
            cleaned["bio"] = f"{cleaned['name']}是一个由用户设定生成的聊天角色。"
        if not cleaned["speech_style"]:
            cleaned["speech_style"] = "自然、稳定，跟随用户当前话题回应。"
        if not cleaned["opening_line"]:
            cleaned["opening_line"] = f"你好，我是{cleaned['name']}。今天想和我聊点什么？"
        return cleaned

    def _parse_turn_analysis_json(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"state": None, "bond": None, "memories": []}
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return {"state": None, "bond": None, "memories": []}
        state = raw.get("state")
        bond = raw.get("bond")
        memories = self._clean_memory_items(raw.get("memories") or [])
        return {
            "state": state if self._valid_state_payload(state) else None,
            "bond": self._clean_relationship_events(bond),
            "memories": memories,
        }

    def _valid_state_payload(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required = {"mood", "tone", "distance", "focus", "energy", "resonance_delta", "behavior", "evidence"}
        return required.issubset(value.keys()) and isinstance(value.get("behavior"), dict)

    def _clean_relationship_events(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, (list, dict)):
            return []
        return self._parse_relationship_events_json(json.dumps(value, ensure_ascii=False))
