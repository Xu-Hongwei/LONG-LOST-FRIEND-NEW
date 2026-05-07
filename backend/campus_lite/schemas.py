from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryType = Literal[
    "stable_user_info",
    "user_preference",
    "open_thread",
    "recent_emotion",
    "relationship_progress",
    "manual_note",
]

MemoryScope = Literal["global", "character", "session"]


class ResolveVisitorRequest(BaseModel):
    visitor_id: str | None = None


class VisitorResponse(BaseModel):
    visitor_id: str
    created: bool


class CharacterCard(BaseModel):
    id: str
    name: str
    archetype: str
    tagline: str
    gender: str = "unknown"
    bio: str
    speech_style: str
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    relationship_pace: str = ""
    opening_line: str
    personality: str = ""
    scenario: str = ""
    mes_example: str = ""
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    interaction_policy: dict[str, Any] = Field(default_factory=dict)
    anti_patterns: list[str] = Field(default_factory=list)
    backstory: dict[str, Any] = Field(default_factory=dict)
    voice: dict[str, Any] = Field(default_factory=dict)
    visual: dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    visitor_id: str
    character_id: str


class SessionResponse(BaseModel):
    session_id: str
    visitor_id: str
    character_id: str
    character: CharacterCard
    character_state: dict[str, Any] = Field(default_factory=dict)
    character_bond: dict[str, Any] = Field(default_factory=dict)
    messages: list["ChatMessage"] = Field(default_factory=list)
    memory_pane: dict[str, Any]


class SendMessageRequest(BaseModel):
    visitor_id: str
    session_id: str
    message: str


class ContextSlot(BaseModel):
    key: str
    content: str
    role: str = "system"
    priority: int = 50
    token_budget: int = 0
    included: bool = True


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class MemoryItem(BaseModel):
    id: str
    memory_type: MemoryType
    memory_scope: MemoryScope = "session"
    content: str
    confidence: float = 0.0
    importance: float = 0.5
    source_message_id: str | None = None
    created_at: str
    updated_at: str


class ChatResponse(BaseModel):
    session_id: str
    visitor_id: str
    character_id: str
    reply: str
    message: ChatMessage
    character_state: dict[str, Any] = Field(default_factory=dict)
    character_bond: dict[str, Any] = Field(default_factory=dict)
    memory_pane: dict[str, Any]
    prompt_slots: list[ContextSlot]
    timings: dict[str, int]


class MemoryPatchRequest(BaseModel):
    frozen: bool | None = None
    manual_note: str | None = None
    memories: list[MemoryItem] | None = None


class MemoryItemPatchRequest(BaseModel):
    memory_type: MemoryType | None = None
    memory_scope: MemoryScope | None = None
    content: str | None = None
    confidence: float | None = None
    importance: float | None = None


class MemoryPaneResponse(BaseModel):
    session_id: str
    memories: list[MemoryItem]
    summary: str
    frozen: bool
    manual_note: str
    last_recall: list[MemoryItem]
    prompt_slots: list[ContextSlot] = Field(default_factory=list)
