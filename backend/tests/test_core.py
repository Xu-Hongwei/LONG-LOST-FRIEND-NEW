from __future__ import annotations

import asyncio
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
from campus_lite.features.novel.event_pool import apply_story_event_pool_delta, bind_story_event_pool_to_chapters, event_pool_replacement_stats, normalize_story_event_pool, score_story_event, story_event_for_chapter
from campus_lite.features.novel.progression import normalize_story_progression
from campus_lite.llm import LlmClient
from campus_lite.memory import MemoryService
from campus_lite.novel import NovelService
from campus_lite.schemas import CharacterCard, NovelChapterGenerateRequest, NovelGenerateRequest, NovelInstructionOptimizeRequest, NovelProjectCreateRequest, SendMessageRequest
from campus_lite.schemas import MemoryItem
from campus_lite.state import CharacterStateService
from campus_lite.storage import Storage, StoragePayloadError
from campus_lite.story import StoryService


class LocalOnlyLlm:
    last_chat_error = None

    def configured(self) -> bool:
        return False


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
        self.assertGreaterEqual(len(cards), 10)
        lin = next(card for card in cards if card.name == "林晚栀")
        self.assertEqual(lin.setting_type, "campus")
        self.assertIn("校园", lin.scenario)
        self.assertTrue(any(card.setting_type == "sci_fi" for card in cards))
        self.assertTrue(any(card.setting_type == "xianxia_wuxia" for card in cards))

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
                "setting_type": "sci_fi",
                "setting_notes": "rainy future city",
                "bio": "A user-created investigator.",
                "speech_style": "calm, concise, observant",
                "relationship_pace": "slow and respectful",
                "opening_line": "I am here. What should we look at first?",
                "personality": "Patient, careful, and quietly warm.",
                "boundaries": ["keep replies safe", "do not force intimacy"],
                "story_seed_pool": {
                    "places": ["rain station", "archive room"],
                    "event_seeds": ["a timestamp is missing"],
                    "hook_seeds": ["the file points back to Mira"],
                    "motifs": ["rain", "old glass"],
                    "forbidden_defaults": ["campus club"],
                },
            })
            self.assertEqual(created.status_code, 200)
            character_id = created.json()["id"]
            self.assertEqual(created.json()["setting_type"], "sci_fi")
            self.assertEqual(created.json()["setting_notes"], "rainy future city")
            self.assertEqual(created.json()["story_seed_pool"]["places"], ["rain station", "archive room"])

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

            async def generate_character_draft(
                self,
                prompt,
                template=None,
                setting_type="modern_daily",
                setting_notes="",
                draft_mode="complete",
            ):
                return self._clean_character_draft({
                    "name": "Nia",
                    "archetype": "calm maker",
                    "tagline": "builds quiet little rituals",
                    "gender": "female",
                    "setting_type": setting_type,
                    "setting_notes": setting_notes,
                    "bio": "A fictional city companion.",
                    "speech_style": "soft, brief, concrete",
                    "opening_line": "I kept a seat for you.",
                    "interaction_policy": {"initiative_level": 0.35, "action_density": "只在确认节奏时出现轻动作，避免连续重复同一姿态。"},
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
                "setting_type": "workplace",
                "setting_notes": "adult cofounder relationship",
            })

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["character"]["name"], "Nia")
            self.assertEqual(payload["character"]["setting_type"], "workplace")
            self.assertEqual(payload["character"]["setting_notes"], "adult cofounder relationship")
            self.assertEqual(payload["character"]["gender"], "女")
            self.assertIn("interaction_policy", payload["character"])
            self.assertIn("确认节奏", payload["character"]["interaction_policy"]["action_density"])
            self.assertEqual(payload["diagnostics"]["source"], "remote")

    def test_character_draft_remote_runs_core_and_pack_in_parallel(self) -> None:
        class FakeSplitDraftLlm(LlmClient):
            def __init__(self) -> None:
                self.provider = {"name": "fake", "model": "fake", "api_key": "fake", "base_url": "http://fake", "timeout_ms": 1000}
                self.embedding_provider = None
                self.last_chat_error = None
                self.last_analysis_error = None
                self.last_character_draft_diagnostics = {}
                self.active_calls = 0
                self.max_active_calls = 0
                self.timeouts: list[int | None] = []

            async def chat_complete(self, messages, timeout_ms=None, response_format=None, temperature=None):
                self.timeouts.append(timeout_ms)
                self.active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self.active_calls)
                try:
                    await asyncio.sleep(0.01)
                    system = messages[0]["content"]
                    if "CORE persona" in system:
                        return json.dumps({
                            "character": {
                                "name": "Lin Yue",
                                "archetype": "reliable operator",
                                "tagline": "keeps order under pressure",
                                "gender": "female",
                                "setting_type": "workplace",
                                "setting_notes": "adult cofounder relationship",
                                "bio": "A focused workplace partner.",
                                "personality": "precise, calm, reliable",
                                "scenario": "adult workplace collaboration",
                                "speech_style": "brief and concrete",
                                "relationship_pace": "slow and bounded",
                                "opening_line": "Sit down. We can split the problem.",
                                "boundaries": ["does not decide for the user"],
                                "anti_patterns": ["no forced intimacy"],
                            }
                        }, ensure_ascii=False)
                    return json.dumps({
                        "character": {
                            "likes": ["clear plans"],
                            "dislikes": ["vague promises"],
                            "mes_example": "user: today is messy\nLin Yue: list the most urgent thing first.",
                            "interaction_policy": {
                                "initiative_level": 0.55,
                                "action_density": "只在确认任务边界或情绪转折时出现轻动作，避免每轮重复姿态。",
                            },
                            "story_seed_pool": {
                                "places": ["meeting room door"],
                                "event_seeds": ["a sudden change forces both sides to solve a concrete work problem"],
                                "hook_seeds": ["one unconfirmed choice waits for the next meeting"],
                                "motifs": ["folded document"],
                                "forbidden_defaults": ["no campus club default"],
                            },
                            "voice": {"sample_lines": ["Split the problem first."]},
                            "visual": {"accent": "#b8a06f"},
                        }
                    }, ensure_ascii=False)
                finally:
                    self.active_calls -= 1

        client = FakeSplitDraftLlm()
        draft = asyncio.run(client.generate_character_draft("reliable workplace partner", None, "workplace", "adult cofounder relationship"))

        self.assertGreaterEqual(client.max_active_calls, 2)
        self.assertEqual(client.last_character_draft_diagnostics["source"], "remote")
        self.assertEqual(client.last_character_draft_diagnostics["core_source"], "remote")
        self.assertEqual(client.last_character_draft_diagnostics["pack_source"], "remote")
        self.assertEqual(client.timeouts, [60000, 60000])
        self.assertEqual(draft["name"], "Lin Yue")
        self.assertEqual(draft["story_seed_pool"]["places"], ["meeting room door"])
        self.assertIn("确认任务边界", draft["interaction_policy"]["action_density"])

    def test_character_draft_partial_remote_uses_local_pack_fallback(self) -> None:
        class FakePartialDraftLlm(LlmClient):
            def __init__(self) -> None:
                self.provider = {"name": "fake", "model": "fake", "api_key": "fake", "base_url": "http://fake", "timeout_ms": 1000}
                self.embedding_provider = None
                self.last_chat_error = None
                self.last_analysis_error = None
                self.last_character_draft_diagnostics = {}

            async def chat_complete(self, messages, timeout_ms=None, response_format=None, temperature=None):
                system = messages[0]["content"]
                if "CORE persona" not in system:
                    raise TimeoutError("pack too slow")
                return json.dumps({
                    "character": {
                        "name": "Cen Jing",
                        "archetype": "cyber detective",
                        "gender": "female",
                        "setting_type": "sci_fi",
                        "setting_notes": "near-future rain city investigation",
                        "bio": "Cen Jing investigates data anomalies in the rain city.",
                        "personality": "calm and sharp",
                        "scenario": "commissioned investigation in a near-future city",
                        "speech_style": "short, direct lines",
                        "relationship_pace": "keeps distance and builds trust slowly",
                        "opening_line": "Give me the important part first.",
                    }
                }, ensure_ascii=False)

        client = FakePartialDraftLlm()
        draft = asyncio.run(client.generate_character_draft("cyber detective, calm and reliable", None, "sci_fi", "near-future rain city"))

        self.assertEqual(client.last_character_draft_diagnostics["source"], "partial")
        self.assertEqual(client.last_character_draft_diagnostics["core_source"], "remote")
        self.assertEqual(client.last_character_draft_diagnostics["pack_source"], "fallback")
        self.assertEqual(client.last_character_draft_diagnostics["pack_error"], "TimeoutError")
        self.assertIsNone(client.last_analysis_error)
        self.assertEqual(draft["name"], "Cen Jing")
        self.assertTrue(draft["story_seed_pool"]["places"])
        self.assertTrue(draft["voice"]["sample_lines"])

    def test_character_draft_fallback_respects_non_campus_setting(self) -> None:
        draft = LlmClient()._fallback_character_draft("赛博侦探，冷静可靠", None, "sci_fi", "近未来雨城")
        combined = json.dumps(draft, ensure_ascii=False)

        self.assertEqual(draft["setting_type"], "sci_fi")
        self.assertIn("近未来雨城", draft["setting_notes"])
        self.assertTrue(draft["story_seed_pool"]["places"])
        self.assertTrue(draft["story_seed_pool"]["event_seeds"])
        for forbidden in ["校园", "社团", "图书馆", "学姐"]:
            self.assertNotIn(forbidden, combined)

        xianxia = LlmClient()._fallback_character_draft("冷淡医修，关系推进慢", None, "xianxia_wuxia", "")
        xianxia_text = json.dumps(xianxia, ensure_ascii=False)
        self.assertEqual(xianxia["setting_type"], "xianxia_wuxia")
        self.assertTrue(xianxia["setting_notes"])
        self.assertIn("低魔江湖", xianxia["setting_notes"])
        self.assertIn("修仙", xianxia_text)
        self.assertIn("医修", xianxia_text)
        self.assertEqual(xianxia["interaction_policy"]["initiative_level"], 0.30)
        self.assertIn("动作保持克制", xianxia["interaction_policy"]["action_density"])
        self.assertNotIn(xianxia["interaction_policy"]["action_density"], {"low", "medium", "high"})

        heroine = LlmClient()._fallback_character_draft("行侠仗义的女侠，关系推进慢", None, "xianxia_wuxia", "")
        self.assertEqual(heroine["gender"], "女")
        self.assertEqual(heroine["visual"]["accent"], "#9bbb8f")
        self.assertIn("慢热克制", heroine["relationship_pace"])

    def test_character_story_seed_pool_filters_misplaced_bio_text(self) -> None:
        client = LlmClient()
        parsed = client._clean_character_draft({
            "name": "Nia",
            "story_seed_pool": {
                "locations": [
                    "一个生活在都市里的高中女生，性格如同她的名字一般温柔可爱。",
                    "雨后公交站",
                ],
                "events": ["临时活动名单被改动，两人被安排一起善后。"],
                "hooks": ["对方没有解释自己为什么突然沉默。"],
                "symbols": ["雨后路灯", "这是一句很长很长的解释性意象，已经不像短名词意象了。"],
            },
        })

        seed_pool = parsed["story_seed_pool"]
        self.assertEqual(seed_pool["places"], ["雨后公交站"])
        self.assertEqual(seed_pool["motifs"], ["雨后路灯"])
        self.assertEqual(seed_pool["event_seeds"], ["临时活动名单被改动，两人被安排一起善后。"])

        completed = client._complete_story_seed_pool(seed_pool, "modern_daily", "温柔可靠的都市角色")
        self.assertTrue(completed["forbidden_defaults"])
        self.assertEqual(completed["places"], ["雨后公交站"])

    def test_character_draft_completion_fills_empty_remote_fields(self) -> None:
        client = LlmClient()
        remote = client._clean_character_draft({
            "name": "柳依云",
            "archetype": "侠女",
            "setting_type": "xianxia_wuxia",
            "gender": "女",
            "bio": "",
            "personality": "",
            "scenario": "",
            "speech_style": "",
            "relationship_pace": "",
            "opening_line": "",
            "likes": [],
            "boundaries": [],
            "interaction_policy": {"action_density": ""},
            "voice": {},
            "visual": {},
            "story_seed_pool": {},
        })

        completed = client._complete_character_draft_fields(
            remote,
            "江湖女侠，冷静可靠，关系推进慢",
            None,
            "xianxia_wuxia",
            "",
        )

        self.assertEqual(completed["name"], "柳依云")
        self.assertEqual(completed["gender"], "女")
        self.assertTrue(completed["bio"])
        self.assertTrue(completed["scenario"])
        self.assertTrue(completed["speech_style"])
        self.assertTrue(completed["relationship_pace"])
        self.assertTrue(completed["opening_line"])
        self.assertTrue(completed["likes"])
        self.assertTrue(completed["boundaries"])
        self.assertTrue(completed["voice"]["sample_lines"])
        self.assertEqual(completed["visual"]["accent"], "#9bbb8f")

    def test_character_rewrite_mode_keeps_only_anchor_template_fields(self) -> None:
        client = LlmClient()
        anchor = client._rewrite_anchor_template({
            "name": "柳依云",
            "setting_type": "xianxia_wuxia",
            "setting_notes": "低魔江湖",
            "bio": "旧简介不应带入",
            "scenario": "旧场景不应带入",
            "story_seed_pool": {"places": ["旧地点"]},
        })

        self.assertEqual(anchor, {
            "name": "柳依云",
            "setting_type": "xianxia_wuxia",
            "setting_notes": "低魔江湖",
        })

    def test_context_composer_default_identity_is_not_campus_locked(self) -> None:
        card = CharacterCard(
            id="custom_generic",
            name="Mira",
            archetype="quiet strategist",
            tagline="notices small choices",
            bio="A fictional chat character.",
            speech_style="calm",
            opening_line="Hello.",
        )
        slots = ContextComposer().compose(
            ComposeInput(
                character=card,
                recent_messages=[],
                user_message="hello",
                memories=[],
                recent_summary="",
            )
        )
        rendered = "\n".join(slot.content for slot in slots)

        self.assertIn("虚构聊天角色", rendered)
        self.assertNotIn("校园轻陪伴", rendered)

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

    def test_non_campus_story_canvas_uses_setting_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)

            canvas = service._default_story_canvas(
                "云外听剑",
                "修仙武侠长篇",
                "克制、锋利、慢热",
                "许砚清",
                {},
                [],
            )
            combined = json.dumps(canvas, ensure_ascii=False)

            self.assertEqual(canvas["diagnostics"]["setting_type"], "xianxia_wuxia")
            self.assertEqual(len(canvas["event_pool"]["active"]), 10)
            self.assertIn("山门", combined)
            self.assertIn("药庐", combined)
            for forbidden in ["图书馆", "公告栏", "社团", "课程误会"]:
                self.assertNotIn(forbidden, combined)

    def test_project_setting_overrides_character_setting_for_novel_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            card = CharacterCard(
                id="custom_cyber",
                name="岑镜",
                archetype="自定义角色",
                tagline="雨城里的赛博侦探",
                setting_type="sci_fi",
                setting_notes="赛博侦探，近未来雨城，义体线索。",
                bio="A custom cyber detective.",
                speech_style="calm",
                opening_line="说吧。",
            )

            canvas = service._default_story_canvas(
                "雨城档案",
                "现代日常长篇",
                "冷静、悬疑",
                "岑镜",
                {},
                [],
                card,
            )
            combined = json.dumps(canvas, ensure_ascii=False)

            self.assertEqual(canvas["diagnostics"]["setting_type"], "modern_daily")
            self.assertIn("街角", combined)
            self.assertNotIn("空轨", combined)
            for forbidden in ["图书馆", "公告栏", "社团", "课程误会"]:
                self.assertNotIn(forbidden, combined)

    def test_character_story_seed_pool_overrides_non_campus_canvas_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            card = CharacterCard(
                id="custom_medic",
                name="寒青辞",
                archetype="冷淡医修",
                tagline="只救该救的人",
                setting_type="xianxia_wuxia",
                bio="A custom healer.",
                speech_style="brief",
                opening_line="坐下。",
                story_seed_pool={
                    "places": ["霜灯药室", "断桥雪亭"],
                    "event_seeds": ["药灯忽然熄灭，旧伤记录被人翻动。"],
                    "hook_seeds": ["雪亭下藏着半张未署名药方。"],
                    "motifs": ["霜灯", "药香"],
                    "forbidden_defaults": ["图书馆", "社团"],
                },
            )

            canvas = service._default_story_canvas(
                "霜灯药事",
                "修仙武侠长篇",
                "冷淡、克制",
                "寒青辞",
                {},
                [],
                card,
            )
            combined = json.dumps(canvas, ensure_ascii=False)

            self.assertEqual(canvas["diagnostics"]["seed_pool_source"], "character_seed")
            self.assertEqual(len(canvas["event_pool"]["active"]), 10)
            self.assertEqual(canvas["event_pool"]["active"][0]["source"], "character_seed")
            self.assertIn("霜灯药室", combined)
            self.assertIn("药灯忽然熄灭", combined)
            self.assertIn("半张未署名药方", combined)
            self.assertNotIn("山门药庐", combined)

    def test_custom_setting_label_does_not_auto_reclassify_from_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            card = CharacterCard(
                id="custom_freeform",
                name="岑镜",
                archetype="自定义角色",
                tagline="雨城里的赛博侦探",
                setting_type="custom",
                setting_notes="赛博侦探，近未来雨城，义体线索。",
                bio="A custom cyber detective.",
                speech_style="calm",
                opening_line="说吧。",
            )

            canvas = service._default_story_canvas(
                "雨城档案",
                "现代日常长篇",
                "冷静、悬疑",
                "岑镜",
                {},
                [],
                card,
            )

            self.assertEqual(canvas["diagnostics"]["setting_type"], "modern_daily")

    def test_cross_setting_character_seed_pool_is_not_copied_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            card = CharacterCard(
                id="custom_cyber_seed",
                name="岑镜",
                archetype="赛博侦探",
                tagline="雨城里的赛博侦探",
                setting_type="sci_fi",
                bio="A custom cyber detective.",
                speech_style="calm",
                opening_line="说吧。",
                story_seed_pool={
                    "places": ["空轨站台", "数据交易所"],
                    "event_seeds": ["监控盲区出现新的时间戳。"],
                    "hook_seeds": ["屏幕上多出一条匿名留言。"],
                    "motifs": ["蓝色霓虹", "旧数据芯片"],
                    "forbidden_defaults": ["图书馆", "社团"],
                },
            )

            canvas = service._default_story_canvas(
                "山门旧案",
                "修仙武侠长篇",
                "冷淡、克制",
                "岑镜",
                {},
                [],
                card,
            )
            combined = json.dumps(canvas, ensure_ascii=False)

            self.assertEqual(canvas["diagnostics"]["setting_type"], "xianxia_wuxia")
            self.assertEqual(canvas["diagnostics"]["seed_pool_source"], "character_seed_translatable")
            self.assertIn("山门", combined)
            self.assertIn("蓝色霓虹", combined)
            self.assertNotIn("空轨站台", combined)
            self.assertNotIn("监控盲区", combined)

    def test_campus_story_canvas_can_still_use_campus_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)

            canvas = service._default_story_canvas(
                "雨后图书馆计划",
                "校园日常长篇",
                "温柔、克制、日常",
                "林晚栀",
                {},
                [],
            )
            combined = json.dumps(canvas, ensure_ascii=False)

            self.assertIn("图书馆", combined)
            self.assertIn("校园", combined)
            self.assertEqual(len(canvas["event_pool"]["active"]), 10)

    def test_rolling_canvas_uses_project_event_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            card = CharacterStore().get("lin_wanzhi")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            raw_project = storage.get_novel_project(project.id)
            current_canvas = {
                "event_pool": {
                    "version": 1,
                    "setting_type": "modern_daily",
                    "active": [
                        {
                            "id": "evt_custom_1",
                            "place": "mirror dock",
                            "event": "custom drifting event",
                            "hook": "custom hook remains",
                            "status": "fresh",
                            "source": "manual",
                        }
                    ],
                    "retired": [],
                },
                "diagnostics": {"setting_type": "modern_daily"},
            }

            canvas = service._default_extension_canvas(raw_project, current_canvas, 0, 2)

            self.assertEqual(len(canvas["event_pool"]["active"]), 10)
            self.assertEqual(canvas["chapters"][0]["event_pool_id"], "evt_custom_1")
            self.assertEqual(canvas["chapters"][0]["external_event"], "custom drifting event")
            self.assertEqual(canvas["scenes"][0]["current_scene"], "mirror dock")

    def test_event_pool_dedupes_against_retired_and_generates_variants(self) -> None:
        raw = {
            "version": 1,
            "setting_type": "modern_daily",
            "active": [
                {
                    "id": "evt_done",
                    "place": "街角咖啡店",
                    "event": "一场临时变更打乱原本普通的见面，两人需要重新确认彼此的节奏。",
                    "hook": "路灯亮起时，对方没有催促主角立刻回答。",
                    "status": "fresh",
                },
                {
                    "id": "evt_b",
                    "place": "街角咖啡店",
                    "event": "一场临时变更打乱原本普通的见面，两人需要重新确认彼此的节奏。",
                    "hook": "路灯亮起时，对方没有催促主角立刻回答。",
                    "status": "fresh",
                },
            ],
            "retired": [
                {
                    "id": "evt_done",
                    "place": "雨后人行道",
                    "event": "雨后路面积水让同行路线改变，一个旧话题被自然带回来。",
                    "hook": "伞沿的水落下来，刚好打断那句快说出口的话。",
                    "status": "retired",
                }
            ],
        }

        pool = normalize_story_event_pool(raw, "modern_daily")
        active_keys = {(item["place"], item["event"], item["hook"]) for item in pool["active"]}
        retired_keys = {(item["place"], item["event"], item["hook"]) for item in pool["retired"]}
        active_ids = [item["id"] for item in pool["active"]]
        retired_ids = [item["id"] for item in pool["retired"]]

        self.assertEqual(len(pool["active"]), 10)
        self.assertEqual(len(active_ids), len(set(active_ids)))
        self.assertTrue(set(active_ids).isdisjoint(retired_ids))
        self.assertEqual(len(active_keys), 10)
        self.assertTrue(active_keys.isdisjoint(retired_keys))
        self.assertTrue(any("变体" in item["event"] for item in pool["active"]))

    def test_event_pool_binding_skips_completed_chapters(self) -> None:
        pool = bind_story_event_pool_to_chapters(
            {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [
                    {
                        "id": "evt_1",
                        "place": "archive room",
                        "event": "archive receipt mismatch reveals a past appointment",
                        "hook": "the old note stays unanswered",
                    },
                    {
                        "id": "evt_2",
                        "place": "rain station",
                        "event": "rain station delay forces the pair to wait together",
                        "hook": "the last train announcement interrupts them",
                    },
                ],
                "retired": [],
            },
            [
                {
                    "chapter_order": 1,
                    "status": "completed",
                    "event_pool_id": "evt_1",
                    "external_event": "archive receipt mismatch reveals a past appointment",
                    "title": "Done",
                },
                {
                    "chapter_order": 2,
                    "status": "planned",
                    "event_pool_id": "evt_1",
                    "external_event": "rain station delay forces the pair to wait together",
                    "title": "Next",
                },
            ],
            "modern_daily",
        )
        evt_1 = next(item for item in pool["active"] if item["id"] == "evt_1")
        evt_2 = next(item for item in pool["active"] if item["id"] == "evt_2")

        self.assertEqual(evt_1["status"], "fresh")
        self.assertEqual(evt_1["bound_chapter_orders"], [])
        self.assertEqual(evt_2["status"], "planned")
        self.assertEqual(evt_2["bound_chapter_orders"], ["2"])

    def test_event_pool_display_bindings_are_rebuilt_from_current_chapters(self) -> None:
        pool = bind_story_event_pool_to_chapters(
            {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [
                    {
                        "id": "evt_a",
                        "place": "old station",
                        "event": "old station delay forces a route choice",
                        "hook": "old station hook",
                        "bound_chapter_orders": ["1", "3", "4"],
                        "bound_chapter_titles": ["stale"],
                    },
                    {
                        "id": "evt_b",
                        "place": "new bookshop",
                        "event": "bookshop mixup forces the pair to pause",
                        "hook": "receipt hook",
                        "bound_chapter_orders": ["2"],
                    },
                ],
                "retired": [],
            },
            [
                {
                    "chapter_order": 1,
                    "event_pool_id": "evt_b",
                    "title": "Bookshop",
                    "status": "planned",
                    "external_event": "bookshop mixup forces the pair to pause",
                    "trigger_event": "bookshop mixup forces the pair to pause",
                },
                {
                    "chapter_order": 4,
                    "event_pool_id": "evt_a",
                    "title": "Station",
                    "status": "planned",
                    "external_event": "old station delay forces a route choice",
                    "trigger_event": "old station delay forces a route choice",
                },
            ],
            "modern_daily",
        )
        by_id = {item["id"]: item for item in pool["active"]}

        self.assertEqual(by_id["evt_a"]["bound_chapter_orders"], ["4"])
        self.assertEqual(by_id["evt_a"]["bound_chapter_titles"], ["Station"])
        self.assertEqual(by_id["evt_b"]["bound_chapter_orders"], ["1"])
        self.assertEqual(by_id["evt_b"]["bound_chapter_titles"], ["Bookshop"])

    def test_story_event_for_chapter_prefers_bound_event_id_over_order(self) -> None:
        pool = {
            "version": 1,
            "setting_type": "modern_daily",
            "active": [
                {"id": "evt_order", "place": "first", "event": "first event", "hook": "first hook"},
                {"id": "evt_bound", "place": "bound", "event": "bound event", "hook": "bound hook"},
            ],
            "retired": [],
        }

        selected = story_event_for_chapter(pool, {"chapter_order": 1, "event_pool_id": "evt_bound"}, "modern_daily")

        self.assertEqual(selected["id"], "evt_bound")

    def test_story_event_for_chapter_can_read_retired_bound_event(self) -> None:
        pool = {
            "version": 1,
            "setting_type": "modern_daily",
            "active": [
                {"id": "evt_active", "place": "active", "event": "active event", "hook": "active hook"},
            ],
            "retired": [
                {
                    "id": "evt_retired",
                    "place": "retired",
                    "event": "retired event",
                    "hook": "retired hook",
                    "bound_chapter_orders": ["2"],
                },
            ],
        }

        selected = story_event_for_chapter(pool, {"chapter_order": 2, "event_pool_id": "evt_retired"}, "modern_daily")

        self.assertEqual(selected["id"], "evt_retired")

    def test_free_event_is_not_auto_bound(self) -> None:
        chapters = [
            {
                "chapter_order": 1,
                "title": "Rain",
                "status": "planned",
                "external_event": "rain station delay forces a route choice",
                "trigger_event": "rain station delay forces a route choice",
            },
        ]
        pool = bind_story_event_pool_to_chapters(
            {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [
                    {
                        "id": "evt_free",
                        "place": "rain station",
                        "event": "rain station delay forces a route choice",
                        "hook": "rain station hook",
                        "use_mode": "free",
                    },
                    {
                        "id": "evt_guide",
                        "place": "bookshop",
                        "event": "bookshop mixup forces a route choice",
                        "hook": "bookshop hook",
                        "use_mode": "guide",
                    },
                ],
                "retired": [],
            },
            chapters,
            "modern_daily",
        )

        self.assertNotEqual(chapters[0].get("event_pool_id"), "evt_free")
        guide = next(item for item in pool["active"] if item["id"] == "evt_guide")
        self.assertEqual(guide["bound_chapter_orders"], ["1"])

    def test_event_pool_delta_add_replaces_unbound_fallback_when_full(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        updated = apply_story_event_pool_delta(
            raw,
            {
                "add": [
                    {
                        "id": "evt_remote_fresh",
                        "place": "湖边步道",
                        "event": "临时降雨让两人改变原本去湖边看夜景的路线",
                        "hook": "远处传来民谣声，打断了未说完的问题",
                        "tags": {
                            "event_type": ["external_interrupt"],
                            "anchors": ["湖边", "夜景", "民谣"],
                            "relationship_motion": ["shared_context"],
                            "boundary_risk": "low",
                        },
                        "source_reason": "命中湖边夜景和民谣偏好",
                    }
                ]
            },
            "modern_daily",
        )
        ids = [item["id"] for item in updated["active"]]

        self.assertEqual(len(updated["active"]), 10)
        self.assertIn("evt_remote_fresh", ids)
        selected = next(item for item in updated["active"] if item["id"] == "evt_remote_fresh")
        self.assertEqual(selected["source"], "remote")
        self.assertEqual(selected["tags"]["boundary_risk"], "low")

    def test_event_pool_delta_bulk_replaces_setting_profile_but_keeps_bound_events(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        raw["active"][0]["bound_chapter_orders"] = ["1"]
        raw["active"][0]["status"] = "planned"
        bound_id = raw["active"][0]["id"]
        updated = apply_story_event_pool_delta(
            raw,
            {
                "add": [
                    {
                        "id": f"evt_remote_bulk_{index}",
                        "place": f"湖边新地点 {index}",
                        "time_anchor": f"周六 19:{index}0，路灯亮起前",
                        "event": f"新的滚动事件 {index} 让两人必须重新选择路线",
                        "hook": f"新的钩子 {index} 留下一句未问完的话",
                        "tags": {
                            "theme_markers": ["湖边", "夜景", "民谣"],
                            "tone_markers": ["克制"],
                            "boundary_risk": "low",
                        },
                        "source_reason": "滚动画布后替换题材兜底",
                    }
                    for index in range(4)
                ]
            },
            "modern_daily",
        )
        sources = [item["source"] for item in updated["active"]]
        ids = [item["id"] for item in updated["active"]]

        self.assertEqual(len(updated["active"]), 10)
        self.assertIn(bound_id, ids)
        self.assertGreaterEqual(sources.count("remote"), 4)
        self.assertLess(sources.count("setting_profile"), 10)
        self.assertTrue(all(item["source"] == "remote" for item in updated["active"][1:5]))

    def test_event_pool_replacement_stats_targets_at_most_three_fallbacks(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        stats = event_pool_replacement_stats(raw)

        self.assertEqual(stats["fallback_count"], 10)
        self.assertEqual(stats["fallback_target_max"], 3)
        self.assertEqual(stats["replacement_needed"], 7)
        self.assertEqual(stats["recommended_add_count"], "7-10")

    def test_event_pool_delta_can_reduce_setting_profile_to_target(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        updated = apply_story_event_pool_delta(
            raw,
            {
                "add": [
                    {
                        "id": f"evt_remote_target_{index}",
                        "place": f"remote place {index}",
                        "time_anchor": f"Saturday 19:{index}0",
                        "event": f"remote event {index} gives the chapter a project-specific pressure",
                        "hook": f"remote hook {index} leaves a concrete next choice",
                        "source_reason": "replace fallback with rolling project event",
                        "tags": {
                            "theme_markers": ["project pressure", "choice"],
                            "tone_markers": ["restrained"],
                            "progression_role": "visible pressure",
                            "progression_markers": ["choice", "obstacle"],
                            "promise_markers": ["project-specific pressure"],
                            "boundary_risk": "low",
                        },
                    }
                    for index in range(1, 8)
                ]
            },
            "modern_daily",
        )
        stats = event_pool_replacement_stats(updated)

        self.assertEqual(len(updated["active"]), 10)
        self.assertLessEqual(stats["fallback_count"], 3)
        self.assertGreaterEqual(stats["source_counts"].get("remote", 0), 7)

    def test_initial_event_binding_prefers_remote_candidates_over_fallback_order(self) -> None:
        pool = normalize_story_event_pool({}, "modern_daily")
        remote_events = [
            {
                "id": f"evt_remote_initial_{index}",
                "place": f"雨夜新地点 {index}",
                "time_anchor": f"周六 20:{index}0",
                "event": f"滚动新增事件 {index} 迫使两人重新确认选择",
                "hook": f"滚动新增钩子 {index} 留下未说完的问题",
                "source": "remote",
                "source_reason": "初版远程新增，替换题材兜底",
                "tags": {
                    "theme_markers": ["雨夜", "选择"],
                    "tone_markers": ["克制"],
                    "progression_role": "压力下的共同选择",
                    "progression_markers": ["重新确认", "共同选择"],
                    "promise_markers": ["可见压力"],
                    "boundary_risk": "low",
                },
            }
            for index in range(1, 5)
        ]
        pool["active"] = [*pool["active"][:6], *remote_events]
        chapters = [
            {
                "id": f"canvas_ch_{order}",
                "chapter_order": order,
                "event_pool_id": pool["active"][order - 1]["id"],
                "goal": pool["active"][order - 1]["event"],
                "external_event": pool["active"][order - 1]["event"],
                "ending_hook": pool["active"][order - 1]["hook"],
                "status": "planned",
            }
            for order in range(1, 5)
        ]

        bound_pool = bind_story_event_pool_to_chapters(
            pool,
            chapters,
            "modern_daily",
            {"prefer_concrete_events": True},
        )
        by_id = {item["id"]: item for item in bound_pool["active"]}

        self.assertTrue(all(by_id[chapter["event_pool_id"]]["source"] == "remote" for chapter in chapters))
        self.assertEqual(len({chapter["event_pool_id"] for chapter in chapters}), 4)

    def test_event_pool_scoring_prefers_continuity_ledger_carryover(self) -> None:
        chapter = {
            "chapter_order": 2,
            "goal": "承接雨夜未说完的问题",
            "external_event": "两人必须处理雨夜未说完的问题",
            "ending_hook": "留下新的选择",
            "status": "planned",
        }
        generic = {
            "id": "evt_generic",
            "place": "街角",
            "time_anchor": "周六 20:00",
            "event": "两人进行一次普通交流",
            "hook": "对话还没有结束",
            "source": "setting_profile",
            "use_mode": "guide",
        }
        carryover = {
            "id": "evt_carryover",
            "place": "雨夜街道",
            "time_anchor": "周六 20:30",
            "event": "雨夜未说完的问题被旁人的到来打断，两人必须先保留答案",
            "hook": "雨夜未说完的问题被写进下一次选择",
            "source": "remote",
            "source_reason": "承接上一章未完成交接",
            "use_mode": "guide",
            "tags": {
                "theme_markers": ["雨夜", "选择"],
                "tone_markers": ["克制"],
                "progression_markers": ["延迟答案"],
                "promise_markers": ["雨夜未说完的问题"],
                "boundary_risk": "low",
            },
        }
        context = {
            "prefer_concrete_events": True,
            "project": {"title": "雨夜计划", "genre": "悬疑探索", "tone": "克制", "worldview": "雨夜街区", "relationship_setup": "慢慢确认彼此"},
            "novel_state": {
                "continuity_ledger": {
                    "next_must_continue": ["雨夜未说完的问题"],
                    "promises_made": ["雨夜未说完的问题"],
                    "avoid_repeating": ["普通交流"],
                    "forbidden_contradictions": ["两人已经解决雨夜问题"],
                }
            },
        }

        generic_score = score_story_event(generic, chapter, context, "modern_daily")
        carryover_score = score_story_event(carryover, chapter, context, "modern_daily")

        self.assertGreater(carryover_score["score"], generic_score["score"])
        self.assertTrue(any("承接账本" in reason for reason in carryover_score["reasons"]))

    def test_event_pool_delta_does_not_reintroduce_retired_duplicate(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        retired = dict(raw["active"][0])
        retired["id"] = "evt_retired_duplicate"
        retired["status"] = "retired"
        raw["retired"] = [retired]
        updated = apply_story_event_pool_delta(
            raw,
            {
                "add": [
                    {
                        "id": "evt_remote_duplicate",
                        "place": retired["place"],
                        "event": retired["event"],
                        "hook": retired["hook"],
                        "source_reason": "should not return",
                    }
                ]
            },
            "modern_daily",
        )

        self.assertFalse(any(item["id"] == "evt_remote_duplicate" for item in updated["active"]))

    def test_event_pool_delta_preserves_time_and_theme_tags(self) -> None:
        raw = normalize_story_event_pool({}, "modern_daily")
        updated = apply_story_event_pool_delta(
            raw,
            {
                "add": [
                    {
                        "id": "evt_theme_time",
                        "place": "lake path",
                        "time_anchor": "Saturday 18:40, before the lake lights turn on",
                        "event": "a folk song rehearsal blocks the lake path and asks them to choose a quieter route",
                        "hook": "one unfinished question stays between them",
                        "tags": {
                            "event_type": ["external_interrupt"],
                            "anchors": ["lake", "folk song"],
                            "theme_markers": ["lake", "folk song", "quiet route"],
                            "tone_markers": ["warm", "restrained"],
                            "relationship_motion": ["slow_trust"],
                            "boundary_risk": "low",
                        },
                        "source_reason": "matches lake night and folk-song project theme",
                    }
                ]
            },
            "modern_daily",
        )
        selected = next(item for item in updated["active"] if item["id"] == "evt_theme_time")

        self.assertEqual(selected["time_anchor"], "Saturday 18:40, before the lake lights turn on")
        self.assertEqual(selected["tags"]["theme_markers"], ["lake", "folk song", "quiet route"])
        self.assertEqual(selected["tags"]["tone_markers"], ["warm", "restrained"])

    def test_event_pool_edit_and_binding_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=LocalOnlyLlm())
            client = TestClient(app)
            session = client.post("/api/sessions", json={"visitor_id": "event-api", "character_id": "lin_wanzhi"})
            self.assertEqual(session.status_code, 200)
            project_response = client.post(
                f"/api/sessions/{session.json()['session_id']}/novel/projects",
                json={"title": "Event API", "genre": "modern_daily", "tone": "quiet"},
            )
            self.assertEqual(project_response.status_code, 200)
            project_id = project_response.json()["id"]
            chapter_id = project_response.json()["chapters"][0]["id"]

            created = client.post(
                f"/api/novel/projects/{project_id}/event-pool/events",
                json={
                    "place": "manual pier",
                    "time_anchor": "Saturday 18:40",
                    "event": "manual pier delay forces one choice",
                    "hook": "the pier light cuts off before the answer",
                    "motifs": ["pier light"],
                    "use_mode": "guide",
                    "source_reason": "manual test",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(created.status_code, 200)
            event = next(item for item in created.json()["story_canvas"]["event_pool"]["active"] if item["place"] == "manual pier")
            self.assertEqual(event["use_mode"], "guide")

            patched = client.patch(
                f"/api/novel/projects/{project_id}/event-pool/events/{event['id']}",
                json={
                    "place": "manual pier revised",
                    "time_anchor": "Saturday 18:50",
                    "event": "manual pier revision forces one choice",
                    "hook": "the revised hook remains",
                    "motifs": ["revised"],
                    "use_mode": "flavor",
                    "source_reason": "manual patch",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(patched.status_code, 200)
            patched_event = next(item for item in patched.json()["story_canvas"]["event_pool"]["active"] if item["id"] == event["id"])
            self.assertEqual(patched_event["place"], "manual pier revised")
            self.assertEqual(patched_event["use_mode"], "flavor")

            bound = client.post(
                f"/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding",
                json={"event_id": event["id"], "use_mode": "strict"},
            )
            self.assertEqual(bound.status_code, 200)
            bound_payload = bound.json()
            bound_chapter = bound_payload["story_canvas"]["chapters"][0]
            self.assertEqual(bound_chapter["event_pool_id"], event["id"])
            self.assertEqual(bound_chapter["event_contract"]["event_id"], event["id"])
            self.assertEqual(bound_chapter["event_contract"]["external_event"], "manual pier revision forces one choice")
            self.assertEqual(bound_chapter["external_event"], "manual pier revision forces one choice")
            self.assertEqual(bound_chapter["trigger_event"], "manual pier revision forces one choice")
            self.assertEqual(bound_chapter["ending_hook"], "the revised hook remains")
            self.assertEqual(bound_payload["chapters"][0]["scene_card"]["event_contract"]["event_id"], event["id"])
            self.assertEqual(bound_payload["chapters"][0]["scene_card"]["surface_event"], "manual pier revision forces one choice")
            bound_event = next(item for item in bound_payload["story_canvas"]["event_pool"]["active"] if item["id"] == event["id"])
            self.assertEqual(bound_chapter["event_contract"]["use_mode"], "strict")
            self.assertEqual(bound_event["use_mode"], "flavor")

            repatched = client.patch(
                f"/api/novel/projects/{project_id}/event-pool/events/{event['id']}",
                json={
                    "place": "manual pier final",
                    "time_anchor": "Saturday 19:05",
                    "event": "manual pier final update changes the route",
                    "hook": "the final route stays unanswered",
                    "motifs": ["final route"],
                    "use_mode": "strict",
                    "source_reason": "manual repatch",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(repatched.status_code, 200)
            repatched_payload = repatched.json()
            repatched_chapter = repatched_payload["story_canvas"]["chapters"][0]
            self.assertEqual(repatched_chapter["event_contract"]["external_event"], "manual pier final update changes the route")
            self.assertEqual(repatched_chapter["external_event"], "manual pier final update changes the route")
            self.assertEqual(repatched_payload["chapters"][0]["scene_card"]["surface_event"], "manual pier final update changes the route")

            blocked_delete = client.delete(f"/api/novel/projects/{project_id}/event-pool/events/{event['id']}")
            self.assertEqual(blocked_delete.status_code, 400)

            cleared = client.post(
                f"/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding",
                json={"event_id": None},
            )
            self.assertEqual(cleared.status_code, 200)
            cleared_payload = cleared.json()
            self.assertEqual(cleared_payload["story_canvas"]["chapters"][0].get("event_pool_id", ""), "")
            self.assertNotIn("event_contract", cleared_payload["story_canvas"]["chapters"][0])
            self.assertNotIn("event_contract", cleared_payload["chapters"][0]["scene_card"])
            retired = client.post(f"/api/novel/projects/{project_id}/event-pool/events/{event['id']}/retire")
            self.assertEqual(retired.status_code, 200)
            self.assertTrue(any(item["id"] == event["id"] for item in retired.json()["story_canvas"]["event_pool"]["retired"]))

    def test_guide_event_binding_first_syncs_then_preserves_manual_scene_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=LocalOnlyLlm())
            client = TestClient(app)
            session = client.post("/api/sessions", json={"visitor_id": "guide-sync", "character_id": "lin_wanzhi"})
            self.assertEqual(session.status_code, 200)
            project_response = client.post(
                f"/api/sessions/{session.json()['session_id']}/novel/projects",
                json={"title": "Guide Sync", "genre": "modern_daily", "tone": "quiet"},
            )
            self.assertEqual(project_response.status_code, 200)
            project_id = project_response.json()["id"]
            chapter_id = project_response.json()["chapters"][0]["id"]

            created = client.post(
                f"/api/novel/projects/{project_id}/event-pool/events",
                json={
                    "place": "old pier",
                    "time_anchor": "Saturday 19:15",
                    "event": "guide event one changes the chapter direction",
                    "hook": "guide hook one remains",
                    "motifs": ["pier"],
                    "use_mode": "guide",
                    "source_reason": "guide sync test",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(created.status_code, 200)
            event = next(item for item in created.json()["story_canvas"]["event_pool"]["active"] if item["place"] == "old pier")

            bound = client.post(
                f"/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding",
                json={"event_id": event["id"], "use_mode": "guide"},
            )
            self.assertEqual(bound.status_code, 200)
            bound_payload = bound.json()
            self.assertEqual(bound_payload["story_canvas"]["chapters"][0]["event_contract"]["use_mode"], "guide")
            self.assertEqual(bound_payload["story_canvas"]["chapters"][0]["external_event"], "guide event one changes the chapter direction")
            self.assertEqual(bound_payload["chapters"][0]["scene_card"]["surface_event"], "guide event one changes the chapter direction")

            storage.update_novel_chapter(
                chapter_id,
                {"scene_card": {**bound_payload["chapters"][0]["scene_card"], "surface_event": "manual scene event"}},
                "manual",
                create_version=False,
            )
            patched = client.patch(
                f"/api/novel/projects/{project_id}/event-pool/events/{event['id']}",
                json={
                    "place": "old pier changed",
                    "time_anchor": "Saturday 19:40",
                    "event": "guide event two should not overwrite manual scene",
                    "hook": "guide hook two remains",
                    "motifs": ["pier changed"],
                    "use_mode": "guide",
                    "source_reason": "guide sync patch",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(patched.status_code, 200)
            patched_payload = patched.json()
            self.assertEqual(patched_payload["story_canvas"]["chapters"][0]["external_event"], "guide event two should not overwrite manual scene")
            self.assertEqual(patched_payload["chapters"][0]["scene_card"]["surface_event"], "manual scene event")

    def test_event_binding_uses_remote_structured_sync_when_configured(self) -> None:
        class RemoteSyncLlm:
            last_chat_error = None

            def __init__(self) -> None:
                self.messages = []

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.messages = messages
                self.timeout_ms = timeout_ms
                self.response_format = response_format
                return json.dumps({
                    "canvas_chapter_patch": {
                        "external_event": "变体8：remote refined pier event",
                        "trigger_event": "remote trigger from the selected contract",
                        "ending_hook": "变体9：remote hook closes the scene",
                    },
                    "scene_card_patch": {
                        "current_scene": "remote pier at dusk",
                        "surface_event": "变体3：remote visible event",
                        "ending_beat": "remote final beat",
                        "required_facts": ["keep selected event"],
                    },
                    "sync_note": "remote structured sync applied",
                })

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            llm = RemoteSyncLlm()
            app = create_app(storage=storage, characters=CharacterStore(), llm=llm)
            client = TestClient(app)
            session = client.post("/api/sessions", json={"visitor_id": "remote-bind", "character_id": "lin_wanzhi"})
            self.assertEqual(session.status_code, 200)
            project_response = client.post(
                f"/api/sessions/{session.json()['session_id']}/novel/projects",
                json={"title": "Remote Binding", "genre": "modern_daily", "tone": "quiet"},
            )
            self.assertEqual(project_response.status_code, 200)
            project_id = project_response.json()["id"]
            chapter_id = project_response.json()["chapters"][0]["id"]

            created = client.post(
                f"/api/novel/projects/{project_id}/event-pool/events",
                json={
                    "place": "remote pier",
                    "time_anchor": "Saturday 20:10",
                    "event": "local event should be refined remotely",
                    "hook": "local hook",
                    "motifs": ["pier"],
                    "use_mode": "guide",
                    "source_reason": "remote sync test",
                    "tags": {"theme_markers": ["pier"], "tone_markers": ["quiet"]},
                },
            )
            self.assertEqual(created.status_code, 200)
            event = next(item for item in created.json()["story_canvas"]["event_pool"]["active"] if item["place"] == "remote pier")

            bound = client.post(
                f"/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding",
                json={"event_id": event["id"], "use_mode": "guide"},
            )
            self.assertEqual(bound.status_code, 200)
            payload = bound.json()
            chapter = payload["story_canvas"]["chapters"][0]
            scene_card = payload["chapters"][0]["scene_card"]
            self.assertEqual(chapter["external_event"], "remote refined pier event")
            self.assertEqual(chapter["trigger_event"], "remote trigger from the selected contract")
            self.assertEqual(chapter["ending_hook"], "remote hook closes the scene")
            self.assertEqual(scene_card["surface_event"], "remote visible event")
            self.assertEqual(scene_card["required_facts"], ["keep selected event"])
            self.assertEqual(chapter["event_sync"]["source"], "remote")
            self.assertEqual(chapter["event_sync"]["remote_status"], "succeeded")
            self.assertEqual(chapter["event_sync"]["source_note"], "remote structured sync applied")
            self.assertIn("event_contract", llm.messages[1]["content"])
            self.assertEqual(llm.response_format, {"type": "json_object"})

    def test_story_event_score_prefers_theme_and_time_anchor(self) -> None:
        chapter = {
            "chapter_order": 2,
            "status": "planned",
            "title": "Lake Night",
            "goal": "The lake night folk-song scene forces a small shared choice.",
            "external_event": "lake night folk song interruption",
            "trigger_event": "lake night folk song interruption",
            "ending_hook": "one unfinished question stays between them",
        }
        context = {
            "project": {
                "title": "Lake Folk Case",
                "genre": "modern daily longform",
                "tone": "warm restrained daily",
                "worldview": "lake night, folk songs, quiet routes",
                "relationship_setup": "slow trust through shared choices",
                "outline": "lake evening scenes",
            },
            "story_bible": {"confirmed_facts": ["folk songs matter"], "relationships": ["slow trust"]},
            "materials": [],
            "novel_state": {"open_threads": ["unfinished question"]},
        }
        themed = {
            "id": "evt_themed",
            "place": "lake path",
            "time_anchor": "Saturday 18:40, before the lake lights turn on",
            "event": "a folk song rehearsal blocks the lake path and asks them to choose a quieter route",
            "hook": "one unfinished question stays between them",
            "source": "remote",
            "tags": {
                "theme_markers": ["lake", "folk song", "quiet route"],
                "tone_markers": ["warm", "restrained"],
                "relationship_motion": ["slow trust"],
                "boundary_risk": "low",
            },
        }
        generic = {
            "id": "evt_generic",
            "place": "cafe",
            "event": "ordinary misunderstanding lets them chat",
            "hook": "they talk again later",
            "source": "remote",
            "tags": {"boundary_risk": "low"},
        }
        old_shape = {
            "id": "evt_old",
            "place": "lake path",
            "event": "a folk song rehearsal blocks the lake path",
            "hook": "one unfinished question stays between them",
            "source": "manual",
            "tags": {"boundary_risk": "low"},
        }

        themed_score = score_story_event(themed, chapter, context, "modern_daily")
        generic_score = score_story_event(generic, chapter, context, "modern_daily")
        old_score = score_story_event(old_shape, chapter, context, "modern_daily")

        self.assertGreater(themed_score["score"], generic_score["score"])
        self.assertGreater(themed_score["score"], old_score["score"])
        self.assertIn("命中主题", themed_score["reasons"][0])
        self.assertTrue(any("具体时间" in reason for reason in themed_score["reasons"]))

    def test_story_event_score_prefers_remote_candidate_over_setting_profile(self) -> None:
        chapter = {
            "chapter_order": 2,
            "status": "planned",
            "goal": "湖边夜景和民谣声让两人重新选择路线。",
            "external_event": "湖边夜景路线变化",
            "ending_hook": "未问完的问题留下来",
        }
        context = {
            "project": {
                "title": "湖边民谣",
                "genre": "现代日常长篇",
                "tone": "温柔克制",
                "worldview": "湖边夜景、民谣、雨后路线",
                "relationship_setup": "慢慢熟悉",
            },
            "story_bible": {"confirmed_facts": ["用户喜欢民谣"]},
            "materials": [],
            "novel_state": {"open_threads": ["未问完的问题"]},
        }
        setting_event = {
            "id": "evt_setting",
            "place": "湖边步道",
            "event": "湖边夜景路线变化",
            "hook": "未问完的问题留下来",
            "source": "setting_profile",
            "tags": {"boundary_risk": "low"},
        }
        remote_event = {
            **setting_event,
            "id": "evt_remote",
            "source": "remote",
            "time_anchor": "周六 19:20，湖边路灯刚亮起",
            "source_reason": "滚动新增，承接湖边民谣和未问完的问题",
            "tags": {
                "theme_markers": ["湖边", "民谣", "夜景"],
                "tone_markers": ["温柔", "克制"],
                "boundary_risk": "low",
            },
        }

        self.assertGreater(
            score_story_event(remote_event, chapter, context, "modern_daily")["score"],
            score_story_event(setting_event, chapter, context, "modern_daily")["score"],
        )

    def test_story_event_score_prefers_progression_protocol_fit(self) -> None:
        chapter = {
            "chapter_order": 2,
            "status": "planned",
            "goal": "雨夜路线变化让两个人必须重新确认选择。",
            "external_event": "雨夜路线变化",
            "ending_hook": "没说完的理由留下来",
            "progression_role": "压力下的共同选择",
        }
        context = {
            "project": {
                "title": "雨夜同行",
                "genre": "悬疑探险",
                "tone": "紧张、克制",
                "worldview": "雨夜街区、路线变化、未确认信息",
                "relationship_setup": "通过共同选择建立谨慎信任",
            },
            "story_promise": {
                "core_experience": "在不可靠信息里共同选择路线",
                "genre_contract": "每章有一个可见压力和一个未确认事实",
                "relationship_engine": "关系通过共同判断推进",
                "tone_commitment": "紧张、克制、留白",
            },
            "progression_protocol": {
                "driver": "用外部压力逼迫角色做小选择",
                "progression_tools": ["路线变化", "未确认信息", "共同选择"],
                "chapter_rules": ["每章兑现一个可见压力"],
                "relationship_rule": "不直接亲密，通过判断建立信任",
                "drift_guards": ["不要变成泛泛聊天"],
                "style_directives": ["克制"],
            },
        }
        matched = {
            "id": "evt_protocol",
            "place": "雨后街角",
            "time_anchor": "周六 20:10",
            "event": "雨夜路线突然被封，两人必须在未确认信息里共同选择绕行方向",
            "hook": "没说完的理由留下来",
            "source": "remote",
            "source_reason": "滚动新增，承接推进协议",
            "tags": {
                "theme_markers": ["雨夜", "路线变化"],
                "tone_markers": ["紧张", "克制"],
                "progression_role": "压力下的共同选择",
                "progression_markers": ["路线变化", "未确认信息", "共同选择"],
                "promise_markers": ["可见压力", "未确认事实"],
                "boundary_risk": "low",
            },
        }
        generic = {
            **matched,
            "id": "evt_generic_protocol",
            "event": "两个人在街角继续普通聊天",
            "source": "setting_profile",
            "source_reason": "",
            "tags": {"boundary_risk": "low"},
        }

        matched_score = score_story_event(matched, chapter, context, "mystery")
        generic_score = score_story_event(generic, chapter, context, "mystery")

        self.assertGreater(matched_score["score"], generic_score["score"])
        self.assertTrue(any("命中推进协议" in reason for reason in matched_score["reasons"]))

    def test_story_progression_defaults_backfill_old_canvas(self) -> None:
        canvas = normalize_story_progression(
            {
                "version": 1,
                "mode": "story_canvas",
                "chapters": [
                    {
                        "id": "canvas_ch_1",
                        "chapter_order": 1,
                        "goal": "雨后街区里两人重新确认路线。",
                    }
                ],
            },
            {
                "title": "雨夜同行",
                "genre": "悬疑探险",
                "tone": "紧张、克制",
                "worldview": "雨夜街区",
                "relationship_setup": "共同判断",
            },
        )

        self.assertIn("story_promise", canvas)
        self.assertIn("progression_protocol", canvas)
        self.assertTrue(canvas["chapters"][0]["chapter_drive"])
        self.assertTrue(canvas["chapters"][0]["promise_targets"])

    def test_canvas_parsing_translates_english_scene_display_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            fallback = service._default_extension_canvas(
                {
                    "id": "p1",
                    "title": "职场风雨",
                    "genre": "现代职场",
                    "tone": "冷静克制",
                    "protagonist": "许观清",
                    "worldview": "公司大楼和雨夜通勤",
                    "relationship_setup": "许观清和林悦在工作事件中建立信任",
                },
                {},
                0,
                1,
            )
            raw = {
                "version": 1,
                "mode": "story_canvas",
                "acts": fallback["acts"],
                "chapters": [
                    {
                        "id": "canvas_ch_1",
                        "chapter_order": 1,
                        "title": "第一章 风雨门口",
                        "goal": "许观清和林悦在公司门口遇到突发事件。",
                        "external_event": "公司门口的突发雨势打乱两人的下班计划",
                        "trigger_event": "林悦发现原定路线被临时封闭",
                        "ending_hook": "林悦留下一个没有解释的提醒",
                        "scene_ids": ["scene_1"],
                    }
                ],
                "scenes": [
                    {
                        "id": "scene_1",
                        "chapter_id": "canvas_ch_1",
                        "current_scene": "company_building_front",
                        "pov": "third_person",
                        "present_characters": ["许观清", "林悦"],
                        "surface_event": "雨势变大",
                        "tension": "路线被封闭",
                        "ending_beat": "林悦回头提醒",
                    }
                ],
            }

            parsed = service._parse_canvas_response(json.dumps(raw, ensure_ascii=False), fallback)
            scene = parsed["scenes"][0]

            self.assertEqual(scene["current_scene"], "公司大楼门口")
            self.assertEqual(scene["pov"], "第三人称限知")
            self.assertEqual(scene["present_characters"], "许观清、林悦")

    def test_compact_canvas_syncs_bound_event_contract_to_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            canvas = {
            "version": 1,
            "mode": "story_canvas",
            "event_pool": {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [
                    {
                        "id": "evt_remote",
                        "place": "湖边小路",
                        "time_anchor": "周六 19:20",
                        "event": "湖边灯光突然熄灭，两人需要临时改路",
                        "hook": "水声盖过了林悦没说完的话",
                        "source": "remote",
                        "use_mode": "guide",
                        "tags": {
                            "theme_markers": ["湖边", "改路"],
                            "tone_markers": ["克制"],
                            "progression_role": "压力下的共同选择",
                            "progression_markers": ["临时改路", "共同选择"],
                            "promise_markers": ["可见压力"],
                            "boundary_risk": "low",
                        },
                    }
                ],
                "retired": [],
            },
            "chapters": [
                {
                    "id": "canvas_ch_1",
                    "act_id": "act_1",
                    "chapter_order": 1,
                    "title": "第一章 湖边",
                    "goal": "两人遇到临时改路。",
                    "external_event": "",
                    "trigger_event": "",
                    "ending_hook": "",
                    "status": "planned",
                    "scene_ids": ["scene_1"],
                }
            ],
            "scenes": [{"id": "scene_1", "chapter_id": "canvas_ch_1", "scene_order": 1}],
            "acts": [{"id": "act_1", "order": 1, "title": "开端", "purpose": "", "chapter_ids": ["canvas_ch_1"]}],
        }

            compacted = service._compact_story_canvas(canvas)
            chapter = compacted["chapters"][0]
            scene = compacted["scenes"][0]

            self.assertEqual(chapter["event_contract"]["event_id"], "evt_remote")
            self.assertEqual(chapter["external_event"], "湖边灯光突然熄灭，两人需要临时改路")
            self.assertEqual(scene["current_scene"], "周六 19:20，湖边小路")

    def test_character_seed_flavor_cannot_outscore_project_continuity(self) -> None:
        chapter = {
            "chapter_order": 3,
            "status": "planned",
            "goal": "At the lake, the previous unfinished question returns during a folk-song rehearsal.",
            "external_event": "lake night folk song interruption",
            "ending_hook": "unfinished question",
        }
        context = {
            "project": {
                "title": "Lake Folk Case",
                "genre": "modern daily longform",
                "tone": "warm restrained",
                "worldview": "lake night, folk songs, quiet routes",
                "relationship_setup": "slow trust through shared choices",
            },
            "story_bible": {"confirmed_facts": ["folk songs matter"]},
            "novel_state": {"open_threads": ["unfinished question"]},
            "character": {
                "story_seed_pool": {
                    "motifs": ["folded note", "rain light"],
                    "event_seeds": ["a familiar default meeting repeats"],
                    "hook_seeds": ["a folded note becomes a reason to meet"],
                }
            },
        }
        project_event = {
            "id": "evt_project",
            "place": "lake path",
            "time_anchor": "Saturday 18:40",
            "event": "a folk song rehearsal blocks the lake path and asks them to choose a quieter route",
            "hook": "unfinished question",
            "source": "remote",
            "tags": {
                "theme_markers": ["lake", "folk songs"],
                "tone_markers": ["warm", "restrained"],
                "relationship_motion": ["shared choice"],
                "boundary_risk": "low",
            },
        }
        character_seed_event = {
            "id": "evt_character",
            "place": "old default doorway",
            "time_anchor": "Saturday 18:40",
            "event": "a familiar default meeting repeats around the folded note and rain light",
            "hook": "a folded note becomes a reason to meet",
            "source": "character_seed",
            "tags": {
                "theme_markers": ["folded note", "rain light"],
                "tone_markers": ["quiet"],
                "relationship_motion": ["familiar motif"],
                "boundary_risk": "low",
            },
        }

        project_score = score_story_event(project_event, chapter, context, "modern_daily")
        character_score = score_story_event(character_seed_event, chapter, context, "modern_daily")

        self.assertGreater(project_score["score"], character_score["score"])
        self.assertIn("character flavor seed", character_score["reasons"])

    def test_story_event_score_blocks_campus_defaults_in_non_campus(self) -> None:
        scored = score_story_event(
            {
                "id": "evt_library",
                "place": "library",
                "time_anchor": "Friday 19:00",
                "event": "a club announcement on the library board changes the class plan",
                "hook": "the class notice leaves one missing name",
                "tags": {
                    "theme_markers": ["library", "club"],
                    "tone_markers": ["quiet"],
                    "boundary_risk": "low",
                    "forbidden_defaults": ["library"],
                },
            },
            {"chapter_order": 1, "status": "planned", "external_event": "library announcement"},
            {"project": {"genre": "xianxia wuxia", "worldview": "mountain sect and medicine"}},
            "xianxia_wuxia",
        )

        self.assertTrue(scored["blocked"])
        self.assertEqual(scored["score"], 0)

    def test_compact_canvas_rebinds_mismatched_event_pool_id_and_marks_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            canvas = {
                "version": 1,
                "mode": "story_canvas",
                "event_pool": {
                    "version": 1,
                    "setting_type": "modern_daily",
                    "active": [
                        {"id": "evt_1", "place": "街角咖啡店", "event": "咖啡店临时变更。", "hook": "路灯亮起。"},
                        {"id": "evt_2", "place": "社区书店", "event": "书店错拿让两人停下处理误会。", "hook": "收据背面多出时间。"},
                    ],
                    "retired": [],
                },
                "chapters": [
                    {
                        "id": "canvas_ch_1",
                        "act_id": "act_1",
                        "chapter_order": 1,
                        "event_pool_id": "evt_1",
                        "title": "第一章",
                        "external_event": "书店错拿让两人停下处理误会。",
                        "trigger_event": "书店错拿让两人停下处理误会。",
                        "goal": "",
                        "scene_ids": ["scene_1"],
                    }
                ],
                "scenes": [{"id": "scene_1", "chapter_id": "canvas_ch_1", "scene_order": 1}],
                "acts": [{"id": "act_1", "order": 1, "title": "阶段", "chapter_ids": ["canvas_ch_1"]}],
                "threads": [],
                "diagnostics": {"setting_type": "modern_daily"},
            }

            compacted = service._compact_story_canvas(canvas)
            chapter = compacted["chapters"][0]
            bound_event = next(item for item in compacted["event_pool"]["active"] if item["id"] == "evt_2")

            self.assertEqual(chapter["event_pool_id"], "evt_2")
            self.assertEqual(bound_event["status"], "planned")
            self.assertEqual(bound_event["bound_chapter_orders"], ["1"])

    def test_extend_canvas_runs_event_pool_update_before_canvas(self) -> None:
        class FakeParallelCanvasLlm:
            def __init__(self, retire_id: str) -> None:
                self.retire_id = retire_id
                self.active_calls = 0
                self.max_active_calls = 0
                self.system_prompts: list[str] = []
                self.last_chat_error = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.system_prompts.append(messages[0]["content"])
                self.active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self.active_calls)
                await asyncio.sleep(0.02)
                self.active_calls -= 1
                system = messages[0]["content"]
                if "long-form novel project event pool" in system:
                    return json.dumps({
                        "event_pool_delta": {
                            "retire": [{"id": self.retire_id}],
                            "add": [
                                {
                                    "id": "evt_parallel_new",
                                    "place": "parallel rain stop",
                                    "time_anchor": "Friday 19:10, after the last tram alert",
                                    "event": "a delayed tram gives both characters one concrete problem to solve",
                                    "hook": "the route map reveals one missing stop",
                                    "motifs": ["rain map"],
                                    "tags": {
                                        "event_type": ["external_interrupt", "shared_route"],
                                        "anchors": ["delayed tram", "route map"],
                                        "theme_markers": ["tram delay", "route map", "rain"],
                                        "tone_markers": ["restrained", "quiet"],
                                        "relationship_motion": ["shared_context", "slow_trust"],
                                        "boundary_risk": "low",
                                        "freshness": ["new_location"],
                                        "continuity": ["unresolved route clue"],
                                        "forbidden_defaults": [],
                                    },
                                    "source_reason": "parallel event pool update",
                                }
                            ],
                        }
                    })
                return json.dumps({
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [{"id": "act_remote", "order": 2, "title": "remote arc", "chapter_ids": ["remote_ch_1", "remote_ch_2"]}],
                    "chapters": [
                        {
                            "id": "remote_ch_1",
                            "act_id": "act_remote",
                            "chapter_order": 2,
                            "title": "Chapter 2",
                            "goal": "The two characters handle the delayed tram and keep one question unresolved.",
                            "external_event": "a delayed tram gives both characters one concrete problem to solve",
                            "trigger_event": "a delayed tram gives both characters one concrete problem to solve",
                            "immediate_reaction": "They first solve the visible problem.",
                            "obstacle_escalation": "The route information conflicts.",
                            "counterpart_reaction": "The other character checks the map.",
                            "character_choice": "The protagonist chooses to wait.",
                            "scene_consequence": "They gain one shared clue.",
                            "relationship_shift": "They become slightly more coordinated.",
                            "ending_hook": "the route map reveals one missing stop",
                            "target_length": 1800,
                            "status": "planned",
                            "emotion_curve": "steady",
                            "scene_ids": ["remote_scene_1"],
                        },
                        {
                            "id": "remote_ch_2",
                            "act_id": "act_remote",
                            "chapter_order": 3,
                            "title": "Chapter 3",
                            "goal": "A second scene follows the clue without resolving it too early.",
                            "external_event": "a saved receipt points to the wrong meeting time",
                            "trigger_event": "a saved receipt points to the wrong meeting time",
                            "immediate_reaction": "They compare the receipt.",
                            "obstacle_escalation": "The time does not match.",
                            "counterpart_reaction": "The other character stays cautious.",
                            "character_choice": "The protagonist asks one direct question.",
                            "scene_consequence": "The clue remains active.",
                            "relationship_shift": "Trust grows slowly.",
                            "ending_hook": "one name on the receipt is missing",
                            "target_length": 1800,
                            "status": "planned",
                            "emotion_curve": "steady",
                            "scene_ids": ["remote_scene_2"],
                        },
                    ],
                    "scenes": [
                        {
                            "id": "remote_scene_1",
                            "chapter_id": "remote_ch_1",
                            "scene_order": 1,
                            "current_scene": "parallel rain stop",
                            "pov": "limited third person",
                            "present_characters": "protagonist and counterpart",
                            "surface_event": "a delayed tram gives both characters one concrete problem to solve",
                            "character_desire": "solve the visible problem",
                            "tension": "the route information conflicts",
                            "required_facts": [],
                            "forbidden_progress": [],
                            "ending_beat": "the route map reveals one missing stop",
                            "linked_material_ids": [],
                        },
                        {
                            "id": "remote_scene_2",
                            "chapter_id": "remote_ch_2",
                            "scene_order": 1,
                            "current_scene": "receipt counter",
                            "pov": "limited third person",
                            "present_characters": "protagonist and counterpart",
                            "surface_event": "a saved receipt points to the wrong meeting time",
                            "character_desire": "compare the receipt",
                            "tension": "the time does not match",
                            "required_facts": [],
                            "forbidden_progress": [],
                            "ending_beat": "one name on the receipt is missing",
                            "linked_material_ids": [],
                        },
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote", "mode": "rolling_extend"},
                })

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            card = CharacterStore().get("lin_wanzhi")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            retire_id = project.story_canvas["event_pool"]["active"][0]["id"]
            llm = FakeParallelCanvasLlm(retire_id)

            asyncio.run(service.extend_canvas(llm, project.id, from_chapter_order=1, count=2))
            updated = storage.get_novel_project(project.id)
            assert updated is not None
            canvas = json.loads(updated["story_canvas_json"])
            active_ids = [item["id"] for item in canvas["event_pool"]["active"]]
            retired_ids = [item["id"] for item in canvas["event_pool"]["retired"]]

            self.assertEqual(llm.max_active_calls, 1)
            self.assertIn("long-form novel project event pool", llm.system_prompts[0])
            self.assertNotIn("long-form novel project event pool", llm.system_prompts[1])
            self.assertIn("evt_parallel_new", active_ids)
            self.assertIn(retire_id, retired_ids)
            selected = next(item for item in canvas["event_pool"]["active"] if item["id"] == "evt_parallel_new")
            self.assertGreater(selected["selection_score"], 0)
            self.assertTrue(selected["selection_reasons"])
            self.assertEqual(selected["time_anchor"], "Friday 19:10, after the last tram alert")
            self.assertEqual(selected["tags"]["boundary_risk"], "low")
            self.assertEqual(selected["tags"]["theme_markers"], ["tram delay", "route map", "rain"])
            self.assertEqual(canvas["diagnostics"]["event_pool_update_source"], "remote")
            self.assertTrue(canvas["diagnostics"]["event_pool_first_update"])
            self.assertFalse(canvas["diagnostics"]["parallel_event_pool_update"])

    def test_canvas_extend_api_preserves_time_anchor_and_theme_tags(self) -> None:
        class FakeApiCanvasLlm:
            last_chat_error = None

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                system = messages[0]["content"]
                if "long-form novel project event pool" in system:
                    return json.dumps({
                        "event_pool_delta": {
                            "add": [
                                {
                                    "id": "evt_api_theme",
                                    "place": "lake bus stop",
                                    "time_anchor": "Saturday 18:40, before the lake lights turn on",
                                    "event": "a folk-song busker blocks the lake stop and forces one route choice",
                                    "hook": "the unfinished melody repeats the question they avoided",
                                    "motifs": ["folk melody"],
                                    "tags": {
                                        "event_type": ["external_interrupt"],
                                        "anchors": ["lake stop", "folk melody"],
                                        "theme_markers": ["lake", "folk melody", "route choice"],
                                        "tone_markers": ["warm", "restrained"],
                                        "relationship_motion": ["slow_trust"],
                                        "boundary_risk": "low",
                                        "freshness": ["new_time_anchor"],
                                        "continuity": ["unfinished question"],
                                        "forbidden_defaults": [],
                                    },
                                    "source_reason": "uses the lake, folk music, and restrained tone",
                                }
                            ]
                        }
                    })
                return json.dumps({
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [{"id": "act_api", "order": 2, "title": "api arc", "chapter_ids": ["api_ch_2"]}],
                    "chapters": [
                        {
                            "id": "api_ch_2",
                            "act_id": "act_api",
                            "chapter_order": 2,
                            "title": "Lake Stop",
                            "goal": "The lake bus stop folk-song interruption forces one route choice and leaves the melody unresolved.",
                            "external_event": "a folk-song busker blocks the lake stop and forces one route choice",
                            "trigger_event": "a folk-song busker blocks the lake stop and forces one route choice",
                            "immediate_reaction": "They check the stop together.",
                            "obstacle_escalation": "The bus stop route is blocked.",
                            "counterpart_reaction": "The counterpart stays cautious.",
                            "character_choice": "The protagonist chooses the quieter route.",
                            "scene_consequence": "They keep moving without forcing intimacy.",
                            "relationship_shift": "Slow trust becomes easier to notice.",
                            "ending_hook": "the unfinished melody repeats the question they avoided",
                            "target_length": 1800,
                            "status": "planned",
                            "emotion_curve": "restrained",
                            "scene_ids": ["api_scene_2"],
                        }
                    ],
                    "scenes": [
                        {
                            "id": "api_scene_2",
                            "chapter_id": "api_ch_2",
                            "scene_order": 1,
                            "current_scene": "lake bus stop",
                            "pov": "limited third person",
                            "present_characters": "protagonist and counterpart",
                            "surface_event": "a folk-song busker blocks the lake stop and forces one route choice",
                            "character_desire": "choose a route",
                            "tension": "the blocked stop delays them",
                            "required_facts": [],
                            "forbidden_progress": [],
                            "ending_beat": "the unfinished melody repeats the question they avoided",
                            "linked_material_ids": [],
                        }
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote", "mode": "rolling_extend"},
                })

        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            app = create_app(storage=storage, characters=CharacterStore(), llm=FakeApiCanvasLlm())
            client = TestClient(app)
            visitor_id = "canvas-api-tester"
            session = client.post("/api/sessions", json={"visitor_id": visitor_id, "character_id": "lin_wanzhi"})
            self.assertEqual(session.status_code, 200)
            project_response = client.post(f"/api/sessions/{session.json()['session_id']}/novel/projects", json={
                "title": "Lake Folk Case",
                "genre": "modern daily longform",
                "tone": "warm restrained daily",
                "worldview": "lake night, folk songs, quiet routes",
                "relationship_setup": "slow trust through shared choices",
            })
            self.assertEqual(project_response.status_code, 200)

            extended = client.post(
                f"/api/novel/projects/{project_response.json()['id']}/canvas/extend",
                json={"from_chapter_order": 1, "count": 2, "instruction": "extend with theme-aware event pool"},
            )
            self.assertEqual(extended.status_code, 200)
            canvas = extended.json()["story_canvas"]
            selected = next(item for item in canvas["event_pool"]["active"] if item["id"] == "evt_api_theme")
            chapter = next(item for item in canvas["story_canvas"]["chapters"] if item["chapter_order"] == 2) if "story_canvas" in canvas else next(item for item in canvas["chapters"] if item["chapter_order"] == 2)

            self.assertEqual(selected["time_anchor"], "Saturday 18:40, before the lake lights turn on")
            self.assertEqual(selected["tags"]["theme_markers"], ["lake", "folk melody", "route choice"])
            self.assertGreater(selected["selection_score"], 0)
            self.assertEqual(chapter["event_pool_id"], "evt_api_theme")
            self.assertEqual(canvas["diagnostics"]["event_pool_update_source"], "remote")

    def test_completed_chapter_advances_project_event_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            card = CharacterStore().get("lin_wanzhi")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            first_chapter = storage.list_novel_chapters(project.id)[0]
            canvas = project.story_canvas
            canvas["chapters"][0]["event_pool_id"] = canvas["event_pool"]["active"][0]["id"]
            storage.update_novel_project(project.id, {"story_canvas": canvas})

            service._update_canvas_from_completed_chapter(
                project.id,
                first_chapter,
                {"current_scene": "updated scene", "surface_event": "updated event"},
                {"title": "done", "summary": "chapter done", "body": "body"},
            )
            updated = storage.get_novel_project(project.id)
            updated_canvas = json.loads(updated["story_canvas_json"])

            self.assertEqual(len(updated_canvas["event_pool"]["active"]), 10)
            self.assertEqual(updated_canvas["event_pool"]["retired"][0]["id"], canvas["chapters"][0]["event_pool_id"])
            self.assertEqual(updated_canvas["event_pool"]["retired"][0]["status"], "retired")

    def test_completed_chapter_advances_event_pool_without_bound_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            card = CharacterStore().get("lin_wanzhi")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            first_chapter = storage.list_novel_chapters(project.id)[0]
            canvas = project.story_canvas
            canvas["chapters"][0]["event_pool_id"] = ""
            expected_retired_id = canvas["event_pool"]["active"][0]["id"]
            storage.update_novel_project(project.id, {"story_canvas": canvas})

            service._update_canvas_from_completed_chapter(
                project.id,
                first_chapter,
                {"current_scene": "雨后人行道", "surface_event": "雨后路面碎水让同行路线改变。"},
                {"title": "第一章", "summary": "第一章完成。", "body": "正文"},
            )
            updated = storage.get_novel_project(project.id)
            assert updated is not None
            updated_canvas = json.loads(updated["story_canvas_json"])

            self.assertEqual(len(updated_canvas["event_pool"]["active"]), 10)
            self.assertEqual(updated_canvas["event_pool"]["retired"][0]["id"], expected_retired_id)
            self.assertEqual(updated_canvas["event_pool"]["retired"][0]["status"], "retired")

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
        self.assertEqual(parsed["interaction_policy"]["action_density"], "")
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

    def test_novel_build_canvas_resets_existing_event_pool_on_fallback(self) -> None:
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
            old_canvas = dict(project.story_canvas)
            old_canvas["event_pool"] = {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [
                    {
                        "id": "evt_old_rebuild_leak",
                        "place": "old dock",
                        "event": "DO_NOT_KEEP_OLD_POOL",
                        "hook": "old hook",
                        "status": "planned",
                        "source": "remote",
                        "bound_chapter_orders": [3],
                    }
                ],
                "retired": [],
            }
            storage.update_novel_project(project.id, {"story_canvas": old_canvas})

            rebuilt = self.run_async(service.build_canvas(CanvasFallbackLlm(), project.id))
            combined = json.dumps(rebuilt.story_canvas.get("event_pool", {}), ensure_ascii=False)

            self.assertNotIn("evt_old_rebuild_leak", combined)
            self.assertNotIn("DO_NOT_KEEP_OLD_POOL", combined)
            self.assertEqual(rebuilt.story_canvas["diagnostics"]["mode"], "initial_rolling")
            self.assertTrue(rebuilt.story_canvas["diagnostics"]["event_pool_reset"])

    def test_novel_build_canvas_remote_prompt_does_not_include_existing_event_pool(self) -> None:
        class CanvasLlm:
            last_chat_error = None

            def __init__(self) -> None:
                self.user_sources = []

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.user_sources.append(messages[1]["content"])
                return json.dumps({
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [{"id": "act_1", "order": 1, "title": "Fresh act", "purpose": "Fresh start", "chapter_ids": ["canvas_ch_1"]}],
                    "chapters": [
                        {
                            "id": "canvas_ch_1",
                            "act_id": "act_1",
                            "chapter_order": 1,
                            "title": "Chapter 1 Fresh Start",
                            "goal": "A fresh visible event starts the new canvas.",
                            "external_event": "A fresh visible event",
                            "trigger_event": "A fresh visible event",
                            "immediate_reaction": "The protagonist handles the new event.",
                            "obstacle_escalation": "A time limit interrupts the conversation.",
                            "counterpart_reaction": "The counterpart gives a bounded response.",
                            "character_choice": "The protagonist makes a small choice.",
                            "scene_consequence": "The scene leaves a new hook.",
                            "relationship_shift": "They gain one shared reference.",
                            "ending_hook": "A fresh hook remains.",
                            "target_length": 1800,
                            "status": "planned",
                            "emotion_curve": "calm -> pressure -> held",
                            "scene_ids": ["scene_1"],
                        }
                    ],
                    "scenes": [
                        {
                            "id": "scene_1",
                            "chapter_id": "canvas_ch_1",
                            "scene_order": 1,
                            "current_scene": "fresh place",
                            "pov": "third person limited",
                            "present_characters": "protagonist, counterpart",
                            "surface_event": "A fresh visible event",
                            "character_desire": "Handle the event without overexplaining.",
                            "tension": "A time limit interrupts the conversation.",
                            "required_facts": [],
                            "forbidden_progress": [],
                            "ending_beat": "A fresh hook remains.",
                            "linked_material_ids": [],
                        }
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote"},
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            old_canvas = dict(project.story_canvas)
            old_canvas["event_pool"] = {
                "version": 1,
                "setting_type": "modern_daily",
                "active": [{"id": "evt_old_prompt_leak", "place": "old place", "event": "DO_NOT_KEEP_OLD_POOL", "hook": "old hook"}],
                "retired": [],
            }
            storage.update_novel_project(project.id, {"story_canvas": old_canvas})

            llm = CanvasLlm()
            rebuilt = self.run_async(service.build_canvas(llm, project.id))
            combined = json.dumps(rebuilt.story_canvas.get("event_pool", {}), ensure_ascii=False)
            combined_sources = "\n".join(llm.user_sources)

            self.assertNotIn("DO_NOT_KEEP_OLD_POOL", combined_sources)
            self.assertNotIn("evt_old_prompt_leak", combined)
            self.assertNotIn("DO_NOT_KEEP_OLD_POOL", combined)
            self.assertTrue(rebuilt.story_canvas["diagnostics"]["event_pool_reset"])

    def test_novel_build_canvas_initial_event_pool_uses_remote_delta(self) -> None:
        class CanvasLlm:
            last_chat_error = None
            calls = 0

            def configured(self) -> bool:
                return True

            async def chat_complete(self, messages, timeout_ms=None, response_format=None):
                self.calls += 1
                if str(messages[0]["content"]).startswith("You maintain a long-form novel project event pool"):
                    return json.dumps({
                        "event_pool_delta": {
                            "add": [
                                {
                                    "place": f"remote place {index}",
                                    "time_anchor": f"Saturday 18:{index}0, before the lamps change",
                                    "event": f"A project-specific remote incident {index} forces a visible choice.",
                                    "hook": f"Remote hook {index} leaves one concrete question.",
                                    "motifs": [f"remote motif {index}"],
                                    "source_reason": "initial remote event pool",
                                    "tags": {
                                        "event_type": ["choice"],
                                        "anchors": ["project"],
                                        "theme_markers": ["remote", "opening"],
                                        "tone_markers": ["restrained"],
                                        "relationship_motion": ["bounded cooperation"],
                                        "boundary_risk": "low",
                                        "freshness": ["new"],
                                        "continuity": ["opening"],
                                        "forbidden_defaults": [],
                                    },
                                }
                                for index in range(1, 7)
                            ],
                            "update": [],
                            "retire": [],
                        }
                    }, ensure_ascii=False)
                return json.dumps({
                    "version": 1,
                    "mode": "story_canvas",
                    "acts": [{"id": "act_1", "order": 1, "title": "Fresh act", "purpose": "Fresh start", "chapter_ids": ["canvas_ch_1"]}],
                    "chapters": [
                        {
                            "id": "canvas_ch_1",
                            "act_id": "act_1",
                            "chapter_order": 1,
                            "title": "Chapter 1 Fresh Start",
                            "goal": "A remote opening incident forces the protagonist to make a visible choice.",
                            "external_event": "A project-specific remote incident 1 forces a visible choice.",
                            "trigger_event": "A project-specific remote incident 1 forces a visible choice.",
                            "immediate_reaction": "The protagonist handles the pressure first.",
                            "obstacle_escalation": "The time window narrows before anyone can explain.",
                            "counterpart_reaction": "The counterpart responds without taking over.",
                            "character_choice": "The protagonist keeps one question for later.",
                            "scene_consequence": "The scene leaves a shared reference.",
                            "relationship_shift": "They gain a bounded shared context.",
                            "ending_hook": "Remote hook 1 leaves one concrete question.",
                            "target_length": 1800,
                            "status": "planned",
                            "emotion_curve": "calm -> pressure -> held",
                            "scene_ids": ["scene_1"],
                        }
                    ],
                    "scenes": [
                        {
                            "id": "scene_1",
                            "chapter_id": "canvas_ch_1",
                            "scene_order": 1,
                            "current_scene": "remote place 1",
                            "pov": "third person limited",
                            "present_characters": "protagonist, counterpart",
                            "surface_event": "A project-specific remote incident 1 forces a visible choice.",
                            "character_desire": "Handle the event without overexplaining.",
                            "tension": "The time window narrows before anyone can explain.",
                            "required_facts": [],
                            "forbidden_progress": [],
                            "ending_beat": "Remote hook 1 leaves one concrete question.",
                            "linked_material_ids": [],
                        }
                    ],
                    "threads": [],
                    "quality_rules": [],
                    "diagnostics": {"source": "remote"},
                }, ensure_ascii=False)

        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())

            llm = CanvasLlm()
            rebuilt = self.run_async(service.build_canvas(llm, project.id))
            active = rebuilt.story_canvas.get("event_pool", {}).get("active", [])
            remote_events = [item for item in active if item.get("source") == "remote"]

            self.assertEqual(llm.calls, 2)
            self.assertEqual(len(active), 10)
            self.assertGreaterEqual(len(remote_events), 6)
            self.assertEqual(rebuilt.story_canvas["diagnostics"]["event_pool_update_source"], "remote")
            self.assertTrue(rebuilt.story_canvas["diagnostics"]["event_pool_first_update"])
            self.assertFalse(rebuilt.story_canvas["diagnostics"]["parallel_event_pool_update"])

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
            self.assertEqual(llm.calls, 2)
            self.assertTrue(all(timeout is not None and timeout >= 120000 for timeout in llm.timeouts))
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
            self.assertEqual(llm.calls, 6)
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
                "continuity_ledger": {
                    "locked_facts": ["新事件"],
                    "changed_states": ["新关系"],
                    "next_must_continue": ["新承接"],
                    "promises_made": ["新钩子"],
                    "avoid_repeating": ["旧场面"],
                    "forbidden_contradictions": ["不能说新事件没发生"],
                },
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
            self.assertIn("新事件", rebuilt["continuity_ledger"]["locked_facts"])
            self.assertIn("新承接", rebuilt["continuity_ledger"]["next_must_continue"])
            self.assertIn("不能说新事件没发生", rebuilt["continuity_ledger"]["forbidden_contradictions"])

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

    def test_chapter_version_snapshot_restores_canvas_event_binding(self) -> None:
        card = CharacterStore().get("lin_wanzhi")
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            visitor_id, _ = storage.resolve_visitor("tester")
            session_id = storage.create_or_get_session(visitor_id, card.id)
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            project = service.create_project(card, visitor_id, session_id, [], [], [], NovelProjectCreateRequest())
            chapter = storage.get_novel_chapter(project.chapters[0].id)
            assert chapter is not None
            canvas = project.story_canvas
            old_event = canvas["event_pool"]["active"][0]
            old_event["use_mode"] = "strict"
            canvas["chapters"][0]["event_pool_id"] = old_event["id"]
            canvas["chapters"][0]["event_pool_score"] = 88
            canvas["chapters"][0]["event_pool_reasons"] = ["old reason"]
            canvas["scenes"][0]["current_scene"] = "old canvas scene"
            storage.update_novel_project(project.id, {"story_canvas": canvas})

            storage.update_novel_chapter(chapter["id"], {
                "title": "Old version",
                "goal": "old goal",
                "summary": "old summary",
                "body": "old body",
                "scene_card": {"current_scene": "old scene", "chapter_handoff": {"happened": ["old"]}, "handoff_source": "remote"},
            }, "remote")
            old_version = storage.list_novel_versions(chapter["id"])[0]
            snapshot = json.loads(old_version["planning_snapshot_json"])
            self.assertEqual(snapshot["event_pool_id"], old_event["id"])
            self.assertEqual(snapshot["event_pool_event"]["use_mode"], "strict")
            self.assertEqual(snapshot["canvas_scene"]["current_scene"], "old canvas scene")

            changed = storage.get_novel_project(project.id)
            changed_canvas = json.loads(changed["story_canvas_json"])
            new_event = changed_canvas["event_pool"]["active"][1]
            changed_canvas["chapters"][0]["event_pool_id"] = new_event["id"]
            changed_canvas["chapters"][0]["event_pool_score"] = 41
            changed_canvas["chapters"][0]["event_pool_reasons"] = ["new reason"]
            changed_canvas["scenes"][0]["current_scene"] = "new canvas scene"
            storage.update_novel_project(project.id, {"story_canvas": changed_canvas})
            storage.update_novel_chapter(chapter["id"], {
                "title": "New version",
                "goal": "new goal",
                "summary": "new summary",
                "body": "new body",
                "scene_card": {"current_scene": "new scene", "chapter_handoff": {"happened": ["new"]}, "handoff_source": "remote"},
            }, "remote")

            self.assertTrue(storage.restore_novel_version(old_version["id"]))
            restored_project = storage.get_novel_project(project.id)
            restored_canvas = json.loads(restored_project["story_canvas_json"])
            restored_chapter = restored_canvas["chapters"][0]
            restored_event = next(item for item in restored_canvas["event_pool"]["active"] if item["id"] == old_event["id"])
            self.assertEqual(restored_chapter["event_pool_id"], old_event["id"])
            self.assertEqual(restored_chapter["event_pool_score"], 88)
            self.assertEqual(restored_chapter["event_pool_reasons"], ["old reason"])
            self.assertEqual(restored_canvas["scenes"][0]["current_scene"], "old canvas scene")
            self.assertEqual(restored_event["use_mode"], "strict")

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

    def test_initial_remote_canvas_completed_status_still_binds_event_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            service = NovelService(CharacterStateService(storage), CharacterBondService(storage), storage)
            fallback = service._default_story_canvas("Test Novel", "modern daily longform", "quiet suspense", "Lin Yue", {}, [])
            text = json.dumps({
                "version": 1,
                "mode": "story_canvas",
                "acts": [{"id": "act_1", "order": 1, "title": "Opening", "purpose": "start the promise"}],
                "chapters": [{
                    "id": "ch_1",
                    "act_id": "act_1",
                    "chapter_order": 1,
                    "title": "Chapter 1 Rain Detour",
                    "goal": "Use the rain detour to start the first shared choice.",
                    "external_event": "A rainstorm blocks the lakeside road and forces both characters to choose a safer detour.",
                    "trigger_event": "A rainstorm blocks the lakeside road and forces both characters to choose a safer detour.",
                    "immediate_reaction": "Lin Yue slows down and checks whether the other person is following.",
                    "obstacle_escalation": "The nearest exit is suddenly closed.",
                    "counterpart_reaction": "The other person points out a narrow side path.",
                    "character_choice": "Lin Yue chooses the detour instead of rushing through the rain.",
                    "scene_consequence": "They arrive late but notice the same strange clue.",
                    "relationship_shift": "cautious cooperation",
                    "ending_hook": "The last streetlight flickers and reveals a hidden note.",
                    "target_length": 1500,
                    "status": "completed",
                    "emotion_curve": "tense to alert",
                    "scene_ids": ["scene_1"],
                }],
                "scenes": [{
                    "id": "scene_1",
                    "chapter_id": "ch_1",
                    "scene_order": 1,
                    "current_scene": "lakeside road",
                    "pov": "third_person",
                    "present_characters": ["Lin Yue", "Xu Yanqing"],
                    "surface_event": "The rain blocks the original route.",
                    "character_desire": "Lin Yue wants to understand why the other person appeared here.",
                    "tension": "The exit closure makes every choice feel deliberate.",
                    "required_facts": [],
                    "forbidden_progress": [],
                    "ending_beat": "A hidden note appears under the flickering streetlight.",
                    "linked_material_ids": [],
                }],
                "event_pool": {
                    "version": 1,
                    "setting_type": "modern_daily",
                    "active": [{
                        "id": "evt_remote_rain_detour",
                        "source": "remote",
                        "status": "fresh",
                        "place": "lakeside road",
                        "time_anchor": "Saturday 20:30, before the last streetlight goes out",
                        "event": "A rainstorm blocks the lakeside road and forces both characters to choose a safer detour.",
                        "hook": "The last streetlight flickers and reveals a hidden note.",
                        "motifs": ["rain", "streetlight", "hidden note"],
                        "source_reason": "matches the opening chapter and project tone",
                        "tags": {
                            "theme_markers": ["rain", "detour", "shared choice"],
                            "tone_markers": ["quiet suspense"],
                            "progression_role": "first shared choice",
                        },
                    }],
                    "retired": [],
                },
                "threads": [],
                "quality_rules": [],
                "diagnostics": {"source": "remote", "setting_type": "modern_daily"},
            }, ensure_ascii=False)

            canvas = service._parse_canvas_response(text, fallback)

            chapter = canvas["chapters"][0]
            self.assertEqual(chapter["status"], "planned")
            self.assertEqual(chapter["event_pool_id"], "evt_remote_rain_detour")
            self.assertIn("1", canvas["event_pool"]["active"][0]["bound_chapter_orders"])

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
                storage.update_novel_project(project.id, {"story_canvas": {"chapters": [{"title": "长" * 37000}]}})
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
                    {"story_canvas": {"chapters": [{"title": "长" * 37000}]}},
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
