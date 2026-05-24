from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from campus_lite.api import create_app
from campus_lite.bond import CharacterBondService
from campus_lite.characters import CharacterStore
from campus_lite.composer import ComposeInput, ContextComposer
from campus_lite.features.chat.service import ChatService
from campus_lite.features.chat.time_awareness import build_time_awareness
from campus_lite.llm import LlmClient
from campus_lite.memory import MemoryService
from campus_lite.novel import NovelService
from campus_lite.schemas import CharacterCard, NovelChapterGenerateRequest, NovelGenerateRequest, NovelProjectCreateRequest, SendMessageRequest
from campus_lite.schemas import MemoryItem
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage, StoragePayloadError
from campus_lite.story import StoryService


class CampusLiteCoreTest(unittest.TestCase):
    def test_llm_router_provider_takes_priority_for_chat_and_optional_embeddings(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_ROUTER_API_KEY": "router-key",
                "LLM_ROUTER_BASE_URL": "http://router.local/v1",
                "LLM_ROUTER_TIMEOUT_MS": "34567",
                "LLM_ROUTER_EMBEDDING_MODEL": "router-embedding",
                "DASHSCOPE_API_KEY": "dashscope-key",
                "DASHSCOPE_MODEL": "dashscope-chat",
            },
            clear=True,
        ):
            client = LlmClient()

        self.assertEqual(client.provider_name(), "router")
        self.assertEqual(client.provider["model"], "auto")
        self.assertEqual(client.provider["timeout_ms"], 34567)
        self.assertEqual(client.embedding_provider_name(), "router:router-embedding")

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

    def test_context_slots_can_include_time_awareness(self) -> None:
        card = CharacterStore().list_cards()[0]
        slots = ContextComposer().compose(
            ComposeInput(
                character=card,
                recent_messages=[],
                user_message="hello again",
                memories=[],
                recent_summary="",
                time_awareness="距离上次对话大约过了3天。角色可以自然感受到重新开口。",
            )
        )

        slot = next(item for item in slots if item.key == "session.time_awareness")
        self.assertTrue(slot.included)
        self.assertIn("3天", slot.content)

    def test_time_awareness_only_appears_after_meaningful_gap(self) -> None:
        now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            build_time_awareness((now - timedelta(minutes=12)).strftime("%Y-%m-%d %H:%M:%S"), now),
            "",
        )

        prompt = build_time_awareness((now - timedelta(days=3, hours=2)).strftime("%Y-%m-%d %H:%M:%S"), now)
        self.assertIn("current_time:", prompt)
        self.assertIn("last_message_at:", prompt)
        self.assertIn("elapsed_since_last_message:", prompt)
        self.assertIn("elapsed_bucket: days_later", prompt)
        self.assertIn("3天", prompt)
        self.assertIn("不是台词模板", prompt)
        self.assertIn("不要机械复述字段或时间戳", prompt)
        self.assertNotIn("回复第一句", prompt)

    def test_chat_send_injects_time_awareness_from_previous_message(self) -> None:
        class FakeLlm:
            last_chat_error = None
            last_embedding_error = None

            async def embed_texts(self, texts):
                return []

            def embedding_provider_name(self):
                return None

            async def chat_complete(self, messages):
                return "我在。隔了一阵，也还是先听你说。"

            def mock_reply(self, character, user_text, memories):
                return "mock"

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            previous_id = storage.add_message(session_id, visitor_id, card.id, "assistant", "上次聊到这里。")
            with storage.connect() as conn:
                conn.execute(
                    "UPDATE messages SET created_at = datetime('now', '-3 days') WHERE id = ?",
                    (previous_id,),
                )
            service = ChatService(
                storage=storage,
                characters=CharacterStore(),
                memory=MemoryService(storage),
                story=StoryService(storage),
                character_state=CharacterStateService(storage),
                character_bond=CharacterBondService(storage),
                composer=ContextComposer(),
                llm=FakeLlm(),
            )

            self.run_async(service.send_message(
                SendMessageRequest(visitor_id=visitor_id, session_id=session_id, message="我回来了。"),
                BackgroundTasks(),
            ))
            session = storage.get_session(session_id)
            slots = json.loads(session["last_prompt_slots"])
            time_slot = next(item for item in slots if item["key"] == "session.time_awareness")

            self.assertTrue(time_slot["included"])
            self.assertIn("3天", time_slot["content"])

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

    def test_custom_character_can_open_chat_and_seed_novel_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=LlmClient())
            client = TestClient(app)
            visitor_id = "custom-character-tester"

            created = client.post("/api/characters", json={
                "visitor_id": visitor_id,
                "name": "Mira",
                "archetype": "quiet strategist",
                "tagline": "notices small choices before speaking",
                "bio": "A user-created campus companion.",
                "speech_style": "calm, concise, observant",
                "relationship_pace": "slow and respectful",
                "opening_line": "I am here. What should we look at first?",
                "personality": "Patient, careful, and quietly warm.",
                "boundaries": ["keep replies safe", "do not force intimacy"],
            })
            self.assertEqual(created.status_code, 200)
            character_id = created.json()["id"]

            listed = client.get(f"/api/characters?visitor_id={visitor_id}")
            self.assertEqual(listed.status_code, 200)
            self.assertTrue(any(item["id"] == character_id and item["origin"] == "custom" for item in listed.json()))

            session = client.post("/api/sessions", json={
                "visitor_id": visitor_id,
                "character_id": character_id,
            })
            self.assertEqual(session.status_code, 200)
            self.assertEqual(session.json()["character"]["name"], "Mira")
            session_id = session.json()["session_id"]
            project = client.post(f"/api/sessions/{session_id}/novel/projects", json={
                "title": "Mira Draft",
                "genre": "campus",
                "tone": "quiet",
            })
            self.assertEqual(project.status_code, 200)
            self.assertEqual(project.json()["character_id"], character_id)

            deleted = client.delete(f"/api/characters/{character_id}?visitor_id={visitor_id}")
            self.assertEqual(deleted.status_code, 200)

    def test_character_draft_endpoint_returns_clean_json_card(self) -> None:
        class FakeDraftLlm(LlmClient):
            provider = {"model": "fake", "api_key": "fake", "base_url": "http://fake", "timeout_ms": 1000}
            embedding_provider = None
            last_analysis_error = None

            async def generate_character_draft(self, prompt, template=None):
                return self._clean_character_draft({
                    "name": "Nia",
                    "archetype": "calm maker",
                    "tagline": "builds quiet little rituals",
                    "gender": "female",
                    "bio": "A fictional campus companion.",
                    "speech_style": "soft, brief, concrete",
                    "opening_line": "I kept a seat for you.",
                    "interaction_policy": {"initiative_level": 0.35, "action_density": "low"},
                    "voice": {"sample_lines": ["We can start small."]},
                    "visual": {"accent": "#88aacc"},
                })

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=FakeDraftLlm())
            client = TestClient(app)

            response = client.post("/api/characters/draft", json={
                "visitor_id": "draft-tester",
                "prompt": "quiet ritual maker",
            })

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["character"]["name"], "Nia")
            self.assertIn("interaction_policy", payload["character"])
            self.assertEqual(payload["diagnostics"]["source"], "remote")

    def test_custom_character_and_novel_project_draft_persist_through_api(self) -> None:
        class FakeNovelDraftLlm(LlmClient):
            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, **kwargs):
                return json.dumps({
                    "title": "雨后图书馆计划",
                    "genre": "慢热校园日常长篇",
                    "tone": "温柔、克制、低戏剧化、对白自然",
                    "protagonist": "Mira",
                    "worldview": "雨后校园、图书馆和社团活动构成主要生活场域。",
                    "relationship_setup": "两人从熟悉但仍谨慎确认边界的状态开始靠近。",
                    "outline": ["雨后重逢", "晚餐约定", "误会与确认", "共同完成社团任务", "回收图书馆伏笔"],
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=FakeNovelDraftLlm())
            client = TestClient(app)
            visitor_id = "novel-project-draft-tester"

            character = client.post("/api/characters", json={
                "visitor_id": visitor_id,
                "name": "Mira",
                "archetype": "quiet strategist",
                "tagline": "notices small choices before speaking",
                "bio": "A user-created campus companion.",
                "speech_style": "calm, concise, observant",
                "relationship_pace": "slow and respectful",
                "opening_line": "I am here. What should we look at first?",
            })
            self.assertEqual(character.status_code, 200)
            character_id = character.json()["id"]
            self.assertEqual(storage.get_character_card(character_id, visitor_id)["origin"], "custom")

            session = client.post("/api/sessions", json={"visitor_id": visitor_id, "character_id": character_id})
            self.assertEqual(session.status_code, 200)
            session_id = session.json()["session_id"]

            draft = client.post(f"/api/sessions/{session_id}/novel/project-draft", json={
                "prompt": "雨后校园慢热日常，从图书馆和晚餐约定开始。",
                "current": {"genre": "校园日常长篇", "tone": "温柔、克制、日常"},
            })
            self.assertEqual(draft.status_code, 200)
            draft_project = draft.json()["project"]
            self.assertEqual(draft_project["title"], "雨后图书馆计划")
            self.assertEqual(draft_project["genre"], "慢热校园日常长篇")
            self.assertIn("晚餐约定", draft_project["outline"])

            created = client.post(f"/api/sessions/{session_id}/novel/projects", json=draft_project)
            self.assertEqual(created.status_code, 200)
            project = created.json()
            self.assertEqual(project["character_id"], character_id)
            self.assertEqual(project["title"], "雨后图书馆计划")
            self.assertEqual(project["genre"], "慢热校园日常长篇")
            self.assertEqual(project["tone"], "温柔、克制、低戏剧化、对白自然")
            self.assertIn("雨后校园", project["worldview"])
            self.assertIn("确认边界", project["relationship_setup"])

            deleted = client.delete(f"/api/novel/projects/{project['id']}")
            self.assertEqual(deleted.status_code, 200)
            listed_projects = client.get(f"/api/sessions/{session_id}/novel/projects")
            self.assertEqual(listed_projects.status_code, 200)
            self.assertFalse(any(item["id"] == project["id"] for item in listed_projects.json()))

    def test_novel_project_draft_genre_hint_overrides_stale_current_draft(self) -> None:
        class FakeStaleDraftLlm(LlmClient):
            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, **kwargs):
                return json.dumps({
                    "title": "湖畔微风与温柔相伴",
                    "genre": "校园日常长篇",
                    "tone": "轻柔舒缓，以细腻情感和温和互动为主",
                    "protagonist": "林晚栀",
                    "worldview": "故事发生在校园和湖边。",
                    "relationship_setup": "普通同学逐渐成为好友。",
                    "outline": "1. 湖边相遇\n2. 图书馆约定",
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=FakeStaleDraftLlm())
            client = TestClient(app)
            visitor_id = "novel-genre-hint-tester"
            character_id = client.get("/api/characters", params={"visitor_id": visitor_id}).json()[0]["id"]
            session = client.post("/api/sessions", json={"visitor_id": visitor_id, "character_id": character_id})
            self.assertEqual(session.status_code, 200)

            response = client.post(f"/api/sessions/{session.json()['session_id']}/novel/project-draft", json={
                "prompt": "修仙武侠，少年剑修和冷淡医修被迫同行。",
                "current": {
                    "title": "湖畔旧草稿",
                    "genre": "校园日常长篇",
                    "tone": "温柔、克制、日常",
                },
            })

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["project"]["genre"], "修仙武侠长篇")
            self.assertEqual(payload["diagnostics"]["genre_hint"], "修仙武侠长篇")

    def test_novel_project_draft_collapses_soft_wrapped_outline(self) -> None:
        class FakeWrappedDraftLlm(LlmClient):
            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, **kwargs):
                return json.dumps({
                    "title": "Soft Wrap Plan",
                    "genre": "campus mystery",
                    "tone": "quiet suspense",
                    "protagonist": "Mira",
                    "worldview": "A school and a lake.",
                    "relationship_setup": "Two classmates investigate carefully.",
                    "outline": "Mira finds a strange note before class.\nShe follows it to the lakeside after school.\nThe second clue changes what she thought she knew.",
                })

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=FakeWrappedDraftLlm())
            client = TestClient(app)
            visitor_id = "novel-soft-wrap-tester"
            character_id = client.get("/api/characters", params={"visitor_id": visitor_id}).json()[0]["id"]
            session = client.post("/api/sessions", json={"visitor_id": visitor_id, "character_id": character_id})
            self.assertEqual(session.status_code, 200)

            response = client.post(f"/api/sessions/{session.json()['session_id']}/novel/project-draft", json={
                "prompt": "campus mystery about a lake clue",
            })

            self.assertEqual(response.status_code, 200)
            outline = response.json()["project"]["outline"]
            self.assertNotIn("\n", outline)
            self.assertIn("before class.She follows", outline)

    def test_character_draft_parser_accepts_textual_initiative_and_rich_examples(self) -> None:
        client = LlmClient()

        parsed = client._clean_character_draft({
            "name": "Nia",
            "archetype": "calm maker",
            "interaction_policy": {"initiative_level": "偏低，慢热", "action_density": "low"},
            "voice": {
                "sample_lines": [
                    "We can start small.",
                    "I will not rush you.",
                    "I remember the quiet parts.",
                    "One step is enough.",
                ],
            },
            "mes_example": "User: hello\nNia: We can start small.",
        })

        self.assertLess(parsed["interaction_policy"]["initiative_level"], 0.5)
        self.assertGreaterEqual(len(parsed["voice"]["sample_lines"]), 4)
        self.assertIn("Nia", parsed["mes_example"])

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

    def test_memory_recall_carries_source_message_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            message_id = storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "quiet library yesterday")
            with storage.connect() as conn:
                conn.execute(
                    "UPDATE messages SET created_at = ? WHERE id = ?",
                    ("2026-05-22 08:00:00", message_id),
                )
            storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "user_preference",
                "user likes quiet library spaces",
                0.9,
                message_id,
                0.8,
            )

            recalled = MemoryService(storage).recall(session_id, "quiet library")

            self.assertTrue(recalled)
            self.assertEqual(recalled[0].source_created_at, "2026-05-22 08:00:00")

    def test_memory_recall_source_time_falls_back_to_memory_created_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "user_preference",
                "user likes green tea",
                0.9,
                None,
                0.8,
            )

            recalled = MemoryService(storage).recall(session_id, "green tea")

            self.assertTrue(recalled)
            self.assertEqual(recalled[0].source_created_at, recalled[0].created_at)

    def test_memory_recall_prompt_adds_relative_time_label(self) -> None:
        composer = ContextComposer()
        now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
        memory = MemoryItem(
            id="mem_time",
            memory_type="open_thread",
            memory_scope="session",
            content="user wanted to continue the lakeside walk topic",
            confidence=0.9,
            importance=0.8,
            source_message_id="msg_1",
            source_created_at="2026-05-22 08:00:00",
            created_at="2026-05-23 08:00:00",
            updated_at="2026-05-23 08:00:00",
        )

        self.assertEqual(composer._memory_time_label(memory, now), "昨天提到")
        composer._memory_time_label = lambda item: "昨天提到"
        prompt = composer._memory_recall([memory])

        self.assertIn("昨天提到", prompt)
        self.assertIn("不要机械复述时间戳", prompt)

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
            self.assertFalse(any("运动场" in item.content for item in recalled))

    def test_memory_hybrid_rank_normalizes_keyword_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            memory = MemoryService(storage)
            high_quality = MemoryItem(
                id="mem_high",
                memory_type="user_preference",
                memory_scope="global",
                content="user likes quiet library spaces",
                confidence=1.0,
                importance=1.0,
                source_message_id=None,
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
            low_quality = MemoryItem(
                id="mem_low",
                memory_type="open_thread",
                memory_scope="session",
                content="quiet library meetup",
                confidence=0.1,
                importance=0.1,
                source_message_id=None,
                created_at="2026-01-01",
                updated_at="2026-01-02",
            )

            ranked = memory._rank_hybrid([low_quality, high_quality], "quiet library meetup")

            self.assertEqual(ranked[0].id, "mem_high")

    def test_text_recall_does_not_fallback_to_unrelated_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            msg_id = storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "我喜欢听歌")
            storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "user_preference",
                "用户喜欢听歌和旅行。",
                0.9,
                msg_id,
                0.8,
            )
            storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "open_thread",
                "询问对方是否吃过晚饭并提到自己还没吃。",
                0.9,
                None,
                0.8,
            )
            storage.add_memory(
                visitor_id,
                session_id,
                "lin_wanzhi",
                "open_thread",
                "询问樱花是否还在开放并提议一同去看樱花。",
                0.9,
                None,
                0.8,
            )

            memory = MemoryService(storage)
            dinner = memory.recall(session_id, "晚饭吃了吗")
            self.assertTrue(any("晚饭" in item.content for item in dinner))
            self.assertFalse(any("樱花" in item.content for item in dinner if item.memory_type == "open_thread"))

            unrelated = memory.recall(session_id, "火星基地怎么建设")
            self.assertFalse(unrelated)

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

    def test_character_bond_event_reducer_and_prompt_hides_scores(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.ensure_bond(visitor_id, card.id, card)
            next_bond, diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-1"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "trust_signal",
                        "evidence_grade": "explicit",
                        "evidence_text": "我信你会认真解释",
                    },
                    {
                        "event_type": "preference_confirmed",
                        "evidence_grade": "strong",
                        "evidence_text": "解释规则时给我行为依据",
                    },
                ],
                evidence_context="我信你会认真解释，解释规则时给我行为依据。",
            )
            self.assertAlmostEqual(next_bond["trust_level"], previous["trust_level"] + 0.05)
            self.assertAlmostEqual(next_bond["closeness_level"], previous["closeness_level"] + 0.02)
            self.assertEqual(next_bond["condition_code"], "warming")
            self.assertEqual(next_bond["relationship_condition"], "升温中")
            self.assertEqual(diagnostics["accepted_events_count"], 2)
            self.assertTrue(diagnostics["condition_changed"])
            self.assertEqual(len(storage.list_relationship_events(visitor_id, card.id)), 2)
            prompt = service.bond_to_prompt(next_bond)
            self.assertIn("长期角色关系档案", prompt)
            self.assertIn("不要提到 Bond", prompt)
            self.assertNotIn("0.35", prompt)

    def test_character_bond_prompt_extracts_events_only(self) -> None:
        prompt = LlmClient().character_bond_system_prompt()
        self.assertIn("event_type", prompt)
        self.assertIn("evidence_grade", prompt)
        self.assertIn("用户只是问技术、规则、实现", prompt)
        self.assertIn("不要输出任何评分", prompt)
        self.assertNotIn("resonance_base_delta", prompt)

    def test_relationship_event_evidence_grades_and_parser_reject_scoring(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        client = LlmClient()
        self.assertEqual(client._parse_relationship_events_json("[{broken json}]"), [])
        structured = client._parse_relationship_events_json(
            """
            {
              "events": [{
                "event_type": "trust_signal",
                "evidence_grade": "explicit",
                "evidence_text": "鎴戜俊浠讳綘"
              }]
            }
            """
        )
        self.assertEqual(structured[0]["event_type"], "trust_signal")
        parsed = client._parse_relationship_events_json(
            """
            [
              {
                "event_type": "trust_signal",
                "evidence_grade": "explicit",
                "evidence_text": "我信你"
              },
              {
                "event_type": "shared_context",
                "evidence_grade": "strong",
                "evidence_text": "还是去湖边走走",
                "confidence": 0.95
              },
              {
                "event_type": "shared_context",
                "evidence_grade": "contextual",
                "evidence_text": "刚才那个约定"
              }
            ]
            """
        )
        self.assertEqual([item["event_type"] for item in parsed], ["trust_signal", "shared_context"])
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.ensure_bond(visitor_id, card.id, card)
            next_bond, diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-2"],
                character=card,
                previous=previous,
                extracted=parsed,
                evidence_context="我信你。刚才那个约定我们再看看。",
            )
            self.assertAlmostEqual(next_bond["trust_level"], previous["trust_level"] + 0.04)
            self.assertEqual(diagnostics["accepted_events_count"], 1)
            self.assertEqual(diagnostics["rejected_event_reasons"]["grade_contextual"], 1)

    def test_relationship_event_extraction_uses_structured_json_contract(self) -> None:
        class StructuredRelationshipLlm(LlmClient):
            response_format = None
            temperature = None
            system_messages: list[str] = []

            async def chat_complete(self, messages, timeout_ms=None, response_format=None, temperature=None):
                self.response_format = response_format
                self.temperature = temperature
                self.system_messages = [
                    str(item.get("content") or "")
                    for item in messages
                    if item.get("role") == "system"
                ]
                return json.dumps({
                    "events": [{
                        "event_type": "trust_signal",
                        "evidence_grade": "explicit",
                        "evidence_text": "鎴戜俊浠讳綘",
                    }],
                }, ensure_ascii=False)

        llm = StructuredRelationshipLlm()
        llm.provider = {
            "name": "fake",
            "api_key": "fake",
            "base_url": "http://fake.local/v1",
            "model": "fake-model",
            "timeout_ms": 1000,
        }
        card = CharacterStore().get("lin_wanzhi")
        extracted = self.run_async(llm.extract_relationship_events(
            card,
            {},
            {},
            [],
            "鎴戜俊浠讳綘銆?",
            "鎴戜細璁ょ湡鍥炲簲銆?",
            [],
        ))

        self.assertEqual(extracted[0]["event_type"], "trust_signal")
        self.assertEqual(llm.response_format, {"type": "json_object"})
        self.assertEqual(llm.temperature, 0.2)
        self.assertTrue(any("Structured output contract" in item for item in llm.system_messages))
        combined_prompt = "\n".join(llm.system_messages)
        self.assertIn("exact contiguous substring", combined_prompt)
        self.assertIn("用户表示", combined_prompt)
        self.assertIn("Do not summarize", combined_prompt)

    def test_character_bond_stage_freeze_and_repair(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.normalize_bond({
                "stage_code": "familiar",
                "trust_level": 0.56,
                "closeness_level": 0.38,
                "boundary_safety": 0.67,
            }, card)
            frozen_bond, frozen_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-3"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "boundary_violation",
                        "evidence_grade": "explicit",
                        "evidence_text": "你刚才越界了",
                    }
                ],
                evidence_context="你刚才越界了。",
            )
            self.assertEqual(frozen_bond["stage_code"], "familiar")
            self.assertEqual(frozen_bond["condition_code"], "strained")
            self.assertTrue(frozen_diagnostics["progression_frozen"])
            repaired_bond, repaired_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-4"],
                character=card,
                previous=frozen_bond,
                extracted=[
                    {
                        "event_type": "repair",
                        "evidence_grade": "explicit",
                        "evidence_text": "这样解释我能接受",
                    },
                    {
                        "event_type": "trust_signal",
                        "evidence_grade": "explicit",
                        "evidence_text": "我还是愿意信你",
                    },
                ],
                evidence_context="这样解释我能接受，我还是愿意信你。",
            )
            self.assertEqual(repaired_bond["stage_code"], "trusted")
            self.assertEqual(repaired_bond["condition_code"], "repairing")
            self.assertFalse(repaired_diagnostics["progression_frozen"])

    def test_character_bond_stage_thresholds_and_turn_caps(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            service = CharacterBondService(Storage(Path(tmp) / "test.db"))
            accepted = [
                {
                    "event_type": "shared_context",
                    "evidence_grade": "explicit",
                    "evidence_text": "我们上次也聊过这里",
                    "source_message_ids": ["message-a"],
                    "accepted": True,
                },
                {
                    "event_type": "emotional_disclosure",
                    "evidence_grade": "strong",
                    "evidence_text": "这件事让我有点难受",
                    "source_message_ids": ["message-a"],
                    "accepted": True,
                },
            ]
            familiar_bond, _, _ = service.apply_events(
                service.normalize_bond({
                    "stage_code": "initial",
                    "trust_level": 0.37,
                    "closeness_level": 0.25,
                    "boundary_safety": 0.60,
                }, card),
                accepted,
                [],
                service._reduce_delta(accepted),
                card,
            )
            self.assertEqual(familiar_bond["stage_code"], "familiar")

            close_events = [
                {
                    "event_type": "boundary_respected",
                    "evidence_grade": "explicit",
                    "evidence_text": "你这样停一下我会舒服很多",
                    "source_message_ids": ["message-c"],
                    "accepted": True,
                },
                {
                    "event_type": "shared_context",
                    "evidence_grade": "strong",
                    "evidence_text": "那就按我们的老约定来",
                    "source_message_ids": ["message-c"],
                    "accepted": True,
                },
            ]
            close_bond, _, _ = service.apply_events(
                service.normalize_bond({
                    "stage_code": "trusted",
                    "trust_level": 0.67,
                    "closeness_level": 0.59,
                    "boundary_safety": 0.67,
                }, card),
                close_events,
                [
                    {
                        "event_type": "trust_signal",
                        "source_message_ids": ["message-a"],
                        "accepted": True,
                    },
                    {
                        "event_type": "emotional_disclosure",
                        "source_message_ids": ["message-b"],
                        "accepted": True,
                    },
                ],
                service._reduce_delta(close_events),
                card,
            )
            self.assertEqual(close_bond["stage_code"], "close")

            cap_delta = service._reduce_delta([
                {"event_type": "emotional_disclosure"},
                {"event_type": "emotional_disclosure"},
                {"event_type": "trust_signal"},
            ])
            self.assertEqual(cap_delta["trust_level"], 0.05)
            self.assertEqual(cap_delta["closeness_level"], 0.05)

    def test_character_bond_prefers_one_event_for_duplicate_evidence(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.ensure_bond(visitor_id, card.id, card)
            next_bond, diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-5"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "negative_feedback",
                        "evidence_grade": "explicit",
                        "evidence_text": "你刚才一直追问让我不舒服，你越界了。",
                    },
                    {
                        "event_type": "boundary_violation",
                        "evidence_grade": "explicit",
                        "evidence_text": "你刚才一直追问让我不舒服，你越界了。",
                    },
                ],
                evidence_context="你刚才一直追问让我不舒服，你越界了。",
            )
            self.assertEqual(diagnostics["accepted_events_count"], 1)
            self.assertEqual(diagnostics["rejected_event_reasons"]["duplicate_evidence"], 1)
            self.assertAlmostEqual(next_bond["trust_level"], previous["trust_level"] - 0.05)
            self.assertAlmostEqual(next_bond["boundary_safety"], previous["boundary_safety"] - 0.08)
            self.assertEqual(next_bond["condition_code"], "strained")

    def test_character_bond_negative_feedback_is_guarded_without_stage_drop(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.normalize_bond({
                "stage_code": "trusted",
                "condition_code": "warming",
                "trust_level": 0.58,
                "closeness_level": 0.45,
                "boundary_safety": 0.66,
            }, card)
            next_bond, diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-6"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "negative_feedback",
                        "evidence_grade": "explicit",
                        "evidence_text": "你这样追问让我想退开一点。",
                    }
                ],
                evidence_context="你这样追问让我想退开一点。",
            )
            self.assertEqual(next_bond["stage_code"], "trusted")
            self.assertEqual(next_bond["condition_code"], "guarded")
            self.assertEqual(next_bond["relationship_condition"], "有保留")
            self.assertTrue(diagnostics["condition_changed"])
            self.assertTrue(diagnostics["progression_frozen"])

    def test_character_bond_condition_settles_after_stable_turns(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            warming = service.normalize_bond({"condition_code": "warming"}, card)
            first_warming, first_warming_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-7"],
                character=card,
                previous=warming,
                extracted=[],
                evidence_context="plain continuation",
            )
            self.assertEqual(first_warming["condition_code"], "warming")
            self.assertEqual(first_warming["condition_settle_turns"], 1)
            self.assertFalse(first_warming_diagnostics["condition_changed"])
            self.assertEqual(service.get_bond(visitor_id, card.id, card)["condition_settle_turns"], 1)
            second_warming, second_warming_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-8"],
                character=card,
                previous=first_warming,
                extracted=[],
                evidence_context="another plain continuation",
            )
            self.assertEqual(second_warming["condition_code"], "steady")
            self.assertEqual(second_warming["condition_settle_turns"], 0)
            self.assertTrue(second_warming_diagnostics["condition_changed"])

            repairing = service.normalize_bond({"condition_code": "repairing"}, card)
            repair_followup = [
                {
                    "event_type": "trust_signal",
                    "evidence_grade": "explicit",
                    "evidence_text": "I still trust you.",
                    "source_message_ids": ["message-9"],
                    "accepted": True,
                }
            ]
            first_repairing, _, _ = service.apply_events(
                repairing,
                repair_followup,
                [],
                service._reduce_delta(repair_followup),
                card,
            )
            self.assertEqual(first_repairing["condition_code"], "repairing")
            self.assertEqual(first_repairing["condition_settle_turns"], 1)
            second_repairing, _, _ = service.apply_events(
                first_repairing,
                [],
                [],
                service._reduce_delta([]),
                card,
            )
            self.assertEqual(second_repairing["condition_code"], "steady")
            self.assertEqual(second_repairing["condition_settle_turns"], 0)

    def test_character_bond_rejects_weak_boundary_and_assistant_only_positive_evidence(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = CharacterBondService(storage)
            previous = service.ensure_bond(visitor_id, card.id, card)
            _, weak_boundary_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-10"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "boundary_respected",
                        "evidence_grade": "explicit",
                        "evidence_text": "Let's talk about today's plan.",
                    }
                ],
                evidence_context="Let's talk about today's plan.",
            )
            self.assertEqual(weak_boundary_diagnostics["accepted_events_count"], 0)
            self.assertEqual(weak_boundary_diagnostics["rejected_event_reasons"]["boundary_without_signal"], 1)

            user_only_context = service._evidence_context(
                [{"role": "assistant", "content": "We have a shared pact."}],
                "Okay.",
                "We have a shared pact.",
            )
            _, assistant_only_diagnostics = service.update_from_events(
                visitor_id=visitor_id,
                session_id=session_id,
                source_message_ids=["message-11"],
                character=card,
                previous=previous,
                extracted=[
                    {
                        "event_type": "shared_context",
                        "evidence_grade": "strong",
                        "evidence_text": "We have a shared pact.",
                    }
                ],
                evidence_context=user_only_context,
            )
            self.assertEqual(assistant_only_diagnostics["accepted_events_count"], 0)
            self.assertEqual(assistant_only_diagnostics["rejected_event_reasons"]["evidence_not_in_context"], 1)

    def test_relationship_event_calibration_cases(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        fixture_path = Path(__file__).parent / "fixtures" / "relationship_event_cases.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = CharacterBondService(storage)
            for index, case in enumerate(cases):
                with self.subTest(case=case["name"]):
                    visitor_id, _ = storage.resolve_visitor(f"calibration-{index}")
                    session_id = storage.create_or_get_session(visitor_id, card.id)
                    previous = service.ensure_bond(visitor_id, card.id, card)
                    next_bond, diagnostics = service.update_from_events(
                        visitor_id=visitor_id,
                        session_id=session_id,
                        source_message_ids=[f"calibration-message-{index}"],
                        character=card,
                        previous=previous,
                        extracted=case["extracted"],
                        evidence_context=case["evidence_context"],
                    )
                    self.assertEqual(
                        [event["event_type"] for event in diagnostics["accepted_events"]],
                        case["accepted_event_types"],
                    )
                    self.assertEqual(diagnostics["rejected_event_reasons"], case["rejected_reasons"])
                    self.assertEqual(next_bond["condition_code"], case["condition_code"])
                    self.assertEqual(len(diagnostics["extracted_events"]), len(case["extracted"]))
                    self.assertTrue(all("evidence_text" in item for item in diagnostics["extracted_events"]))

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
              "bond": [{
                "event_type": "preference_confirmed",
                "evidence_grade": "explicit",
                "evidence_text": "解释规则要说明行为表现"
              }],
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
        self.assertEqual(parsed["bond"][0]["event_type"], "preference_confirmed")
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
            self.assertEqual(diagnostics["remote_status"], "skipped")
            self.assertEqual(diagnostics["fallback_reason"], "llm_not_configured")

    def test_story_refresh_uses_dedicated_timeout(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def __init__(self) -> None:
                self.timeout_ms = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.timeout_ms = timeout_ms
                return """[
                    {
                        "kind": "story_beat",
                        "label": "湖边约定",
                        "content": "用户和角色约定周六一起去湖边拍照。",
                        "evidence": "我们周六一起去湖边拍照吧。",
                        "evidence_level": "explicit",
                        "status": "active",
                        "source_message_ids": ["msg_1"]
                    }
                ]"""

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "我们周六一起去湖边拍照吧。")
            fake_llm = FakeLlm()
            diagnostics = self.run_async(
                StoryService(storage).refresh(
                    fake_llm,
                    session_id,
                    storage.session_messages(session_id),
                    [],
                )
            )
            self.assertEqual(fake_llm.timeout_ms, 24000)
            self.assertEqual(diagnostics["source"], "remote")
            self.assertEqual(diagnostics["remote_status"], "succeeded")

    def test_story_refresh_reports_remote_failure_before_fallback(self) -> None:
        class FakeLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                raise TimeoutError("story refresh timed out")

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, "lin_wanzhi")
            storage.add_message(session_id, visitor_id, "lin_wanzhi", "user", "我们周六一起去湖边拍照吧。")
            storage.add_message(session_id, visitor_id, "lin_wanzhi", "assistant", "好呀，我们慢慢选个角度。")
            diagnostics = self.run_async(
                StoryService(storage).refresh(
                    FakeLlm(),
                    session_id,
                    storage.session_messages(session_id),
                    [],
                )
            )
            self.assertEqual(diagnostics["source"], "fallback")
            self.assertEqual(diagnostics["remote_status"], "failed")
            self.assertEqual(diagnostics["remote_error"], "TimeoutError")
            self.assertEqual(diagnostics["fallback_reason"], "remote_error")

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
            self.assertEqual(rebuilt.story_canvas["diagnostics"]["mode"], "initial_rolling")
            canvas_chapters = rebuilt.story_canvas.get("chapters", [])
            self.assertGreaterEqual(len(canvas_chapters), 4)
            self.assertEqual([item["chapter_order"] for item in canvas_chapters[:4]], [1, 2, 3, 4])
            self.assertEqual(len(rebuilt.chapters), len(canvas_chapters))
            self.assertEqual(rebuilt.chapters[-1].chapter_order, len(canvas_chapters))

    def test_canvas_prompt_includes_real_identity_mapping_for_custom_character(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            card_data = storage.create_custom_character(visitor_id, {
                "name": "林悦",
                "archetype": "成熟高冷御姐",
                "tagline": "优雅冷艳，内心温柔",
                "bio": "一位边界感清晰的角色。",
                "speech_style": "简洁、冷静。",
                "opening_line": "你好。",
            })
            card = CharacterCard.model_validate(card_data)
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(
                card,
                visitor_id,
                session_id,
                [],
                [],
                [],
                NovelProjectCreateRequest(title="暗影迷踪", protagonist="许砚清"),
            )
            row = storage.get_novel_project(project.id)
            self.assertIsNotNone(row)

            source = service._initial_canvas_source(row, project.story_bible, [])

            self.assertIn("用户小说名/主角名：许砚清", source)
            self.assertIn("AI角色名：林悦", source)
            self.assertIn("禁止在 chapters、scenes、threads 中把人物写成“用户”“助手”“AI”", source)
            self.assertIn("不要写“许砚清、用户”", source)

    def test_novel_build_canvas_lock_depends_on_initial_chapter_versions(self) -> None:
        class CanvasFallbackLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            storage.update_novel_chapter(project.chapters[0].id, {"body": "正文已经开始。"}, "manual")
            with self.assertRaisesRegex(ValueError, "Cannot rebuild initial canvas"):
                self.run_async(service.build_canvas(CanvasFallbackLlm(), project.id))

            for version in storage.list_novel_versions(project.chapters[0].id):
                storage.delete_novel_version(version["id"])
            rebuilt = self.run_async(service.build_canvas(CanvasFallbackLlm(), project.id))
            self.assertEqual(rebuilt.story_canvas.get("mode"), "story_canvas")

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
            self.assertEqual(rebuilt.story_canvas["diagnostics"]["mode"], "initial_rolling")
            self.assertEqual(rebuilt.story_canvas["chapters"][0]["title"], "远程画布")
            self.assertEqual(rebuilt.story_canvas["chapters"][0]["target_length"], 1800)
            self.assertEqual(rebuilt.chapters[0].title, "远程画布")

    def test_novel_generation_rolls_forward_two_future_chapters(self) -> None:
        class FakeLlm:
            last_chat_error = None
            calls = 0

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"beats": [
                        {"type": "event", "purpose": "start", "visible_action": "林晚栀抱着书在走廊停下。", "dialogue": ["“这个是你的？”", "“谢谢。”"], "inner_turn": "她记住了对方的名字。"},
                        {"type": "choice", "purpose": "choice", "visible_action": "她没有立刻离开。", "dialogue": ["“你叫什么？”", "“许砚清。”"], "inner_turn": "她放慢了脚步。"},
                        {"type": "hook", "purpose": "hook", "visible_action": "便签从书页里露出一角。", "dialogue": ["“明天见。”", "“嗯。”"], "inner_turn": "她把便签收好。"},
                    ]}, ensure_ascii=False)
                if self.calls == 2:
                    return json.dumps({
                        "title": "第一章",
                        "summary": "林晚栀在走廊遇见许砚清，并记住了他的名字。",
                        "body": "林晚栀抱着书走过走廊，风把便签吹出一角。许砚清停在她面前：“这个是你的？”她接过来：“谢谢。”两个人都没有急着走。她低头把便签夹回书里，忽然问：“你叫什么？”他把书脊理正，回答：“许砚清。”铃声从楼下传来，她点点头：“明天见。”走到楼梯口时，她才发现自己已经记住了这个名字。",
                        "source_material_ids": [],
                    }, ensure_ascii=False)
                if self.calls == 3:
                    return json.dumps({"hard_fail": False, "rewrite_required": False, "checks": {"has_visible_event": True, "has_character_choice": True, "has_dialogue": True, "has_ending_hook": True, "uses_scene_card_terms": False, "has_meta_narration": False, "has_repeated_paragraphs": False, "breaks_confirmed_facts": False, "style_breaks_previous_chapter": False}, "issues": [], "rewrite_brief": ""}, ensure_ascii=False)
                return json.dumps({
                    "happened": ["林晚栀和许砚清在走廊正式说话。"],
                    "relationship_delta": ["从陌生到记住名字。"],
                    "ending_hook": ["便签留下未完问题。"],
                    "next_must_continue": ["承接便签。"],
                    "avoid_repeating": ["不要重复初次遇见。"],
                    "open_threads": ["便签"],
                    "global_summary": "林晚栀和许砚清在走廊正式说话。",
                    "confirmed_facts": ["两人已经互通姓名。"],
                    "character_states": [],
                    "relationship_states": ["从陌生到记住名字。"],
                    "resolved_threads": [],
                    "chapter_handoffs": [{"chapter_order": 1, "happened": ["互通姓名"]}],
                    "last_completed_chapter_order": 1,
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [],
                    "chapters": [
                        {"id": "canvas_ch_2", "act_id": "act_1", "chapter_order": 2, "title": "第二章", "goal": "承接便签", "external_event": "便签引出小事件", "trigger_event": "便签露出", "immediate_reaction": "她犹豫", "obstacle_escalation": "同学打断", "counterpart_reaction": "对方帮忙", "character_choice": "她留下", "scene_consequence": "再次说话", "relationship_shift": "更熟一点", "ending_hook": "新的疑问", "target_length": 1000, "status": "planned", "emotion_curve": "克制", "scene_ids": ["scene_2"]},
                        {"id": "canvas_ch_3", "act_id": "act_1", "chapter_order": 3, "title": "第三章", "goal": "继续承接", "external_event": "共同整理资料", "trigger_event": "资料散落", "immediate_reaction": "她去捡", "obstacle_escalation": "时间紧", "counterpart_reaction": "对方递回", "character_choice": "她开口", "scene_consequence": "留下约定", "relationship_shift": "能协作", "ending_hook": "约定未定", "target_length": 1000, "status": "planned", "emotion_curve": "克制", "scene_ids": ["scene_3"]},
                    ],
                    "scenes": [
                        {"id": "scene_2", "chapter_id": "canvas_ch_2", "scene_order": 1, "current_scene": "走廊", "pov": "林晚栀", "present_characters": "林晚栀、许砚清", "surface_event": "便签引出小事件", "character_desire": "确认", "tension": "同学打断", "required_facts": [], "forbidden_progress": [], "ending_beat": "新的疑问", "linked_material_ids": []},
                        {"id": "scene_3", "chapter_id": "canvas_ch_3", "scene_order": 1, "current_scene": "教室", "pov": "林晚栀", "present_characters": "林晚栀、许砚清", "surface_event": "整理资料", "character_desire": "自然回应", "tension": "时间紧", "required_facts": [], "forbidden_progress": [], "ending_beat": "约定未定", "linked_material_ids": []},
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote", "mode": "rolling_extend"},
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            raw_project = storage.get_novel_project(project.id)
            assert raw_project is not None
            prior_to_first = service._novel_state_until(raw_project, 0)
            self.assertEqual(prior_to_first["global_summary"], "")
            self.assertFalse(prior_to_first["chapter_handoffs"])
            llm = FakeLlm()
            generated, chapter = self.run_async(
                service.generate_chapter(llm, project.id, project.chapters[0].id, "写第一章。", 1000)
            )
            self.assertEqual(chapter.chapter_order, 1)
            self.assertEqual(generated.novel_state["last_completed_chapter_order"], 1)
            self.assertEqual(len(generated.story_canvas["chapters"]), 3)
            self.assertEqual([item["chapter_order"] for item in generated.story_canvas["chapters"]], [1, 2, 3])
            self.assertEqual([item.chapter_order for item in generated.chapters], [1, 2, 3])
            self.assertEqual(generated.story_canvas["diagnostics"]["mode"], "rolling_extend")
            self.assertEqual(llm.calls, 5)
            raw_project = storage.get_novel_project(project.id)
            assert raw_project is not None
            prior_to_second = service._novel_state_until(raw_project, 1)
            self.assertEqual(prior_to_second["last_completed_chapter_order"], 1)
            self.assertEqual(len(prior_to_second["chapter_handoffs"]), 1)

    def test_deferred_handoff_updates_bound_version_state_delta(self) -> None:
        class DeferredLlm:
            last_chat_error = None
            calls = 0

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"beats": [
                        {"type": "event", "purpose": "start", "visible_action": "林晚栀在走廊停下。", "dialogue": ["“这个是你的？”", "“谢谢。”"], "inner_turn": "她记住了名字。"},
                        {"type": "choice", "purpose": "choice", "visible_action": "她没有立刻离开。", "dialogue": ["“你叫什么？”", "“许砚清。”"], "inner_turn": "她放慢了脚步。"},
                    ]}, ensure_ascii=False)
                if self.calls == 2:
                    return json.dumps({
                        "title": "第一章",
                        "summary": "林晚栀和许砚清在走廊正式说话。",
                        "body": "傍晚的风穿过走廊时，林晚栀怀里的书页轻轻翻起。她蹲下去捡便签，许砚清先一步把书递过来：“这个是你的？”她接住书，低声说：“谢谢。”两个人都没有急着往前走。楼梯口有人经过，脚步声短促地响了一下，她把便签重新夹回书里，停了半秒，才问：“你叫什么？”许砚清把书脊理正，回答：“许砚清。”她点点头，走到转角时又回头看了一眼，才发现自己已经记住了这个名字。",
                        "source_material_ids": [],
                    }, ensure_ascii=False)
                if self.calls == 3:
                    return json.dumps({"hard_fail": False, "rewrite_required": False, "checks": {"has_visible_event": True, "has_character_choice": True, "has_dialogue": True, "has_ending_hook": True, "uses_scene_card_terms": False, "has_meta_narration": False, "has_repeated_paragraphs": False, "breaks_confirmed_facts": False, "style_breaks_previous_chapter": False}, "issues": [], "rewrite_brief": ""}, ensure_ascii=False)
                if self.calls == 4:
                    return json.dumps({
                        "happened": ["林晚栀和许砚清在走廊互通姓名。"],
                        "relationship_delta": ["从路人变成会被记住的人。"],
                        "ending_hook": ["林晚栀回头确认许砚清的名字。"],
                        "next_must_continue": ["下一章承接这个名字带来的再次注意。"],
                        "avoid_repeating": ["不要重复捡书和互通姓名。"],
                        "open_threads": ["许砚清为什么也停在走廊。"],
                    }, ensure_ascii=False)
                if self.calls == 5:
                    return json.dumps({
                        "global_summary": "林晚栀和许砚清在走廊互通姓名。",
                        "confirmed_facts": ["林晚栀和许砚清已经互通姓名。"],
                        "character_states": [],
                        "relationship_states": ["从路人变成会被记住的人。"],
                        "open_threads": ["许砚清为什么也停在走廊。"],
                        "resolved_threads": [],
                        "chapter_handoffs": [{"chapter_order": 1, "happened": ["林晚栀和许砚清在走廊互通姓名。"]}],
                        "last_completed_chapter_order": 1,
                    }, ensure_ascii=False)
                return json.dumps({
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [],
                    "chapters": [
                        {"id": "canvas_ch_2", "act_id": "act_1", "chapter_order": 2, "title": "第二章", "goal": "再次注意到对方", "external_event": "社团名单出现误会", "trigger_event": "名单被贴出", "immediate_reaction": "她停下确认", "obstacle_escalation": "同学催她去集合", "counterpart_reaction": "许砚清帮她指认", "character_choice": "她主动道谢", "scene_consequence": "两人有了下一次说话理由", "relationship_shift": "多了一点熟悉", "ending_hook": "名单背面有未写完的备注", "target_length": 1000, "status": "planned", "emotion_curve": "克制", "scene_ids": ["scene_2"]},
                        {"id": "canvas_ch_3", "act_id": "act_1", "chapter_order": 3, "title": "第三章", "goal": "承接备注", "external_event": "借阅卡被误拿", "trigger_event": "备注被发现", "immediate_reaction": "她迟疑", "obstacle_escalation": "老师叫走许砚清", "counterpart_reaction": "他留下纸条", "character_choice": "她保存纸条", "scene_consequence": "线索延后", "relationship_shift": "信任增加", "ending_hook": "纸条只写了一半", "target_length": 1000, "status": "planned", "emotion_curve": "克制", "scene_ids": ["scene_3"]},
                    ],
                    "scenes": [
                        {"id": "scene_2", "chapter_id": "canvas_ch_2", "scene_order": 1, "current_scene": "公告栏前", "pov": "林晚栀", "present_characters": "林晚栀、许砚清", "surface_event": "社团名单出现误会", "character_desire": "她想确认名单", "tension": "同学催促让她不能马上问清", "required_facts": [], "forbidden_progress": [], "ending_beat": "名单背面有未写完的备注", "linked_material_ids": []},
                        {"id": "scene_3", "chapter_id": "canvas_ch_3", "scene_order": 1, "current_scene": "图书馆门口", "pov": "林晚栀", "present_characters": "林晚栀、许砚清", "surface_event": "借阅卡被误拿", "character_desire": "她想把卡还回去", "tension": "老师叫走许砚清使事情延后", "required_facts": [], "forbidden_progress": [], "ending_beat": "纸条只写了一半", "linked_material_ids": []},
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote", "mode": "rolling_extend"},
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            llm = DeferredLlm()
            _, chapter = self.run_async(
                service.generate_chapter(llm, project.id, project.chapters[0].id, "写第一章。", 1000, defer_postprocess=True)
            )
            before_delta = json.loads(storage.list_novel_versions(chapter.id)[0]["state_delta_json"])
            self.assertFalse(before_delta.get("chapter_handoff"))

            self.run_async(service.finalize_chapter_postprocess(llm, project.id, chapter.id))
            refreshed = storage.get_novel_chapter(chapter.id)
            assert refreshed is not None
            scene_card = json.loads(refreshed["scene_card_json"])
            version_delta = json.loads(storage.list_novel_versions(chapter.id)[0]["state_delta_json"])
            self.assertEqual(scene_card["active_state_delta"]["chapter_handoff"]["happened"], ["林晚栀和许砚清在走廊互通姓名。"])
            self.assertEqual(version_delta["chapter_handoff"]["happened"], ["林晚栀和许砚清在走廊互通姓名。"])

    def test_handoff_sanitizer_does_not_copy_required_facts_as_current_happened(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            first = project.chapters[0]
            first_handoff = {
                "happened": ["林晚栀和许砚清在图书馆附近相遇并问候。"],
                "relationship_delta": ["两人从久别后的拘谨开始重新说话。"],
                "ending_hook": ["林晚栀问许砚清明天是否有时间。"],
                "next_must_continue": ["承接明天是否有时间的问题。"],
                "open_threads": ["明天是否能见面。"],
            }
            storage.update_novel_chapter(
                first.id,
                {
                    "summary": "林晚栀和许砚清在图书馆附近相遇并问候。",
                    "body": "林晚栀和许砚清在图书馆附近相遇并问候。",
                    "scene_card": {"chapter_handoff": first_handoff, "handoff_source": "remote"},
                },
                "remote",
            )
            second_id = storage.create_novel_chapter(project.id, "第二章", "承接明天的约定", "", "", "draft")
            project_row = storage.get_novel_project(project.id)
            second = storage.get_novel_chapter(second_id)
            assert project_row is not None and second is not None
            scene_card = {
                "surface_event": "许砚清回答林晚栀关于明天时间的询问，两人商讨明天的安排。",
                "character_desire": "许砚清想答应又担心时间冲突。",
                "ending_beat": "许砚清答应林晚栀明天有空。",
                "required_facts": ["林晚栀和许砚清在图书馆附近相遇并问候。"],
            }
            parsed = {
                "title": "第二章",
                "summary": "许砚清在纠结后答应林晚栀明天有空。",
                "body": "许砚清在纠结后答应林晚栀明天有空。",
            }
            stale_remote = {
                "happened": ["林晚栀和许砚清在图书馆附近相遇并问候。"],
                "relationship_delta": ["两人从久别后的拘谨开始重新说话。"],
                "ending_hook": ["明天的约定还需要确认时间。"],
                "next_must_continue": ["承接明天的具体安排。"],
                "open_threads": ["明天如何见面。"],
            }
            fallback = service._mock_chapter_handoff(second, scene_card, parsed)
            cleaned = service._sanitize_chapter_handoff(project_row, second, scene_card, parsed, stale_remote, fallback)
            self.assertEqual(cleaned["chapter_order"], 2)
            self.assertNotIn("林晚栀和许砚清在图书馆附近相遇并问候。", cleaned["happened"])
            self.assertIn("许砚清回答林晚栀关于明天时间的询问", cleaned["happened"][0])

    def test_generation_prompts_include_previous_tail_and_split_instruction_roles(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            first = project.chapters[0]
            previous_tail = "TAIL_SENTINEL: she turned back before the rain."
            storage.update_novel_chapter(
                first.id,
                {
                    "summary": "chapter one summary",
                    "body": f"chapter one body. {previous_tail}",
                    "scene_card": {
                        "chapter_handoff": {
                            "happened": ["chapter one happened"],
                            "next_must_continue": ["continue from rain"],
                        },
                        "handoff_source": "remote",
                    },
                },
                "remote",
            )
            second_id = storage.create_novel_chapter(project.id, "Chapter 2", "story summary only", "", "", "draft")
            project_row = storage.get_novel_project(project.id)
            second = storage.get_novel_chapter(second_id)
            assert project_row is not None and second is not None
            chapters = storage.list_novel_chapters(project.id)
            beat_source = service._beat_source(project_row, second, [], chapters, "write with more dialogue", 1200, {})
            chapter_source = service._chapter_source(project_row, second, [], chapters, "write with more dialogue", 1200, {}, [])

            self.assertIn(previous_tail, beat_source)
            self.assertIn(previous_tail, chapter_source)
            self.assertIn("[上一章尾段]", beat_source)
            self.assertIn("[本章剧情概述]", chapter_source)
            self.assertIn("[用户写作指令]", chapter_source)
            self.assertIn("[信息优先级]", chapter_source)
            self.assertIn("story summary only", chapter_source)
            self.assertIn("write with more dialogue", chapter_source)

    def test_novel_generation_roll_anchor_ignores_stale_future_drafts(self) -> None:
        class FakeLlm:
            last_chat_error = None
            calls = 0

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"beats": [
                        {"type": "event", "purpose": "start", "visible_action": "林晚栀抱着书停下。", "dialogue": ["“这个是你的？”", "“谢谢。”"], "inner_turn": "她记住名字。"},
                        {"type": "choice", "purpose": "choice", "visible_action": "她问了名字。", "dialogue": ["“你叫什么？”", "“许砚清。”"], "inner_turn": "她没有离开。"},
                        {"type": "hook", "purpose": "hook", "visible_action": "便签露出一角。", "dialogue": ["“明天见。”", "“嗯。”"], "inner_turn": "她收好便签。"},
                    ]}, ensure_ascii=False)
                if self.calls == 2:
                    return json.dumps({
                        "title": "第一章",
                        "summary": "林晚栀和许砚清在走廊互通姓名。",
                        "body": "林晚栀抱着书停在走廊里，便签从书页里露出一角。许砚清把它递回来：“这个是你的？”她接过来：“谢谢。”她本来可以立刻走开，却还是问：“你叫什么？”他说：“许砚清。”铃声响起来，她把名字在心里过了一遍，点头说：“明天见。”",
                        "source_material_ids": [],
                    }, ensure_ascii=False)
                if self.calls == 3:
                    return json.dumps({
                        "title": "Chapter One",
                        "summary": "Lin and Xu speak in the corridor.",
                        "body": "Lin stopped in the corridor with books in her arms. A folded note slipped from the pages, and Xu picked it up before the wind could carry it away. \"Is this yours?\" he asked. \"Thanks,\" she said, taking it back. She could have left at once, but she stayed by the window for another second. \"What is your name?\" Xu answered, \"Xu Yanqing.\" The bell rang downstairs. Lin tucked the note into the book and said, \"See you tomorrow.\"",
                        "source_material_ids": [],
                        "hard_fail": False,
                        "rewrite_required": False,
                        "checks": {"has_visible_event": True, "has_character_choice": True, "has_dialogue": True, "has_ending_hook": True},
                        "issues": [],
                        "rewrite_brief": "",
                    }, ensure_ascii=False)
                return "{}"

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            for order in (2, 3, 4):
                storage.create_novel_chapter(
                    project.id,
                    f"Old chapter {order}",
                    "stale future draft",
                    "stale summary",
                    f"stale body {order}",
                    "draft",
                    {},
                    [],
                    order,
                )
            generated, chapter = self.run_async(
                service.generate_chapter(FakeLlm(), project.id, project.chapters[0].id, "write chapter one", 1000)
            )
            self.assertEqual(chapter.chapter_order, 1)
            self.assertEqual([item["chapter_order"] for item in generated.story_canvas["chapters"]], [1, 2, 3])
            self.assertEqual(generated.story_canvas["diagnostics"]["extended_from_order"], 1)
            self.assertNotIn(5, [item["chapter_order"] for item in generated.story_canvas["chapters"]])

    def test_mock_chapter_does_not_update_global_state_or_roll_canvas(self) -> None:
        class FailingChapterLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                user = messages[-1]["content"]
                if response_format == {"type": "json_object"}:
                    return json.dumps({"ok": True})
                if "Scene Beats" in user or "Scene Card" in user:
                    raise RuntimeError("chapter_generation_failed")
                return json.dumps({
                    "beats": [
                        {
                            "type": "event",
                            "purpose": "start",
                            "visible_action": "林晚栀抱着书走过走廊。",
                            "dialogue": ["“我来帮你。”", "“谢谢。”"],
                            "inner_turn": "她停了一下。",
                        }
                    ]
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            generated, chapter = self.run_async(
                service.generate_chapter(FailingChapterLlm(), project.id, project.chapters[0].id, "write chapter one", 1000)
            )
            self.assertEqual(generated.novel_state["last_completed_chapter_order"], 0)
            self.assertEqual(len(generated.novel_state["chapter_handoffs"]), 0)
            self.assertEqual([item["chapter_order"] for item in generated.story_canvas["chapters"]], [1, 2, 3, 4])
            self.assertEqual(chapter.scene_card.get("handoff_source"), "skipped_mock")
            self.assertTrue(chapter.scene_card.get("chapter_audit", {}).get("global_state_skipped"))

    def test_rebuilding_novel_state_uses_latest_trusted_chapter_version(self) -> None:
        class OfflineLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            storage.update_novel_project(project.id, {
                "novel_state": {
                    "global_summary": "旧摘要污染",
                    "confirmed_facts": ["旧事实污染"],
                    "relationship_states": ["旧关系污染"],
                    "open_threads": ["旧线索污染"],
                    "chapter_handoffs": [{"chapter_order": 1, "happened": ["旧交接单污染"]}],
                    "last_completed_chapter_order": 1,
                }
            })
            old_handoff = {
                "happened": ["旧事件"],
                "relationship_delta": ["旧关系"],
                "ending_hook": ["旧钩子"],
                "next_must_continue": ["旧承接"],
                "avoid_repeating": [],
                "open_threads": ["旧线索"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "title": "第一章",
                "summary": "旧摘要",
                "body": "旧正文",
                "scene_card": {"chapter_handoff": old_handoff, "handoff_source": "remote"},
            }, "remote")
            new_handoff = {
                "happened": ["新事件"],
                "relationship_delta": ["新关系"],
                "ending_hook": ["新钩子"],
                "next_must_continue": ["新承接"],
                "avoid_repeating": [],
                "open_threads": ["新线索"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "title": "第一章新版",
                "summary": "新摘要",
                "body": "新正文",
                "scene_card": {"chapter_handoff": new_handoff, "handoff_source": "remote"},
            }, "remote")

            self.run_async(service._rebuild_novel_state_from_latest_chapters(project.id, OfflineLlm()))
            rebuilt = service.project_response(project.id).novel_state

            self.assertIn("新摘要", rebuilt["global_summary"])
            self.assertIn("新事件", rebuilt["confirmed_facts"])
            self.assertIn("新关系", rebuilt["relationship_states"])
            self.assertIn("新线索", rebuilt["open_threads"])
            self.assertNotIn("旧事实污染", rebuilt["confirmed_facts"])
            self.assertNotIn("旧关系污染", rebuilt["relationship_states"])
            self.assertNotIn("旧线索污染", rebuilt["open_threads"])
            self.assertEqual(rebuilt["chapter_handoffs"][0]["happened"], ["新事件"])

    def test_restored_chapter_version_restores_bound_state_delta(self) -> None:
        class OfflineLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            chapter2_id = storage.create_novel_chapter(project.id, "Chapter 2", "future goal", "future summary", "future body", "draft", {}, [], 2)

            old_handoff = {
                "happened": ["old event"],
                "relationship_delta": ["old relationship"],
                "ending_hook": ["old hook"],
                "next_must_continue": ["old carry"],
                "avoid_repeating": [],
                "open_threads": ["old thread"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "title": "Chapter 1 old",
                "summary": "old summary",
                "body": "old body",
                "scene_card": {"chapter_handoff": old_handoff, "handoff_source": "remote"},
            }, "remote")
            old_version_id = storage.list_novel_versions(chapter["id"])[0]["id"]

            new_handoff = {
                "happened": ["new event"],
                "relationship_delta": ["new relationship"],
                "ending_hook": ["new hook"],
                "next_must_continue": ["new carry"],
                "avoid_repeating": [],
                "open_threads": ["new thread"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "title": "Chapter 1 new",
                "summary": "new summary",
                "body": "new body",
                "scene_card": {"chapter_handoff": new_handoff, "handoff_source": "remote"},
            }, "remote")
            self.run_async(service._rebuild_novel_state_from_latest_chapters(project.id, OfflineLlm()))
            rebuilt = service.project_response(project.id).novel_state
            self.assertIn("new event", rebuilt["confirmed_facts"])
            self.assertNotIn("old event", rebuilt["confirmed_facts"])

            self.assertTrue(storage.restore_novel_version(old_version_id))
            service.mark_chapter_revision_boundary(project.id, 1)
            restored_chapter = storage.get_novel_chapter(chapter["id"])
            affected_future = storage.get_novel_chapter(chapter2_id)
            assert restored_chapter is not None and affected_future is not None
            restored_card = json.loads(restored_chapter["scene_card_json"])
            self.assertEqual(restored_card["active_version_id"], old_version_id)
            self.assertEqual(restored_card["active_state_delta"]["chapter_handoff"]["happened"], ["old event"])
            self.assertEqual(affected_future["status"], "affected")
            restored_state = service.project_response(project.id).novel_state
            self.assertIn("old event", restored_state["confirmed_facts"])
            self.assertNotIn("new event", restored_state["confirmed_facts"])

    def test_restored_chapter_version_restores_planning_snapshot(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None

            storage.update_novel_chapter(chapter["id"], {
                "title": "Chapter old",
                "goal": "old plot goal",
                "summary": "old summary",
                "body": "old body",
                "status": "draft",
                "scene_card": {
                    "current_scene": "old scene",
                    "generation_instruction": "old instruction",
                    "chapter_handoff": {"happened": ["old event"]},
                    "handoff_source": "remote",
                },
                "source_material_ids": ["mat-old"],
            }, "remote")
            old_version = storage.list_novel_versions(chapter["id"])[0]
            old_snapshot = json.loads(old_version["planning_snapshot_json"])
            self.assertEqual(old_snapshot["goal"], "old plot goal")
            self.assertEqual(old_snapshot["scene_card"]["current_scene"], "old scene")

            storage.update_novel_chapter(chapter["id"], {
                "title": "Chapter new",
                "goal": "new plot goal",
                "summary": "new summary",
                "body": "new body",
                "status": "locked",
                "scene_card": {
                    "current_scene": "new scene",
                    "generation_instruction": "new instruction",
                    "chapter_handoff": {"happened": ["new event"]},
                    "handoff_source": "remote",
                },
                "source_material_ids": ["mat-new"],
            }, "remote")

            self.assertTrue(storage.restore_novel_version(old_version["id"]))
            restored = storage.get_novel_chapter(chapter["id"])
            assert restored is not None
            restored_card = json.loads(restored["scene_card_json"])
            self.assertEqual(restored["title"], "Chapter old")
            self.assertEqual(restored["goal"], "old plot goal")
            self.assertEqual(restored["summary"], "old summary")
            self.assertEqual(restored["body"], "old body")
            self.assertEqual(restored["status"], "draft")
            self.assertEqual(restored_card["current_scene"], "old scene")
            self.assertEqual(restored_card["generation_instruction"], "old instruction")
            self.assertEqual(restored_card["active_version_id"], old_version["id"])
            self.assertEqual(json.loads(restored["source_material_ids_json"]), ["mat-old"])

    def test_delete_novel_chapter_reorders_and_cascades_versions(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter2_id = storage.create_novel_chapter(project.id, "Chapter 2", "goal", "summary", "body 2", "draft", {}, [], 2)
            chapter3_id = storage.create_novel_chapter(project.id, "Chapter 3", "goal", "summary", "body 3", "draft", {}, [], 3)

            self.assertTrue(storage.list_novel_versions(chapter2_id))
            deleted = storage.delete_novel_chapter(chapter2_id)
            self.assertIsNotNone(deleted)
            self.assertFalse(storage.list_novel_versions(chapter2_id))
            chapters = storage.list_novel_chapters(project.id)
            self.assertEqual([int(item["chapter_order"]) for item in chapters], [1, 2])
            self.assertEqual(storage.get_novel_chapter(chapter3_id)["chapter_order"], 2)
            service.mark_chapter_revision_boundary(project.id, 1)
            self.assertEqual(storage.get_novel_chapter(chapter3_id)["status"], "affected")

    def test_delete_novel_chapter_cleans_story_canvas_nodes(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter2_id = storage.create_novel_chapter(project.id, "Chapter 2", "goal", "summary", "body 2", "draft", {}, [], 2)
            storage.create_novel_chapter(project.id, "Chapter 3", "goal", "summary", "body 3", "draft", {}, [], 3)
            canvas = {
                "mode": "story_canvas",
                "acts": [{"id": "act1", "order": 1, "title": "Act", "purpose": "test", "chapter_ids": ["c1", "c2", "c3"]}],
                "chapters": [
                    {"id": "c1", "chapter_order": 1, "title": "One", "scene_ids": ["s1"]},
                    {"id": "c2", "chapter_order": 2, "title": "Two", "scene_ids": ["s2"]},
                    {"id": "c3", "chapter_order": 3, "title": "Three", "scene_ids": ["s3"]},
                ],
                "scenes": [
                    {"id": "s1", "chapter_id": "c1"},
                    {"id": "s2", "chapter_id": "c2"},
                    {"id": "s3", "chapter_id": "c3"},
                ],
                "threads": [
                    {"id": "t1", "setup_chapter_id": "c2", "payoff_chapter_id": "c3"},
                    {"id": "t2", "setup_chapter_id": "c1", "payoff_chapter_id": "c3"},
                ],
            }
            storage.update_novel_project(project.id, {"story_canvas": canvas})

            deleted = storage.delete_novel_chapter(chapter2_id)
            self.assertIsNotNone(deleted)
            service.remove_chapter_from_story_canvas(project.id, 2)
            updated_project = storage.get_novel_project(project.id)
            assert updated_project is not None
            updated_canvas = json.loads(updated_project["story_canvas_json"])

            self.assertEqual([item["chapter_order"] for item in updated_canvas["chapters"]], [1, 2])
            self.assertNotIn("c2", [item["id"] for item in updated_canvas["chapters"]])
            self.assertNotIn("s2", [item["id"] for item in updated_canvas["scenes"]])
            self.assertEqual(updated_canvas["acts"][0]["chapter_ids"], ["c1", "c3"])
            self.assertEqual([item["id"] for item in updated_canvas["threads"]], ["t2"])

    def test_canvas_compaction_dedupes_acts_and_filters_orphans(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            canvas = {
                "mode": "story_canvas",
                "acts": [
                    {"id": "act_1", "order": 1, "title": "old", "chapter_ids": ["c1", "missing"]},
                    {"id": "act_1", "order": 1, "title": "new", "chapter_ids": ["c1", "c2"]},
                    {"id": "act_2", "order": 2, "title": "second", "chapter_ids": ["missing"]},
                ],
                "chapters": [
                    {"id": "c1", "chapter_order": 1, "title": "One"},
                    {"id": "c2", "chapter_order": 2, "title": "Two"},
                ],
                "scenes": [
                    {"id": "s1", "chapter_id": "c1"},
                    {"id": "orphan", "chapter_id": "missing"},
                ],
                "threads": [
                    {"id": "t1", "setup_chapter_id": "c1", "payoff_chapter_id": "c2"},
                    {"id": "orphan-thread", "setup_chapter_id": "missing", "payoff_chapter_id": "c2"},
                ],
            }
            compacted = service._compact_story_canvas(canvas)

            self.assertEqual([item["title"] for item in compacted["acts"]], ["new", "second"])
            self.assertEqual(compacted["acts"][0]["chapter_ids"], ["c1", "c2"])
            self.assertEqual(compacted["acts"][1]["chapter_ids"], [])
            self.assertEqual([item["id"] for item in compacted["scenes"]], ["s1"])
            self.assertEqual([item["id"] for item in compacted["threads"]], ["t1"])

    def test_sync_story_canvas_updates_planning_without_losing_runtime_state(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            storage.update_novel_chapter(chapter["id"], {
                "goal": "old goal",
                "scene_card": {
                    "current_scene": "old scene",
                    "chapter_handoff": {"happened": ["kept event"]},
                    "active_state_delta": {"summary_delta": "kept summary"},
                    "generation_progress": {"stage": "kept"},
                },
            }, "manual")
            canvas = {
                "mode": "story_canvas",
                "acts": [{"id": "act_1", "order": 1, "title": "Act", "chapter_ids": ["c1"]}],
                "chapters": [{
                    "id": "c1",
                    "chapter_order": 1,
                    "title": "Canvas title",
                    "goal": "canvas goal",
                    "trigger_event": "canvas trigger",
                    "character_choice": "canvas choice",
                    "ending_hook": "canvas hook",
                    "scene_ids": ["s1"],
                }],
                "scenes": [{
                    "id": "s1",
                    "chapter_id": "c1",
                    "scene_order": 1,
                    "current_scene": "canvas scene",
                    "surface_event": "canvas event",
                    "tension": "canvas tension",
                }],
                "threads": [],
            }
            storage.update_novel_project(project.id, {"story_canvas": canvas})

            service.sync_story_canvas_to_chapters(project.id)
            synced = storage.get_novel_chapter(chapter["id"])
            assert synced is not None
            synced_card = json.loads(synced["scene_card_json"])

            self.assertEqual(synced["title"], "Canvas title")
            self.assertEqual(synced["goal"], "canvas goal")
            self.assertEqual(synced_card["current_scene"], "canvas scene")
            self.assertEqual(synced_card["surface_event"], "canvas trigger")
            self.assertEqual(synced_card["canvas_chapter_id"], "c1")
            self.assertEqual(synced_card["canvas_scene_id"], "s1")
            self.assertEqual(
                [(item["label"], item["text"]) for item in synced_card["canvas_action_chain"]],
                [("触发事件", "canvas trigger"), ("人物选择", "canvas choice"), ("结尾钩子", "canvas hook")],
            )
            self.assertEqual(synced_card["chapter_handoff"]["happened"], ["kept event"])
            self.assertEqual(synced_card["active_state_delta"]["summary_delta"], "kept summary")
            self.assertEqual(synced_card["generation_progress"]["stage"], "kept")

    def test_completed_chapter_updates_canvas_before_rolling_keeps_it(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            canvas = {
                "mode": "story_canvas",
                "chapters": [{"id": "c1", "chapter_order": 1, "title": "Old", "goal": "old goal", "status": "planned", "scene_ids": ["s1"]}],
                "scenes": [{"id": "s1", "chapter_id": "c1", "current_scene": "old scene"}],
                "acts": [],
                "threads": [],
            }
            storage.update_novel_project(project.id, {"story_canvas": canvas})
            service._update_canvas_from_completed_chapter(
                project.id,
                chapter,
                {"current_scene": "new scene", "surface_event": "new event", "ending_beat": "new hook"},
                {"title": "New title", "summary": "new summary", "body": "新的正文。"},
            )
            updated = storage.get_novel_project(project.id)
            assert updated is not None
            updated_canvas = json.loads(updated["story_canvas_json"])

            self.assertEqual(updated_canvas["chapters"][0]["title"], "New title")
            self.assertEqual(updated_canvas["chapters"][0]["status"], "complete")
            self.assertEqual(updated_canvas["chapters"][0]["completed_summary"], "new summary")
            self.assertEqual(updated_canvas["scenes"][0]["current_scene"], "new scene")
            self.assertEqual(updated_canvas["scenes"][0]["surface_event"], "new event")

    def test_initial_canvas_rebuild_prunes_empty_extra_chapters(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            storage.create_novel_chapter(project.id, "Empty 5", "old", "", "", "planned", {}, [], 5)
            canvas = {
                "mode": "story_canvas",
                "chapters": [
                    {"id": f"c{index}", "chapter_order": index, "title": f"Chapter {index}", "goal": f"goal {index}", "scene_ids": [f"s{index}"]}
                    for index in range(1, 5)
                ],
                "scenes": [
                    {"id": f"s{index}", "chapter_id": f"c{index}", "current_scene": f"scene {index}"}
                    for index in range(1, 5)
                ],
                "acts": [],
                "threads": [],
            }

            service._prune_empty_chapters_outside_canvas(project.id, canvas)
            chapters = storage.list_novel_chapters(project.id)

            self.assertEqual([int(item["chapter_order"]) for item in chapters], [1])
            self.assertFalse(any(item["title"] == "Empty 5" for item in chapters))

    def test_latest_mock_version_blocks_chapter_from_novel_state(self) -> None:
        class OfflineLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return False

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            handoff = {
                "happened": ["可信事件"],
                "relationship_delta": ["可信关系"],
                "ending_hook": ["可信钩子"],
                "next_must_continue": ["可信承接"],
                "avoid_repeating": [],
                "open_threads": ["可信线索"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "title": "第一章",
                "summary": "可信摘要",
                "body": "可信正文",
                "scene_card": {"chapter_handoff": handoff, "handoff_source": "remote"},
            }, "remote")
            storage.update_novel_chapter(chapter["id"], {
                "title": "第一章本地",
                "summary": "本地摘要",
                "body": "本地正文",
                "scene_card": {"chapter_handoff": {}, "handoff_source": "skipped_mock"},
            }, "mock")

            self.run_async(service._rebuild_novel_state_from_latest_chapters(project.id, OfflineLlm()))
            rebuilt = service.project_response(project.id).novel_state

            self.assertEqual(rebuilt["last_completed_chapter_order"], 0)
            self.assertEqual(rebuilt["chapter_handoffs"], [])
            self.assertNotIn("可信事件", rebuilt["confirmed_facts"])

    def test_mock_version_snapshot_drops_stale_remote_state_delta(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            handoff = {
                "happened": ["remote happened"],
                "relationship_delta": ["remote relationship"],
                "ending_hook": ["remote hook"],
                "next_must_continue": ["remote next"],
                "open_threads": ["remote thread"],
            }
            storage.update_novel_chapter(chapter["id"], {
                "summary": "remote summary",
                "body": "remote body",
                "scene_card": {"chapter_handoff": handoff, "handoff_source": "remote", "current_scene": "remote scene"},
            }, "remote")
            remote_chapter = storage.get_novel_chapter(chapter["id"])
            assert remote_chapter is not None
            stale_scene_card = json.loads(remote_chapter["scene_card_json"])
            self.assertIn("active_state_delta", stale_scene_card)

            storage.update_novel_chapter(chapter["id"], {
                "summary": "local summary",
                "body": "local body",
                "scene_card": {**stale_scene_card, "current_scene": "local scene", "handoff_source": "skipped_mock", "chapter_handoff": {}},
            }, "mock")
            mock_version = storage.list_novel_versions(chapter["id"])[0]
            snapshot = json.loads(mock_version["planning_snapshot_json"])
            snapshot_card = snapshot["scene_card"]
            self.assertEqual(mock_version["source"], "mock")
            self.assertNotIn("active_state_delta", snapshot_card)
            self.assertNotIn("chapter_handoff", snapshot_card)
            self.assertNotIn("handoff_source", snapshot_card)

            project_row = storage.get_novel_project(project.id)
            assert project_row is not None
            state = service._novel_state_until(project_row, 1)
            self.assertEqual(state["last_completed_chapter_order"], 0)
            self.assertNotIn("remote happened", state["confirmed_facts"])

    def test_chapter_revision_uses_cutoff_state_and_marks_future_affected(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter1 = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter1 is not None
            chapter2_id = storage.create_novel_chapter(project.id, "第二章", "第二章目标", "第二章摘要", "第二章正文", "draft", {
                "chapter_handoff": {
                    "happened": ["第二章已发生"],
                    "relationship_delta": ["第二章关系"],
                    "ending_hook": ["第二章钩子"],
                    "next_must_continue": ["第二章承接"],
                    "avoid_repeating": [],
                    "open_threads": ["第二章线索"],
                },
                "handoff_source": "remote",
            }, [], 2)
            chapter3_id = storage.create_novel_chapter(project.id, "第三章", "第三章目标", "第三章摘要", "第三章正文", "draft", {}, [], 3)
            handoff1 = {
                "happened": ["第一章已发生"],
                "relationship_delta": ["第一章关系"],
                "ending_hook": ["第一章钩子"],
                "next_must_continue": ["第一章承接"],
                "avoid_repeating": [],
                "open_threads": ["第一章线索"],
            }
            storage.update_novel_chapter(chapter1["id"], {
                "summary": "第一章摘要",
                "body": "第一章正文",
                "scene_card": {"chapter_handoff": handoff1, "handoff_source": "remote"},
            }, "remote")
            project_row = storage.get_novel_project(project.id)
            assert project_row is not None

            cutoff = service._novel_state_until(project_row, 1)
            self.assertIn("第一章已发生", cutoff["confirmed_facts"])
            self.assertNotIn("第二章已发生", cutoff["confirmed_facts"])

            service.mark_chapter_revision_boundary(project.id, 1)
            affected = storage.get_novel_chapter(chapter2_id)
            untouched_future = storage.get_novel_chapter(chapter3_id)
            assert affected is not None and untouched_future is not None
            self.assertEqual(affected["status"], "affected")
            self.assertEqual(untouched_future["status"], "affected")
            rebuilt = service.project_response(project.id).novel_state
            self.assertEqual(rebuilt["last_completed_chapter_order"], 1)
            self.assertIn("第一章已发生", rebuilt["confirmed_facts"])
            self.assertNotIn("第二章已发生", rebuilt["confirmed_facts"])

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
                    "scene_ids": ["sc_1"],
                }],
                "threads": [],
                "quality_rules": [],
                "diagnostics": {"source": "remote"},
            }, ensure_ascii=False)
            canvas = service._parse_canvas_response(text, fallback)
            self.assertEqual(canvas["diagnostics"]["source"], "remote")
            self.assertEqual(canvas["chapters"][0]["chapter_order"], 1)
            self.assertEqual(canvas["chapters"][0]["title"], "风起")
            self.assertEqual(canvas["diagnostics"]["scene_source"], "derived_from_chapters")
            self.assertEqual(canvas["scenes"][0]["id"], "sc_1")
            self.assertEqual(canvas["scenes"][0]["surface_event"], "傍晚起风。")

    def test_canvas_parser_normalizes_numeric_scene_tension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            fallback = service._default_story_canvas("测试长篇", "校园日常长篇", "温柔", "林晚栀", {}, [])
            text = json.dumps({
                "version": 1,
                "mode": "story_canvas",
                "acts": [],
                "chapters": [{
                    "id": "ch_1",
                    "act_id": "act_1",
                    "chapter_order": 1,
                    "title": "第一章",
                    "goal": "推进一次交流",
                    "external_event": "林晚栀在公告栏前遇见许砚清。",
                    "trigger_event": "公告栏名单引出误会。",
                    "immediate_reaction": "她想确认名字。",
                    "obstacle_escalation": "旁人催促和名单误会让她不能马上问清。",
                    "counterpart_reaction": "许砚清先替她挡住催促。",
                    "character_choice": "她留下核对名单。",
                    "scene_consequence": "两人多说了几句话。",
                    "relationship_shift": "更熟一点。",
                    "ending_hook": "名单旁边出现陌生名字。",
                    "target_length": 1200,
                    "status": "planned",
                    "emotion_curve": "克制",
                    "scene_ids": ["scene_1"],
                }],
                "scenes": [{
                    "id": "scene_1",
                    "chapter_id": "ch_1",
                    "scene_order": 1,
                    "current_scene": "公告栏前",
                    "pov": "林晚栀",
                    "present_characters": "林晚栀、许砚清",
                    "surface_event": "核对名单",
                    "character_desire": "确认名字",
                    "tension": "3",
                    "required_facts": [],
                    "forbidden_progress": [],
                    "ending_beat": "陌生名字出现",
                    "linked_material_ids": [],
                }],
                "threads": [],
                "quality_rules": [],
                "diagnostics": {"source": "remote"},
            }, ensure_ascii=False)
            canvas = service._parse_canvas_response(text, fallback)
            self.assertNotEqual(canvas["scenes"][0]["tension"], "3")
            self.assertIn("旁人催促", canvas["scenes"][0]["tension"])
            self.assertEqual(canvas["diagnostics"]["scene_tension_repaired"], 1)
            self.assertEqual(
                canvas["diagnostics"]["scene_tension_repair_reason"],
                "remote_returned_number_instead_of_obstacle_text",
            )

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
            self.assertEqual(canvas["chapters"][0]["title"], "风起")
            self.assertEqual(canvas["chapters"][0]["target_length"], 1800)
            self.assertEqual(canvas["scenes"][0]["scene_order"], 1)

    def test_novel_versions_are_immutable_even_for_identical_content(self) -> None:
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
            self.assertNotEqual(first, second)
            self.assertEqual(len(storage.list_novel_versions(chapter_id)), 2)
            third = storage.add_novel_version(project.id, chapter_id, "draft", "第一章", "另一版正文。", "同一版摘要。", "manual")
            self.assertNotEqual(first, third)
            self.assertEqual(len(storage.list_novel_versions(chapter_id)), 3)
            self.assertTrue(storage.delete_novel_version(first))
            self.assertEqual(
                {row["id"] for row in storage.list_novel_versions(chapter_id)},
                {second, third},
            )
            self.assertFalse(storage.delete_novel_version(first))

    def test_novel_json_payloads_reject_oversize_without_truncating(self) -> None:
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
            original = storage.get_novel_project(project.id)
            assert original is not None
            with self.assertRaises(StoragePayloadError):
                storage.update_novel_project(project.id, {"story_canvas": {"chapters": [{"title": "长" * 21000}]}})
            unchanged = storage.get_novel_project(project.id)
            assert unchanged is not None
            self.assertEqual(unchanged["story_canvas_json"], original["story_canvas_json"])

    def test_version_planning_snapshot_excludes_runtime_state(self) -> None:
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
            storage.update_novel_chapter(
                chapter_id,
                {
                    "body": "远程正文。",
                    "summary": "远程摘要。",
                    "scene_card": {
                        "current_scene": "图书馆",
                        "generation_progress": {"stage": "done"},
                        "postprocess": {"status": "done"},
                        "chapter_audit": {"pass": True},
                        "active_state_delta": {"summary_delta": "旧"},
                        "chapter_handoff": {"happened": ["互通姓名"]},
                        "handoff_source": "remote",
                    },
                },
                "remote",
            )
            version = storage.list_novel_versions(chapter_id)[0]
            snapshot = json.loads(version["planning_snapshot_json"])
            snapshot_card = snapshot["scene_card"]
            self.assertEqual(snapshot_card["current_scene"], "图书馆")
            self.assertNotIn("generation_progress", snapshot_card)
            self.assertNotIn("postprocess", snapshot_card)
            self.assertNotIn("chapter_audit", snapshot_card)
            self.assertNotIn("active_state_delta", snapshot_card)
            self.assertNotIn("chapter_handoff", snapshot_card)
            delta = json.loads(version["state_delta_json"])
            self.assertEqual(delta["chapter_handoff"]["happened"], ["互通姓名"])

    def test_atomic_chapter_draft_save_rejects_project_payload_before_chapter_update(self) -> None:
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
            with self.assertRaises(StoragePayloadError):
                storage.update_novel_chapter_draft(
                    project.id,
                    chapter_id,
                    {"story_canvas": {"chapters": [{"title": "长" * 21000}]}},
                    {"body": "不应写入。", "summary": "不应写入。"},
                )
            chapter = storage.get_novel_chapter(chapter_id)
            assert chapter is not None
            self.assertEqual(chapter["body"], "")
            self.assertEqual(storage.list_novel_versions(chapter_id), [])

    def test_restore_version_does_not_restore_runtime_progress_fields(self) -> None:
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
            storage.update_novel_chapter(
                chapter_id,
                {
                    "body": "远程正文。",
                    "summary": "远程摘要。",
                    "scene_card": {
                        "current_scene": "图书馆",
                        "generation_progress": {"stage": "done"},
                        "postprocess": {"status": "done"},
                        "chapter_handoff": {"happened": ["互通姓名"]},
                        "handoff_source": "remote",
                    },
                },
                "remote",
            )
            version_id = storage.list_novel_versions(chapter_id)[0]["id"]
            storage.update_novel_chapter(
                chapter_id,
                {
                    "body": "手动正文。",
                    "summary": "手动摘要。",
                    "scene_card": {"current_scene": "操场", "generation_progress": {"stage": "failed"}},
                },
                "manual",
            )
            version_count = len(storage.list_novel_versions(chapter_id))
            self.assertTrue(storage.restore_novel_version(version_id))
            restored = storage.get_novel_chapter(chapter_id)
            assert restored is not None
            restored_card = json.loads(restored["scene_card_json"])
            self.assertEqual(restored["body"], "远程正文。")
            self.assertNotIn("generation_progress", restored_card)
            self.assertNotIn("postprocess", restored_card)
            self.assertEqual(restored_card["active_version_id"], version_id)
            self.assertEqual(len(storage.list_novel_versions(chapter_id)), version_count)

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
            self.assertEqual(chapter.scene_card.get("handoff_source"), "skipped_mock")
            self.assertEqual(generated.novel_state.get("last_completed_chapter_order", 0), 0)
            self.assertEqual(generated.novel_state.get("global_summary"), "")
            self.assertFalse(generated.novel_state.get("chapter_handoffs"))
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

    def test_novel_local_quality_allows_story_material_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            body = (
                "林晚栀把社团材料抱在怀里，纸页边缘被风吹得轻轻响。"
                "许砚清从走廊另一端走来，停在她面前：“要不要我帮你拿一点？”"
                "她摇头，又很快把最上面那本递过去：“那你拿这本，别弄乱顺序。”"
                "两个人并肩往教室走，楼下的铃声催得很急，她却第一次没有把脚步放得太快。"
                "到门口时，许砚清把材料还给她，指尖在封皮上停了一下：“明天还要继续吗？”"
                "林晚栀低头看着那行被压弯的字，点了点头。"
            )
            parsed = service._parse_chapter_response(json.dumps({
                "title": "第二章",
                "summary": "林晚栀和许砚清整理社团材料。",
                "body": body,
                "source_material_ids": [],
            }, ensure_ascii=False), 800)
            check = service._chapter_local_check(parsed["body"], 800)
            self.assertEqual(check["blockers"], [])

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
