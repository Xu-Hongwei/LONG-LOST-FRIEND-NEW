from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from campus_lite.api import create_app
from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.features.novel.concurrency import NovelConflictError, NovelOperationGuard
from campus_lite.novel import NovelService
from campus_lite.schemas import NovelProjectCreateRequest, StoryEventPoolBindingRequest
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage
from test_support import OfflineTestCase


class NovelConcurrencyTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.storage = Storage(self.test_root / "novel.db")
        card = CharacterStore().get("lin_wanzhi")
        visitor, _ = self.storage.resolve_visitor("concurrency-test")
        session = self.storage.create_or_get_session(visitor, card.id)
        self.service = NovelService(CharacterStateService(self.storage), CharacterBondService(self.storage), self.storage)
        self.project = self.service.create_project(card, visitor, session, [], [], [], NovelProjectCreateRequest())
        self.chapter_id = self.project.chapters[0].id
        self.llm = SimpleNamespace(configured=lambda: False, last_chat_error=None)

    def chapter(self):
        return self.storage.get_novel_chapter(self.chapter_id)

    def revision(self):
        return self.storage.get_novel_project(self.project.id)["revision"]

    def pending(self):
        self.storage.update_novel_chapter(self.chapter_id, {"body": "generated body", "scene_card": {
            "postprocess": {"status": "pending"}, "generation_progress": {"run_id": "old-run"},
        }}, "remote")
        return self.revision()

    def test_generation_stops_after_manual_edit_during_model_wait(self):
        async def beats(*args):
            self.storage.update_novel_chapter(self.chapter_id, {"body": "user edit"})
            return [], "remote"
        with patch.object(self.service, "_build_scene_beats", side_effect=beats):
            with self.assertRaises(NovelConflictError):
                asyncio.run(self.service.generate_chapter(self.llm, self.project.id, self.chapter_id, "write", 1000))
        self.assertEqual(self.chapter()["body"], "user edit")
        self.assertEqual(len(self.storage.list_novel_versions(self.chapter_id)), 1)
        self.assertNotIn("generation_progress", json.loads(self.chapter()["scene_card_json"]))

    def test_new_generation_supersedes_old_generation(self):
        async def run():
            started, release = asyncio.Event(), asyncio.Event()
            calls = 0
            async def beats(*args):
                nonlocal calls
                calls += 1
                if calls == 1:
                    started.set()
                    await release.wait()
                return [], "local"
            with patch.object(self.service, "_build_scene_beats", side_effect=beats):
                old = asyncio.create_task(self.service.generate_chapter(self.llm, self.project.id, self.chapter_id, "old", 1000))
                await started.wait()
                await self.service.generate_chapter(self.llm, self.project.id, self.chapter_id, "new", 1000)
                saved = dict(self.chapter())
                release.set()
                with self.assertRaises(NovelConflictError):
                    await old
                self.assertEqual(dict(self.chapter()), saved)
        asyncio.run(run())

    def test_background_handoff_cannot_overwrite_edit_or_restore_even_on_error(self):
        for restore in (False, True):
            for fail in (False, True):
                with self.subTest(restore=restore, fail=fail):
                    self.storage.update_novel_chapter(self.chapter_id, {"body": "restorable"})
                    version = self.storage.list_novel_versions(self.chapter_id)[0]
                    revision = self.pending()
                    saved = {}
                    async def handoff(*args):
                        if restore:
                            self.storage.restore_novel_version(version["id"])
                        else:
                            self.storage.update_novel_chapter(self.chapter_id, {"body": "manual"})
                        saved.update(dict(self.chapter()))
                        if fail:
                            raise RuntimeError("model failed after editing")
                        return {"happened": ["stale fact"]}, "remote"
                    with patch.object(self.service, "_build_chapter_handoff", side_effect=handoff):
                        asyncio.run(self.service.finalize_chapter_postprocess(self.llm, self.project.id, self.chapter_id, revision, "old-run"))
                    self.assertEqual(dict(self.chapter()), saved)
                    self.assertNotIn("stale fact", self.service.project_response(self.project.id).novel_state.get("confirmed_facts", []))

    def test_queued_background_job_is_bound_to_original_revision(self):
        revision = self.pending()
        self.storage.update_novel_chapter(self.chapter_id, {"body": "new body"})
        saved = dict(self.chapter())
        with patch.object(self.service, "_build_chapter_handoff", new_callable=AsyncMock) as handoff:
            asyncio.run(self.service.finalize_chapter_postprocess(self.llm, self.project.id, self.chapter_id, revision, "old-run"))
        handoff.assert_not_called()
        self.assertEqual(dict(self.chapter()), saved)

    def test_duplicate_background_delivery_runs_handoff_once(self):
        revision = self.pending()
        async def run():
            started, release = asyncio.Event(), asyncio.Event()
            async def handoff(*args):
                started.set()
                await release.wait()
                return {"happened": ["event"]}, "remote"
            with patch.object(self.service, "_build_chapter_handoff", side_effect=handoff) as build:
                first = asyncio.create_task(self.service.finalize_chapter_postprocess(self.llm, self.project.id, self.chapter_id, revision, "old-run"))
                await started.wait()
                await self.service.finalize_chapter_postprocess(self.llm, self.project.id, self.chapter_id, revision, "old-run")
                release.set()
                await first
                self.assertEqual(build.call_count, 1)
        asyncio.run(run())
        self.assertEqual(json.loads(self.chapter()["scene_card_json"])["postprocess"]["status"], "done")

    def test_rolling_canvas_rejects_changes_made_while_model_waits(self):
        saved = {}
        async def chat(*args, **kwargs):
            self.storage.update_novel_chapter(self.chapter_id, {"body": "edited during replan"})
            saved.update(dict(self.storage.get_novel_project(self.project.id)))
            raise RuntimeError("remote unavailable")
        llm = SimpleNamespace(configured=lambda: True, chat_complete=chat, last_chat_error=None)
        with self.assertRaises(NovelConflictError):
            asyncio.run(self.service.extend_canvas(llm, self.project.id, 1, 2))
        self.assertEqual(dict(self.storage.get_novel_project(self.project.id)), saved)
        self.assertEqual(self.chapter()["body"], "edited during replan")

    def test_deleted_project_is_not_recreated_by_background_job(self):
        revision = self.pending()
        async def handoff(*args):
            with self.storage.connect() as conn:
                conn.execute("DELETE FROM novel_projects WHERE id = ?", (self.project.id,))
            return {}, "remote"
        with patch.object(self.service, "_build_chapter_handoff", side_effect=handoff):
            asyncio.run(self.service.finalize_chapter_postprocess(self.llm, self.project.id, self.chapter_id, revision, "old-run"))
        self.assertIsNone(self.chapter())
        self.assertIsNone(self.storage.get_novel_project(self.project.id))

    def test_revision_persists_across_instances_and_detects_restore_to_same_body(self):
        self.storage.update_novel_chapter(self.chapter_id, {"body": "same"})
        version = self.storage.list_novel_versions(self.chapter_id)[0]
        guard = NovelOperationGuard(self.storage, self.project.id, self.revision())
        other = Storage(self.storage.db_path)
        other.update_novel_chapter(self.chapter_id, {"body": "changed"})
        other.restore_novel_version(version["id"])
        with self.assertRaises(NovelConflictError):
            with guard.write():
                self.fail("stale write allowed")
        self.assertEqual(self.chapter()["body"], "same")

    def test_conflict_is_http_409_and_not_model_fallback(self):
        with patch.object(NovelService, "generate_chapter", side_effect=NovelConflictError()):
            client = TestClient(create_app(storage=self.storage))
            response = client.post(f"/api/novel/projects/{self.project.id}/generate-chapter", json={"chapter_id": self.chapter_id})
        self.assertEqual(response.status_code, 409)

    def test_status_only_cleanup_does_not_cancel_a_newer_operation(self):
        revision = self.pending()
        old = NovelOperationGuard(self.storage, self.project.id, revision)
        old.run_id = "old-run"
        self.storage.update_novel_project(self.project.id, {"title": "edited project"})
        newer = NovelOperationGuard(self.storage, self.project.id, self.revision())
        old.supersede_progress(self.chapter_id)
        newer.check()
        self.assertEqual(json.loads(self.chapter()["scene_card_json"])["postprocess"]["status"], "superseded")

    def test_manual_planning_edit_clears_background_runtime_markers(self):
        revision = self.pending()
        self.storage.update_novel_chapter(self.chapter_id, {"goal": "new plan"})
        card = json.loads(self.chapter()["scene_card_json"])
        self.assertNotIn("postprocess", card)
        self.assertNotIn("generation_progress", card)
        self.assertGreater(self.revision(), revision)
        self.assertEqual(self.chapter()["body"], "generated body")

    def test_old_schema_upgrade_preserves_novel_content_and_versions(self):
        self.pending()
        before = dict(self.chapter())
        versions = [dict(row) for row in self.storage.list_novel_versions(self.chapter_id)]
        with self.storage.connect() as conn:
            names = [row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE '%revision%'")]
            for name in names:
                conn.execute(f'DROP TRIGGER "{name}"')
            conn.execute("ALTER TABLE novel_projects DROP COLUMN revision")
        upgraded = Storage(self.storage.db_path)
        self.assertEqual(dict(upgraded.get_novel_chapter(self.chapter_id)), before)
        self.assertEqual([dict(row) for row in upgraded.list_novel_versions(self.chapter_id)], versions)
        self.assertEqual(upgraded.get_novel_project(self.project.id)["revision"], 0)
        upgraded.update_novel_chapter(self.chapter_id, {"body": "after upgrade"})
        self.assertGreater(upgraded.get_novel_project(self.project.id)["revision"], 0)

    def test_event_contract_response_cannot_overwrite_new_binding(self):
        event = self.project.story_canvas["event_pool"]["active"][0]
        saved = {}
        async def chat(*args, **kwargs):
            self.storage.update_novel_chapter(self.chapter_id, {"goal": "new plan"})
            saved.update(dict(self.chapter()))
            raise RuntimeError("late remote failure")
        llm = SimpleNamespace(configured=lambda: True, chat_complete=chat, last_chat_error=None)
        with self.assertRaises(NovelConflictError):
            asyncio.run(self.service.bind_event_pool_event_to_chapter_remote(llm, self.project.id, self.chapter_id,
                StoryEventPoolBindingRequest(event_id=event["id"], use_mode="strict")))
        self.assertEqual(dict(self.chapter()), saved)

    def test_state_summary_cannot_reintroduce_facts_after_edit(self):
        self.storage.update_novel_chapter(self.chapter_id, {"body": "remote body", "scene_card": {
            "chapter_handoff": {"happened": ["old fact"]}, "handoff_source": "remote",
        }}, "remote")
        saved = {}
        async def chat(*args, **kwargs):
            self.storage.update_novel_chapter(self.chapter_id, {"body": "user body"})
            self.service.rebuild_novel_state_from_latest_chapters_sync(self.project.id)
            saved.update(dict(self.storage.get_novel_project(self.project.id)))
            return json.dumps({"confirmed_facts": ["stale remote fact"]})
        llm = SimpleNamespace(configured=lambda: True, chat_complete=chat, last_chat_error=None)
        with self.assertRaises(NovelConflictError):
            asyncio.run(self.service._rebuild_novel_state_from_latest_chapters(self.project.id, llm))
        self.assertEqual(dict(self.storage.get_novel_project(self.project.id)), saved)

    def test_background_replan_cannot_mark_a_restored_version_done(self):
        self.storage.update_novel_chapter(self.chapter_id, {"body": "restore target"})
        version = self.storage.list_novel_versions(self.chapter_id)[0]
        revision = self.pending()
        saved = {}
        async def chat(*args, **kwargs):
            self.storage.restore_novel_version(version["id"])
            self.service.mark_chapter_revision_boundary(self.project.id, 1)
            saved.update(dict(self.chapter()))
            return "{}"
        llm = SimpleNamespace(configured=lambda: True, chat_complete=chat, last_chat_error=None)
        with patch.object(self.service, "_build_chapter_handoff", return_value=({"happened": ["new event"]}, "remote")):
            asyncio.run(self.service.finalize_chapter_postprocess(llm, self.project.id, self.chapter_id, revision, "old-run"))
        self.assertEqual(dict(self.chapter()), saved)
        self.assertEqual(self.chapter()["body"], "restore target")
