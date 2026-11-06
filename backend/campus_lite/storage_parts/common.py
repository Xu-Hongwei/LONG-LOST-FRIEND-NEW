from __future__ import annotations

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
_configured_path = Path(os.getenv("CAMPUS_DB_PATH") or "data/campus_lite.db")
DB_PATH = (_configured_path if _configured_path.is_absolute() else PROJECT_ROOT / _configured_path).resolve()

JSON_LIMITS = {
    "story_canvas_json": 36000,
    "novel_state_json": 24000,
    "scene_card_json": 8000,
    "state_delta_json": 12000,
    "planning_snapshot_json": 32000,
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
