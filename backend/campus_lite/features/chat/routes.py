from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI

from ...bond import CharacterBondService
from ...characters import CharacterStore
from ...composer import ContextComposer
from ...llm import LlmClient
from ...memory import MemoryService
from ...schemas import (
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
from .service import ChatService


def register_chat_routes(
    app: FastAPI,
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
    service = ChatService(
        storage=storage,
        characters=characters,
        memory=memory,
        story=story,
        character_state=character_state,
        character_bond=character_bond,
        composer=composer,
        llm=llm,
    )

    @app.post("/api/sessions", response_model=SessionResponse)
    def create_session(payload: CreateSessionRequest) -> SessionResponse:
        return service.create_session(payload)

    @app.post("/api/chat/send", response_model=ChatResponse)
    async def send_message(payload: SendMessageRequest, background_tasks: BackgroundTasks) -> ChatResponse:
        return await service.send_message(payload, background_tasks)

    @app.get("/api/sessions/{session_id}/memory", response_model=MemoryPaneResponse)
    def get_memory(session_id: str) -> MemoryPaneResponse:
        return service.get_memory(session_id)

    @app.get("/api/sessions/{session_id}/memory/wait", response_model=MemoryPaneResponse)
    async def wait_memory(session_id: str, user_message_id: str = "", timeout_seconds: float = 45.0) -> MemoryPaneResponse:
        return await service.wait_memory(session_id, user_message_id, timeout_seconds)

    @app.get("/api/sessions/{session_id}/export")
    def export_session(session_id: str) -> dict[str, object]:
        return service.export_session(session_id)

    @app.get("/api/sessions/{session_id}/story", response_model=StoryPaneResponse)
    def get_story_pane(session_id: str) -> StoryPaneResponse:
        return service.get_story_pane(session_id)

    @app.post("/api/sessions/{session_id}/story/refresh", response_model=StoryPaneResponse)
    async def refresh_story_pane(session_id: str) -> StoryPaneResponse:
        return await service.refresh_story_pane(session_id)

    @app.patch("/api/sessions/{session_id}/memory", response_model=MemoryPaneResponse)
    def patch_memory(session_id: str, payload: MemoryPatchRequest) -> MemoryPaneResponse:
        return service.patch_memory(session_id, payload)

    @app.patch("/api/sessions/{session_id}/memory/items/{memory_id}", response_model=MemoryPaneResponse)
    async def patch_memory_item(session_id: str, memory_id: str, payload: MemoryItemPatchRequest) -> MemoryPaneResponse:
        return await service.patch_memory_item(session_id, memory_id, payload)

    @app.delete("/api/sessions/{session_id}/memory/items/{memory_id}", response_model=MemoryPaneResponse)
    def delete_memory_item(session_id: str, memory_id: str) -> MemoryPaneResponse:
        return service.delete_memory_item(session_id, memory_id)
