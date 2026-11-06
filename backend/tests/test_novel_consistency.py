"""Novel persistence regressions; all data lives in a temporary database."""
from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from campus_lite.api import create_app
from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.novel import NovelService
from campus_lite.schemas import NovelProjectCreateRequest
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage, StoragePayloadError
from test_support import OfflineTestCase


class NovelConsistencyTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.storage = Storage(self.test_root / "novel.db")
        card = CharacterStore().get("lin_wanzhi")
        visitor, _ = self.storage.resolve_visitor("consistency-test")
        session = self.storage.create_or_get_session(visitor, card.id)
        self.service = NovelService(CharacterStateService(self.storage), CharacterBondService(self.storage), self.storage)
        self.project = self.service.create_project(card, visitor, session, [], [], [], NovelProjectCreateRequest())
        self.chapter_id = self.project.chapters[0].id

    def chapter(self):
        return self.storage.get_novel_chapter(self.chapter_id)

    def canvas(self):
        return json.loads(self.storage.get_novel_project(self.project.id)["story_canvas_json"])

    def save(self, body="old body"):
        self.storage.update_novel_chapter(self.chapter_id, {
            "body": body, "scene_card": {
                "chapter_handoff": {"happened": ["confirmed old event"]}, "handoff_source": "remote",
            },
        }, "remote")
        return self.storage.list_novel_versions(self.chapter_id)[0]

    def test_create_rolls_back_if_version_insert_fails(self):
        before = [dict(row) for row in self.storage.list_novel_chapters(self.project.id)]
        with patch.object(self.storage, "_insert_novel_version", side_effect=StoragePayloadError("snapshot too large")):
            with self.assertRaises(StoragePayloadError):
                self.storage.create_novel_chapter(self.project.id, "new chapter", body="new body")
        self.assertEqual([dict(row) for row in self.storage.list_novel_chapters(self.project.id)], before)

    def test_create_sets_active_version_from_saved_fields(self):
        chapter_id = self.storage.create_novel_chapter(self.project.id, "  ", body="  text  ")
        chapter = self.storage.get_novel_chapter(chapter_id)
        version = self.storage.list_novel_versions(chapter_id)[0]
        self.assertEqual(version["title"], chapter["title"])
        self.assertEqual(json.loads(chapter["scene_card_json"])["active_version_id"], version["id"])

    def test_body_hash_matches_persisted_truncated_body(self):
        version = self.save("  " + "长" * 20020 + "  ")
        delta = json.loads(version["state_delta_json"])
        self.assertEqual(delta["body_hash"], hashlib.sha256(version["body"].encode()).hexdigest()[:16])
        self.assertEqual(version["body"], self.chapter()["body"])

    def test_clearing_body_clears_active_state_but_keeps_history(self):
        self.save()
        self.storage.update_novel_chapter(self.chapter_id, {"body": "   "})
        card = json.loads(self.chapter()["scene_card_json"])
        self.assertNotIn("active_version_id", card)
        self.assertNotIn("chapter_handoff", card)
        self.assertEqual(len(self.storage.list_novel_versions(self.chapter_id)), 1)

    def test_restore_rolls_back_chapter_when_canvas_write_fails(self):
        version = self.save()
        self.save("new body")
        before = dict(self.chapter())
        before_canvas = self.canvas()
        # Exercise the actual JSON size rejection after restoring chapter fields.
        from campus_lite.storage_parts.common import JSON_LIMITS
        with patch.dict(JSON_LIMITS, {"story_canvas_json": 1}):
            with self.assertRaises(StoragePayloadError):
                self.storage.restore_novel_version(version["id"])
        self.assertEqual(dict(self.chapter()), before)
        self.assertEqual(self.canvas(), before_canvas)

    def test_restore_preserves_empty_goal_and_empty_scene_card(self):
        self.storage.update_novel_chapter(self.chapter_id, {"body": "old", "goal": "", "scene_card": {}})
        version = self.storage.list_novel_versions(self.chapter_id)[0]
        self.storage.update_novel_chapter(self.chapter_id, {"body": "new", "goal": "new goal", "scene_card": {"current_scene": "new scene"}})
        self.storage.restore_novel_version(version["id"])
        self.assertEqual(self.chapter()["goal"], "")
        self.assertNotIn("current_scene", json.loads(self.chapter()["scene_card_json"]))

    def test_restore_reconciles_event_bindings_without_reverting_other_chapters(self):
        canvas = self.canvas()
        event_a, event_b = canvas["event_pool"]["active"][:2]
        canvas["chapters"][0]["event_pool_id"] = event_a["id"]
        event_a["bound_chapter_orders"] = [1]
        self.storage.update_novel_project(self.project.id, {"story_canvas": canvas})
        version = self.save()
        canvas["chapters"][0]["event_pool_id"] = event_b["id"]
        canvas["chapters"][1]["event_pool_id"] = event_a["id"]
        event_a["bound_chapter_orders"] = [2]
        event_b["bound_chapter_orders"] = [1]
        self.storage.update_novel_project(self.project.id, {"story_canvas": canvas})
        self.storage.restore_novel_version(version["id"])
        restored = self.canvas()
        events = {item["id"]: item for item in restored["event_pool"]["active"]}
        self.assertEqual(restored["chapters"][1], canvas["chapters"][1])
        self.assertIn(2, events[event_a["id"]]["bound_chapter_orders"])
        self.assertIn(1, events[event_a["id"]]["bound_chapter_orders"])
        self.assertNotIn(1, events[event_b["id"]]["bound_chapter_orders"])

    def test_state_rebuild_rejects_mismatched_version_body(self):
        self.save()
        # A stale/imported state marker must not make unrelated body text trusted.
        self.storage.update_novel_chapter(self.chapter_id, {"body": "different body"}, create_version=False)
        self.service.rebuild_novel_state_from_latest_chapters_sync(self.project.id)
        state = self.service.project_response(self.project.id).novel_state
        self.assertNotIn("confirmed old event", state["confirmed_facts"])

    def test_save_and_restore_routes_roll_back_if_state_rebuild_fails(self):
        version = self.save()
        self.save("new body")
        client = TestClient(create_app(storage=self.storage))
        for method, url, payload in (
            ("patch", f"/api/novel/chapters/{self.chapter_id}", {"body": "edit"}),
            ("patch", f"/api/novel/chapters/{self.chapter_id}/draft", {"project": {"title": "edited title"}, "chapter": {"body": "edit"}}),
            ("post", f"/api/novel/versions/{version['id']}/restore", None),
            ("delete", f"/api/novel/chapters/{self.chapter_id}", None),
        ):
            with self.subTest(method=method, url=url):
                before = dict(self.chapter())
                before_project = dict(self.storage.get_novel_project(self.project.id))
                versions = [dict(row) for row in self.storage.list_novel_versions(self.chapter_id)]
                with patch.object(NovelService, "rebuild_novel_state_from_latest_chapters_sync", side_effect=RuntimeError("rebuild failed")):
                    with self.assertRaisesRegex(RuntimeError, "rebuild failed"):
                        client.request(method, url, json=payload)
                self.assertEqual(dict(self.chapter()), before)
                self.assertEqual(dict(self.storage.get_novel_project(self.project.id)), before_project)
                self.assertEqual([dict(row) for row in self.storage.list_novel_versions(self.chapter_id)], versions)

    def test_restore_uses_current_order_after_preceding_chapter_deleted(self):
        first_id = self.chapter_id
        self.chapter_id = self.storage.create_novel_chapter(self.project.id, "second", chapter_order=2)
        version = self.save()
        canvas_before = self.canvas()
        old_node_id = canvas_before["chapters"][1]["id"]
        self.storage.delete_novel_chapter(first_id)
        self.service.remove_chapter_from_story_canvas(self.project.id, 1)
        self.storage.restore_novel_version(version["id"])
        restored = self.canvas()
        node = next(item for item in restored["chapters"] if item["id"] == old_node_id)
        self.assertEqual(node["chapter_order"], 1)
        orders = [item["chapter_order"] for item in restored["chapters"]]
        self.assertEqual(len(orders), len(set(orders)))

    def test_full_bound_event_pool_rejects_restore_without_losing_data(self):
        version = self.save()
        snapshot = json.loads(version["planning_snapshot_json"])
        old_event_id = snapshot["event_pool_id"]
        self.assertTrue(old_event_id)
        canvas = self.canvas()
        canvas["event_pool"]["active"] = [{"id": f"new-{i}", "bound_chapter_orders": [i + 2]} for i in range(10)]
        canvas["event_pool"]["retired"] = []
        canvas["chapters"] = [canvas["chapters"][0]] + [
            {"id": f"node-{i}", "chapter_order": i + 2, "event_pool_id": f"new-{i}"} for i in range(10)
        ]
        self.storage.update_novel_project(self.project.id, {"story_canvas": canvas})
        self.save("new body")
        before = dict(self.chapter())
        client = TestClient(create_app(storage=self.storage))
        response = client.post(f"/api/novel/versions/{version['id']}/restore")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(dict(self.chapter()), before)
        self.assertEqual(self.canvas(), canvas)

    def test_restore_api_commits_body_and_rebuilt_state_together(self):
        version = self.save()
        self.storage.update_novel_chapter(self.chapter_id, {
            "body": "new body", "scene_card": {
                "chapter_handoff": {"happened": ["new event"]}, "handoff_source": "remote",
            },
        }, "remote")
        self.service.rebuild_novel_state_from_latest_chapters_sync(self.project.id)
        client = TestClient(create_app(storage=self.storage))
        response = client.post(f"/api/novel/versions/{version['id']}/restore")
        self.assertEqual(response.status_code, 200)
        self.assertIn("confirmed old event", response.json()["novel_state"]["confirmed_facts"])
        self.assertNotIn("new event", response.json()["novel_state"]["confirmed_facts"])
        reopened = Storage(self.storage.db_path)
        self.assertEqual(reopened.get_novel_chapter(self.chapter_id)["body"], "old body")
        state = json.loads(reopened.get_novel_project(self.project.id)["novel_state_json"])
        self.assertEqual(state, response.json()["novel_state"])

    def test_draft_save_rolls_back_project_when_version_payload_fails(self):
        self.save()
        before = dict(self.chapter())
        before_project = dict(self.storage.get_novel_project(self.project.id))
        from campus_lite.storage_parts.common import JSON_LIMITS
        with patch.dict(JSON_LIMITS, {"planning_snapshot_json": 1}):
            with self.assertRaises(StoragePayloadError):
                self.storage.update_novel_chapter_draft(self.project.id, self.chapter_id,
                    {"title": "changed project"}, {"body": "changed body"})
        self.assertEqual(dict(self.chapter()), before)
        self.assertEqual(dict(self.storage.get_novel_project(self.project.id)), before_project)
