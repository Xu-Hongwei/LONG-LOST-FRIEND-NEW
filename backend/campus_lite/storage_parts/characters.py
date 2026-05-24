from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4


class CharacterStorageMixin:
    def upsert_character(self, card: dict[str, Any], owner_visitor_id: str = "", origin: str = "builtin") -> None:
        stored = self._stored_character_card(card, owner_visitor_id, origin)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO characters (id, name, card_json, owner_visitor_id, origin, deleted_at, updated_at)
                VALUES (?, ?, ?, ?, ?, '', datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    card_json = excluded.card_json,
                    owner_visitor_id = excluded.owner_visitor_id,
                    origin = excluded.origin,
                    deleted_at = '',
                    updated_at = datetime('now')
                """,
                (
                    stored["id"],
                    stored["name"],
                    json.dumps(stored, ensure_ascii=False),
                    owner_visitor_id,
                    origin,
                ),
            )

    def list_character_cards(self, visitor_id: str = "") -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM characters
                WHERE deleted_at = ''
                  AND (origin = 'builtin' OR owner_visitor_id = ?)
                ORDER BY
                    CASE origin WHEN 'builtin' THEN 0 ELSE 1 END,
                    updated_at DESC,
                    name COLLATE NOCASE ASC
                """,
                (visitor_id,),
            ).fetchall()
        return [self._row_to_character_card(row) for row in rows]

    def get_character_card(self, character_id: str, visitor_id: str = "") -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM characters
                WHERE id = ?
                  AND deleted_at = ''
                  AND (origin = 'builtin' OR owner_visitor_id = ?)
                LIMIT 1
                """,
                (character_id, visitor_id),
            ).fetchone()
        return self._row_to_character_card(row) if row else None

    def create_custom_character(self, visitor_id: str, card: dict[str, Any]) -> dict[str, Any]:
        character_id = f"custom_{uuid4().hex[:12]}"
        stored = self._stored_character_card({**card, "id": character_id}, visitor_id, "custom")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO characters (id, name, card_json, owner_visitor_id, origin, deleted_at, updated_at)
                VALUES (?, ?, ?, ?, 'custom', '', datetime('now'))
                """,
                (character_id, stored["name"], json.dumps(stored, ensure_ascii=False), visitor_id),
            )
        return stored

    def update_custom_character(self, visitor_id: str, character_id: str, card: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_character_card(character_id, visitor_id)
        if not existing or existing.get("origin") != "custom" or existing.get("owner_visitor_id") != visitor_id:
            return None
        stored = self._stored_character_card({**card, "id": character_id}, visitor_id, "custom")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE characters
                SET name = ?, card_json = ?, updated_at = datetime('now')
                WHERE id = ? AND owner_visitor_id = ? AND origin = 'custom' AND deleted_at = ''
                """,
                (stored["name"], json.dumps(stored, ensure_ascii=False), character_id, visitor_id),
            )
        return stored

    def delete_custom_character(self, visitor_id: str, character_id: str) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                """
                UPDATE characters
                SET deleted_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ? AND owner_visitor_id = ? AND origin = 'custom' AND deleted_at = ''
                """,
                (character_id, visitor_id),
            )
        return result.rowcount > 0

    def _stored_character_card(self, card: dict[str, Any], owner_visitor_id: str, origin: str) -> dict[str, Any]:
        name = str(card.get("name") or "").strip()[:80] or "自定义角色"
        archetype = str(card.get("archetype") or "").strip()[:120] or "自定义人格"
        stored = {
            "id": str(card.get("id") or "").strip(),
            "name": name,
            "archetype": archetype,
            "tagline": str(card.get("tagline") or "").strip()[:160] or f"{name}的自定义角色卡",
            "gender": str(card.get("gender") or "unknown").strip()[:32] or "unknown",
            "bio": str(card.get("bio") or "").strip()[:1200] or f"{name}是一个由用户创建的聊天角色。",
            "speech_style": str(card.get("speech_style") or "").strip()[:800] or "自然、稳定，跟随用户当前话题回应。",
            "likes": self._short_list(card.get("likes"), 12, 80),
            "dislikes": self._short_list(card.get("dislikes"), 12, 80),
            "boundaries": self._short_list(card.get("boundaries"), 12, 160),
            "relationship_pace": str(card.get("relationship_pace") or "").strip()[:800] or "根据聊天自然推进关系，不突然越界。",
            "opening_line": str(card.get("opening_line") or "").strip()[:800] or f"你好，我是{name}。今天想和我聊点什么？",
            "personality": str(card.get("personality") or "").strip()[:2000],
            "scenario": str(card.get("scenario") or "").strip()[:2000],
            "mes_example": str(card.get("mes_example") or "").strip()[:3000],
            "creator_notes": str(card.get("creator_notes") or "").strip()[:1600],
            "system_prompt": str(card.get("system_prompt") or "").strip()[:2000],
            "post_history_instructions": str(card.get("post_history_instructions") or "").strip()[:2000],
            "interaction_policy": card.get("interaction_policy") if isinstance(card.get("interaction_policy"), dict) else {},
            "anti_patterns": self._short_list(card.get("anti_patterns"), 12, 160),
            "backstory": card.get("backstory") if isinstance(card.get("backstory"), dict) else {},
            "voice": card.get("voice") if isinstance(card.get("voice"), dict) else {},
            "visual": card.get("visual") if isinstance(card.get("visual"), dict) else {},
            "origin": origin,
            "owner_visitor_id": owner_visitor_id,
        }
        if not stored["id"]:
            stored["id"] = f"custom_{uuid4().hex[:12]}"
        return stored

    def _short_list(self, value: Any, limit: int, item_limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text[:item_limit])
            if len(result) >= limit:
                break
        return result

    def _row_to_character_card(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            card = json.loads(row["card_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            card = {}
        if not isinstance(card, dict):
            card = {}
        card["id"] = card.get("id") or row["id"]
        card["name"] = card.get("name") or row["name"]
        card["origin"] = row["origin"] if "origin" in row.keys() else card.get("origin") or "builtin"
        card["owner_visitor_id"] = row["owner_visitor_id"] if "owner_visitor_id" in row.keys() else card.get("owner_visitor_id") or ""
        return card

    def get_character_bond(self, visitor_id: str, character_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM character_bonds
                WHERE visitor_id = ? AND character_id = ?
                LIMIT 1
                """,
                (visitor_id, character_id),
            ).fetchone()

    def upsert_character_bond(self, visitor_id: str, character_id: str, bond: dict[str, Any]) -> None:
        milestones = bond.get("milestones") or []
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO character_bonds (
                    visitor_id, character_id, familiarity_stage, stage_code, condition_code, condition_settle_turns,
                    resonance_base, trust_level, closeness_level, boundary_safety,
                    trust_notes, boundary_notes, interaction_preferences,
                    milestones_json, evidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(visitor_id, character_id) DO UPDATE SET
                    familiarity_stage = excluded.familiarity_stage,
                    stage_code = excluded.stage_code,
                    condition_code = excluded.condition_code,
                    condition_settle_turns = excluded.condition_settle_turns,
                    resonance_base = excluded.resonance_base,
                    trust_level = excluded.trust_level,
                    closeness_level = excluded.closeness_level,
                    boundary_safety = excluded.boundary_safety,
                    trust_notes = excluded.trust_notes,
                    boundary_notes = excluded.boundary_notes,
                    interaction_preferences = excluded.interaction_preferences,
                    milestones_json = excluded.milestones_json,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (
                    visitor_id,
                    character_id,
                    str(bond.get("familiarity_stage") or "初识")[:80],
                    str(bond.get("stage_code") or "initial")[:24],
                    str(bond.get("condition_code") or "steady")[:24],
                    max(0, min(2, int(bond.get("condition_settle_turns") or 0))),
                    max(0.0, min(1.0, float(bond.get("resonance_base") or 0.30))),
                    max(0.0, min(1.0, float(bond.get("trust_level") or 0.30))),
                    max(0.0, min(1.0, float(bond.get("closeness_level") or 0.20))),
                    max(0.0, min(1.0, float(bond.get("boundary_safety") or 0.60))),
                    str(bond.get("trust_notes") or "")[:600],
                    str(bond.get("boundary_notes") or "")[:600],
                    str(bond.get("interaction_preferences") or "")[:600],
                    json.dumps(milestones[:8], ensure_ascii=False),
                    str(bond.get("evidence") or "")[:300],
                ),
            )

    def add_relationship_event(
        self,
        *,
        visitor_id: str,
        character_id: str,
        session_id: str,
        event: dict[str, Any],
    ) -> str:
        event_id = str(uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO relationship_events (
                    id, visitor_id, character_id, session_id, event_type,
                    evidence_grade, local_confidence, evidence_text,
                    source_message_ids_json, accepted, applied_delta_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    visitor_id,
                    character_id,
                    session_id,
                    str(event.get("event_type") or "")[:60],
                    str(event.get("evidence_grade") or "")[:24],
                    max(0.0, min(1.0, float(event.get("local_confidence") or 0.0))),
                    str(event.get("evidence_text") or "")[:420],
                    json.dumps(event.get("source_message_ids") or [], ensure_ascii=False),
                    1 if event.get("accepted", True) else 0,
                    json.dumps(event.get("applied_delta") or {}, ensure_ascii=False),
                ),
            )
        return event_id

    def list_relationship_events(self, visitor_id: str, character_id: str, limit: int = 24) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM relationship_events
                WHERE visitor_id = ? AND character_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (visitor_id, character_id, limit),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                source_message_ids = json.loads(row["source_message_ids_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                source_message_ids = []
            try:
                applied_delta = json.loads(row["applied_delta_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                applied_delta = {}
            events.append({
                "id": row["id"],
                "event_type": row["event_type"],
                "evidence_grade": row["evidence_grade"],
                "local_confidence": row["local_confidence"],
                "evidence_text": row["evidence_text"],
                "source_message_ids": source_message_ids if isinstance(source_message_ids, list) else [],
                "accepted": bool(row["accepted"]),
                "applied_delta": applied_delta if isinstance(applied_delta, dict) else {},
                "created_at": row["created_at"],
            })
        return events
