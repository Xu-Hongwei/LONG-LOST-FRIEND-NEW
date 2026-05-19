from __future__ import annotations

import json
import sqlite3
from typing import Any


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
                    visitor_id, character_id, familiarity_stage, resonance_base,
                    trust_notes, boundary_notes, interaction_preferences,
                    milestones_json, evidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(visitor_id, character_id) DO UPDATE SET
                    familiarity_stage = excluded.familiarity_stage,
                    resonance_base = excluded.resonance_base,
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
                    max(0.0, min(1.0, float(bond.get("resonance_base") or 0.30))),
                    str(bond.get("trust_notes") or "")[:600],
                    str(bond.get("boundary_notes") or "")[:600],
                    str(bond.get("interaction_preferences") or "")[:600],
                    json.dumps(milestones[:8], ensure_ascii=False),
                    str(bond.get("evidence") or "")[:300],
                ),
            )
