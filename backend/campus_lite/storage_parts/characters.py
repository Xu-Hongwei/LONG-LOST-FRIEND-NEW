from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4


class CharacterStorageMixin:
    def upsert_character(self, card: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO characters (id, name, card_json, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    card_json = excluded.card_json,
                    updated_at = datetime('now')
                """,
                (card["id"], card["name"], json.dumps(card, ensure_ascii=False)),
            )

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
