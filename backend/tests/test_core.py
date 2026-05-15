from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.composer import ComposeInput, ContextComposer
from campus_lite.llm import LlmClient
from campus_lite.memory import MemoryService
from campus_lite.novel import NovelService
from campus_lite.schemas import NovelChapterGenerateRequest, NovelGenerateRequest, NovelProjectCreateRequest
from campus_lite.schemas import MemoryItem
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage
from campus_lite.story import StoryService


class CampusLiteCoreTest(unittest.TestCase):
    def test_character_cards_load(self) -> None:
        cards = CharacterStore().list_cards()
        self.assertGreaterEqual(len(cards), 5)
        self.assertTrue(any(card.name == "林晚栀" for card in cards))

    def test_context_slots_keep_persona_and_memory(self) -> None:
        card = CharacterStore().list_cards()[0]
        memories = [
            MemoryItem(
                id="mem_1",
                memory_type="user_preference",
                content="用户喜欢雨天图书馆。",
                confidence=0.9,
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
        ]
        slots = ContextComposer().compose(
            ComposeInput(
                character=card,
                recent_messages=[],
                user_message="你还记得我喜欢什么吗？",
                memories=memories,
                recent_summary="",
                live_state="当前互动状态：放慢回复，少追问，不要提到状态条或分数。",
                relationship_memory="长期关系档案：自然参考用户偏好，不要提到 Bond 或分数。",
            )
        )
        keys = {slot.key for slot in slots if slot.included}
        self.assertIn("persona.identity", keys)
        self.assertIn("persona.personality", keys)
        self.assertIn("persona.scenario", keys)
        self.assertIn("persona.interaction_policy", keys)
        self.assertIn("persona.relationship_memory", keys)
        self.assertIn("persona.live_state", keys)
        self.assertIn("persona.speech_style", keys)
        self.assertIn("persona.examples", keys)
        self.assertIn("memory.recall", keys)
        self.assertIn("user.current_message", keys)

    def test_context_budget_estimates_chinese_text_more_realistically(self) -> None:
        composer = ContextComposer()
        short = composer._slot("test.short", "hello world", 50)
        chinese = composer._slot("test.zh", "这是一段中文上下文，用来估算预算。", 50)
        self.assertGreater(chinese.token_budget, short.token_budget)

    def test_storage_visitor_session_memory_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, created = storage.resolve_visitor("tester")
            self.assertTrue(created)
            same_id, created_again = storage.resolve_visitor("tester")
            self.assertEqual(visitor_id, same_id)
            self.assertFalse(created_again)

            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            msg_id = storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "我喜欢热可可")
            storage.add_memory(visitor_id, session_id, "lin_wanzhi", "user_preference", "用户喜欢热可可。", 0.8, msg_id)

            memory = MemoryService(storage)
            recalled = memory.recall(session_id, "还记得我喜欢什么吗")
            self.assertTrue(recalled)
            self.assertEqual(recalled[0].memory_type, "user_preference")
            self.assertEqual(recalled[0].memory_scope, "global")

    def test_session_messages_can_restore_recent_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            for index in range(5):
                storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", f"第 {index} 条")
            restored = storage.session_messages(session_id, 3)
            self.assertEqual(len(restored), 3)
            self.assertEqual([item["content"] for item in restored], ["第 2 条", "第 3 条", "第 4 条"])

    def test_message_lookup_returns_created_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            message_id = storage.add_message(session_id, visitor_id, "lin_wanzhi", "assistant", "你好呀")
            message = storage.get_message(message_id)
            self.assertIsNotNone(message)
            self.assertEqual(message["id"], message_id)
            self.assertEqual(message["role"], "assistant")
            self.assertTrue(message["created_at"])

    def test_schema_indexes_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            with storage.connect() as conn:
                migrations = conn.execute("SELECT name FROM schema_migrations WHERE version = 1").fetchall()
                indexes = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
                    ).fetchall()
                }
            self.assertEqual([row["name"] for row in migrations], ["initial_indexes"])
            self.assertIn("idx_sessions_visitor_character_updated", indexes)
            self.assertIn("idx_messages_session_created", indexes)
            self.assertIn("idx_memories_visible", indexes)

    def test_global_memory_recalls_across_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            first_session = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            msg_id = storage.add_message(first_session, visitor_id, "lin_wanzhi", "user", "我喜欢安静的图书馆")
            storage.add_memory(
                visitor_id,
                first_session,
                "lin_wanzhi",
                "user_preference",
                "用户喜欢安静的图书馆。",
                0.9,
                msg_id,
                0.8,
            )

            second_session = storage.create_or_get_session(visitor_id, "shen_yan")
            memory = MemoryService(storage)
            recalled = memory.recall(second_session, "我平时喜欢什么地方？")
            self.assertTrue(any(item.memory_scope == "global" for item in recalled))
            self.assertTrue(any("图书馆" in item.content for item in recalled))

    def test_vector_memory_can_rescue_semantic_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            library_id = storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "user_preference",
                "用户喜欢安静的图书馆。",
                0.8,
                None,
                0.8,
            )
            gym_id = storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "user_preference",
                "用户喜欢热闹的运动场。",
                0.8,
                None,
                0.8,
            )
            self.assertIsNotNone(library_id)
            self.assertIsNotNone(gym_id)
            storage.upsert_embedding("memory", str(library_id), "test", [1.0, 0.0])
            storage.upsert_embedding("memory", str(gym_id), "test", [0.0, 1.0])

            memory = MemoryService(storage)
            recalled = memory.recall(
                session_id,
                "我一般去哪里放松？",
                query_vector=[1.0, 0.0],
                embedding_provider="test",
            )
            self.assertTrue(recalled)
            self.assertIn("图书馆", recalled[0].content)

    def test_memory_item_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            memory_id = storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "open_thread",
                "用户想下次继续聊社团报名。",
                0.7,
                None,
                0.5,
            )
            self.assertIsNotNone(memory_id)
            updated = storage.update_memory_item(
                str(memory_id),
                visitor_id,
                "lin_wanzhi",
                session_id,
                memory_scope="global",
                content="用户想长期关注社团报名。",
                importance=0.9,
            )
            self.assertTrue(updated)
            memory = MemoryService(storage)
            listed = memory.list_memories(session_id)
            self.assertEqual(listed[0].memory_scope, "global")
            self.assertEqual(listed[0].importance, 0.9)
            self.assertIn("长期关注", listed[0].content)

            deleted = storage.delete_memory_item(str(memory_id), visitor_id, "lin_wanzhi", session_id)
            self.assertTrue(deleted)
            self.assertFalse(memory.list_memories(session_id))

    def test_memory_extraction_prompt_has_scoring_rubric(self) -> None:
        prompt = LlmClient().memory_extraction_system_prompt()
        self.assertIn("不要保存助手单方面说了什么", prompt)
        self.assertIn("短期 session 上下文要宽松", prompt)
        self.assertIn("地点建议", prompt)
        self.assertIn("当前会话正在讨论", prompt)
        self.assertIn("confidence 评分", prompt)
        self.assertIn("importance 评分", prompt)
        self.assertIn("短期上下文", prompt)
        self.assertIn("通常不要低于 0.35", prompt)
        self.assertIn("最多输出 5 条", prompt)

    def test_character_state_guardrail_and_prompt_hides_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            service = CharacterStateService(storage)
            previous = service.ensure_state(session_id)
            scored = {
                "mood": "认真听",
                "tone": "放慢一点",
                "distance": "自然熟悉",
                "focus": "用户正在确认实现规则",
                "energy": 1.5,
                "resonance_delta": 0.8,
                "behavior": {
                    "pace": "解释清楚，别太快",
                    "initiative": "少追问，优先接住问题",
                    "warmth": "熟悉但不过度亲密",
                    "memory_use": "只使用明确相关记忆",
                    "avoid": "不要说状态条或评分",
                },
                "evidence": "用户在讨论评分规则，需要机制解释。",
            }
            next_state = service.apply_model_score(previous, scored)
            self.assertEqual(next_state["energy"], 1.0)
            self.assertAlmostEqual(next_state["resonance"], previous["resonance"] + 0.05)
            prompt = service.state_to_prompt(next_state)
            self.assertIn("回复节奏=解释清楚，别太快", prompt)
            self.assertNotIn("1.0", prompt)
            self.assertNotIn("0.35", prompt)

    def test_character_state_prompt_has_rubric(self) -> None:
        prompt = LlmClient().character_state_system_prompt()
        self.assertIn("只输出 JSON 对象", prompt)
        self.assertIn("用户只是在问技术、规则、实现", prompt)
        self.assertIn("助手单方面建议", prompt)
        self.assertIn("behavior.pace", prompt)

    def test_character_state_defaults_are_character_bound(self) -> None:
        cards = {card.id: card for card in CharacterStore().list_cards()}
        with tempfile.TemporaryDirectory() as tmp:
            service = CharacterStateService(Storage(Path(tmp) / "test.db"))
            lin = service.default_state(cards["lin_wanzhi"])
            shen = service.default_state(cards["shen_yan"])
            self.assertNotEqual(lin["tone"], shen["tone"])
            self.assertNotEqual(lin["behavior"]["pace"], shen["behavior"]["pace"])
            self.assertIn("林晚栀", lin["evidence"])
            self.assertIn("沈砚", shen["evidence"])

    def test_character_bond_guardrail_and_prompt_hides_scores(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            service = CharacterBondService(storage)
            previous = service.ensure_bond(visitor_id, card.id, card)
            scored = {
                "should_update": True,
                "familiarity_stage": "逐渐熟悉",
                "resonance_base_delta": 0.8,
                "trust_notes": "用户明确认可角色用慢节奏解释问题。",
                "boundary_notes": "用户不希望被连续追问。",
                "interaction_preferences": "解释规则时要给行为依据，不只给分数。",
                "milestone": "用户确认状态分数应映射到行为表现。",
                "evidence": "用户明确表达长期互动设计偏好。",
            }
            next_bond = service.apply_model_update(previous, scored, card)
            self.assertAlmostEqual(next_bond["resonance_base"], previous["resonance_base"] + 0.02)
            self.assertIn("用户确认状态分数", next_bond["milestones"][0])
            prompt = service.bond_to_prompt(next_bond)
            self.assertIn("长期角色关系档案", prompt)
            self.assertIn("不要提到 Bond", prompt)
            self.assertNotIn("0.32", prompt)

    def test_character_bond_prompt_has_conservative_rubric(self) -> None:
        prompt = LlmClient().character_bond_system_prompt()
        self.assertIn("should_update", prompt)
        self.assertIn("用户只是问技术、规则、实现", prompt)
        self.assertIn("助手单方面建议", prompt)
        self.assertIn("宁可不更新", prompt)

    def test_turn_analysis_prompt_and_parser_merge_postprocessing(self) -> None:
        client = LlmClient()
        prompt = client.turn_analysis_system_prompt()
        self.assertIn("state、bond、memories", prompt)
        self.assertIn("一次性输出 JSON 对象", prompt)
        self.assertIn("宁可少写", prompt)
        parsed = client._parse_turn_analysis_json(
            """
            {
              "state": {
                "mood": "认真听",
                "tone": "放慢一点",
                "distance": "自然熟悉",
                "focus": "解释规则和行为依据",
                "energy": 0.42,
                "resonance_delta": 0.01,
                "behavior": {
                  "pace": "慢一点",
                  "initiative": "少追问",
                  "warmth": "自然",
                  "memory_use": "只用相关记忆",
                  "avoid": "不要说分数"
                },
                "evidence": "用户在讨论实现规则。"
              },
              "bond": {
                "should_update": true,
                "familiarity_stage": "逐渐熟悉",
                "resonance_base_delta": 0.02,
                "trust_notes": "用户认可解释时给行为依据。",
                "boundary_notes": "不要只给分数。",
                "interaction_preferences": "解释规则要说明行为表现。",
                "milestone": "用户明确偏好行为映射。",
                "evidence": "用户表达了长期互动偏好。"
              },
              "memories": [
                {
                  "memory_type": "user_preference",
                  "content": "用户希望解释规则时给出行为依据，不要只给分数。",
                  "confidence": 0.92,
                  "importance": 0.86
                }
              ]
            }
            """
        )
        self.assertIsNotNone(parsed["state"])
        self.assertIsNotNone(parsed["bond"])
        self.assertEqual(len(parsed["memories"]), 1)
        self.assertEqual(parsed["memories"][0]["memory_type"], "user_preference")

    def test_novel_service_falls_back_without_remote_llm(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            storage.add_message(session_id, visitor_id, card.id, "user", "我想把今天这段聊天写成短篇。")
            storage.add_message(session_id, visitor_id, card.id, "assistant", "那我们就慢慢把它折成一页故事。")
            memory_id = storage.add_memory(
                visitor_id,
                session_id,
                card.id,
                "user_preference",
                "用户喜欢温柔克制的叙事风格。",
                0.9,
                None,
                0.8,
            )
            self.assertIsNotNone(memory_id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage))
            response = self.run_async(
                service.generate(
                    FakeLlm(),
                    card,
                    visitor_id,
                    session_id,
                    storage.session_messages(session_id),
                    MemoryService(storage).list_memories(session_id),
                    StoryService(storage).list_items(session_id),
                    NovelGenerateRequest(),
                )
            )
            self.assertIn("林晚栀", response.title)
            self.assertIn("今天这段聊天", response.body)
            self.assertNotIn("如果把这段聊天写成小说", response.body)
            self.assertNotIn("记忆列表", response.body)
            self.assertIn("温柔克制", response.used_memories[0])
            self.assertEqual(response.diagnostics["source"], "mock")

    def test_novel_fallback_uses_requested_controls(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            storage.add_message(session_id, visitor_id, card.id, "user", "我想把今天这段聊天写成短篇。")
            storage.add_message(session_id, visitor_id, card.id, "assistant", "那我们就慢慢把它折成一页故事。")
            storage.add_message(session_id, visitor_id, card.id, "user", "希望像番外一样，语气清冷一点。")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage))
            messages = storage.session_messages(session_id)
            memory_items = MemoryService(storage).list_memories(session_id)
            story_items = StoryService(storage).list_items(session_id)
            user_view = self.run_async(
                service.generate(
                    FakeLlm(),
                    card,
                    visitor_id,
                    session_id,
                    messages,
                    memory_items,
                    story_items,
                    NovelGenerateRequest(
                        form="side_story",
                        perspective="user_view",
                        fidelity="literary",
                        atmosphere="清冷、克制",
                        target_length=1000,
                    ),
                )
            )
            dual_view = self.run_async(
                service.generate(
                    FakeLlm(),
                    card,
                    visitor_id,
                    session_id,
                    messages,
                    memory_items,
                    story_items,
                    NovelGenerateRequest(
                        form="campus_romance",
                        perspective="dual_view",
                        fidelity="faithful",
                        atmosphere="明亮、轻快",
                        target_length=1000,
                    ),
                )
            )
            self.assertIn("清冷、克制", user_view.body)
            self.assertIn("我把那句", user_view.body)
            self.assertIn("番外", user_view.title)
            self.assertIn("明亮、轻快", dual_view.body)
            self.assertIn("校园", dual_view.body)
            self.assertNotEqual(user_view.body, dual_view.body)
            self.assertEqual(user_view.diagnostics["perspective"], "user_view")
            self.assertEqual(dual_view.diagnostics["form"], "campus_romance")

    def test_story_items_can_store_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            story_id = storage.upsert_story_item(
                session_id,
                "open_thread",
                "樱花邀约",
                "樱花可以作为还未发生的校园同行伏笔。",
                "用户提到樱花是否还开放。",
                "explicit",
                "seed",
                ["msg_1"],
            )
            self.assertIsNotNone(story_id)
            items = StoryService(storage).list_items(session_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].label, "樱花邀约")
            self.assertEqual(items[0].source_message_ids, ["msg_1"])

    def test_story_refresh_falls_back_to_two_tags(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "你好啊，樱花还开着吗？")
            storage.add_message(session_id, visitor_id, "lin_wanzhi", "assistant", "应该还在，我们可以慢慢去看看。")
            memory_id = storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "open_thread",
                "用户询问樱花是否还开放并提到可以一起去看。",
                0.8,
                None,
                0.7,
            )
            self.assertIsNotNone(memory_id)
            service = StoryService(storage)
            diagnostics = self.run_async(
                service.refresh(
                    FakeLlm(),
                    session_id,
                    storage.session_messages(session_id),
                    MemoryService(storage).list_memories(session_id),
                )
            )
            items = service.list_items(session_id)
            self.assertGreaterEqual(len(items), 1)
            self.assertLessEqual(len(items), 2)
            self.assertEqual(diagnostics["source"], "fallback")

    def test_novel_project_creates_story_bible_materials_and_chapter(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            msg_id = storage.add_message(session_id, visitor_id, card.id, "user", "我想把樱花作为后续伏笔。")
            storage.add_memory(
                visitor_id,
                session_id,
                card.id,
                "user_preference",
                "用户喜欢温柔克制的长篇叙事。",
                0.9,
                msg_id,
                0.8,
            )
            storage.upsert_story_item(
                session_id,
                "open_thread",
                "樱花伏笔",
                "樱花是还未发生的同行伏笔。",
                "用户提到樱花。",
                "explicit",
                "seed",
                [msg_id],
            )
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                storage.session_messages(session_id),
                MemoryService(storage).list_memories(session_id),
                StoryService(storage).list_items(session_id),
                NovelProjectCreateRequest(title="樱花长篇"),
            )
            self.assertEqual(project.title, "樱花长篇")
            self.assertGreaterEqual(len(project.materials), 2)
            self.assertEqual(len(project.chapters), 1)
            self.assertIn("boundaries", project.story_bible)
            self.assertGreaterEqual(len(project.story_canvas.get("chapters", [])), 4)
            self.assertGreaterEqual(len(project.story_canvas.get("scenes", [])), 4)
            self.assertIn("external_event", project.story_canvas["chapters"][0])
            self.assertIn("trigger_event", project.story_canvas["chapters"][0])
            self.assertIn("immediate_reaction", project.story_canvas["chapters"][0])
            self.assertIn("obstacle_escalation", project.story_canvas["chapters"][0])
            self.assertIn("character_choice", project.story_canvas["chapters"][0])
            self.assertIn("scene_consequence", project.story_canvas["chapters"][0])
            self.assertIn("surface_event", project.story_canvas["scenes"][0])
            self.assertTrue(any(item.category == "foreshadowing" for item in project.materials))

            class CanvasFallbackLlm:
                last_chat_error = None

                def configured(self) -> bool:
                    return False

            rebuilt = self.run_async(service.build_canvas(CanvasFallbackLlm(), project.id))
            self.assertGreaterEqual(len(rebuilt.story_canvas.get("threads", [])), 1)
            self.assertEqual(rebuilt.story_canvas.get("mode"), "story_canvas")
            canvas_chapters = rebuilt.story_canvas.get("chapters", [])
            self.assertGreaterEqual(len(canvas_chapters), 4)
            self.assertEqual(len(rebuilt.chapters), len(canvas_chapters))
            self.assertEqual(rebuilt.chapters[-1].chapter_order, len(canvas_chapters))

    def test_novel_build_canvas_uses_remote_when_configured(self) -> None:
        class CanvasLlm:
            last_chat_error = None
            calls = 0
            timeouts = []

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.calls += 1
                self.timeouts.append(timeout_ms)
                self.response_format = response_format
                return json.dumps({
                    "version": "v1",
                    "mode": "story_canvas",
                    "acts": [
                        {"id": "act_remote", "order": "第一阶段", "title": "远程阶段", "purpose": "远程规划。", "chapter_ids": ["canvas_ch_remote"]}
                    ],
                    "chapters": [
                        {
                            "id": "canvas_ch_remote",
                            "act_id": "act_remote",
                            "chapter_order": "第一章",
                            "title": "第一章 远程画布",
                            "goal": "用远程生成的事件建立开场。",
                            "external_event": "林晚栀在雨天图书馆门口拿错了书。",
                            "trigger_event": "借阅单被雨打湿，书脊上的名字露出来。",
                            "immediate_reaction": "她先护住夹页，再抬头确认对方是否看见。",
                            "obstacle_escalation": "闭馆广播响起，身后排队的人催她离开。",
                            "counterpart_reaction": "对方没有追问，只替她挡住吹来的雨。",
                            "character_choice": "她没有立刻走，而是把拿错的书递回去。",
                            "scene_consequence": "两人因此有了下一次见面的理由。",
                            "relationship_shift": "从陌生到记住一次小失误。",
                            "ending_hook": "她发现借阅单背面多了一行提醒。",
                            "target_length": "约1800字",
                            "status": "planned",
                            "emotion_curve": "慌乱 -> 被接住 -> 留下钩子",
                            "conflict_level": "中等 3",
                            "scene_ids": ["scene_remote"],
                        }
                    ],
                    "scenes": [
                        {
                            "id": "scene_remote",
                            "chapter_id": "canvas_ch_remote",
                            "scene_order": "第1场",
                            "current_scene": "雨天图书馆门口。",
                            "pov": "第三人称限知。",
                            "present_characters": "林晚栀、对方",
                            "surface_event": "拿错书和借阅单被雨打湿。",
                            "character_desire": "她想把尴尬处理得自然一点。",
                            "tension": "闭馆和排队让她没有时间解释。",
                            "required_facts": [],
                            "forbidden_progress": ["不突然表白。"],
                            "ending_beat": "借阅单背面出现提醒。",
                            "linked_material_ids": [],
                        }
                    ],
                    "threads": [
                        {"id": "thread_remote", "kind": "foreshadowing", "label": "借阅单提醒", "setup_chapter_id": "canvas_ch_remote", "payoff_chapter_id": "canvas_ch_remote", "status": "seed", "notes": "提醒下次带伞。"}
                    ],
                    "quality_rules": ["正文必须从场景卡生成。"],
                    "diagnostics": {"source": "remote"},
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                [],
                [],
                [],
                NovelProjectCreateRequest(),
            )
            llm = CanvasLlm()
            rebuilt = self.run_async(service.build_canvas(llm, project.id))
            self.assertEqual(llm.calls, 1)
            self.assertIsNotNone(llm.timeouts[0])
            self.assertGreaterEqual(llm.timeouts[0], 120000)
            self.assertEqual(llm.response_format, {"type": "json_object"})
            self.assertEqual(rebuilt.story_canvas["diagnostics"]["source"], "remote")
            self.assertEqual(rebuilt.story_canvas["chapters"][0]["title"], "第1章 远程画布")
            self.assertEqual(rebuilt.story_canvas["chapters"][0]["target_length"], 1800)
            self.assertEqual(rebuilt.story_canvas["chapters"][0]["conflict_level"], 3)
            self.assertEqual(rebuilt.chapters[0].title, "第1章 远程画布")

    def test_novel_canvas_parser_derives_scenes_when_remote_omits_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            fallback = service._default_story_canvas("测试长篇", "校园日常长篇", "温柔", "林晚栀", {}, [])
            text = json.dumps({
                "version": 1,
                "mode": "story_canvas",
                "acts": ["初识"],
                "chapters": [{
                    "id": "ch_1",
                    "act_id": "act_1",
                    "chapter_order": 1,
                    "title": "第一章 风起",
                    "goal": "用外部事件打开关系",
                    "external_event": "书页被风吹散。",
                    "trigger_event": "傍晚起风。",
                    "immediate_reaction": "她先去按住便签。",
                    "obstacle_escalation": "门口人流催促。",
                    "counterpart_reaction": "对方递回书。",
                    "character_choice": "她停下来问名字。",
                    "scene_consequence": "彼此记住。",
                    "relationship_shift": "陌生到记住名字。",
                    "ending_hook": "便签背面多了一行字。",
                    "target_length": 1800,
                    "status": "planned",
                    "emotion_curve": "慌乱到安定",
                    "conflict_level": 3,
                    "scene_ids": ["sc_1"],
                }],
                "threads": [],
                "quality_rules": [],
                "diagnostics": {"source": "remote"},
            }, ensure_ascii=False)
            canvas = service._parse_canvas_response(text, fallback)
            self.assertEqual(canvas["diagnostics"]["source"], "remote")
            self.assertEqual(canvas["chapters"][0]["chapter_order"], 1)
            self.assertEqual(canvas["chapters"][0]["title"], "第1章 风起")
            self.assertEqual(canvas["diagnostics"]["scene_source"], "derived_from_chapters")
            self.assertEqual(canvas["scenes"][0]["id"], "sc_1")
            self.assertEqual(canvas["scenes"][0]["surface_event"], "傍晚起风。")

    def test_novel_canvas_parser_repairs_common_llm_json_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            fallback = service._default_story_canvas("测试长篇", "校园日常长篇", "温柔", "林晚栀", {}, [])
            text = """
            ```json
            {
              version: "1.0",
              mode: "story_canvas",
              acts: [{id: "act_1", order: "第一阶段", title: "初识", purpose: "建立开场", chapter_ids: ["ch_1",],},],
              chapters: [{
                id: "ch_1",
                act_id: "act_1",
                chapter_order: "第一章",
                title: "第一章 风起",
                goal: "用外部事件打开关系",
                external_event: "书页被风吹散。",
                trigger_event: "傍晚起风。",
                immediate_reaction: "她先去按住便签。",
                obstacle_escalation: "门口人流催促。",
                counterpart_reaction: "对方递回书。",
                character_choice: "她停下来问名字。",
                scene_consequence: "彼此记住。",
                relationship_shift: "陌生到记住名字。",
                ending_hook: "便签背面多了一行字。",
                target_length: "约1800字",
                status: "planned",
                emotion_curve: "慌乱到安定",
                conflict_level: "中等3",
                scene_ids: ["sc_1",],
              },],
              scenes: [{
                id: "sc_1",
                chapter_id: "ch_1",
                scene_order: "第1场",
                current_scene: "图书馆门口",
                pov: "第三人称限知",
                present_characters: "林晚栀、对方",
                surface_event: "书页散落，对方帮忙。",
                character_desire: "她想自然一点。",
                tension: "便签不能被看清。",
                required_facts: [],
                forbidden_progress: ["不表白",],
                ending_beat: "她记住对方名字。",
                linked_material_ids: [],
              },],
              threads: [],
              quality_rules: ["正文必须有事件",],
              diagnostics: {source: "remote",},
            }
            ```
            """
            canvas = service._parse_canvas_response(text, fallback)
            self.assertEqual(canvas["diagnostics"]["source"], "remote")
            self.assertEqual(canvas["chapters"][0]["chapter_order"], 1)
            self.assertEqual(canvas["chapters"][0]["title"], "第1章 风起")
            self.assertEqual(canvas["chapters"][0]["target_length"], 1800)
            self.assertEqual(canvas["chapters"][0]["conflict_level"], 3)
            self.assertEqual(canvas["scenes"][0]["scene_order"], 1)

    def test_novel_versions_dedupe_identical_content(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                [],
                [],
                [],
                NovelProjectCreateRequest(),
            )
            chapter_id = project.chapters[0].id
            first = storage.add_novel_version(project.id, chapter_id, "draft", "第一章", "同一版正文。", "同一版摘要。", "mock")
            second = storage.add_novel_version(project.id, chapter_id, "draft", "第一章", "同一版正文。", "同一版摘要。", "restore")
            self.assertEqual(first, second)
            self.assertEqual(len(storage.list_novel_versions(chapter_id)), 1)
            third = storage.add_novel_version(project.id, chapter_id, "draft", "第一章", "另一版正文。", "同一版摘要。", "manual")
            self.assertNotEqual(first, third)
            self.assertEqual(len(storage.list_novel_versions(chapter_id)), 2)

    def test_novel_chapter_generation_versions_and_restore(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            storage.add_message(session_id, visitor_id, card.id, "user", "今晚想写第一章。")
            storage.add_message(session_id, visitor_id, card.id, "assistant", "那就从一个安静场景开始。")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                storage.session_messages(session_id),
                MemoryService(storage).list_memories(session_id),
                StoryService(storage).list_items(session_id),
                NovelProjectCreateRequest(),
            )
            generated, chapter = self.run_async(
                service.generate_chapter(
                    FakeLlm(),
                    project.id,
                    project.chapters[0].id,
                    NovelChapterGenerateRequest().instruction,
                    1000,
                )
            )
            self.assertEqual(generated.id, project.id)
            self.assertNotIn("伏笔", chapter.body)
            self.assertNotIn("这一章", chapter.body)
            self.assertNotIn("素材", chapter.body)
            self.assertNotIn("校园日常长篇", chapter.body)
            self.assertNotIn("两人还不熟", chapter.body)
            self.assertNotIn("从路人变成", chapter.body)
            self.assertNotIn("听见自己的声音", chapter.body)
            self.assertIn("傍晚", chapter.body)
            self.assertIn("“", chapter.body)
            self.assertGreaterEqual(len(chapter.body.replace("\n", "").replace(" ", "")), 700)
            self.assertIn("surface_event", chapter.scene_card)
            self.assertIn("character_desire", chapter.scene_card)
            self.assertIn("tension", chapter.scene_card)
            self.assertIn("ending_beat", chapter.scene_card)
            self.assertTrue(chapter.scene_card["surface_event"])
            self.assertTrue(chapter.scene_card["ending_beat"])
            versions = storage.list_novel_versions(chapter.id)
            self.assertGreaterEqual(len(versions), 1)
            storage.update_novel_chapter(chapter.id, {"body": "手动改写版本。", "summary": "手动摘要。"}, "manual")
            version_count_before_restore = len(storage.list_novel_versions(chapter.id))
            self.assertTrue(storage.restore_novel_version(versions[-1]["id"]))
            restored = storage.get_novel_chapter(chapter.id)
            self.assertIsNotNone(restored)
            self.assertNotIn("伏笔", restored["body"])
            self.assertIn("傍晚", restored["body"])
            self.assertEqual(len(storage.list_novel_versions(chapter.id)), version_count_before_restore)

    def test_novel_chapter_ignores_corrupted_question_mark_instruction(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                [],
                [],
                [],
                NovelProjectCreateRequest(),
            )
            chapter_id = project.chapters[0].id
            _, chapter = self.run_async(
                service.generate_chapter(
                    FakeLlm(),
                    project.id,
                    chapter_id,
                    "?????,?????????,?????????",
                    1000,
                )
            )
            self.assertNotIn("?", chapter.goal)
            self.assertIn("第一印象", chapter.goal)

    def test_novel_chapter_rejects_internal_label_leakage(self) -> None:
        class LeakyLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                return json.dumps({
                    "title": "泄露草稿",
                    "summary": "错误草稿。",
                    "body": "这一章把 recent_emotion、stable_user_info、user_preference 放在场景边缘。",
                    "source_material_ids": ["mat_bad1234"],
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            msg_id = storage.add_message(session_id, visitor_id, card.id, "user", "我喜欢雨天图书馆。")
            storage.add_memory(
                visitor_id,
                session_id,
                card.id,
                "user_preference",
                "用户喜欢雨天图书馆。",
                0.9,
                msg_id,
                0.8,
            )
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                storage.session_messages(session_id),
                MemoryService(storage).list_memories(session_id),
                [],
                NovelProjectCreateRequest(),
            )
            llm = LeakyLlm()
            _, chapter = self.run_async(
                service.generate_chapter(
                    llm,
                    project.id,
                    project.chapters[0].id,
                    "写出一个雨天图书馆里的安静开场。",
                    1000,
                )
            )
            self.assertEqual(llm.last_chat_error, "ValueError")
            self.assertNotIn("recent_emotion", chapter.body)
            self.assertNotIn("stable_user_info", chapter.body)
            self.assertNotIn("user_preference", chapter.body)
            self.assertNotIn("这一章", chapter.body)
            self.assertIn("雨天图书馆", chapter.body)

    def test_novel_continuity_flags_internal_terms_and_seed_risk(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                [],
                [],
                [],
                NovelProjectCreateRequest(),
            )
            chapter_id = project.chapters[0].id
            seed = "樱花是还未发生的同行伏笔。"
            storage.update_novel_project(project.id, {"story_bible": {"unresolved_threads": [seed], "boundaries": ["不要突然承诺。"]}})
            storage.update_novel_chapter(chapter_id, {"body": f"prompt 泄露。recent_emotion。{seed} 终于已经发生。"}, "manual")
            report = service.check_continuity(project.id, chapter_id)
            labels = {issue.label for issue in report.issues}
            self.assertIn("小说质检未通过", labels)
            self.assertIn("伏笔状态需人工确认", labels)

    def run_async(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
