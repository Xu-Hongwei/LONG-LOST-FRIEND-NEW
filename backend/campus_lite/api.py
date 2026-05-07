from __future__ import annotations

import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .bond import CharacterBondService
from .characters import CharacterStore
from .composer import ComposeInput, ContextComposer
from .llm import LlmClient
from .memory import MemoryService
from .schemas import (
    ChatMessage,
    ChatResponse,
    CreateSessionRequest,
    MemoryItemPatchRequest,
    MemoryPaneResponse,
    MemoryPatchRequest,
    ResolveVisitorRequest,
    SendMessageRequest,
    SessionResponse,
    VisitorResponse,
)
from .state import CharacterStateService
from .storage import Storage


def create_app() -> FastAPI:
    app = FastAPI(title="Campus Pulse Lite", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    storage = Storage()
    characters = CharacterStore()
    memory = MemoryService(storage)
    character_state = CharacterStateService(storage)
    character_bond = CharacterBondService(storage)
    composer = ContextComposer()
    llm = LlmClient()

    for card in characters.list_cards():
        storage.upsert_character(card.model_dump())

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"ok": True, "llm_configured": llm.configured(), "embedding_configured": llm.embedding_configured()}

    @app.post("/api/visitors/resolve", response_model=VisitorResponse)
    def resolve_visitor(payload: ResolveVisitorRequest) -> VisitorResponse:
        visitor_id, created = storage.resolve_visitor(payload.visitor_id)
        return VisitorResponse(visitor_id=visitor_id, created=created)

    @app.get("/api/characters")
    def list_characters() -> list[dict[str, object]]:
        return [card.model_dump() for card in characters.list_cards()]

    @app.post("/api/sessions", response_model=SessionResponse)
    def create_session(payload: CreateSessionRequest) -> SessionResponse:
        visitor_id, _ = storage.resolve_visitor(payload.visitor_id)
        try:
            card = characters.get(payload.character_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        session_id = storage.create_or_get_session(visitor_id, card.id)
        session = storage.get_session(session_id)
        if not storage.recent_messages(session_id, 1):
            storage.add_message(session_id, visitor_id, card.id, "assistant", card.opening_line)
        state = character_state.ensure_state(session_id, card)
        bond = character_bond.ensure_bond(visitor_id, card.id, card)
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
                for item in storage.session_messages(session_id, 40)
            ],
            memory_pane=memory.build_pane(session_id),
        )

    @app.post("/api/chat/send", response_model=ChatResponse)
    async def send_message(payload: SendMessageRequest) -> ChatResponse:
        started = time.perf_counter()
        session = storage.get_session(payload.session_id)
        if not session or session["visitor_id"] != payload.visitor_id:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc

        user_text = payload.message.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="Message is empty")

        user_message_id = storage.add_message(payload.session_id, payload.visitor_id, card.id, "user", user_text)
        after_user_ms = int((time.perf_counter() - started) * 1000)

        query_vectors = await llm.embed_texts([user_text])
        embedding_provider = llm.embedding_provider_name() if query_vectors else None
        recall = memory.recall(
            payload.session_id,
            user_text,
            query_vector=query_vectors[0] if query_vectors else None,
            embedding_provider=embedding_provider,
        )
        recent = storage.recent_messages(payload.session_id, 12)
        session = storage.get_session(payload.session_id)
        summary = session["recent_summary"] if session else ""
        current_state = character_state.get_state(payload.session_id, card)
        current_bond = character_bond.ensure_bond(payload.visitor_id, card.id, card)
        compose_input = ComposeInput(
            character=card,
            recent_messages=recent,
            user_message=user_text,
            memories=recall,
            recent_summary=summary,
            manual_note=session["manual_note"] if session else "",
            live_state=character_state.state_to_prompt(current_state),
            relationship_memory=character_bond.bond_to_prompt(current_bond),
        )
        slots = composer.compose(compose_input)
        storage.set_prompt_slots(payload.session_id, [slot.model_dump() for slot in slots])
        after_compose_ms = int((time.perf_counter() - started) * 1000)

        try:
            reply = await llm.chat_complete(composer.render_messages(slots))
            reply_source = "remote"
        except Exception:
            reply = llm.mock_reply(card, user_text, [item.content for item in recall])
            reply_source = "mock"

        assistant_message_id = storage.add_message(payload.session_id, payload.visitor_id, card.id, "assistant", reply)
        after_reply_ms = int((time.perf_counter() - started) * 1000)

        analysis = await llm.analyze_turn(
            card,
            current_state,
            current_bond,
            recent,
            user_text,
            reply,
            recall,
        )
        updated_state = character_state.update_from_score(
            payload.session_id,
            current_state,
            analysis.get("state"),
            card,
        )
        updated_bond = character_bond.update_from_score(
            payload.visitor_id,
            card,
            current_bond,
            analysis.get("bond"),
        )
        after_analysis_ms = int((time.perf_counter() - started) * 1000)

        session = storage.get_session(payload.session_id)
        if session and not bool(session["frozen"]):
            extracted = analysis.get("memories") or []
            memory_records = memory.add_extracted(payload.visitor_id, payload.session_id, card.id, user_message_id, extracted)
            if memory_records:
                vectors = await llm.embed_texts([content for _, content in memory_records])
                memory.store_embeddings(memory_records, vectors, llm.embedding_provider_name() if vectors else None)
            if extracted or len(storage.recent_messages(payload.session_id, 20)) >= 6:
                memory.update_recent_summary(payload.session_id)

        recent_pane = memory.build_pane(payload.session_id, recall)
        return ChatResponse(
            session_id=payload.session_id,
            visitor_id=payload.visitor_id,
            character_id=card.id,
            reply=reply,
            message=ChatMessage(
                id=assistant_message_id,
                role="assistant",
                content=reply,
                created_at="",
            ),
            character_state=updated_state,
            character_bond=updated_bond,
            memory_pane=recent_pane,
            prompt_slots=slots,
            timings={
                "storeUserMs": after_user_ms,
                "composeMs": after_compose_ms,
                "replyMs": after_reply_ms,
                "analysisMs": after_analysis_ms,
                "totalMs": int((time.perf_counter() - started) * 1000),
                "replySource": 0 if reply_source == "mock" else 1,
                "embeddingSource": 1 if embedding_provider else 0,
            },
        )

    @app.get("/api/sessions/{session_id}/memory", response_model=MemoryPaneResponse)
    def get_memory(session_id: str) -> MemoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        pane = memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
        )

    @app.get("/api/sessions/{session_id}/export")
    def export_session(session_id: str) -> dict[str, object]:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        pane = memory.build_pane(session_id)
        return {
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session": dict(session),
            "character": card.model_dump(),
            "character_state": character_state.get_state(session_id, card),
            "character_bond": character_bond.get_bond(session["visitor_id"], card.id, card),
            "messages": storage.session_messages(session_id),
            "memory_pane": pane,
            "prompt_slots": pane.get("prompt_slots", []),
        }

    @app.patch("/api/sessions/{session_id}/memory", response_model=MemoryPaneResponse)
    def patch_memory(session_id: str, payload: MemoryPatchRequest) -> MemoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        storage.update_session_memory(session_id, payload.frozen, payload.manual_note)
        pane = memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
        )

    @app.patch("/api/sessions/{session_id}/memory/items/{memory_id}", response_model=MemoryPaneResponse)
    async def patch_memory_item(session_id: str, memory_id: str, payload: MemoryItemPatchRequest) -> MemoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        updated = storage.update_memory_item(
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
            vectors = await llm.embed_texts([payload.content])
            memory.store_embeddings([(memory_id, payload.content)], vectors, llm.embedding_provider_name() if vectors else None)
        pane = memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
        )

    @app.delete("/api/sessions/{session_id}/memory/items/{memory_id}", response_model=MemoryPaneResponse)
    def delete_memory_item(session_id: str, memory_id: str) -> MemoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        deleted = storage.delete_memory_item(memory_id, session["visitor_id"], session["character_id"], session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        pane = memory.build_pane(session_id)
        return MemoryPaneResponse(
            session_id=session_id,
            memories=memory.list_memories(session_id),
            summary=pane["summary"],
            frozen=pane["frozen"],
            manual_note=pane["manual_note"],
            last_recall=[],
            prompt_slots=[slot for slot in pane.get("prompt_slots", [])],
        )

    return app


app = create_app()
