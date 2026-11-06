"""Local SQLite backup, verification and recovery inventory (standard library only)."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "campus_lite.db"
TABLES = (
    "visitors", "characters", "sessions", "messages", "memories",
    "character_bonds", "relationship_events", "story_items", "novel_projects",
    "novel_materials", "novel_chapters", "novel_versions",
)


def read_only(path: Path) -> sqlite3.Connection:
    path = path.resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_database(path: Path) -> dict:
    with closing(read_only(path)) as connection:
        connection.execute("BEGIN")
        checks = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if checks != ["ok"]:
            raise ValueError("Database integrity check failed")
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(TABLES) - existing
        if missing:
            raise ValueError("Missing application tables: " + ", ".join(sorted(missing)))
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in TABLES}
        foreign_keys = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
        return {"integrity": "ok", "table_counts": counts, "foreign_key_violations": foreign_keys}


def code_version() -> dict:
    def git(*args):
        try:
            result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                                    text=True, timeout=10, check=True)
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    revision = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=normal")
    return {"commit": revision, "working_tree_dirty": bool(status) if status is not None else None}


def backup_database(source: Path, output_root: Path) -> Path:
    source = source.resolve(strict=True)
    timestamp = datetime.now(timezone.utc)
    folder = output_root.resolve() / (timestamp.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    # Opening the source read-only must succeed before creating any output.
    with closing(read_only(source)) as origin:
        folder.mkdir(parents=True, exist_ok=False)
        destination = folder / "campus_lite.db"
        deadline = time.monotonic() + 60

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("Backup timed out; retry when database activity is lower")

        with closing(sqlite3.connect(destination)) as target:
            origin.backup(target, pages=256, progress=progress, sleep=0.05)
            # The archive is one closed, standalone database, including committed WAL data.
            target.execute("PRAGMA journal_mode=DELETE")
    summary = inspect_database(destination)
    manifest = {
        "format_version": 1,
        "created_at_utc": timestamp.isoformat(),
        "source": str(source),
        "database": destination.name,
        "sha256": sha256(destination),
        "size_bytes": destination.stat().st_size,
        "code": code_version(),
        **summary,
    }
    # Written last: an interrupted/failed backup has no valid manifest.
    with (folder / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return folder


def verify_backup(folder: Path) -> dict:
    folder = folder.resolve(strict=True)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or manifest.get("database") != "campus_lite.db":
        raise ValueError("Unsupported backup manifest")
    database = folder / "campus_lite.db"
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Backup has SQLite sidecar files; keep archives closed and immutable")
    if database.stat().st_size != manifest["size_bytes"] or sha256(database) != manifest["sha256"]:
        raise ValueError("Backup checksum mismatch")
    summary = inspect_database(database)
    if any(summary[key] != manifest[key] for key in summary):
        raise ValueError("Backup contents do not match manifest")
    return manifest


def restore_database(folder: Path, destination: Path) -> dict:
    manifest = verify_backup(folder)
    destination = destination.resolve()
    if destination == DEFAULT_DB.resolve():
        raise ValueError("Restore to a new path first; replacing the live database is a separate operation")
    if destination.exists() or any(Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise FileExistsError("Restore destination or SQLite sidecar already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a target appearing after the check.
    with destination.open("xb") as target:
        with (folder / "campus_lite.db").open("rb") as source:
            shutil.copyfileobj(source, target)
    if sha256(destination) != manifest["sha256"]:
        raise ValueError("Restored checksum mismatch; do not use this restore")
    return {"restored_database": str(destination), **inspect_database(destination)}


def recovery_inventory(database: Path) -> dict:
    """List ownership and counts, without exporting conversation or novel text."""
    summary = inspect_database(database)
    with closing(read_only(database)) as connection:
        connection.execute("BEGIN")
        sessions = [dict(row) for row in connection.execute("""
            SELECT s.id AS session_id, s.visitor_id, s.character_id,
                   c.name AS character_name, c.origin AS character_origin,
                   c.deleted_at AS character_deleted_at, s.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS messages,
                   (SELECT COUNT(*) FROM memories m WHERE m.session_id=s.id) AS memories,
                   (SELECT COUNT(*) FROM novel_projects p WHERE p.session_id=s.id) AS projects,
                   (SELECT COUNT(*) FROM sessions s2 WHERE s2.visitor_id=s.visitor_id
                    AND s2.character_id=s.character_id) AS sessions_for_same_pair
            FROM sessions s LEFT JOIN characters c ON c.id=s.character_id
            ORDER BY s.updated_at DESC, s.id
        """)]
        projects = [dict(row) for row in connection.execute("""
            SELECT p.id AS project_id, p.visitor_id, p.character_id, p.session_id,
                   p.title, p.status,
                   (SELECT COUNT(*) FROM novel_chapters c WHERE c.project_id=p.id) AS chapters,
                   (SELECT COUNT(*) FROM novel_versions v WHERE v.project_id=p.id) AS versions
            FROM novel_projects p ORDER BY p.updated_at DESC, p.id
        """)]
    return {"database": str(database.resolve()), **summary, "sessions": sessions, "projects": projects}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a verified SQLite snapshot and manifest")
    backup.add_argument("--database", type=Path, default=DEFAULT_DB)
    backup.add_argument("--output-dir", type=Path, default=ROOT / "data" / "backups")
    verify = commands.add_parser("verify", help="Verify a backup folder")
    verify.add_argument("backup", type=Path)
    restore = commands.add_parser("restore", help="Restore to a NEW database path; never overwrite")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    inventory = commands.add_parser("inventory", help="Read-only session/project recovery index")
    inventory.add_argument("--database", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            folder = backup_database(args.database, args.output_dir)
            result = {"backup_directory": str(folder), **verify_backup(folder)}
        elif args.command == "verify":
            result = verify_backup(args.backup)
        elif args.command == "restore":
            result = restore_database(args.backup, args.destination)
        else:
            result = recovery_inventory(args.database)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, sqlite3.Error, TimeoutError) as exc:
        print(f"Data operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
