from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from campus_lite.api import create_app
from campus_lite.llm import LlmClient
from campus_lite.storage import Storage
from fastapi.testclient import TestClient
from test_support import OfflineTestCase


class ApplicationIsolationTest(OfflineTestCase):
    def test_importing_entry_points_does_not_initialize_storage(self) -> None:
        script = """
from unittest.mock import patch
from campus_lite.storage_parts.base import BaseStorageMixin
with patch.object(BaseStorageMixin, '__init__', side_effect=AssertionError('Import initialized storage')):
    import campus_lite.api
    import campus_lite.app
    import run
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_separate_apps_keep_sessions_in_their_injected_databases(self) -> None:
        first = Storage(self.test_root / "first.db")
        second = Storage(self.test_root / "second.db")
        with TestClient(create_app(storage=first, llm=LlmClient())) as client:
            response = client.post("/api/sessions", json={
                "visitor_id": "isolated-visitor", "character_id": "lin_wanzhi",
            })
            self.assertEqual(response.status_code, 200)
            session_id = response.json()["session_id"]
            self.assertIsNotNone(first.get_session(session_id))
            self.assertIsNone(second.get_session(session_id))
            self.assertFalse(client.get("/api/health").json()["llm_configured"])
