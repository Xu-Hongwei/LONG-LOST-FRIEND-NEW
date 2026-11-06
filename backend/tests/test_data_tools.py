from __future__ import annotations

from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from campus_lite.storage import Storage
from test_support import OfflineTestCase

spec = importlib.util.spec_from_file_location("data_tools", Path(__file__).resolve().parents[2] / "scripts" / "data_tools.py")
data_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data_tools)


class DataToolsTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.database = self.test_root / "source.db"
        self.storage = Storage(self.database)
        self.storage.resolve_visitor("test-visitor")
        self.session = self.storage.create_or_get_session("test-visitor", "test-character")
        self.storage.add_message(self.session, "test-visitor", "test-character", "user", "测试消息")
        self.enterContext(patch.object(data_tools, "code_version", return_value={"commit": "test", "working_tree_dirty": False}))

    def test_snapshot_restore_preserves_content_and_does_not_touch_source(self):
        before = data_tools.sha256(self.database)
        folder = data_tools.backup_database(self.database, self.test_root / "backups")
        restored = self.test_root / "restore" / "copy.db"
        result = data_tools.restore_database(folder, restored)
        self.assertEqual(result["table_counts"]["messages"], 1)
        with closing(data_tools.read_only(restored)) as connection:
            self.assertEqual(connection.execute("SELECT content FROM messages").fetchone()[0], "测试消息")
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM messages")
        self.assertEqual(data_tools.sha256(self.database), before)

    def test_backup_includes_committed_wal_but_not_uncommitted_changes(self):
        with closing(sqlite3.connect(self.database)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO visitors(id) VALUES ('committed')")
            writer.commit()
            writer.execute("INSERT INTO visitors(id) VALUES ('not-committed')")
            folder = data_tools.backup_database(self.database, self.test_root / "backups")
            with closing(data_tools.read_only(folder / "campus_lite.db")) as snapshot:
                ids = {row[0] for row in snapshot.execute("SELECT id FROM visitors")}
                self.assertIn("committed", ids)
                self.assertNotIn("not-committed", ids)
            writer.rollback()
        self.assertEqual(data_tools.verify_backup(folder)["integrity"], "ok")

    def test_restore_refuses_existing_destination_and_modified_backup(self):
        folder = data_tools.backup_database(self.database, self.test_root / "backups")
        before = data_tools.sha256(self.database)
        with self.assertRaises(FileExistsError):
            data_tools.restore_database(folder, self.database)
        self.assertEqual(data_tools.sha256(self.database), before)
        with (folder / "campus_lite.db").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            data_tools.restore_database(folder, self.test_root / "new.db")
        self.assertFalse((self.test_root / "new.db").exists())

    def test_missing_source_is_not_created(self):
        missing = self.test_root / "missing.db"
        with self.assertRaises(FileNotFoundError):
            data_tools.backup_database(missing, self.test_root / "backups")
        self.assertFalse(missing.exists())
        self.assertFalse((self.test_root / "backups").exists())

    def test_existing_orphan_is_reported_and_preserved_without_repair(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO character_bonds(visitor_id, character_id) VALUES ('missing-visitor', 'test-character')")
            connection.commit()
        folder = data_tools.backup_database(self.database, self.test_root / "backups")
        self.assertEqual(data_tools.verify_backup(folder)["foreign_key_violations"], 1)
        result = data_tools.restore_database(folder, self.test_root / "restored.db")
        self.assertEqual(result["foreign_key_violations"], 1)
        self.assertEqual(result["table_counts"]["character_bonds"], 1)

    def test_restore_refuses_live_path_and_leftover_sidecars(self):
        folder = data_tools.backup_database(self.database, self.test_root / "backups")
        with patch.object(data_tools, "DEFAULT_DB", self.database):
            with self.assertRaisesRegex(ValueError, "live database"):
                data_tools.restore_database(folder, self.database)
        destination = self.test_root / "new.db"
        sidecar = self.test_root / "new.db-wal"
        sidecar.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            data_tools.restore_database(folder, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(sidecar.read_bytes(), b"existing")

    def test_inventory_lists_ownership_without_message_content(self):
        inventory = data_tools.recovery_inventory(self.database)
        self.assertEqual(inventory["sessions"][0]["visitor_id"], "test-visitor")
        self.assertEqual(inventory["sessions"][0]["messages"], 1)
        self.assertNotIn("测试消息", json.dumps(inventory, ensure_ascii=False))
