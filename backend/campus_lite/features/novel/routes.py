from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException

from ...characters import CharacterStore
from ...llm import LlmClient
from ...novel import NovelService
from ...schemas import (
    CharacterCard,
    NovelCanvasExtendRequest,
    NovelChapterDraftSaveRequest,
    NovelChapterGenerateRequest,
    NovelChapterUpdateRequest,
    NovelContinuityReport,
    NovelGenerateRequest,
    NovelGenerateResponse,
    NovelInstructionOptimizeRequest,
    NovelInstructionOptimizeResponse,
    NovelProjectCreateRequest,
    NovelProjectDraftGenerateRequest,
    NovelProjectDraftGenerateResponse,
    NovelProjectResponse,
    NovelProjectUpdateRequest,
    NovelVersion,
    StoryEventPoolBindingRequest,
    StoryEventPoolEventWriteRequest,
)
from ...storage import Storage, StoragePayloadError
from ...story import StoryService
from ..relationship.memory import MemoryService


def register_novel_routes(
    app: FastAPI,
    *,
    storage: Storage,
    characters: CharacterStore,
    memory: MemoryService,
    story: StoryService,
    novel: NovelService,
    llm: LlmClient,
) -> None:
    def get_character_for_session(session: dict[str, object]) -> CharacterCard:
        character_id = str(session["character_id"])
        visitor_id = str(session["visitor_id"])
        card = storage.get_character_card(character_id, visitor_id)
        if card:
            return CharacterCard.model_validate(card)
        try:
            return characters.get(character_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Character not found") from exc

    @app.post("/api/sessions/{session_id}/novel/generate", response_model=NovelGenerateResponse)
    async def generate_novel(session_id: str, payload: NovelGenerateRequest) -> NovelGenerateResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        card = get_character_for_session(dict(session))
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

    @app.post("/api/sessions/{session_id}/novel/project-draft", response_model=NovelProjectDraftGenerateResponse)
    async def generate_novel_project_draft(
        session_id: str,
        payload: NovelProjectDraftGenerateRequest,
    ) -> NovelProjectDraftGenerateResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        card = get_character_for_session(dict(session))
        messages = storage.session_messages(session_id, 80)
        return await novel.generate_project_draft(
            llm,
            card,
            messages,
            memory.list_memories(session_id),
            story.list_items(session_id),
            payload,
        )

    @app.post("/api/sessions/{session_id}/novel/projects", response_model=NovelProjectResponse)
    def create_novel_project(session_id: str, payload: NovelProjectCreateRequest) -> NovelProjectResponse:
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        card = get_character_for_session(dict(session))
        messages = storage.session_messages(session_id, 80)
        try:
            return novel.create_project(
                card,
                session["visitor_id"],
                session_id,
                messages,
                memory.list_memories(session_id),
                story.list_items(session_id),
                payload,
            )
        except StoragePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/novel/projects/{project_id}", response_model=NovelProjectResponse)
    def get_novel_project(project_id: str) -> NovelProjectResponse:
        try:
            return novel.project_response(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Novel project not found") from exc

    @app.patch("/api/novel/projects/{project_id}", response_model=NovelProjectResponse)
    def update_novel_project(project_id: str, payload: NovelProjectUpdateRequest) -> NovelProjectResponse:
        updates = payload.model_dump(exclude_unset=True)
        try:
            updated = storage.update_novel_project(project_id, updates)
        except StoragePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Novel project not found")
        if payload.story_canvas is not None:
            novel.sync_story_canvas_to_chapters(project_id)
        return novel.project_response(project_id)

    @app.delete("/api/novel/projects/{project_id}")
    def delete_novel_project(project_id: str) -> dict[str, bool]:
        deleted = storage.delete_novel_project(project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Novel project not found")
        return {"deleted": True}

    @app.post("/api/novel/projects/{project_id}/canvas/build", response_model=NovelProjectResponse)
    async def build_novel_canvas(project_id: str) -> NovelProjectResponse:
        try:
            return await novel.build_canvas(llm, project_id)
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/canvas/extend", response_model=NovelProjectResponse)
    async def extend_novel_canvas(project_id: str, payload: NovelCanvasExtendRequest) -> NovelProjectResponse:
        try:
            return await novel.extend_canvas(llm, project_id, payload.from_chapter_order, payload.count, payload.instruction)
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/chapters", response_model=NovelProjectResponse)
    def create_novel_chapter(project_id: str, payload: NovelChapterUpdateRequest) -> NovelProjectResponse:
        project = storage.get_novel_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Novel project not found")
        try:
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
        except StoragePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return novel.project_response(project_id)

    @app.patch("/api/novel/chapters/{chapter_id}", response_model=NovelProjectResponse)
    def update_novel_chapter(chapter_id: str, payload: NovelChapterUpdateRequest) -> NovelProjectResponse:
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        try:
            updated = storage.update_novel_chapter(chapter_id, payload.model_dump(exclude_unset=True), "manual")
        except StoragePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        if payload.body is not None or payload.summary is not None or payload.scene_card is not None:
            novel.mark_chapter_revision_boundary(chapter["project_id"], int(chapter["chapter_order"]))
        return novel.project_response(chapter["project_id"])

    @app.patch("/api/novel/chapters/{chapter_id}/draft", response_model=NovelProjectResponse)
    def save_novel_chapter_draft(chapter_id: str, payload: NovelChapterDraftSaveRequest) -> NovelProjectResponse:
        chapter = storage.get_novel_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        project_updates = payload.project.model_dump(exclude_unset=True) if payload.project else {}
        chapter_updates = payload.chapter.model_dump(exclude_unset=True)
        try:
            updated = storage.update_novel_chapter_draft(chapter["project_id"], chapter_id, project_updates, chapter_updates, "manual")
        except StoragePayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        if (
            payload.chapter.body is not None
            or payload.chapter.summary is not None
            or payload.chapter.scene_card is not None
            or payload.chapter.goal is not None
            or payload.chapter.title is not None
            or payload.chapter.source_material_ids is not None
        ):
            novel.mark_chapter_revision_boundary(chapter["project_id"], int(chapter["chapter_order"]))
        return novel.project_response(chapter["project_id"])

    @app.delete("/api/novel/chapters/{chapter_id}", response_model=NovelProjectResponse)
    def delete_novel_chapter(chapter_id: str) -> NovelProjectResponse:
        chapter = storage.delete_novel_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Novel chapter not found")
        novel.remove_chapter_from_story_canvas(chapter["project_id"], int(chapter["chapter_order"]))
        novel.mark_chapter_revision_boundary(chapter["project_id"], max(0, int(chapter["chapter_order"]) - 1))
        return novel.project_response(chapter["project_id"])

    @app.post("/api/novel/projects/{project_id}/generate-chapter", response_model=NovelProjectResponse)
    async def generate_novel_chapter(
        project_id: str,
        payload: NovelChapterGenerateRequest,
        background_tasks: BackgroundTasks,
    ) -> NovelProjectResponse:
        try:
            project, chapter = await novel.generate_chapter(
                llm,
                project_id,
                payload.chapter_id,
                payload.instruction,
                payload.target_length,
                payload.defer_postprocess,
            )
            if payload.defer_postprocess:
                background_tasks.add_task(novel.finalize_chapter_postprocess, llm, project_id, chapter.id)
            return project
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/optimize-instruction", response_model=NovelInstructionOptimizeResponse)
    async def optimize_novel_instruction(
        project_id: str,
        payload: NovelInstructionOptimizeRequest,
    ) -> NovelInstructionOptimizeResponse:
        try:
            return await novel.optimize_chapter_instruction(llm, project_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/event-pool/events", response_model=NovelProjectResponse)
    def create_event_pool_event(project_id: str, payload: StoryEventPoolEventWriteRequest) -> NovelProjectResponse:
        try:
            return novel.create_event_pool_event(project_id, payload)
        except ValueError as exc:
            status = 404 if "project" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.patch("/api/novel/projects/{project_id}/event-pool/events/{event_id}", response_model=NovelProjectResponse)
    def update_event_pool_event(project_id: str, event_id: str, payload: StoryEventPoolEventWriteRequest) -> NovelProjectResponse:
        try:
            return novel.update_event_pool_event(project_id, event_id, payload)
        except ValueError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/event-pool/events/{event_id}/retire", response_model=NovelProjectResponse)
    def retire_event_pool_event(project_id: str, event_id: str) -> NovelProjectResponse:
        try:
            return novel.retire_event_pool_event(project_id, event_id)
        except ValueError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.delete("/api/novel/projects/{project_id}/event-pool/events/{event_id}", response_model=NovelProjectResponse)
    def delete_event_pool_event(project_id: str, event_id: str) -> NovelProjectResponse:
        try:
            return novel.delete_event_pool_event(project_id, event_id)
        except ValueError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.post("/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding", response_model=NovelProjectResponse)
    def bind_event_pool_event(project_id: str, chapter_id: str, payload: StoryEventPoolBindingRequest) -> NovelProjectResponse:
        try:
            return novel.bind_event_pool_event_to_chapter(project_id, chapter_id, payload)
        except ValueError as exc:
            status = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

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
                state_delta=novel._json_dict(row["state_delta_json"] if "state_delta_json" in row.keys() else "{}"),
                planning_snapshot=novel._json_dict(row["planning_snapshot_json"] if "planning_snapshot_json" in row.keys() else "{}"),
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
        chapter = storage.get_novel_chapter(version["chapter_id"])
        if chapter:
            novel.mark_chapter_revision_boundary(version["project_id"], int(chapter["chapter_order"]))
        return novel.project_response(version["project_id"])

    @app.delete("/api/novel/versions/{version_id}", response_model=NovelProjectResponse)
    def delete_novel_version(version_id: str) -> NovelProjectResponse:
        version = storage.get_novel_version(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Novel version not found")
        deleted = storage.delete_novel_version(version_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Novel version not found")
        return novel.project_response(version["project_id"])
