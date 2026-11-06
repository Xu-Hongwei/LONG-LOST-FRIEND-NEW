"""Shared isolation for offline tests; never use the application's local data."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OfflineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        root = tempfile.TemporaryDirectory(prefix="campus_test_")
        self.addCleanup(root.cleanup)
        self.test_root = Path(root.name).resolve()
        # Existing tests create their own TemporaryDirectory; nest those here.
        self.enterContext(patch.object(tempfile, "tempdir", root.name))
        clean_env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("LLM_ROUTER_", "DASHSCOPE_", "DEEPSEEK_", "ARK_"))
        }
        self.enterContext(patch.dict(os.environ, clean_env, clear=True))

        connect = sqlite3.connect
        self.blocked_database_attempts: list[str] = []

        def temporary_connect(database, *args, **kwargs):
            if str(database) != ":memory:":
                if kwargs.get("uri") or not Path(database).resolve().is_relative_to(self.test_root):
                    self.blocked_database_attempts.append(str(database))
                    raise AssertionError("Offline tests must use a database inside their temporary directory")
            return connect(database, *args, **kwargs)

        self.enterContext(patch("sqlite3.connect", side_effect=temporary_connect))
        self.http_guards = [
            self.enterContext(patch(target, side_effect=AssertionError("Real HTTP is disabled in offline tests")))
            for target in (
                "httpx.HTTPTransport.handle_request",
                "httpx.AsyncHTTPTransport.handle_async_request",
            )
        ]
        # Run even if application fallback code catches the guard exception.
        self.addCleanup(self._assert_no_external_access)

    def _assert_no_external_access(self) -> None:
        self.assertEqual(self.blocked_database_attempts, [], "A test attempted to access a non-temporary database")
        for guard in self.http_guards:
            self.assertEqual(guard.call_count, 0, "A test attempted a real HTTP request; use a fake or MockTransport")
