from __future__ import annotations

from .storage_parts.base import BaseStorageMixin
from .storage_parts.characters import CharacterStorageMixin
from .storage_parts.common import DB_PATH, StoragePayloadError, now_sql
from .storage_parts.memories import MemoryStorageMixin
from .storage_parts.novel_chapters import NovelChapterStorageMixin
from .storage_parts.novel_projects import NovelProjectStorageMixin
from .storage_parts.novel_versions import NovelVersionStorageMixin
from .storage_parts.sessions import SessionStorageMixin
from .storage_parts.stories import StoryStorageMixin


class Storage(
    BaseStorageMixin,
    CharacterStorageMixin,
    SessionStorageMixin,
    StoryStorageMixin,
    NovelProjectStorageMixin,
    NovelChapterStorageMixin,
    NovelVersionStorageMixin,
    MemoryStorageMixin,
):
    pass
