"""Optimistic guards for long-running novel operations (no DB lock during I/O)."""
from contextlib import contextmanager
from uuid import uuid4

from ...storage import Storage


class NovelConflictError(RuntimeError):
    def __init__(self):
        super().__init__("项目已被编辑或另一个任务更新，已停止写入旧生成结果。请重新加载后再试。")


class NovelOperationGuard:
    def __init__(self, storage: Storage, project_id: str, revision: int):
        self.storage = storage
        self.project_id = project_id
        self.revision = revision
        self.run_id = uuid4().hex

    def claim(self):
        with self.write():
            with self.storage.connect() as conn:
                conn.execute("UPDATE novel_projects SET revision = revision + 1 WHERE id = ?", (self.project_id,))

    def check(self):
        project = self.storage.get_novel_project(self.project_id)
        if not project or project["revision"] != self.revision:
            raise NovelConflictError()

    @contextmanager
    def write(self):
        with self.storage.transaction():
            self.check()
            yield
            self.revision = self.storage.get_novel_project(self.project_id)["revision"]

    def supersede_progress(self, chapter_id: str):
        # A conflict may update only this run's status, never another run's content.
        with self.storage.transaction():
            chapter = self.storage.get_novel_chapter(chapter_id)
            if not chapter:
                return
            card = self.storage._json_dict(chapter["scene_card_json"])
            if card.get("generation_progress", {}).get("run_id") != self.run_id:
                return
            card["generation_progress"] = {"stage": "superseded", "percent": 100, "run_id": self.run_id,
                                           "detail": "项目已变化，旧任务已停止写入，请重新加载后核对。"}
            card["postprocess"] = {"status": "superseded"}
            self.storage.update_novel_chapter(chapter_id, {"scene_card": card}, "system")
