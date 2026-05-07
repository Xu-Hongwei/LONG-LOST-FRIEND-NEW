from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.composer import ComposeInput, ContextComposer
from campus_lite.llm import LlmClient
from campus_lite.memory import MemoryService
from campus_lite.schemas import MemoryItem
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage


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


if __name__ == "__main__":
    unittest.main()
