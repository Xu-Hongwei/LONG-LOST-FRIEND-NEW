from __future__ import annotations

import asyncio
import logging
import time

from fastapi import BackgroundTasks, HTTPException

from ...bond import CharacterBondService
from ...characters import CharacterStore
from ...composer import ComposeInput, ContextComposer
from ...llm import LlmClient
from ...memory import MemoryService
from ...schemas import (
    ChatMessage,
    ChatResponse,
    CreateSessionRequest,
    MemoryItemPatchRequest,
    MemoryPaneResponse,
    MemoryPatchRequest,
    SendMessageRequest,
    SessionResponse,
    StoryPaneResponse,
)
from ...state import CharacterStateService
from ...storage import Storage
from ...story import StoryService


logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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

    async def run_post_turn_analysis(
        self,
        visitor_id: str,
        session_id: str,
        user_message_id: str,
        card_id: str,
        user_text: str,
        reply: str,
        recalled: list,
        recent: list[dict[str, str]],
        previous_state: dict[str, object],
        previous_bond: dict[str, object],
    ) -> None:
        started = time.perf_counter()
        diagnostics = {
            "status": "running",
            "user_message_id": user_message_id,
            "started_at": utc_timestamp(),
            "stages": {
                "memory": {"status": "queued"},
                "state": {"status": "queued"},
                "bond": {"status": "queued"},
            },
        }

        def set_stage(stage: str, payload: dict[str, object]) -> None:
            stages = diagnostics.setdefault("stages", {})
            stage_payload = dict(stages.get(stage, {})) if isinstance(stages, dict) else {}
            stage_payload.update(payload)
            diagnostics["stages"][stage] = stage_payload
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)

        self.storage.set_postprocess_diagnostics(session_id, diagnostics)
        try:
            if not self.llm.provider:
                diagnostics.update({
                    "status": "skipped",
                    "finished_at": utc_timestamp(),
                    "duration_ms": elapsed_ms(started),
                    "reason": "llm_not_configured",
                    "stages": {
                        "memory": {"status": "skipped", "reason": "llm_not_configured"},
                        "state": {"status": "skipped", "reason": "llm_not_configured"},
                        "bond": {"status": "skipped", "reason": "llm_not_configured"},
                    },
                })
                self.storage.set_postprocess_diagnostics(session_id, diagnostics)
                return

            card = self.characters.get(card_id)
            session = self.storage.get_session(session_id)
            frozen = bool(session["frozen"]) if session else False
            extracted = []
            memory_records = []
            embedded_count = 0
            summary_updated = False

            memory_started = time.perf_counter()
            if frozen:
                set_stage("memory", {"status": "skipped", "reason": "session_frozen", "finished_at": utc_timestamp()})
            else:
                set_stage("memory", {"status": "running", "started_at": utc_timestamp()})
                extracted = await self.llm.extract_memories(user_text, reply)
                memory_error = self.llm.last_chat_error
                if memory_error:
                    set_stage(
                        "memory",
                        {
                            "status": "failed",
                            "finished_at": utc_timestamp(),
                            "duration_ms": elapsed_ms(memory_started),
                            "error_type": memory_error,
                        },
                    )
                    logger.warning("memory extraction failed for session %s: %s", session_id, memory_error)
                else:
                    memory_records = self.memory.add_extracted(visitor_id, session_id, card.id, user_message_id, extracted)
                    if memory_records:
                        vectors = await self.llm.embed_texts([content for _, content in memory_records])
                        self.memory.store_embeddings(memory_records, vectors, self.llm.embedding_provider_name() if vectors else None)
                        embedded_count = len(vectors)
                    if extracted or len(self.storage.recent_messages(session_id, 20)) >= 6:
                        self.memory.update_recent_summary(session_id)
                        summary_updated = True
                    set_stage(
                        "memory",
                        {
                            "status": "succeeded",
                            "finished_at": utc_timestamp(),
                            "duration_ms": elapsed_ms(memory_started),
                            "extracted_count": len(extracted),
                            "stored_count": len(memory_records),
                            "embedded_count": embedded_count,
                            "summary_updated": summary_updated,
                        },
                    )

            state_started = time.perf_counter()
            set_stage("state", {"status": "running", "started_at": utc_timestamp()})
            scored_state = await self.llm.score_character_state(card, previous_state, recent, user_text, reply, recalled)
            state_error = self.llm.last_chat_error
            if state_error:
                set_stage(
                    "state",
                    {
                        "status": "failed",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(state_started),
                        "error_type": state_error,
                    },
                )
                logger.warning("state analysis failed for session %s: %s", session_id, state_error)
            else:
                self.character_state.update_from_score(session_id, previous_state, scored_state, card)
                set_stage(
                    "state",
                    {
                        "status": "succeeded",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(state_started),
                        "updated": bool(scored_state),
                    },
                )

            bond_started = time.perf_counter()
            set_stage("bond", {"status": "running", "started_at": utc_timestamp()})
            scored_bond = await self.llm.score_character_bond(card, previous_bond, previous_state, recent, user_text, reply, recalled)
            bond_error = self.llm.last_chat_error
            if bond_error:
                set_stage(
                    "bond",
                    {
                        "status": "failed",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(bond_started),
                        "error_type": bond_error,
                    },
                )
                logger.warning("bond analysis failed for session %s: %s", session_id, bond_error)
            else:
                self.character_bond.update_from_score(visitor_id, card, previous_bond, scored_bond)
                set_stage(
                    "bond",
                    {
                        "status": "succeeded",
                        "finished_at": utc_timestamp(),
                        "duration_ms": elapsed_ms(bond_started),
                        "updated": bool(scored_bond and scored_bond.get("should_update")),
                    },
                )

            stage_statuses = [
                str(stage.get("status"))
                for stage in diagnostics.get("stages", {}).values()
                if isinstance(stage, dict)
            ]
            failed_count = sum(status == "failed" for status in stage_statuses)
            completed_count = sum(status in {"succeeded", "skipped"} for status in stage_statuses)
            overall_status = "succeeded"
            if failed_count and completed_count:
                overall_status = "partial"
            elif failed_count:
                overall_status = "failed"
            diagnostics.update({
                "status": overall_status,
                "finished_at": utc_timestamp(),
                "duration_ms": elapsed_ms(started),
                "extracted_count": len(extracted),
                "stored_count": len(memory_records),
                "embedded_count": embedded_count,
                "summary_updated": summary_updated,
                "frozen": frozen,
            })
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)
        except Exception as exc:
            diagnostics.update({
                "status": "failed",
                "finished_at": utc_timestamp(),
                "duration_ms": elapsed_ms(started),
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:400],
            })
            self.storage.set_postprocess_diagnostics(session_id, diagnostics)
            logger.exception("post-turn analysis failed for session %s: %s", session_id, exc)

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
        recent = self.storage.recent_messages(payload.session_id, 12)
        session = self.storage.get_session(payload.session_id)
        summary = session["recent_summary"] if session else ""
        current_state = self.character_state.get_state(payload.session_id, card)
        current_bond = self.character_bond.ensure_bond(payload.visitor_id, card.id, card)
        compose_input = ComposeInput(
            character=card,
            recent_messages=recent,
            user_message=user_text,
            memories=recall,
            recent_summary=summary,
            manual_note=session["manual_note"] if session else "",
            live_state=self.character_state.state_to_prompt(current_state),
            relationship_memory=self.character_bond.bond_to_prompt(current_bond),
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
            reply = self.llm.mock_reply(card, user_text, [item.content for item in recall])
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
            self.run_post_turn_analysis,
            payload.visitor_id,
            payload.session_id,
            user_message_id,
            card.id,
            user_text,
            reply,
            recall,
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

    def get_memory(self, session_id: str) -> MemoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        pane = self.memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=self.memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
            diagnostics=pane.get("diagnostics", {}),
        )

    async def wait_memory(
        self,
        session_id: str,
        user_message_id: str = "",
        timeout_seconds: float = 45.0,
    ) -> MemoryPaneResponse:
        deadline = time.perf_counter() + max(1.0, min(timeout_seconds, 90.0))
        terminal_statuses = {"succeeded", "failed", "skipped", "partial"}
        while True:
            pane = self.get_memory(session_id)
            diagnostics = pane.diagnostics or {}
            status = str(diagnostics.get("status") or "")
            diagnostic_message_id = str(diagnostics.get("user_message_id") or "")
            matches_message = not user_message_id or diagnostic_message_id == user_message_id
            if matches_message and status in terminal_statuses:
                return pane
            if time.perf_counter() >= deadline:
                return pane
            await asyncio.sleep(0.5)

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

    def patch_memory(self, session_id: str, payload: MemoryPatchRequest) -> MemoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        self.storage.update_session_memory(session_id, payload.frozen, payload.manual_note)
        pane = self.memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=self.memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
            diagnostics=pane.get("diagnostics", {}),
        )

    async def patch_memory_item(self, session_id: str, memory_id: str, payload: MemoryItemPatchRequest) -> MemoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        updated = self.storage.update_memory_item(
            memory_id,
            session["visitor_id"],
            session["character_id"],
            session_id,
            payload.memory_type,
            payload.memory_scope,
            payload.content,
            payload.confidence,
            payload.importance,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Memory not found")
        if payload.content:
            vectors = await self.llm.embed_texts([payload.content])
            self.memory.store_embeddings([(memory_id, payload.content)], vectors, self.llm.embedding_provider_name() if vectors else None)
        pane = self.memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=self.memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
            diagnostics=pane.get("diagnostics", {}),
        )

    def delete_memory_item(self, session_id: str, memory_id: str) -> MemoryPaneResponse:
        session = self.storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        deleted = self.storage.delete_memory_item(memory_id, session["visitor_id"], session["character_id"], session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        pane = self.memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=self.memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
            diagnostics=pane.get("diagnostics", {}),
        )
