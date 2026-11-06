"""Controlled model waits exercise turn ordering and freeze at write time."""
from __future__ import annotations

import asyncio
import json

from campus_lite.characters import CharacterStore
from campus_lite.storage import Storage
from campus_lite.features.relationship.memory import MemoryService
from campus_lite.features.relationship.state import CharacterStateService
from campus_lite.features.relationship.bond import CharacterBondService
from campus_lite.features.relationship.postprocess import RelationshipPostprocessService
from test_support import OfflineTestCase


class FakeLlm:
    provider = {"name": "offline"}
    last_chat_error = None

    async def extract_memories(self, user, reply): return []
    async def extract_relationship_events(self, *args): return []
    async def embed_texts(self, *args): return []
    def embedding_provider_name(self): return None


class RelationshipConcurrencyTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.storage = Storage(self.test_root / "relationship.db")
        self.characters = CharacterStore()
        self.card = self.characters.get("lin_wanzhi")
        self.visitor, _ = self.storage.resolve_visitor("ordering-test")
        self.session = self.storage.create_or_get_session(self.visitor, self.card.id)
        self.memory = MemoryService(self.storage)
        self.state = CharacterStateService(self.storage)
        self.bond = CharacterBondService(self.storage)
        self.previous_state = self.state.ensure_state(self.session, self.card)
        self.previous_bond = self.bond.ensure_bond(self.visitor, self.card.id, self.card)

    def service(self, llm):
        return RelationshipPostprocessService(storage=self.storage, characters=self.characters,
            memory=self.memory, character_state=self.state, character_bond=self.bond, llm=llm)

    def args(self, text):
        message = self.storage.add_message(self.session, self.visitor, self.card.id, "user", text)
        return (self.visitor, self.session, message, self.card.id, text, "fictional reply", [], [], self.previous_state, self.previous_bond)

    def test_queued_turn_uses_committed_state_and_cannot_be_overwritten(self):
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()
            seen = []
            class Llm(FakeLlm):
                async def score_character_state(self, card, previous, recent, text, *args):
                    seen.append((text, previous["resonance"]))
                    if text == "old":
                        entered.set()
                        await release.wait()
                    return {"mood": text, "resonance_delta": .02 if text == "old" else .05}
            svc = self.service(Llm())
            old_args, new_args = self.args("old"), self.args("new")
            old = asyncio.create_task(svc.run(*old_args))
            await entered.wait()
            self.storage.set_postprocess_diagnostics(self.session, {"status": "queued", "user_message_id": new_args[2]})
            new = asyncio.create_task(svc.run(*new_args))
            await asyncio.sleep(0)
            self.assertEqual(len(seen), 1)
            release.set()
            await asyncio.wait_for(asyncio.gather(old, new), 3)
            final = self.state.get_state(self.session, self.card)
            self.assertEqual(final["mood"], "new")
            self.assertAlmostEqual(final["resonance"], .37)
            self.assertAlmostEqual(seen[1][1], .32)
            diag = json.loads(self.storage.get_session(self.session)["postprocess_diagnostics_json"])
            self.assertEqual(diag["user_message_id"], new_args[2])
            self.assertEqual(diag["status"], "succeeded")
        asyncio.run(scenario())

    def test_late_older_and_duplicate_turns_are_ignored_after_restart(self):
        seen = []
        class Llm(FakeLlm):
            async def score_character_state(self, card, previous, recent, text, *args):
                seen.append(text)
                return {"mood": text, "resonance_delta": .05}
        old, new = self.args("old"), self.args("new")
        asyncio.run(self.service(Llm()).run(*new))
        asyncio.run(self.service(Llm()).run(*old))
        asyncio.run(self.service(Llm()).run(*new))
        self.assertEqual(seen, ["new"])
        self.storage.set_postprocess_diagnostics(self.session, {"status": "queued", "user_message_id": old[2]})
        diag = json.loads(self.storage.get_session(self.session)["postprocess_diagnostics_json"])
        self.assertEqual(diag["user_message_id"], new[2])

    def test_freeze_during_extraction_prevents_memory_write(self):
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()
            class Llm(FakeLlm):
                async def extract_memories(self, *args):
                    entered.set()
                    await release.wait()
                    return [{"memory_type": "user_preference", "content": "Fictional blue notebooks", "confidence": .9}]
                async def score_character_state(self, *args): return {}
            task = asyncio.create_task(self.service(Llm()).run(*self.args("freeze test")))
            await entered.wait()
            self.storage.update_session_memory(self.session, frozen=True)
            release.set()
            await task
            self.assertEqual(self.memory.list_memories(self.session), [])
            diag = json.loads(self.storage.get_session(self.session)["postprocess_diagnostics_json"])
            self.assertEqual(diag["stages"]["memory"]["reason"], "session_frozen")
        asyncio.run(scenario())

    def test_frozen_memory_write_is_rejected_at_storage_boundary(self):
        message = self.args("frozen")[2]
        self.storage.update_session_memory(self.session, frozen=True)
        result = self.memory.add_extracted(self.visitor, self.session, self.card.id, message,
            [{"memory_type": "user_preference", "content": "fictional", "confidence": .9}])
        self.assertEqual(result, [])
        self.assertEqual(self.memory.list_memories(self.session), [])
