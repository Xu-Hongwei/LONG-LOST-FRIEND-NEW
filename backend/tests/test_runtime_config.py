from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from test_support import OfflineTestCase

ROOT = Path(__file__).resolve().parents[2]


class RuntimeConfigurationTest(OfflineTestCase):
    def test_preflight_rejects_invalid_timeout_without_disclosing_value(self):
        env = dict(os.environ, LLM_ROUTER_TIMEOUT_MS="private-invalid-value")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/check-env.py")],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LLM_ROUTER_TIMEOUT_MS", result.stderr)
        self.assertNotIn("private-invalid-value", result.stdout + result.stderr)

    def test_preflight_rejects_incomplete_router_without_disclosing_key(self):
        env = dict(os.environ, LLM_ROUTER_API_KEY="private-test-key")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/check-env.py")],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LLM_ROUTER_BASE_URL", result.stderr)
        self.assertNotIn("private-test-key", result.stdout + result.stderr)

    def test_custom_database_path_is_shared_without_creating_the_database(self):
        destination = self.test_root / "custom.db"
        env = dict(os.environ, CAMPUS_DB_PATH=str(destination))
        script = """
import runpy
from pathlib import Path
from campus_lite.storage_parts.common import DB_PATH
tool = runpy.run_path(str(Path.cwd().parent / 'scripts/data_tools.py'))
assert DB_PATH == tool['DEFAULT_DB']
assert not DB_PATH.exists()
"""
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT / "backend",
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(destination.exists())
