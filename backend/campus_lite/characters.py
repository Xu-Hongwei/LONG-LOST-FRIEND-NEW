from __future__ import annotations

import json
from pathlib import Path

from .schemas import CharacterCard


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHARACTER_DIR = PROJECT_ROOT / "characters"


class CharacterStore:
    def __init__(self, directory: Path = CHARACTER_DIR) -> None:
        self.directory = directory

    def list_cards(self) -> list[CharacterCard]:
        cards: list[CharacterCard] = []
        for path in sorted(self.directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            cards.append(CharacterCard.model_validate(data))
        return cards

    def get(self, character_id: str) -> CharacterCard:
        for card in self.list_cards():
            if card.id == character_id:
                return card
        raise KeyError(character_id)
