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


NovelPerspective = Literal["third_person", "user_view", "character_view", "dual_view"]
NovelForm = Literal["daily_short", "campus_romance", "vignette", "chapter_one", "side_story"]
NovelFidelity = Literal["faithful", "polished", "literary"]
NovelMaterialSource = Literal["message", "memory", "story", "manual"]
NovelMaterialCategory = Literal["fact", "foreshadowing", "open_thread", "relationship", "boundary", "inspiration"]
NovelChapterStatus = Literal["planned", "drafting", "draft", "revised", "locked", "affected"]


class NovelGenerateRequest(BaseModel):
    message_limit: int = Field(default=40, ge=4, le=120)
    perspective: NovelPerspective = "third_person"
    form: NovelForm = "daily_short"
    fidelity: NovelFidelity = "polished"
    atmosphere: str = Field(default="温柔、克制、日常", max_length=80)
    target_length: int = Field(default=1200, ge=400, le=4000)


class NovelGenerateResponse(BaseModel):
    title: str
    synopsis: str
    body: str
    used_memories: list[str] = Field(default_factory=list)
    source_message_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class NovelMaterial(BaseModel):
    id: str
    source_type: NovelMaterialSource
    source_id: str = ""
    category: NovelMaterialCategory
    label: str
    content: str
    evidence_level: Literal["explicit", "inferred", "weak"] = "inferred"
    created_at: str


class NovelVersion(BaseModel):
    id: str
    chapter_id: str
    version_type: str
    title: str
    body: str
    summary: str = ""
    source: str = ""
    state_delta: dict[str, Any] = Field(default_factory=dict)
    planning_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class NovelChapter(BaseModel):
    id: str
    project_id: str
    chapter_order: int
    title: str
    goal: str = ""
    summary: str = ""
    body: str = ""
    status: NovelChapterStatus = "planned"
    scene_card: dict[str, Any] = Field(default_factory=dict)
    source_material_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    version_count: int = 0
    versions: list[NovelVersion] = Field(default_factory=list)


class NovelProjectCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    genre: str = Field(default="校园日常长篇", max_length=80)
    tone: str = Field(default="温柔、克制、日常", max_length=120)
    protagonist: str = Field(default="", max_length=120)
    worldview: str = Field(default="", max_length=2000)
    relationship_setup: str = Field(default="", max_length=2000)
    outline: str = Field(default="", max_length=4000)
    story_canvas: dict[str, Any] | None = None


class NovelProjectUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    genre: str | None = Field(default=None, max_length=80)
    tone: str | None = Field(default=None, max_length=120)
    protagonist: str | None = Field(default=None, max_length=120)
    worldview: str | None = Field(default=None, max_length=2000)
    relationship_setup: str | None = Field(default=None, max_length=2000)
    outline: str | None = Field(default=None, max_length=4000)
    story_bible: dict[str, Any] | None = None
    story_canvas: dict[str, Any] | None = None


class NovelChapterUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    goal: str | None = Field(default=None, max_length=1000)
    summary: str | None = Field(default=None, max_length=1200)
    body: str | None = Field(default=None, max_length=20000)
    status: NovelChapterStatus | None = None
    scene_card: dict[str, Any] | None = None
    source_material_ids: list[str] | None = None


class NovelChapterDraftSaveRequest(BaseModel):
    project: NovelProjectUpdateRequest | None = None
    chapter: NovelChapterUpdateRequest


class NovelChapterGenerateRequest(BaseModel):
    chapter_id: str | None = None
    instruction: str = Field(default="生成下一章正文", max_length=4000)
    target_length: int = Field(default=1800, ge=400, le=6000)
    defer_postprocess: bool = True


class NovelCanvasExtendRequest(BaseModel):
    from_chapter_order: int = Field(default=0, ge=0, le=999)
    count: int = Field(default=4, ge=2, le=6)
    instruction: str = Field(default="", max_length=4000)


class NovelInstructionOptimizeRequest(BaseModel):
    chapter_id: str | None = None
    base_instruction: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=1000)
    summary: str = Field(default="", max_length=1200)
    body: str = Field(default="", max_length=20000)
    status: NovelChapterStatus | None = None
    scene_card: dict[str, Any] = Field(default_factory=dict)
    canvas_chapter: dict[str, Any] = Field(default_factory=dict)
    previous_handoff: dict[str, Any] = Field(default_factory=dict)
    prior_novel_state: dict[str, Any] = Field(default_factory=dict)
    quality_diagnosis: dict[str, Any] = Field(default_factory=dict)
    target_length: int = Field(default=1800, ge=400, le=6000)


class NovelInstructionOptimizeResponse(BaseModel):
    instruction: str
    source: Literal["remote", "fallback"] = "fallback"
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class NovelContinuityIssue(BaseModel):
    severity: Literal["ok", "warning", "error"] = "ok"
    label: str
    detail: str


class NovelContinuityReport(BaseModel):
    project_id: str
    chapter_id: str | None = None
    issues: list[NovelContinuityIssue] = Field(default_factory=list)
    summary: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class NovelProjectResponse(BaseModel):
    id: str
    session_id: str
    visitor_id: str
    character_id: str
    title: str
    genre: str
    tone: str
    protagonist: str
    worldview: str
    relationship_setup: str
    outline: str
    story_bible: dict[str, Any] = Field(default_factory=dict)
    story_canvas: dict[str, Any] = Field(default_factory=dict)
    novel_state: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    created_at: str
    updated_at: str
    materials: list[NovelMaterial] = Field(default_factory=list)
    chapters: list[NovelChapter] = Field(default_factory=list)


StoryKind = Literal["motif", "story_beat", "open_thread", "relationship_texture", "boundary"]
StoryEvidenceLevel = Literal["explicit", "inferred", "weak"]
StoryStatus = Literal["active", "seed", "developed", "archived"]


class StoryItem(BaseModel):
    id: str
    kind: StoryKind
    label: str
    content: str
    evidence: str = ""
    evidence_level: StoryEvidenceLevel = "inferred"
    status: StoryStatus = "active"
    source_message_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class StoryPaneResponse(BaseModel):
    session_id: str
    items: list[StoryItem] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


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
    source_created_at: str | None = None
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
    diagnostics: dict[str, Any] = Field(default_factory=dict)


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
    diagnostics: dict[str, Any] = Field(default_factory=dict)
