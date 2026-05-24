from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .characters import CharacterStore
from .composer import ContextComposer
from .features.chat.routes import register_chat_routes
from .features.novel.routes import register_novel_routes
from .features.relationship.bond import CharacterBondService
from .features.relationship.memory import MemoryService
from .features.relationship.state import CharacterStateService
from .llm import LlmClient
from .novel import NovelService
from .schemas import (
    CharacterDraftGenerateRequest,
    CharacterDraftGenerateResponse,
    CharacterWriteRequest,
    ResolveVisitorRequest,
    VisitorResponse,
)
from .storage import Storage
from .story import StoryService


def create_app(
    storage: Storage | None = None,
    characters: CharacterStore | None = None,
    llm: LlmClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Campus Pulse Lite", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    storage = storage or Storage()
    characters = characters or CharacterStore()
    memory = MemoryService(storage)
    story = StoryService(storage)
    character_state = CharacterStateService(storage)
    character_bond = CharacterBondService(storage)
    composer = ContextComposer()
    novel = NovelService(character_state, character_bond, storage)
    llm = llm or LlmClient()

    for card in characters.list_cards():
        storage.upsert_character(card.model_dump(), origin="builtin")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "llm_configured": llm.configured(),
            "llm_provider": llm.provider_name(),
            "embedding_configured": llm.embedding_configured(),
            "embedding_provider": llm.embedding_provider_name(),
        }

    @app.post("/api/visitors/resolve", response_model=VisitorResponse)
    def resolve_visitor(payload: ResolveVisitorRequest) -> VisitorResponse:
        visitor_id, created = storage.resolve_visitor(payload.visitor_id)
        return VisitorResponse(visitor_id=visitor_id, created=created)

    @app.get("/api/characters")
    def list_characters(visitor_id: str = "") -> list[dict[str, object]]:
        resolved_visitor_id = visitor_id
        if visitor_id:
            resolved_visitor_id, _ = storage.resolve_visitor(visitor_id)
        return storage.list_character_cards(resolved_visitor_id)

    @app.post("/api/characters/draft", response_model=CharacterDraftGenerateResponse)
    async def generate_character_draft(payload: CharacterDraftGenerateRequest) -> CharacterDraftGenerateResponse:
        storage.resolve_visitor(payload.visitor_id)
        character = await llm.generate_character_draft(payload.prompt, payload.template)
        return CharacterDraftGenerateResponse(
            character=character,
            diagnostics={
                "source": "remote" if llm.provider and not llm.last_analysis_error else "fallback",
                "error": llm.last_analysis_error,
            },
        )

    @app.post("/api/characters")
    def create_character(payload: CharacterWriteRequest) -> dict[str, object]:
        visitor_id, _ = storage.resolve_visitor(payload.visitor_id)
        return storage.create_custom_character(visitor_id, payload.model_dump(exclude={"visitor_id"}))

    @app.put("/api/characters/{character_id}")
    def update_character(character_id: str, payload: CharacterWriteRequest) -> dict[str, object]:
        visitor_id, _ = storage.resolve_visitor(payload.visitor_id)
        updated = storage.update_custom_character(visitor_id, character_id, payload.model_dump(exclude={"visitor_id"}))
        if not updated:
            raise HTTPException(status_code=404, detail="Custom character not found")
        return updated

    @app.delete("/api/characters/{character_id}")
    def delete_character(character_id: str, visitor_id: str) -> dict[str, bool]:
        resolved_visitor_id, _ = storage.resolve_visitor(visitor_id)
        deleted = storage.delete_custom_character(resolved_visitor_id, character_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Custom character not found")
        return {"deleted": True}

    register_chat_routes(
        app,
        storage=storage,
        characters=characters,
        memory=memory,
        story=story,
        character_state=character_state,
        character_bond=character_bond,
        composer=composer,
        llm=llm,
    )

    register_novel_routes(
        app,
        storage=storage,
        characters=characters,
        memory=memory,
        story=story,
        novel=novel,
        llm=llm,
    )

    return app


app = create_app()
