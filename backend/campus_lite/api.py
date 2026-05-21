from __future__ import annotations

from fastapi import FastAPI
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
from .schemas import ResolveVisitorRequest, VisitorResponse
from .storage import Storage
from .story import StoryService


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
    def list_characters() -> list[dict[str, object]]:
        return [card.model_dump() for card in characters.list_cards()]

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
