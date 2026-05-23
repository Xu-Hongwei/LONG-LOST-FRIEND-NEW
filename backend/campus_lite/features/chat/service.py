from __future__ import annotations

import logging
import time

from fastapi import BackgroundTasks, HTTPException

from ...characters import CharacterStore
from ...composer import ComposeInput, ContextComposer
from ...llm import LlmClient
from ...schemas import (
    ChatMessage,
    ChatResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SessionResponse,
    StoryPaneResponse,
)
from ...storage import Storage
from ...story import StoryService
from ..relationship.bond import CharacterBondService
from ..relationship.memory import MemoryService
from ..relationship.postprocess import RelationshipPostprocessService
from ..relationship.state import CharacterStateService
from .time_awareness import build_time_awareness


logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ChatService:
    def __init__(
        self,
        *,
        storage: Storage,
        characters: CharacterStore,
        memory: MemoryService,
        story: StoryService,
        character_state: CharacterStateService,
        character_bond: CharacterBondService,
        composer: ContextComposer,
        llm: LlmClient,
    ) -> None:
        self.storage = storage
        self.characters = characters
        self.memory = memory
        self.story = story
        self.character_state = character_state
        self.character_bond = character_bond
        self.composer = composer
        self.llm = llm
        self.postprocess = RelationshipPostprocessService(
            storage=storage,
            characters=characters,
            memory=memory,
            character_state=character_state,
            character_bond=character_bond,
            llm=llm,
        )

    def create_session(self, payload: CreateSessionRequest) -> SessionResponse:
        visitor_id, _ = self.storage.resolve_visitor(payload.visitor_id)
        try:
            card = self.characters.get(payload.character_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        session_id = self.storage.create_or_get_session(visitor_id, card.id)
        session = self.storage.get_session(session_id)
        if not self.storage.recent_messages(session_id, 1):
            self.storage.add_message(session_id, visitor_id, card.id, "assistant", card.opening_line)
        state = self.character_state.ensure_state(session_id, card)
        bond = self.character_bond.ensure_bond(visitor_id, card.id, card)
        return SessionResponse(
            session_id=session_id,
            visitor_id=visitor_id,
            character_id=card.id,
            character=card,
            character_state=state,
            character_bond=bond,
            messages=[
                ChatMessage(
                    id=item["id"],
                    role=item["role"],
                    content=item["content"],
                    created_at=item["created_at"],
                )
                for item in self.storage.session_messages(session_id, 40)
            ],
            memory_pane=self.memory.build_pane(session_id),
        )

    async def send_message(self, payload: SendMessageRequest, background_tasks: BackgroundTasks) -> ChatResponse:
        started = time.perf_counter()
        session = self.storage.get_session(payload.session_id)
        if not session or session["visitor_id"] != payload.visitor_id:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = self.characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc

        user_text = payload.message.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="Message is empty")

        previous_messages = self.storage.session_messages(payload.session_id, 1)
        last_message_at = previous_messages[-1]["created_at"] if previous_messages else ""
        time_awareness = build_time_awareness(last_message_at)
        user_message_id = self.storage.add_message(payload.session_id, payload.visitor_id, card.id, "user", user_text)
        after_user_ms = int((time.perf_counter() - started) * 1000)

        query_vectors = await self.llm.embed_texts([user_text])
        embedding_provider = self.llm.embedding_provider_name() if query_vectors else None
        recall = self.memory.recall(
            payload.session_id,
            user_text,
            query_vector=query_vectors[0] if query_vectors else None,
            embedding_provider=embedding_provider,
        )
        profile_memories = self.memory.profile(payload.session_id, 10)
        prompt_memories = self.memory.merge_for_prompt(profile_memories, recall)
        recent = self.storage.recent_messages(payload.session_id, 12)
        session = self.storage.get_session(payload.session_id)
        summary = session["recent_summary"] if session else ""
        current_state = self.character_state.get_state(payload.session_id, card)
        current_bond = self.character_bond.ensure_bond(payload.visitor_id, card.id, card)
        compose_input = ComposeInput(
            character=card,
            recent_messages=recent,
            user_message=user_text,
            memories=prompt_memories,
            profile_memories=profile_memories,
            recall_memories=recall,
            recent_summary=summary,
            manual_note=session["manual_note"] if session else "",
            live_state=self.character_state.state_to_prompt(current_state),
            relationship_memory=self.character_bond.bond_to_prompt(current_bond),
            time_awareness=time_awareness,
        )
        slots = self.composer.compose(compose_input)
        self.storage.set_prompt_slots(payload.session_id, [slot.model_dump() for slot in slots])
        after_compose_ms = int((time.perf_counter() - started) * 1000)

        try:
            reply = await self.llm.chat_complete(self.composer.render_messages(slots))
            reply_source = "remote"
            reply_error = None
        except Exception as exc:
            self.llm.last_chat_error = type(exc).__name__
            logger.warning("reply generation failed, using mock reply: %s", exc)
            reply = self.llm.mock_reply(card, user_text, [item.content for item in prompt_memories])
            reply_source = "mock"
            reply_error = type(exc).__name__

        assistant_message_id = self.storage.add_message(payload.session_id, payload.visitor_id, card.id, "assistant", reply)
        assistant_message = self.storage.get_message(assistant_message_id) or {
            "id": assistant_message_id,
            "role": "assistant",
            "content": reply,
            "created_at": "",
        }
        after_reply_ms = int((time.perf_counter() - started) * 1000)
        postprocess_diagnostics = {
            "status": "queued",
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "queued_at": utc_timestamp(),
        }
        self.storage.set_postprocess_diagnostics(payload.session_id, postprocess_diagnostics)
        background_tasks.add_task(
            self.postprocess.run,
            payload.visitor_id,
            payload.session_id,
            user_message_id,
            card.id,
            user_text,
            reply,
            prompt_memories,
            recent,
            current_state,
            current_bond,
        )

        recent_pane = self.memory.build_pane(payload.session_id, recall)
        return ChatResponse(
            session_id=payload.session_id,
            visitor_id=payload.visitor_id,
            character_id=card.id,
            reply=reply,
            message=ChatMessage(
                id=assistant_message["id"],
                role=assistant_message["role"],
                content=assistant_message["content"],
                created_at=assistant_message["created_at"],
            ),
            character_state=current_state,
            character_bond=current_bond,
            memory_pane=recent_pane,
            prompt_slots=slots,
            timings={
                "storeUserMs": after_user_ms,
                "composeMs": after_compose_ms,
                "replyMs": after_reply_ms,
                "analysisMs": 0,
                "totalMs": int((time.perf_counter() - started) * 1000),
                "replySource": 0 if reply_source == "mock" else 1,
                "embeddingSource": 1 if embedding_provider else 0,
                "postProcessQueued": 1,
            },
            diagnostics={
                "reply_source": reply_source,
                "reply_error": reply_error,
                "embedding_provider": embedding_provider,
                "embedding_error": self.llm.last_embedding_error,
                "post_processing": "queued",
                "postprocess": postprocess_diagnostics,
            },
        )

    def export_session(self, session_id: str) -> dict[str, object]:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = self.characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        pane = self.memory.build_pane(session_id)
        return {
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session": dict(session),
            "character": card.model_dump(),
            "character_state": self.character_state.get_state(session_id, card),
            "character_bond": self.character_bond.get_bond(session["visitor_id"], card.id, card),
            "messages": self.storage.session_messages(session_id),
            "memory_pane": pane,
            "prompt_slots": pane.get("prompt_slots", []),
        }

    def get_story_pane(self, session_id: str) -> StoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return StoryPaneResponse(session_id=session_id, items=self.story.list_items(session_id))

    async def refresh_story_pane(self, session_id: str) -> StoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        diagnostics = await self.story.refresh(
            self.llm,
            session_id,
            self.storage.session_messages(session_id, 40),
            self.memory.list_memories(session_id),
        )
        return StoryPaneResponse(session_id=session_id, items=self.story.list_items(session_id), diagnostics=diagnostics)

