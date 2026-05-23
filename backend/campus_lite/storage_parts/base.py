from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .common import DB_PATH, StoragePayloadError


class BaseStorageMixin:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS visitors (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_active_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    card_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    frozen INTEGER NOT NULL DEFAULT 0,
                    manual_note TEXT NOT NULL DEFAULT '',
                    recent_summary TEXT NOT NULL DEFAULT '',
                    character_state_json TEXT NOT NULL DEFAULT '{}',
                    last_prompt_slots TEXT NOT NULL DEFAULT '[]',
                    postprocess_diagnostics_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS character_bonds (
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    familiarity_stage TEXT NOT NULL DEFAULT '初识',
                    stage_code TEXT NOT NULL DEFAULT 'initial',
                    condition_code TEXT NOT NULL DEFAULT 'steady',
                    condition_settle_turns INTEGER NOT NULL DEFAULT 0,
                    resonance_base REAL NOT NULL DEFAULT 0.30,
                    trust_level REAL NOT NULL DEFAULT 0.30,
                    closeness_level REAL NOT NULL DEFAULT 0.20,
                    boundary_safety REAL NOT NULL DEFAULT 0.60,
                    trust_notes TEXT NOT NULL DEFAULT '',
                    boundary_notes TEXT NOT NULL DEFAULT '',
                    interaction_preferences TEXT NOT NULL DEFAULT '',
                    milestones_json TEXT NOT NULL DEFAULT '[]',
                    evidence TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (visitor_id, character_id)
                );

                CREATE TABLE IF NOT EXISTS relationship_events (
                    id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    evidence_grade TEXT NOT NULL,
                    local_confidence REAL NOT NULL DEFAULT 0,
                    evidence_text TEXT NOT NULL,
                    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                    accepted INTEGER NOT NULL DEFAULT 1,
                    applied_delta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    character_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    memory_scope TEXT NOT NULL DEFAULT 'session',
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    importance REAL NOT NULL DEFAULT 0.5,
                    normalized_key TEXT NOT NULL DEFAULT '',
                    source_message_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(session_id, memory_type, content)
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    summary_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    owner_type TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(owner_type, owner_id, provider)
                );

                CREATE TABLE IF NOT EXISTS story_items (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '',
                    evidence_level TEXT NOT NULL DEFAULT 'inferred',
                    status TEXT NOT NULL DEFAULT 'active',
                    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(session_id, kind, label)
                );

                CREATE TABLE IF NOT EXISTS novel_projects (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    genre TEXT NOT NULL DEFAULT '',
                    tone TEXT NOT NULL DEFAULT '',
                    protagonist TEXT NOT NULL DEFAULT '',
                    worldview TEXT NOT NULL DEFAULT '',
                    relationship_setup TEXT NOT NULL DEFAULT '',
                    outline TEXT NOT NULL DEFAULT '',
                    story_bible_json TEXT NOT NULL DEFAULT '{}',
                    story_canvas_json TEXT NOT NULL DEFAULT '{}',
                    novel_state_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS novel_materials (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES novel_projects(id) ON DELETE CASCADE,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL,
                    label TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence_level TEXT NOT NULL DEFAULT 'inferred',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(project_id, source_type, source_id, label)
                );

                CREATE TABLE IF NOT EXISTS novel_chapters (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES novel_projects(id) ON DELETE CASCADE,
                    chapter_order INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planned',
                    scene_card_json TEXT NOT NULL DEFAULT '{}',
                    source_material_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(project_id, chapter_order)
                );

                CREATE TABLE IF NOT EXISTS novel_versions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES novel_projects(id) ON DELETE CASCADE,
                    chapter_id TEXT NOT NULL REFERENCES novel_chapters(id) ON DELETE CASCADE,
                    version_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    planning_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content,
                    memory_id UNINDEXED,
                    session_id UNINDEXED,
                    visitor_id UNINDEXED
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_visitor_character_updated
                    ON sessions(visitor_id, character_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_memories_visible
                    ON memories(visitor_id, memory_scope, character_id, session_id, memory_type, updated_at);
                CREATE INDEX IF NOT EXISTS idx_embeddings_owner_provider
                    ON embeddings(owner_type, owner_id, provider);
                CREATE INDEX IF NOT EXISTS idx_relationship_events_character_created
                    ON relationship_events(visitor_id, character_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_story_items_session_status
                    ON story_items(session_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_novel_projects_session_updated
                    ON novel_projects(session_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_novel_chapters_project_order
                    ON novel_chapters(project_id, chapter_order);
                CREATE INDEX IF NOT EXISTS idx_novel_versions_chapter_created
                    ON novel_versions(chapter_id, created_at);
                INSERT OR IGNORE INTO schema_migrations (version, name)
                    VALUES (1, 'initial_indexes');
                """
            )
            self._ensure_column(conn, "memories", "memory_scope", "TEXT NOT NULL DEFAULT 'session'")
            self._ensure_column(conn, "memories", "importance", "REAL NOT NULL DEFAULT 0.5")
            self._ensure_column(conn, "memories", "normalized_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "sessions", "character_state_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "sessions", "postprocess_diagnostics_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "character_bonds", "stage_code", "TEXT NOT NULL DEFAULT 'initial'")
            self._ensure_column(conn, "character_bonds", "condition_code", "TEXT NOT NULL DEFAULT 'steady'")
            self._ensure_column(conn, "character_bonds", "condition_settle_turns", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "character_bonds", "trust_level", "REAL NOT NULL DEFAULT 0.30")
            self._ensure_column(conn, "character_bonds", "closeness_level", "REAL NOT NULL DEFAULT 0.20")
            self._ensure_column(conn, "character_bonds", "boundary_safety", "REAL NOT NULL DEFAULT 0.60")
            self._ensure_column(conn, "novel_projects", "story_canvas_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "novel_projects", "novel_state_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "novel_chapters", "scene_card_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "novel_versions", "state_delta_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "novel_versions", "planning_snapshot_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                """
                UPDATE memories
                SET memory_scope = CASE
                    WHEN memory_type IN ('stable_user_info', 'user_preference') THEN 'global'
                    WHEN memory_type = 'relationship_progress' THEN 'character'
                    ELSE 'session'
                END
                WHERE memory_scope = 'session'
                  AND memory_type IN ('stable_user_info', 'user_preference', 'relationship_progress')
                """
            )
            rows = conn.execute("SELECT id, content FROM memories WHERE normalized_key = ''").fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE memories SET normalized_key = ? WHERE id = ?",
                    (self._normalize_memory_key(row["content"]), row["id"]),
                )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
