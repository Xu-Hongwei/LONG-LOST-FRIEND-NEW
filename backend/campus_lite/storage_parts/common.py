from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "campus_lite.db"

JSON_LIMITS = {
    "story_canvas_json": 20000,
    "novel_state_json": 24000,
    "scene_card_json": 8000,
    "state_delta_json": 8000,
    "planning_snapshot_json": 12000,
}

UNTRUSTED_VERSION_SOURCES = {"mock", "manual", "create", "system", "canvas", "restore"}
STATE_SCENE_CARD_FIELDS = {
    "active_state_delta",
    "active_version_id",
    "chapter_handoff",
    "chapter_state_delta",
    "handoff_source",
}
RUNTIME_SCENE_CARD_FIELDS = {
    *STATE_SCENE_CARD_FIELDS,
    "chapter_audit",
    "generation_progress",
    "postprocess",
    "scene_beats",
}


class StoragePayloadError(ValueError):
    pass


def now_sql() -> str:
    return "datetime('now')"
