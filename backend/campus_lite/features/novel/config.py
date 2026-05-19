from __future__ import annotations

import os


def env_timeout_ms(name: str, default: int) -> int:
    try:
        return max(1000, int(os.getenv(name) or default))
    except ValueError:
        return default


NOVEL_GENERATION_TIMEOUT_MS = env_timeout_ms("NOVEL_GENERATION_TIMEOUT_MS", 120000)
NOVEL_CANVAS_TIMEOUT_MS = env_timeout_ms("NOVEL_CANVAS_TIMEOUT_MS", 180000)
NOVEL_PLANNING_TIMEOUT_MS = env_timeout_ms("NOVEL_PLANNING_TIMEOUT_MS", 90000)
