from __future__ import annotations

import json
import logging
import time

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .bond import CharacterBondService
from .characters import CharacterStore
from .composer import ComposeInput, ContextComposer
from .llm import LlmClient
from .memory import MemoryService
from .novel import NovelService
from .schemas import (
    ChatMessage,
    ChatResponse,
    CreateSessionRequest,
    MemoryItemPatchRequest,
    MemoryPaneResponse,
    MemoryPatchRequest,
    NovelChapterGenerateRequest,
    NovelChapterUpdateRequest,
    NovelContinuityReport,
    NovelGenerateRequest,
    NovelGenerateResponse,
    NovelProjectCreateRequest,
    NovelProjectResponse,
    NovelProjectUpdateRequest,
    NovelVersion,
    ResolveVisitorRequest,
    SendMessageRequest,
    SessionResponse,
    StoryPaneResponse,
    VisitorResponse,
)
from .state import CharacterStateService
from .storage import Storage
from .story import StoryService


logger = logging.getLogger(__name__)


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
    story = StoryService(storage)
    character_state = CharacterStateService(storage)
    character_bond = CharacterBondService(storage)
    composer = ContextComposer()
    novel = NovelService(character_state, character_bond, storage)
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

    async def run_post_turn_analysis(
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
        try:
            card = characters.get(card_id)
            analysis = await llm.analyze_turn(
                card,
                previous_state,
                previous_bond,
                recent,
                user_text,
                reply,
                recalled,
            )
            character_state.update_from_score(session_id, previous_state, analysis.get("state"), card)
            character_bond.update_from_score(visitor_id, card, previous_bond, analysis.get("bond"))
            session = storage.get_session(session_id)
            if session and not bool(session["frozen"]):
                extracted = analysis.get("memories") or []
                memory_records = memory.add_extracted(visitor_id, session_id, card.id, user_message_id, extracted)
                if memory_records:
                    vectors = await llm.embed_texts([content for _, content in memory_records])
                    memory.store_embeddings(memory_records, vectors, llm.embedding_provider_name() if vectors else None)
                if extracted or len(storage.recent_messages(session_id, 20)) >= 6:
                    memory.update_recent_summary(session_id)
        except Exception as exc:
            logger.exception("post-turn analysis failed for session %s: %s", session_id, exc)

    @app.post("/api/chat/send", response_model=ChatResponse)
    async def send_message(payload: SendMessageRequest, background_tasks: BackgroundTasks) -> ChatResponse:
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
            reply_error = None
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            logger.warning("reply generation failed, using mock reply: %s", exc)
            reply = llm.mock_reply(card, user_text, [item.content for item in recall])
            reply_source = "mock"
            reply_error = type(exc).__name__

        assistant_message_id = storage.add_message(payload.session_id, payload.visitor_id, card.id, "assistant", reply)
        assistant_message = storage.get_message(assistant_message_id) or {
            "id": assistant_message_id,
            "role": "assistant",
            "content": reply,
            "created_at": "",
        }
        after_reply_ms = int((time.perf_counter() - started) * 1000)
        background_tasks.add_task(
            run_post_turn_analysis,
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

        recent_pane = memory.build_pane(payload.session_id, recall)
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
                "embedding_error": llm.last_embedding_error,
                "post_processing": "queued",
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

    @app.post("/api/sessions/{session_id}/novel/generate", response_model=NovelGenerateResponse)
    async def generate_novel(session_id: str, payload: NovelGenerateRequest) -> NovelGenerateResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        messages = storage.session_messages(session_id, payload.message_limit)
        if len(messages) < 2:
            raise HTTPException(status_code=400, detail="Not enough messages to generate a novel")
        return await novel.generate(
            llm,
            card,
            session["visitor_id"],
            session_id,
            messages,
            memory.list_memories(session_id),
            story.list_items(session_id),
            payload,
        )

    @app.get("/api/sessions/{session_id}/novel/projects", response_model=list[NovelProjectResponse])
    def list_novel_projects(session_id: str) -> list[NovelProjectResponse]:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return novel.project_responses(session_id)

    @app.post("/api/sessions/{session_id}/novel/projects", response_model=NovelProjectResponse)
    def create_novel_project(session_id: str, payload: NovelProjectCreateRequest) -> NovelProjectResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            card = characters.get(session["character_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc
        messages = storage.session_messages(session_id, 80)
        return novel.create_project(
            card,
            session["visitor_id"],
            session_id,
            messages,
            memory.list_memories(session_id),
            story.list_items(session_id),
            payload,
        )

    @app.get("/api/novel/projects/{project_id}", response_model=NovelProjectResponse)
    def get_novel_project(project_id: str) -> NovelProjectResponse:
        try:
            return novel.project_response(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Novel project not found") from exc

    @app.patch("/api/novel/projects/{project_id}", response_model=NovelProjectResponse)
    def update_novel_project(project_id: str, payload: NovelProjectUpdateRequest) -> NovelProjectResponse:
        updated = storage.update_novel_project(project_id, payload.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Novel project not found")
        return novel.project_response(project_id)

    @app.post("/api/novel/projects/{project_id}/canvas/build", response_model=NovelProjectResponse)
    async def build_novel_canvas(project_id: str) -> NovelProjectResponse:
        try:
            return await novel.build_canvas(llm, project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/chapters", response_model=NovelProjectResponse)
    def create_novel_chapter(project_id: str, payload: NovelChapterUpdateRequest) -> NovelProjectResponse:
        project = storage.get_novel_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Novel project not found")
        storage.create_novel_chapter(
            project_id,
            payload.title or "新章节",
            payload.goal or "",
            payload.summary or "",
            payload.body or "",
            payload.status or "planned",
            payload.scene_card or {},
            payload.source_material_ids or [],
        )
        return novel.project_response(project_id)

    @app.patch("/api/novel/chapters/{chapter_id}", response_model=NovelProjectResponse)
    def update_novel_chapter(chapter_id: str, payload: NovelChapterUpdateRequest) -> NovelProjectResponse:
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        updated = storage.update_novel_chapter(chapter_id, payload.model_dump(exclude_unset=True), "manual")
        if not updated:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        return novel.project_response(chapter["project_id"])

    @app.post("/api/novel/projects/{project_id}/generate-chapter", response_model=NovelProjectResponse)
    async def generate_novel_chapter(project_id: str, payload: NovelChapterGenerateRequest) -> NovelProjectResponse:
        try:
            project, _chapter = await novel.generate_chapter(
                llm,
                project_id,
                payload.chapter_id,
                payload.instruction,
                payload.target_length,
            )
            return project
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/check", response_model=NovelContinuityReport)
    def check_novel_continuity(project_id: str, payload: NovelChapterGenerateRequest | None = None) -> NovelContinuityReport:
        try:
            return novel.check_continuity(project_id, payload.chapter_id if payload else None)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/novel/chapters/{chapter_id}/versions", response_model=list[NovelVersion])
    def list_novel_versions(chapter_id: str) -> list[NovelVersion]:
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        return [
            NovelVersion(
                id=row["id"],
                chapter_id=row["chapter_id"],
                version_type=row["version_type"],
                title=row["title"],
                body=row["body"],
                summary=row["summary"],
                source=row["source"],
                created_at=row["created_at"],
            )
            for row in storage.list_novel_versions(chapter_id)
        ]

    @app.post("/api/novel/versions/{version_id}/restore", response_model=NovelProjectResponse)
    def restore_novel_version(version_id: str) -> NovelProjectResponse:
        version = storage.get_novel_version(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Novel version not found")
        restored = storage.restore_novel_version(version_id)
        if not restored:
            raise HTTPException(status_code=404, detail="Novel version not found")
        return novel.project_response(version["project_id"])

    @app.get("/api/sessions/{session_id}/story", response_model=StoryPaneResponse)
    def get_story_pane(session_id: str) -> StoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return StoryPaneResponse(session_id=session_id, items=story.list_items(session_id))

    @app.post("/api/sessions/{session_id}/story/refresh", response_model=StoryPaneResponse)
    async def refresh_story_pane(session_id: str) -> StoryPaneResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        diagnostics = await story.refresh(
            llm,
            session_id,
            storage.session_messages(session_id, 40),
            memory.list_memories(session_id),
        )
        return StoryPaneResponse(session_id=session_id, items=story.list_items(session_id), diagnostics=diagnostics)

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
