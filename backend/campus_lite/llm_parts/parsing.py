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

    def _parse_bond_json(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return None
        if "should_update" not in raw or "evidence" not in raw:
            return None
        return raw

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
            "bond": bond if self._valid_bond_payload(bond) else None,
            "memories": memories,
        }

    def _valid_state_payload(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required = {"mood", "tone", "distance", "focus", "energy", "resonance_delta", "behavior", "evidence"}
        return required.issubset(value.keys()) and isinstance(value.get("behavior"), dict)

    def _valid_bond_payload(self, value: Any) -> bool:
        return isinstance(value, dict) and "should_update" in value and "evidence" in value
