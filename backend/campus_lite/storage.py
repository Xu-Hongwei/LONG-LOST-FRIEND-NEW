from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "campus_lite.db"


def now_sql() -> str:
    return "datetime('now')"


class Storage:
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
                    last_prompt_slots TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS character_bonds (
                    visitor_id TEXT NOT NULL REFERENCES visitors(id),
                    character_id TEXT NOT NULL,
                    familiarity_stage TEXT NOT NULL DEFAULT '初识',
                    resonance_base REAL NOT NULL DEFAULT 0.30,
                    trust_notes TEXT NOT NULL DEFAULT '',
                    boundary_notes TEXT NOT NULL DEFAULT '',
                    interaction_preferences TEXT NOT NULL DEFAULT '',
                    milestones_json TEXT NOT NULL DEFAULT '[]',
                    evidence TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (visitor_id, character_id)
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
            self._ensure_column(conn, "novel_projects", "story_canvas_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "novel_chapters", "scene_card_json", "TEXT NOT NULL DEFAULT '{}'")
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

    def _normalize_memory_key(self, text: str) -> str:
        compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())
        return compact[:160] or uuid.uuid4().hex

    def _memory_scope(self, memory_type: str) -> str:
        if memory_type in {"stable_user_info", "user_preference"}:
            return "global"
        if memory_type == "relationship_progress":
            return "character"
        return "session"

    def memory_visible_in_session(self, memory_id: str, visitor_id: str, character_id: str, session_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE id = ?
                  AND {self._memory_scope_where()}
                LIMIT 1
                """,
                (memory_id, visitor_id, character_id, session_id, session_id),
            ).fetchone()

    def resolve_visitor(self, visitor_id: str | None) -> tuple[str, bool]:
        normalized = (visitor_id or "").strip() or f"visitor_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM visitors WHERE id = ?", (normalized,)).fetchone()
            created = row is None
            if created:
                conn.execute("INSERT INTO visitors (id) VALUES (?)", (normalized,))
            else:
                conn.execute("UPDATE visitors SET last_active_at = datetime('now') WHERE id = ?", (normalized,))
        return normalized, created

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

    def create_or_get_session(self, visitor_id: str, character_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM sessions
                WHERE visitor_id = ? AND character_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (visitor_id, character_id),
            ).fetchone()
            if row:
                conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (row["id"],))
                return str(row["id"])
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO sessions (id, visitor_id, character_id) VALUES (?, ?, ?)",
                (session_id, visitor_id, character_id),
            )
            return session_id

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def add_message(self, session_id: str, visitor_id: str, character_id: str, role: str, content: str) -> str:
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, session_id, visitor_id, character_id, role, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, visitor_id, character_id, role, content),
            )
            conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
        return message_id

    def get_message(self, message_id: str) -> dict[str, str] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, role, content, created_at FROM messages
                WHERE id = ?
                LIMIT 1
                """,
                (message_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}

    def recent_messages(self, session_id: str, limit: int = 12) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE session_id = ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [{"role": row["role"], "content": row["content"], "created_at": row["created_at"]} for row in rows]

    def session_messages(self, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        with self.connect() as conn:
            if limit:
                rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT rowid AS message_order, id, role, content, created_at FROM messages
                        WHERE session_id = ?
                        ORDER BY rowid DESC
                        LIMIT ?
                    )
                    ORDER BY message_order ASC
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, role, content, created_at FROM messages
                    WHERE session_id = ?
                    ORDER BY rowid ASC
                    """,
                    (session_id,),
                ).fetchall()
        return [
            {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}
            for row in rows
        ]

    def upsert_story_item(
        self,
        session_id: str,
        kind: str,
        label: str,
        content: str,
        evidence: str = "",
        evidence_level: str = "inferred",
        status: str = "active",
        source_message_ids: list[str] | None = None,
    ) -> str | None:
        clean_label = label.strip()[:80]
        clean_content = content.strip()[:500]
        if not clean_label or not clean_content:
            return None
        story_id = f"story_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO story_items (
                    id, session_id, kind, label, content, evidence,
                    evidence_level, status, source_message_ids_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, kind, label) DO UPDATE SET
                    content = excluded.content,
                    evidence = excluded.evidence,
                    evidence_level = excluded.evidence_level,
                    status = excluded.status,
                    source_message_ids_json = excluded.source_message_ids_json,
                    updated_at = datetime('now')
                """,
                (
                    story_id,
                    session_id,
                    kind,
                    clean_label,
                    clean_content,
                    evidence.strip()[:500],
                    evidence_level,
                    status,
                    json.dumps(source_message_ids or [], ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT id FROM story_items WHERE session_id = ? AND kind = ? AND label = ?",
                (session_id, kind, clean_label),
            ).fetchone()
        return str(row["id"]) if row else None

    def list_story_items(self, session_id: str, include_archived: bool = False) -> list[sqlite3.Row]:
        with self.connect() as conn:
            where = "session_id = ?" if include_archived else "session_id = ? AND status != 'archived'"
            return conn.execute(
                f"""
                SELECT * FROM story_items
                WHERE {where}
                ORDER BY
                    CASE kind
                        WHEN 'story_beat' THEN 0
                        WHEN 'open_thread' THEN 1
                        WHEN 'motif' THEN 2
                        WHEN 'relationship_texture' THEN 3
                        WHEN 'boundary' THEN 4
                        ELSE 5
                    END,
                    updated_at DESC
                """,
                (session_id,),
            ).fetchall()

    def create_novel_project(
        self,
        session_id: str,
        visitor_id: str,
        character_id: str,
        title: str,
        genre: str,
        tone: str,
        protagonist: str,
        worldview: str,
        relationship_setup: str,
        outline: str,
        story_bible: dict[str, Any],
        story_canvas: dict[str, Any] | None = None,
    ) -> str:
        project_id = f"novel_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO novel_projects (
                    id, session_id, visitor_id, character_id, title, genre, tone,
                    protagonist, worldview, relationship_setup, outline, story_bible_json,
                    story_canvas_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    visitor_id,
                    character_id,
                    title.strip()[:120],
                    genre.strip()[:80],
                    tone.strip()[:120],
                    protagonist.strip()[:120],
                    worldview.strip()[:2000],
                    relationship_setup.strip()[:2000],
                    outline.strip()[:4000],
                    json.dumps(story_bible, ensure_ascii=False),
                    json.dumps(story_canvas or {}, ensure_ascii=False),
                ),
            )
        return project_id

    def get_novel_project(self, project_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_projects WHERE id = ?", (project_id,)).fetchone()

    def list_novel_projects(self, session_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_projects
                WHERE session_id = ? AND status != 'archived'
                ORDER BY updated_at DESC
                """,
                (session_id,),
            ).fetchall()

    def update_novel_project(self, project_id: str, updates: dict[str, Any]) -> bool:
        allowed = {
            "title": 120,
            "genre": 80,
            "tone": 120,
            "protagonist": 120,
            "worldview": 2000,
            "relationship_setup": 2000,
            "outline": 4000,
            "status": 40,
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, limit in allowed.items():
            if key in updates and updates[key] is not None:
                fields.append(f"{key} = ?")
                values.append(str(updates[key]).strip()[:limit])
        if "story_bible" in updates and updates["story_bible"] is not None:
            fields.append("story_bible_json = ?")
            values.append(json.dumps(updates["story_bible"], ensure_ascii=False))
        if "story_canvas" in updates and updates["story_canvas"] is not None:
            fields.append("story_canvas_json = ?")
            values.append(json.dumps(updates["story_canvas"], ensure_ascii=False)[:20000])
        if not fields:
            return bool(self.get_novel_project(project_id))
        fields.append("updated_at = datetime('now')")
        values.append(project_id)
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE novel_projects SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            return cur.rowcount > 0

    def upsert_novel_material(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        category: str,
        label: str,
        content: str,
        evidence_level: str = "inferred",
    ) -> str | None:
        clean_label = label.strip()[:100]
        clean_content = content.strip()[:1000]
        if not clean_label or not clean_content:
            return None
        material_id = f"mat_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO novel_materials (
                    id, project_id, source_type, source_id, category,
                    label, content, evidence_level
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_type, source_id, label) DO UPDATE SET
                    category = excluded.category,
                    content = excluded.content,
                    evidence_level = excluded.evidence_level
                """,
                (
                    material_id,
                    project_id,
                    source_type,
                    source_id.strip()[:120],
                    category,
                    clean_label,
                    clean_content,
                    evidence_level,
                ),
            )
            row = conn.execute(
                """
                SELECT id FROM novel_materials
                WHERE project_id = ? AND source_type = ? AND source_id = ? AND label = ?
                """,
                (project_id, source_type, source_id.strip()[:120], clean_label),
            ).fetchone()
        return str(row["id"]) if row else None

    def list_novel_materials(self, project_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_materials
                WHERE project_id = ?
                ORDER BY
                    CASE category
                        WHEN 'fact' THEN 0
                        WHEN 'boundary' THEN 1
                        WHEN 'relationship' THEN 2
                        WHEN 'foreshadowing' THEN 3
                        WHEN 'open_thread' THEN 4
                        ELSE 5
                    END,
                    created_at ASC
                """,
                (project_id,),
            ).fetchall()

    def create_novel_chapter(
        self,
        project_id: str,
        title: str,
        goal: str = "",
        summary: str = "",
        body: str = "",
        status: str = "planned",
        scene_card: dict[str, Any] | None = None,
        source_material_ids: list[str] | None = None,
    ) -> str:
        chapter_id = f"chapter_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT coalesce(max(chapter_order), 0) + 1 AS next_order FROM novel_chapters WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            chapter_order = int(row["next_order"] if row else 1)
            conn.execute(
                """
                INSERT INTO novel_chapters (
                    id, project_id, chapter_order, title, goal, summary, body,
                    status, scene_card_json, source_material_ids_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    project_id,
                    chapter_order,
                    title.strip()[:120] or f"第 {chapter_order} 章",
                    goal.strip()[:1000],
                    summary.strip()[:1200],
                    body.strip()[:20000],
                    status,
                    json.dumps(scene_card or {}, ensure_ascii=False),
                    json.dumps(source_material_ids or [], ensure_ascii=False),
                ),
            )
            conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
        if body:
            self.add_novel_version(project_id, chapter_id, "draft", title, body, summary, "create")
        return chapter_id

    def get_novel_chapter(self, chapter_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_chapters WHERE id = ?", (chapter_id,)).fetchone()

    def list_novel_chapters(self, project_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_chapters
                WHERE project_id = ?
                ORDER BY chapter_order ASC
                """,
                (project_id,),
            ).fetchall()

    def update_novel_chapter(self, chapter_id: str, updates: dict[str, Any], version_source: str = "manual") -> bool:
        existing = self.get_novel_chapter(chapter_id)
        if not existing:
            return False
        allowed = {
            "title": 120,
            "goal": 1000,
            "summary": 1200,
            "body": 20000,
            "status": 40,
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, limit in allowed.items():
            if key in updates and updates[key] is not None:
                fields.append(f"{key} = ?")
                values.append(str(updates[key]).strip()[:limit])
        if "source_material_ids" in updates and updates["source_material_ids"] is not None:
            fields.append("source_material_ids_json = ?")
            values.append(json.dumps(updates["source_material_ids"][:24], ensure_ascii=False))
        if "scene_card" in updates and updates["scene_card"] is not None:
            fields.append("scene_card_json = ?")
            values.append(json.dumps(updates["scene_card"], ensure_ascii=False)[:8000])
        if not fields:
            return True
        fields.append("updated_at = datetime('now')")
        values.append(chapter_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE novel_chapters SET {', '.join(fields)} WHERE id = ?", values)
            conn.execute("UPDATE novel_projects SET updated_at = datetime('now') WHERE id = ?", (existing["project_id"],))
        if "body" in updates and updates["body"] is not None and str(updates["body"]).strip():
            next_title = str(updates.get("title") if updates.get("title") is not None else existing["title"])
            next_summary = str(updates.get("summary") if updates.get("summary") is not None else existing["summary"])
            self.add_novel_version(existing["project_id"], chapter_id, "draft", next_title, str(updates["body"]), next_summary, version_source)
        return True

    def add_novel_version(
        self,
        project_id: str,
        chapter_id: str,
        version_type: str,
        title: str,
        body: str,
        summary: str = "",
        source: str = "",
    ) -> str:
        next_title = title.strip()[:120]
        next_body = body.strip()[:20000]
        next_summary = summary.strip()[:1200]
        next_source = source.strip()[:120]
        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM novel_versions
                WHERE chapter_id = ?
                  AND title = ?
                  AND body = ?
                  AND summary = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (chapter_id, next_title, next_body, next_summary),
            ).fetchone()
            if existing:
                return str(existing["id"])
            conn.execute(
                """
                INSERT INTO novel_versions (
                    id, project_id, chapter_id, version_type, title, body, summary, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    project_id,
                    chapter_id,
                    version_type,
                    next_title,
                    next_body,
                    next_summary,
                    next_source,
                ),
            )
        return version_id

    def list_novel_versions(self, chapter_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM novel_versions
                WHERE chapter_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (chapter_id,),
            ).fetchall()

    def get_novel_version(self, version_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM novel_versions WHERE id = ?", (version_id,)).fetchone()

    def restore_novel_version(self, version_id: str) -> bool:
        version = self.get_novel_version(version_id)
        if not version:
            return False
        return self.update_novel_chapter(
            version["chapter_id"],
            {
                "title": version["title"],
                "body": version["body"],
                "summary": version["summary"],
                "status": "revised",
            },
            "restore",
        )

    def add_memory(
        self,
        visitor_id: str,
        session_id: str,
        character_id: str,
        memory_type: str,
        content: str,
        confidence: float,
        source_message_id: str | None,
        importance: float = 0.5,
    ) -> str | None:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        memory_scope = self._memory_scope(memory_type)
        normalized_key = self._normalize_memory_key(content)
        with self.connect() as conn:
            existing = self._find_existing_memory(
                conn,
                visitor_id,
                session_id,
                character_id,
                memory_scope,
                memory_type,
                normalized_key,
                content,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE memories SET
                        content = ?,
                        confidence = max(confidence, ?),
                        importance = max(importance, ?),
                        source_message_id = coalesce(?, source_message_id),
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (content, confidence, importance, source_message_id, existing["id"]),
                )
                row = conn.execute("SELECT id FROM memories WHERE id = ?", (existing["id"],)).fetchone()
            else:
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, visitor_id, session_id, character_id, memory_type, memory_scope,
                        content, confidence, importance, normalized_key, source_message_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        visitor_id,
                        session_id,
                        character_id,
                        memory_type,
                        memory_scope,
                        content,
                        confidence,
                        importance,
                        normalized_key,
                        source_message_id,
                    ),
                )
                row = conn.execute("SELECT id FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row:
                conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (row["id"],))
                conn.execute(
                    "INSERT INTO memory_fts (content, memory_id, session_id, visitor_id) VALUES (?, ?, ?, ?)",
                    (content, row["id"], session_id, visitor_id),
                )
                return str(row["id"])
        return None

    def upsert_embedding(self, owner_type: str, owner_id: str, provider: str, vector: list[float]) -> None:
        if not vector:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (id, owner_type, owner_id, provider, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(owner_type, owner_id, provider) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    created_at = datetime('now')
                """,
                (
                    f"emb_{uuid.uuid4().hex[:12]}",
                    owner_type,
                    owner_id,
                    provider,
                    json.dumps(vector),
                ),
            )

    def vector_memory_candidates(
        self,
        visitor_id: str,
        character_id: str,
        session_id: str,
        provider: str,
        limit: int = 200,
    ) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT memories.*, embeddings.vector_json
                FROM memories
                JOIN embeddings
                  ON embeddings.owner_type = 'memory'
                 AND embeddings.owner_id = memories.id
                 AND embeddings.provider = ?
                WHERE {self._memory_scope_where()}
                ORDER BY memories.importance DESC, memories.confidence DESC, memories.updated_at DESC
                LIMIT ?
                """,
                (provider, visitor_id, character_id, session_id, session_id, limit),
            ).fetchall()

    def update_memory_item(
        self,
        memory_id: str,
        visitor_id: str,
        character_id: str,
        session_id: str,
        memory_type: str | None = None,
        memory_scope: str | None = None,
        content: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
    ) -> bool:
        existing = self.memory_visible_in_session(memory_id, visitor_id, character_id, session_id)
        if not existing:
            return False
        next_content = (content if content is not None else existing["content"]).strip()
        next_type = memory_type or existing["memory_type"]
        next_scope = memory_scope or existing["memory_scope"] or self._memory_scope(next_type)
        next_confidence = max(0.0, min(1.0, float(confidence if confidence is not None else existing["confidence"] or 0)))
        next_importance = max(0.0, min(1.0, float(importance if importance is not None else existing["importance"] or 0.5)))
        if not next_content:
            return False
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE memories SET
                    memory_type = ?,
                    memory_scope = ?,
                    content = ?,
                    confidence = ?,
                    importance = ?,
                    normalized_key = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    next_type,
                    next_scope,
                    next_content[:280],
                    next_confidence,
                    next_importance,
                    self._normalize_memory_key(next_content),
                    memory_id,
                ),
            )
            conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            conn.execute(
                "INSERT INTO memory_fts (content, memory_id, session_id, visitor_id) VALUES (?, ?, ?, ?)",
                (next_content[:280], memory_id, session_id, visitor_id),
            )
        return True

    def delete_memory_item(self, memory_id: str, visitor_id: str, character_id: str, session_id: str) -> bool:
        existing = self.memory_visible_in_session(memory_id, visitor_id, character_id, session_id)
        if not existing:
            return False
        with self.connect() as conn:
            conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
            conn.execute("DELETE FROM embeddings WHERE owner_type = 'memory' AND owner_id = ?", (memory_id,))
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return True

    def _find_existing_memory(
        self,
        conn: sqlite3.Connection,
        visitor_id: str,
        session_id: str,
        character_id: str,
        memory_scope: str,
        memory_type: str,
        normalized_key: str,
        content: str,
    ) -> sqlite3.Row | None:
        if memory_scope == "global":
            return conn.execute(
                """
                SELECT id FROM memories
                WHERE visitor_id = ? AND memory_scope = 'global'
                  AND memory_type = ? AND normalized_key = ?
                LIMIT 1
                """,
                (visitor_id, memory_type, normalized_key),
            ).fetchone()
        if memory_scope == "character":
            return conn.execute(
                """
                SELECT id FROM memories
                WHERE visitor_id = ? AND character_id = ? AND memory_scope = 'character'
                  AND memory_type = ? AND normalized_key = ?
                LIMIT 1
                """,
                (visitor_id, character_id, memory_type, normalized_key),
            ).fetchone()
        return conn.execute(
            """
            SELECT id FROM memories
            WHERE session_id = ? AND memory_type = ?
              AND (normalized_key = ? OR content = ?)
            LIMIT 1
            """,
            (session_id, memory_type, normalized_key, content),
        ).fetchone()

    def _memory_scope_where(self) -> str:
        return """
            visitor_id = ? AND (
                memory_scope = 'global'
                OR (memory_scope = 'character' AND character_id = ?)
                OR (memory_scope = 'session' AND session_id = ?)
                OR (memory_scope = '' AND session_id = ?)
            )
        """

    def list_memories(self, visitor_id: str, character_id: str, session_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                ORDER BY
                    CASE memory_scope
                        WHEN 'global' THEN 0
                        WHEN 'character' THEN 1
                        WHEN 'session' THEN 2
                        ELSE 3
                    END,
                    CASE memory_type
                        WHEN 'stable_user_info' THEN 0
                        WHEN 'user_preference' THEN 1
                        WHEN 'relationship_progress' THEN 2
                        WHEN 'open_thread' THEN 3
                        WHEN 'recent_emotion' THEN 4
                        ELSE 5
                    END,
                    importance DESC,
                    updated_at DESC
                """,
                (visitor_id, character_id, session_id, session_id),
            ).fetchall()

    def profile_memories(self, visitor_id: str, character_id: str, session_id: str, limit: int = 12) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                  AND memory_type IN ('stable_user_info', 'user_preference', 'relationship_progress')
                ORDER BY
                    CASE memory_scope
                        WHEN 'global' THEN 0
                        WHEN 'character' THEN 1
                        ELSE 2
                    END,
                    importance DESC,
                    confidence DESC,
                    updated_at DESC
                LIMIT ?
                """,
                (visitor_id, character_id, session_id, session_id, limit),
            ).fetchall()

    def search_memories(self, visitor_id: str, character_id: str, session_id: str, query: str, limit: int = 8) -> list[sqlite3.Row]:
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query)
        terms = " ".join(part for part in cleaned.split() if len(part) >= 2)
        with self.connect() as conn:
            if terms:
                try:
                    rows = conn.execute(
                        f"""
                        SELECT memories.* FROM memory_fts
                        JOIN memories ON memories.id = memory_fts.memory_id
                        WHERE memory_fts MATCH ?
                          AND memories.visitor_id = ? AND (
                            memories.memory_scope = 'global'
                            OR (memories.memory_scope = 'character' AND memories.character_id = ?)
                            OR (memories.memory_scope = 'session' AND memories.session_id = ?)
                            OR (memories.memory_scope = '' AND memories.session_id = ?)
                          )
                        ORDER BY memories.importance DESC, memories.confidence DESC, memories.updated_at DESC
                        LIMIT ?
                        """,
                        (terms, visitor_id, character_id, session_id, session_id, limit),
                    ).fetchall()
                    if rows:
                        return rows
                except sqlite3.Error:
                    pass
            return conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {self._memory_scope_where()}
                ORDER BY importance DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (visitor_id, character_id, session_id, session_id, limit),
            ).fetchall()

    def update_session_memory(self, session_id: str, frozen: bool | None = None, manual_note: str | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if frozen is not None:
            fields.append("frozen = ?")
            values.append(1 if frozen else 0)
        if manual_note is not None:
            fields.append("manual_note = ?")
            values.append(manual_note[:1000])
        if not fields:
            return
        values.append(session_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", values)

    def set_summary(self, session_id: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET recent_summary = ?, updated_at = datetime('now') WHERE id = ?", (content[:1600], session_id))
            conn.execute(
                "INSERT INTO summaries (id, session_id, summary_type, content) VALUES (?, ?, 'recent', ?)",
                (f"sum_{uuid.uuid4().hex[:12]}", session_id, content[:1600]),
            )

    def set_prompt_slots(self, session_id: str, slots: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET last_prompt_slots = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(slots, ensure_ascii=False), session_id),
            )

    def set_character_state(self, session_id: str, state: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET character_state_json = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(state, ensure_ascii=False), session_id),
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
