"""Rolling plans must retain their causal order and avoid redundant model calls."""
from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.features.novel.concurrency import NovelConflictError
from campus_lite.features.novel.event_pool import bind_story_event_pool_to_chapters
from campus_lite.novel import NovelService
from campus_lite.schemas import NovelProjectCreateRequest
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage
from test_support import OfflineTestCase


class NovelPlanningTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.storage = Storage(self.test_root / "planning.db")
        card = CharacterStore().get("lin_wanzhi")
        visitor, _ = self.storage.resolve_visitor("planning-test")
        session = self.storage.create_or_get_session(visitor, card.id)
        self.service = NovelService(CharacterStateService(self.storage), CharacterBondService(self.storage), self.storage)
        self.project = self.service.create_project(card, visitor, session, [], [], [], NovelProjectCreateRequest())
        self.canvas = copy.deepcopy(self.project.story_canvas)
        events = self.canvas["event_pool"]["active"]
        for i, event in enumerate(events[:7]):
            event.update(source="remote", status="fresh", event=f"核对第{i + 1}份旧档案，发现新的纸条线索。", place="旧书店", hook=f"纸条指向编号{i + 1}。")
        self.events = events
        self.storage.update_novel_project(self.project.id, {"story_canvas": self.canvas})

    def proposal(self):
        chapters = []
        scenes = []
        for index, event in enumerate(self.events[4:6]):
            order = index + 2
            chapter_id = f"planned_{order}"
            chapters.append({
                "id": chapter_id, "chapter_order": order, "title": f"第{order}章 查阅档案",
                "event_pool_id": event["id"], "external_event": event["event"],
                "goal": f"先核对馆藏编号，再{event['event']}林舟决定保留纸条供下次比对。",
                "obstacle_escalation": "档案缺少日期，需要对照背面的印章。",
                "character_choice": "先核对印章，再查下一册。", "ending_hook": event["hook"],
            })
            scenes.append({"id": f"scene_{order}", "chapter_id": chapter_id,
                           "current_scene": "靠窗的档案桌", "surface_event": "摊开地图逐项核对", "tension": "印章模糊，无法立即确认日期。"})
        return {"chapters": chapters, "scenes": scenes}

    def fake_llm(self, fail_pool=False, edit_during_call=False):
        calls = []
        async def complete(messages, **kwargs):
            calls.append(messages)
            if edit_during_call:
                self.storage.update_novel_project(self.project.id, {"title": "作者的新标题"})
            if messages[0]["content"] == self.service._event_pool_delta_system_prompt():
                if fail_pool:
                    raise TimeoutError("test timeout")
                return json.dumps({"add": []})
            return json.dumps(self.proposal(), ensure_ascii=False)
        return SimpleNamespace(configured=lambda: True, chat_complete=complete, calls=calls, last_chat_error=None)

    def test_healthy_pool_skips_refresh_and_preserves_generated_plan(self):
        llm = self.fake_llm()
        result = asyncio.run(self.service.extend_canvas(llm, self.project.id, 1, 2))
        self.assertEqual(len(llm.calls), 1)
        diagnostics = result.story_canvas["diagnostics"]
        self.assertEqual(diagnostics["event_pool_update_source"], "reused")
        self.assertEqual(diagnostics["remote_call_count"], 1)
        self.assertIn("canvas", diagnostics["timings_ms"])
        expected = self.proposal()["chapters"][0]
        actual = result.story_canvas["chapters"][1]
        for key in ("goal", "obstacle_escalation", "character_choice", "event_pool_id"):
            self.assertEqual(actual[key], expected[key])
        self.assertEqual(result.story_canvas["scenes"][1]["current_scene"], "靠窗的档案桌")

    def test_generic_pool_still_refreshes_before_planning(self):
        for event in self.canvas["event_pool"]["active"]:
            event["source"] = "setting_profile"
        self.storage.update_novel_project(self.project.id, {"story_canvas": self.canvas})
        llm = self.fake_llm()
        result = asyncio.run(self.service.extend_canvas(llm, self.project.id, 1, 2))
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(result.story_canvas["diagnostics"]["event_pool_refresh"]["reason"], "replace_generic_events")

    def test_used_and_blocked_candidates_do_not_count_as_available(self):
        for event in self.events[:6]:
            event["status"] = "used"
        self.events[6]["tags"] = {"boundary_risk": "high"}
        project = self.storage.get_novel_project(self.project.id)
        refresh = self.service._rolling_event_pool_refresh(project, self.canvas, 1, 2)
        self.assertTrue(refresh["required"])
        self.assertEqual(refresh["available_count"], 0)

    def test_refresh_failure_keeps_canvas_generation_available(self):
        for event in self.events[:7]:
            event["status"] = "used"
        self.storage.update_novel_project(self.project.id, {"story_canvas": self.canvas})
        llm = self.fake_llm(fail_pool=True)
        result = asyncio.run(self.service.extend_canvas(llm, self.project.id, 1, 2))
        self.assertEqual(result.story_canvas["diagnostics"]["source"], "remote")
        self.assertEqual(result.story_canvas["diagnostics"]["event_pool_update_error"], "TimeoutError")

    def test_reuse_path_rejects_model_result_after_saved_edit(self):
        llm = self.fake_llm(edit_during_call=True)
        with self.assertRaises(NovelConflictError):
            asyncio.run(self.service.extend_canvas(llm, self.project.id, 1, 2))
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(self.storage.get_novel_project(self.project.id)["title"], "作者的新标题")

    def test_parser_uses_declared_chapter_order_and_keeps_scene_links(self):
        proposal = self.proposal()
        proposal["chapters"].reverse()
        parsed = self.service._parse_canvas_response(json.dumps(proposal), self.canvas)
        self.assertEqual([c["id"] for c in parsed["chapters"]], ["planned_2", "planned_3"])
        self.assertEqual(parsed["scenes"][0]["chapter_id"], "planned_2")

    def test_higher_candidate_score_does_not_swap_valid_bound_events(self):
        chapters = copy.deepcopy(self.proposal()["chapters"])
        expected_ids = [chapter["event_pool_id"] for chapter in chapters]
        def score(event, chapter, *args):
            return {"score": 60 if event["id"] == chapter["event_pool_id"] else 95,
                    "reasons": [], "penalties": [], "blocked": False}
        with patch("campus_lite.features.novel.event_pool.score_story_event", side_effect=score):
            bind_story_event_pool_to_chapters(self.canvas["event_pool"], chapters, context={"prefer_concrete_events": True})
        self.assertEqual([chapter["event_pool_id"] for chapter in chapters], expected_ids)

    def test_manual_strict_binding_still_replaces_plan(self):
        proposal = self.proposal()
        chapter = proposal["chapters"][0]
        replacement = self.events[6]
        self.service._sync_event_contract_to_chapter(proposal, chapter, replacement, None, use_mode="strict")
        self.assertEqual(chapter["external_event"], replacement["event"])
        self.assertIn(replacement["event"], chapter["goal"])

    def test_automatic_contract_keeps_existing_goal_and_scene(self):
        proposal = self.proposal()
        proposal["event_pool"] = self.canvas["event_pool"]
        proposal["diagnostics"] = {"source": "remote"}
        expected = copy.deepcopy(proposal)
        compacted = self.service._compact_story_canvas(proposal)
        for index, chapter in enumerate(compacted["chapters"]):
            self.assertEqual(chapter["goal"], expected["chapters"][index]["goal"])
            self.assertEqual(chapter["obstacle_escalation"], expected["chapters"][index]["obstacle_escalation"])
            self.assertEqual(compacted["scenes"][index]["current_scene"], expected["scenes"][index]["current_scene"])

    def test_missing_event_id_does_not_inherit_unrelated_fallback_contract(self):
        proposal = self.proposal()
        chapter = proposal["chapters"][0]
        chapter.pop("event_pool_id")
        chapter.update(external_event="书店突然停电", trigger_event="灯光闪烁后熄灭",
                       goal="两人在黑暗中发现隐蔽门把手。", ending_hook="寻找备用电源")
        parsed = self.service._parse_canvas_response(json.dumps(proposal), self.canvas)
        parsed["diagnostics"]["source"] = "remote"
        merged = self.service._merge_extended_canvas(self.canvas, parsed, 1)
        actual = merged["chapters"][1]
        self.assertEqual(actual["event_pool_id"], "")
        self.assertNotIn("event_contract", actual)
        self.assertEqual(actual["goal"], chapter["goal"])

    def test_automatic_flavor_sync_preserves_previously_synced_scene(self):
        proposal = self.proposal()
        chapter = proposal["chapters"][0]
        scene = proposal["scenes"][0]
        original = scene["surface_event"]
        chapter["event_sync"] = {"scene_fields": {"surface_event": original}}
        self.service._sync_event_contract_to_chapter(
            proposal, chapter, self.events[4], None, use_mode="flavor", preserve_plan=True,
        )
        self.assertEqual(scene["surface_event"], original)
