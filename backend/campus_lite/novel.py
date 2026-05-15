from __future__ import annotations

import json
import os
import re
from typing import Any

from .bond import CharacterBondService
from .schemas import (
    CharacterCard,
    MemoryItem,
    NovelChapter,
    NovelContinuityIssue,
    NovelContinuityReport,
    NovelGenerateRequest,
    NovelGenerateResponse,
    NovelMaterial,
    NovelProjectCreateRequest,
    NovelProjectResponse,
    NovelVersion,
    StoryItem,
)
from .state import CharacterStateService
from .storage import Storage


PERSPECTIVE_LABELS = {
    "third_person": "第三人称",
    "user_view": "用户视角第一人称",
    "character_view": "角色视角第一人称",
    "dual_view": "双视角交错",
}

FORM_LABELS = {
    "daily_short": "日常短篇",
    "campus_romance": "校园恋爱短篇",
    "vignette": "片段随笔",
    "chapter_one": "第一章",
    "side_story": "番外",
}

FIDELITY_LABELS = {
    "faithful": "忠实原对话，只做少量衔接和描写",
    "polished": "轻度润色，保留事实并增强氛围",
    "literary": "文学化改编，可扩写心理和环境，但不制造重大关系进展",
}

MEMORY_LABELS = {
    "stable_user_info": "人物事实",
    "user_preference": "偏好细节",
    "relationship_progress": "关系进展",
    "open_thread": "未完成话题",
    "recent_emotion": "近期情绪",
    "manual_note": "手动备注",
}

MATERIAL_CATEGORY_LABELS = {
    "fact": "已确认事实",
    "foreshadowing": "可埋伏笔",
    "open_thread": "未完成线索",
    "relationship": "关系质感",
    "boundary": "边界规则",
    "inspiration": "可扩写灵感",
}

STORY_BIBLE_LABELS = {
    "confirmed_facts": "已确认事实",
    "foreshadowing": "只可暗示的伏笔",
    "unresolved_threads": "未解决线索",
    "relationships": "人物关系",
    "boundaries": "不可改写边界",
    "inspirations": "可扩写灵感",
}

INTERNAL_NOVEL_TERMS = {
    "prompt",
    "记忆系统",
    "评分",
    "内部模块",
    "用户/助手",
    "user/assistant",
    "recent_emotion",
    "stable_user_info",
    "user_preference",
    "relationship_progress",
    "open_thread",
    "memory_type",
    "source_material_ids",
    "Story Bible",
    "story_bible",
    "confirmed_facts",
    "foreshadowing",
    "unresolved_threads",
    "relationships",
    "boundaries",
    "inspirations",
}

INTERNAL_ID_PATTERN = re.compile(r"\b(?:mat|mem|msg|story|chapter|novel|ver)_[0-9a-f]{6,}\b", re.I)

META_NARRATION_PHRASES = [
    "这一章",
    "本章",
    "素材",
    "材料",
    "确认的事实",
    "已经确认的事实",
    "作为伏笔",
    "未完成线索",
    "关系推进",
    "创作过程",
    "生成",
    "用户喜欢",
    "用户询问",
]


def _env_timeout_ms(name: str, default: int) -> int:
    try:
        return max(1000, int(os.getenv(name) or default))
    except ValueError:
        return default


NOVEL_GENERATION_TIMEOUT_MS = _env_timeout_ms("NOVEL_GENERATION_TIMEOUT_MS", 120000)
NOVEL_CANVAS_TIMEOUT_MS = _env_timeout_ms("NOVEL_CANVAS_TIMEOUT_MS", 180000)
NOVEL_PLANNING_TIMEOUT_MS = _env_timeout_ms("NOVEL_PLANNING_TIMEOUT_MS", 90000)


class NovelService:
    def __init__(
        self,
        state_service: CharacterStateService,
        bond_service: CharacterBondService,
        storage: Storage | None = None,
    ) -> None:
        self.state_service = state_service
        self.bond_service = bond_service
        self.storage = storage

    async def generate(
        self,
        llm: Any,
        character: CharacterCard,
        visitor_id: str,
        session_id: str,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        request: NovelGenerateRequest,
    ) -> NovelGenerateResponse:
        state = self.state_service.get_state(session_id, character)
        bond = self.bond_service.get_bond(visitor_id, character.id, character)
        source = self._build_source(character, messages, memories, story_items, state, bond, request)
        if llm.configured():
            try:
                text = await llm.chat_complete([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": source},
                ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
                parsed = self._parse_response(text)
                return NovelGenerateResponse(
                    **parsed,
                    source_message_count=len(messages),
                    diagnostics={
                        "source": "remote",
                        "message_limit": request.message_limit,
                        "form": request.form,
                        "perspective": request.perspective,
                        "fidelity": request.fidelity,
                        "atmosphere": request.atmosphere,
                    },
                )
            except Exception as exc:
                llm.last_chat_error = type(exc).__name__
        fallback = self._mock_response(character, messages, memories, story_items, request)
        return NovelGenerateResponse(
            **fallback,
            source_message_count=len(messages),
            diagnostics={
                "source": "mock",
                "generation_mode": "local_fallback",
                "llm_configured": False,
                "message_limit": request.message_limit,
                "form": request.form,
                "perspective": request.perspective,
                "fidelity": request.fidelity,
                "atmosphere": request.atmosphere,
                "error": llm.last_chat_error,
            },
        )

    def create_project(
        self,
        character: CharacterCard,
        visitor_id: str,
        session_id: str,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        request: NovelProjectCreateRequest,
    ) -> NovelProjectResponse:
        storage = self._require_storage()
        story_bible = self.build_story_bible(character, memories, story_items)
        title = (request.title or "").strip() or f"{character.name}的长篇计划"
        worldview = request.worldview.strip() or self._default_worldview(character, story_items)
        relationship_setup = request.relationship_setup.strip() or self._default_relationship_setup(
            visitor_id,
            character,
            session_id,
            memories,
        )
        outline = request.outline.strip() or self._default_outline(character, story_items)
        story_canvas = request.story_canvas or self._default_story_canvas(
            title,
            request.genre,
            request.tone,
            request.protagonist or character.name,
            story_bible,
            story_items,
        )
        if not request.outline.strip():
            outline = self._canvas_outline(story_canvas)
        project_id = storage.create_novel_project(
            session_id,
            visitor_id,
            character.id,
            title,
            request.genre,
            request.tone,
            request.protagonist or character.name,
            worldview,
            relationship_setup,
            outline,
            story_bible,
            story_canvas,
        )
        self.seed_project_materials(project_id, messages, memories, story_items)
        story_canvas = self._story_canvas_with_materials(story_canvas, storage.list_novel_materials(project_id))
        storage.update_novel_project(project_id, {"story_canvas": story_canvas, "outline": self._canvas_outline(story_canvas)})
        if not storage.list_novel_chapters(project_id):
            first_chapter = self._canvas_chapters(story_canvas)[0] if self._canvas_chapters(story_canvas) else {}
            first_scene = self._canvas_scene_for_canvas_chapter(story_canvas, str(first_chapter.get("id", ""))) or {}
            storage.create_novel_chapter(
                project_id,
                str(first_chapter.get("title") or "第一章"),
                str(first_chapter.get("goal") or "建立角色当前关系和日常场景，不制造越界进展。"),
                "",
                "",
                "planned",
                first_scene,
                [row["id"] for row in storage.list_novel_materials(project_id)[:6]],
            )
        return self.project_response(project_id)

    async def build_canvas(self, llm: Any, project_id: str) -> NovelProjectResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        story_bible = self._json_dict(project["story_bible_json"])
        materials = storage.list_novel_materials(project_id)
        canvas = self._default_story_canvas(
            project["title"],
            project["genre"],
            project["tone"],
            project["protagonist"],
            story_bible,
            [],
        )
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._canvas_system_prompt()},
                {"role": "user", "content": self._canvas_source(project, story_bible, materials, canvas)},
            ], timeout_ms=NOVEL_CANVAS_TIMEOUT_MS, response_format={"type": "json_object"})
            canvas = self._parse_canvas_response(text, canvas)
            canvas["diagnostics"] = {**self._json_dict(canvas.get("diagnostics")), "source": "remote"}
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            canvas["diagnostics"] = {
                **self._json_dict(canvas.get("diagnostics")),
                "source": "local",
                "fallback_reason": type(exc).__name__,
                "fallback_detail": str(exc)[:240],
            }
        canvas = self._story_canvas_with_materials(canvas, materials)
        storage.update_novel_project(project_id, {"story_canvas": canvas, "outline": self._canvas_outline(canvas)})
        self._sync_chapters_from_canvas(project_id, canvas)
        return self.project_response(project_id)

    def _sync_chapters_from_canvas(self, project_id: str, canvas: dict[str, Any]) -> None:
        storage = self._require_storage()
        existing = list(storage.list_novel_chapters(project_id))
        existing_by_order = {int(row["chapter_order"]): row for row in existing}
        material_ids = [str(row["id"]) for row in storage.list_novel_materials(project_id)[:6]]
        for canvas_chapter in self._canvas_chapters(canvas):
            order = self._coerce_int(canvas_chapter.get("chapter_order"), len(existing_by_order) + 1, 1, 99)
            scene = self._canvas_scene_for_canvas_chapter(canvas, str(canvas_chapter.get("id", ""))) or {}
            updates = {
                "title": canvas_chapter.get("title") or f"第{order}章",
                "goal": canvas_chapter.get("goal") or canvas_chapter.get("external_event") or "",
                "scene_card": scene,
                "source_material_ids": material_ids,
            }
            row = existing_by_order.get(order)
            if row:
                storage.update_novel_chapter(row["id"], updates, "canvas")
            else:
                chapter_id = storage.create_novel_chapter(
                    project_id,
                    str(updates["title"]),
                    str(updates["goal"]),
                    "",
                    "",
                    "planned",
                    scene,
                    material_ids,
                )
                created = storage.get_novel_chapter(chapter_id)
                if created:
                    existing_by_order[int(created["chapter_order"])] = created

    def build_story_bible(
        self,
        character: CharacterCard,
        memories: list[MemoryItem],
        story_items: list[StoryItem],
    ) -> dict[str, Any]:
        facts = [item.content for item in memories if item.memory_type in {"stable_user_info", "user_preference"}][:8]
        relationship = [
            item.content
            for item in memories
            if item.memory_type in {"relationship_progress", "open_thread", "manual_note"}
        ][:8]
        foreshadowing = [
            item.content
            for item in story_items
            if item.kind in {"open_thread", "motif"} and item.status in {"seed", "active"}
        ][:8]
        unresolved = [
            item.content
            for item in story_items
            if item.kind == "open_thread" and item.status in {"seed", "active"}
        ][:8]
        boundaries = [*character.boundaries, *[item.content for item in story_items if item.kind == "boundary"]][:10]
        inspirations = [
            item.content
            for item in story_items
            if item.kind in {"story_beat", "relationship_texture"}
        ][:8]
        return {
            "confirmed_facts": facts,
            "foreshadowing": foreshadowing,
            "unresolved_threads": unresolved,
            "relationships": relationship,
            "boundaries": boundaries,
            "inspirations": inspirations,
        }

    def _canvas_system_prompt(self) -> str:
        return (
            "你是长篇小说 Story Canvas 规划师。你的任务是根据作品设定、Story Bible 和素材，"
            "生成结构化故事画布，不写正文。画布必须让后续章节能写成有事件、有阻碍、有选择、有钩子的小说。"
            "素材只作为熟悉感锚点，可以自由新增合理的校园日常事件、道具、误会和场面压力；"
            "不得改变已确认事实，不得把未发生线索写成已经发生。"
            "只输出严格 JSON 对象，不要 Markdown，不要注释，不要代码块，不要省略双引号。"
            "字段必须包含 version, mode, acts, chapters, scenes, threads, quality_rules, diagnostics。"
            "chapters 每项必须包含 id, act_id, chapter_order, title, goal, external_event, trigger_event, immediate_reaction, "
            "obstacle_escalation, counterpart_reaction, character_choice, scene_consequence, relationship_shift, ending_hook, "
            "target_length, status, emotion_curve, conflict_level, scene_ids。"
            "scenes 每项必须包含 id, chapter_id, scene_order, current_scene, pov, present_characters, surface_event, "
            "character_desire, tension, required_facts, forbidden_progress, ending_beat, linked_material_ids。"
        )

    def _canvas_source(
        self,
        project: Any,
        story_bible: dict[str, Any],
        materials: list[Any],
        fallback_canvas: dict[str, Any],
    ) -> str:
        material_lines = "\n".join(self._canvas_material_line(row) for row in materials[:8]) or "无"
        return "\n\n".join([
            "[作品设定]",
            f"标题：{project['title']}",
            f"类型：{project['genre']}",
            f"基调：{project['tone']}",
            f"主角：{project['protagonist']}",
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
            "[Story Bible]",
            self._story_bible_prompt(story_bible),
            "[可用素材]",
            material_lines,
            "[结构要求]",
            self._canvas_schema_hint(),
            "[生成要求]",
            "重新生成完整故事画布，从第 1 章开始编号，生成 4-6 章，不要续写旧画布，不要从第 5 章或后续章节开始。"
            "每章必须有一个具体外部事件、一个阻碍升级、一个人物小选择和一个具体结尾钩子。"
            "不要按聊天顺序把“晚饭、听歌、出去玩”等问答流水账改成章节。"
            "素材只允许作为 1-2 个熟悉锚点、道具、地点或伏笔，其余剧情必须自由创作具体校园事件。"
            "优先使用图书馆、走廊、公告栏、社团活动、课程误会、遗失物、雨天、便签、借书卡等可见事件承载关系推进。"
            f"角色名必须准确，主角只能写作“{project['protagonist']}”；不要写错别字或相近名字。"
            "场景卡必须写可见事件，不要写“关系变近”“两人还不熟”这类分析句。"
            "acts, chapters, scenes, threads 必须是数组。diagnostics.source 写 remote。",
        ])

    def _canvas_schema_hint(self) -> str:
        return (
            "acts: 4 个阶段对象；chapters: 4-6 个章节对象，chapter_order 必须为 1..N；"
            "scenes: 至少每章 1 个场景对象，chapter_id 必须指向章节 id；"
            "threads: 线索对象数组，可为空；quality_rules: 字符串数组。"
        )

    def _parse_canvas_response(self, text: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raw = self._load_llm_json_object(text, "canvas")
        if not isinstance(raw, dict):
            raise ValueError("Canvas payload is not an object")
        canvas = raw.get("story_canvas") if isinstance(raw.get("story_canvas"), dict) else raw
        if not isinstance(canvas, dict):
            raise ValueError("Canvas payload is not an object")
        chapters_raw = canvas.get("chapters")
        scenes_raw = canvas.get("scenes")
        if not isinstance(chapters_raw, list) or not chapters_raw:
            raise ValueError("Canvas missing chapters")
        if not isinstance(scenes_raw, list):
            scenes_raw = []

        fallback_chapters = self._canvas_chapters(fallback)
        fallback_scenes = self._canvas_scenes(fallback)
        acts_raw = canvas.get("acts") if isinstance(canvas.get("acts"), list) else fallback.get("acts", [])
        acts: list[dict[str, Any]] = []
        for index, item in enumerate(acts_raw[:8]):
            source = item if isinstance(item, dict) else {"title": item}
            acts.append({
                "id": str(source.get("id") or f"act_{index + 1}"),
                "order": self._coerce_int(source.get("order"), index + 1, 1, 99),
                "title": str(source.get("title") or f"阶段 {index + 1}")[:80],
                "purpose": str(source.get("purpose") or "")[:240],
                "chapter_ids": [str(value) for value in source.get("chapter_ids", [])] if isinstance(source.get("chapter_ids"), list) else [],
            })

        chapters: list[dict[str, Any]] = []
        for index, item in enumerate(chapters_raw[:12]):
            if not isinstance(item, dict):
                continue
            base = fallback_chapters[min(index, len(fallback_chapters) - 1)] if fallback_chapters else {}
            chapter_id = str(item.get("id") or base.get("id") or f"canvas_ch_{index + 1}")
            chapters.append({
                "id": chapter_id,
                "act_id": str(item.get("act_id") or base.get("act_id") or "act_1"),
                "chapter_order": index + 1,
                "title": self._normalize_chapter_title(str(item.get("title") or base.get("title") or ""), index + 1),
                "goal": str(item.get("goal") or base.get("goal") or "")[:500],
                "external_event": str(item.get("external_event") or base.get("external_event") or "")[:500],
                "trigger_event": str(item.get("trigger_event") or item.get("external_event") or base.get("trigger_event") or "")[:500],
                "immediate_reaction": str(item.get("immediate_reaction") or base.get("immediate_reaction") or "")[:500],
                "obstacle_escalation": str(item.get("obstacle_escalation") or base.get("obstacle_escalation") or "")[:500],
                "counterpart_reaction": str(item.get("counterpart_reaction") or base.get("counterpart_reaction") or "")[:500],
                "character_choice": str(item.get("character_choice") or base.get("character_choice") or "")[:500],
                "scene_consequence": str(item.get("scene_consequence") or base.get("scene_consequence") or "")[:500],
                "relationship_shift": str(item.get("relationship_shift") or base.get("relationship_shift") or "")[:260],
                "ending_hook": str(item.get("ending_hook") or base.get("ending_hook") or "")[:500],
                "target_length": self._coerce_int(item.get("target_length") or base.get("target_length"), 1800, 300, 12000),
                "status": str(item.get("status") or base.get("status") or "planned"),
                "emotion_curve": str(item.get("emotion_curve") or base.get("emotion_curve") or "")[:260],
                "conflict_level": self._coerce_int(item.get("conflict_level") or base.get("conflict_level"), 2, 1, 5),
                "scene_ids": [str(value) for value in item.get("scene_ids", [])] if isinstance(item.get("scene_ids"), list) else [],
            })

        chapter_ids = {chapter["id"] for chapter in chapters}
        first_chapter_id = chapters[0]["id"]
        derived_scenes = False
        if not scenes_raw:
            scenes_raw = self._derive_canvas_scenes_from_chapters(chapters)
            derived_scenes = True
        scenes: list[dict[str, Any]] = []
        for index, item in enumerate(scenes_raw[:20]):
            if not isinstance(item, dict):
                continue
            base = fallback_scenes[min(index, len(fallback_scenes) - 1)] if fallback_scenes else {}
            chapter_id = str(item.get("chapter_id") or base.get("chapter_id") or first_chapter_id)
            if chapter_id not in chapter_ids:
                chapter_id = first_chapter_id
            scenes.append({
                "id": str(item.get("id") or base.get("id") or f"scene_{index + 1}"),
                "chapter_id": chapter_id,
                "scene_order": self._coerce_int(item.get("scene_order"), index + 1, 1, 99),
                "current_scene": str(item.get("current_scene") or base.get("current_scene") or "")[:500],
                "pov": str(item.get("pov") or base.get("pov") or "")[:260],
                "present_characters": str(item.get("present_characters") or base.get("present_characters") or "")[:260],
                "surface_event": str(item.get("surface_event") or base.get("surface_event") or "")[:500],
                "character_desire": str(item.get("character_desire") or base.get("character_desire") or "")[:500],
                "tension": str(item.get("tension") or base.get("tension") or "")[:500],
                "required_facts": [str(value)[:260] for value in item.get("required_facts", [])] if isinstance(item.get("required_facts"), list) else [],
                "forbidden_progress": [str(value)[:260] for value in item.get("forbidden_progress", [])] if isinstance(item.get("forbidden_progress"), list) else [],
                "ending_beat": str(item.get("ending_beat") or base.get("ending_beat") or "")[:500],
                "linked_material_ids": [str(value) for value in item.get("linked_material_ids", [])] if isinstance(item.get("linked_material_ids"), list) else [],
            })

        threads_raw = canvas.get("threads") if isinstance(canvas.get("threads"), list) else []
        threads: list[dict[str, Any]] = []
        for index, item in enumerate(threads_raw[:12]):
            if not isinstance(item, dict):
                continue
            threads.append({
                "id": str(item.get("id") or f"thread_{index + 1}"),
                "kind": str(item.get("kind") or "foreshadowing")[:60],
                "label": str(item.get("label") or "")[:120],
                "setup_chapter_id": str(item.get("setup_chapter_id") or first_chapter_id),
                "payoff_chapter_id": str(item.get("payoff_chapter_id") or chapters[-1]["id"]),
                "status": str(item.get("status") or "seed")[:60],
                "notes": str(item.get("notes") or "")[:500],
            })

        quality_rules = canvas.get("quality_rules") if isinstance(canvas.get("quality_rules"), list) else fallback.get("quality_rules", [])
        diagnostics = self._json_dict(canvas.get("diagnostics"))
        if derived_scenes:
            diagnostics = {**diagnostics, "scene_source": "derived_from_chapters"}
        return {
            "version": self._coerce_int(canvas.get("version"), 1, 1, 99),
            "mode": str(canvas.get("mode") or "story_canvas"),
            "acts": acts or fallback.get("acts", []),
            "chapters": chapters,
            "scenes": scenes,
            "threads": threads or fallback.get("threads", []),
            "quality_rules": [str(value)[:240] for value in quality_rules],
            "diagnostics": diagnostics,
        }

    def _derive_canvas_scenes_from_chapters(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for index, chapter in enumerate(chapters):
            scene_ids = chapter.get("scene_ids") if isinstance(chapter.get("scene_ids"), list) else []
            scene_id = str(scene_ids[0]) if scene_ids else f"scene_{index + 1}"
            scenes.append({
                "id": scene_id,
                "chapter_id": chapter["id"],
                "scene_order": 1,
                "current_scene": chapter.get("external_event") or chapter.get("trigger_event") or chapter.get("title") or "",
                "pov": "第三人称限知",
                "present_characters": "",
                "surface_event": chapter.get("trigger_event") or chapter.get("external_event") or "",
                "character_desire": chapter.get("immediate_reaction") or chapter.get("goal") or "",
                "tension": chapter.get("obstacle_escalation") or "",
                "required_facts": [],
                "forbidden_progress": [],
                "ending_beat": chapter.get("ending_hook") or chapter.get("scene_consequence") or "",
                "linked_material_ids": [],
            })
        return scenes

    def _default_story_canvas(
        self,
        title: str,
        genre: str,
        tone: str,
        protagonist: str,
        story_bible: dict[str, Any],
        story_items: list[StoryItem],
    ) -> dict[str, Any]:
        lead = protagonist or title or "主角"
        inspirations = [item.content for item in story_items if item.kind in {"story_beat", "relationship_texture"}][:3]
        unresolved = [
            item.content
            for item in story_items
            if item.kind in {"open_thread", "motif"} and item.status in {"seed", "active"}
        ][:3]
        facts = [str(item).strip() for item in story_bible.get("confirmed_facts", []) if str(item).strip()][:3]
        boundaries = [str(item).strip() for item in story_bible.get("boundaries", []) if str(item).strip()][:3]
        hook = unresolved[0] if unresolved else "一次没有说满的普通回应，在下一次见面时变得更具体。"
        acts = [
            {"id": "act_1", "order": 1, "title": "初识与日常接触", "purpose": "用可见事件建立人物第一印象。", "chapter_ids": ["canvas_ch_1"]},
            {"id": "act_2", "order": 2, "title": "共同事件与小误会", "purpose": "让关系在共同处理问题时产生张力。", "chapter_ids": ["canvas_ch_2"]},
            {"id": "act_3", "order": 3, "title": "犹豫与选择", "purpose": "把未说出口的情绪转化为一次具体选择。", "chapter_ids": ["canvas_ch_3"]},
            {"id": "act_4", "order": 4, "title": "伏笔回收与情绪落点", "purpose": "回收前文线索，完成克制但明确的情绪变化。", "chapter_ids": ["canvas_ch_4"]},
        ]
        chapters = [
            {
                "id": "canvas_ch_1",
                "act_id": "act_1",
                "chapter_order": 1,
                "title": "第一章 校园初识",
                "goal": "通过一次具体的小事件让两人正式产生第一印象。",
                "external_event": "林晚栀在图书馆门口掉落书本，对方帮她捡起，两人因此第一次正式说话。",
                "trigger_event": "傍晚风从图书馆门口穿过，林晚栀怀里的书和便签一起散落。",
                "immediate_reaction": "她急忙蹲下去捡，先遮住便签，声音比平时轻。",
                "obstacle_escalation": "对方已经看见便签露出一角，但没有立刻问。",
                "counterpart_reaction": "对方把书脊理正递还给她，只提醒她夹页快掉了。",
                "character_choice": "林晚栀原本可以立刻走开，却停下来问了对方的名字。",
                "scene_consequence": "两人没有变熟，但彼此从路人变成了会被记住的人。",
                "relationship_shift": "从陌生到记住彼此名字。",
                "ending_hook": "分别后，林晚栀意识到自己记住了对方说话时的停顿。",
                "target_length": 1800,
                "status": "planned",
                "emotion_curve": "轻微紧张 -> 礼貌试探 -> 留下印象",
                "conflict_level": 2,
                "scene_ids": ["scene_1"],
            },
            {
                "id": "canvas_ch_2",
                "act_id": "act_2",
                "chapter_order": 2,
                "title": "第二章 共同的麻烦",
                "goal": "让两人因为一个普通问题短暂合作，并产生可见误会。",
                "external_event": "两人被同一件校园小事牵连，需要一起处理。",
                "trigger_event": "校园公告栏前的一张通知被贴错位置，两人都被临时叫去处理。",
                "immediate_reaction": "林晚栀想按规则重贴，对方却先去安抚等在旁边的人。",
                "obstacle_escalation": "旁人催促让两人的处理方式显得不一致，误会被放大。",
                "counterpart_reaction": "对方替她挡下一句玩笑，却让她误以为自己拖累了对方。",
                "character_choice": "林晚栀没有沉默离开，而是留下来把剩下的通知整理完。",
                "scene_consequence": "误会没解释清楚，但两人都有了下一次说话的理由。",
                "relationship_shift": "从礼貌相识到愿意多停留几分钟。",
                "ending_hook": "误会没有完全解释清楚，留下下一章继续见面的理由。",
                "target_length": 2000,
                "status": "planned",
                "emotion_curve": "熟悉感 -> 小误会 -> 想解释",
                "conflict_level": 3,
                "scene_ids": ["scene_2"],
            },
            {
                "id": "canvas_ch_3",
                "act_id": "act_3",
                "chapter_order": 3,
                "title": "第三章 没有说破的话",
                "goal": "把关系推进放在人物选择里，而不是直接表白或越界。",
                "external_event": "林晚栀在一个日常场景里选择主动回应对方一次。",
                "trigger_event": "放学后两人在安静角落再次遇见，前一章的误会被一句普通问候带出来。",
                "immediate_reaction": "林晚栀下意识想说没关系，却发现这次自己并不想敷衍过去。",
                "obstacle_escalation": "她越想解释，越怕这份在意显得过重。",
                "counterpart_reaction": "对方没有逼问，只把话题放慢，给她留下继续说的空隙。",
                "character_choice": "她主动补上一句真正想说的话，而不是只道谢。",
                "scene_consequence": "两人之间第一次出现了可被回望的信任停顿。",
                "relationship_shift": "从被动回应到主动靠近一点。",
                "ending_hook": "对方没有追问，只用一个动作接住她的迟疑。",
                "target_length": 2200,
                "status": "planned",
                "emotion_curve": "犹豫 -> 主动 -> 被温和接住",
                "conflict_level": 4,
                "scene_ids": ["scene_3"],
            },
            {
                "id": "canvas_ch_4",
                "act_id": "act_4",
                "chapter_order": 4,
                "title": "第四章 普通傍晚",
                "goal": "回收前文小线索，让关系停在可继续发展的明确落点。",
                "external_event": f"两人在普通傍晚重新谈到前文线索：{hook}",
                "trigger_event": "前文留下的小线索在傍晚重新出现，打断了原本普通的同行。",
                "immediate_reaction": "林晚栀先假装没有立刻认出来，指尖却停在书页边。",
                "obstacle_escalation": "她知道只要多问一句，关系就会被推到更近的位置。",
                "counterpart_reaction": "对方没有替她做决定，只把选择交还给她。",
                "character_choice": "她选择用一个普通约定回应，而不是把情绪说满。",
                "scene_consequence": "前文线索被回收，但新的日常约定被留下。",
                "relationship_shift": "从不确定到愿意约定下一次普通见面。",
                "ending_hook": "留下新的日常约定，而不是一次性完成关系。",
                "target_length": 2200,
                "status": "planned",
                "emotion_curve": "回望 -> 确认 -> 新的日常约定",
                "conflict_level": 3,
                "scene_ids": ["scene_4"],
            },
        ]
        scenes = [
            self._canvas_scene(
                "scene_1",
                "canvas_ch_1",
                1,
                f"{genre or '校园日常'}的傍晚，图书馆门口或教学楼走廊，氛围{tone or '温柔克制'}。",
                lead,
                "林晚栀抱着书经过时，书本被风吹散，对方帮她捡起，两人第一次正式说话。",
                "她想自然地道谢，也想确认对方是不是注意到了自己的慌乱。",
                "两人还不熟，只能用礼貌和停顿试探距离。",
                facts,
                boundaries,
                "她走远后才发现自己已经记住了对方的名字。",
            ),
            self._canvas_scene(
                "scene_2",
                "canvas_ch_2",
                1,
                "校园日常里的小麻烦现场，旁边有人经过，时间有限。",
                lead,
                "两人因为同一件事短暂合作，却在一句话里产生误会。",
                "她想把事情解释清楚，但不想显得太在意。",
                "对方的好意和她的紧张错开了半步。",
                facts,
                boundaries,
                "误会暂时没解开，却让下一次见面变得必要。",
            ),
            self._canvas_scene(
                "scene_3",
                "canvas_ch_3",
                1,
                "放学后的安静角落，周围声音渐渐远去。",
                lead,
                "林晚栀主动把一个普通话题接下去，而不是像以前那样停住。",
                "她想靠近一点，但仍希望自己保有退路。",
                "越是普通的话题，越容易暴露她真正的在意。",
                facts,
                boundaries,
                "对方没有追问，只把节奏放慢，等她继续说。",
            ),
            self._canvas_scene(
                "scene_4",
                "canvas_ch_4",
                1,
                "傍晚的校园路灯下，前文小线索重新出现。",
                lead,
                "两人重新谈到前文留下的小线索，并用日常方式完成一次确认。",
                "她想确认这份靠近是真的，但不想让它变成压力。",
                "关系已经变化，却不能被急着命名。",
                facts,
                boundaries,
                "他们约定下一次仍从一个普通话题开始。",
            ),
        ]
        threads = [
            {
                "id": "thread_1",
                "kind": "foreshadowing",
                "label": "未说满的话",
                "setup_chapter_id": "canvas_ch_1",
                "payoff_chapter_id": "canvas_ch_4",
                "status": "seed",
                "notes": hook,
            },
            {
                "id": "thread_2",
                "kind": "relationship",
                "label": "慢速靠近",
                "setup_chapter_id": "canvas_ch_1",
                "payoff_chapter_id": "canvas_ch_3",
                "status": "active",
                "notes": "每次推进必须表现为动作、对话或选择，不直接跳到关系确认。",
            },
        ]
        return {
            "version": 1,
            "mode": "story_canvas",
            "acts": acts,
            "chapters": chapters,
            "scenes": scenes,
            "threads": threads,
            "quality_rules": [
                "每章至少一个外部事件。",
                "每章至少两轮人物对话。",
                "每章至少一个人物小选择。",
                "结尾必须留下具体可续写钩子。",
            ],
            "diagnostics": {"source": "local"},
        }

    def _canvas_scene(
        self,
        scene_id: str,
        chapter_id: str,
        scene_order: int,
        current_scene: str,
        protagonist: str,
        surface_event: str,
        character_desire: str,
        tension: str,
        facts: list[str],
        boundaries: list[str],
        ending_beat: str,
    ) -> dict[str, Any]:
        return {
            "id": scene_id,
            "chapter_id": chapter_id,
            "scene_order": scene_order,
            "current_scene": current_scene,
            "pov": f"第三人称限知，主要贴近{protagonist}的感受。",
            "present_characters": protagonist,
            "surface_event": surface_event,
            "character_desire": character_desire,
            "tension": tension,
            "required_facts": facts,
            "forbidden_progress": boundaries or ["不突然表白、不亲密越界、不把未发生线索写成已发生。"],
            "ending_beat": ending_beat,
            "linked_material_ids": [],
        }

    def _story_canvas_with_materials(self, canvas: dict[str, Any], materials: list[Any]) -> dict[str, Any]:
        material_ids = [str(row["id"]) for row in materials[:6]]
        next_canvas = json.loads(json.dumps(canvas, ensure_ascii=False))
        for scene in self._canvas_scenes(next_canvas):
            if not scene.get("linked_material_ids"):
                scene["linked_material_ids"] = material_ids[:4]
        return next_canvas

    def _canvas_outline(self, canvas: dict[str, Any]) -> str:
        lines: list[str] = []
        for chapter in self._canvas_chapters(canvas):
            order = chapter.get("chapter_order") or len(lines) + 1
            title = chapter.get("title") or f"第{order}章"
            trigger = chapter.get("trigger_event") or chapter.get("external_event") or chapter.get("goal") or ""
            choice = chapter.get("character_choice") or chapter.get("relationship_shift") or ""
            hook = chapter.get("ending_hook") or ""
            lines.append(f"{order}. {title}：{trigger} → {choice} → {hook}")
        return "\n".join(lines)[:4000] or ""

    def _canvas_chapters(self, canvas: dict[str, Any]) -> list[dict[str, Any]]:
        chapters = canvas.get("chapters", [])
        return chapters if isinstance(chapters, list) else []

    def _canvas_scenes(self, canvas: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = canvas.get("scenes", [])
        return scenes if isinstance(scenes, list) else []

    def _canvas_scene_for_canvas_chapter(self, canvas: dict[str, Any], canvas_chapter_id: str) -> dict[str, Any] | None:
        for scene in self._canvas_scenes(canvas):
            if str(scene.get("chapter_id", "")) == canvas_chapter_id:
                return scene
        return None

    def _canvas_for_chapter(self, project: Any, chapter: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        matched_chapter: dict[str, Any] = {}
        chapter_order = int(chapter["chapter_order"])
        for item in self._canvas_chapters(canvas):
            if int(item.get("chapter_order") or 0) == chapter_order:
                matched_chapter = item
                break
        matched_scene = self._canvas_scene_for_canvas_chapter(canvas, str(matched_chapter.get("id", ""))) or {}
        return matched_chapter, matched_scene

    def seed_project_materials(
        self,
        project_id: str,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
    ) -> None:
        storage = self._require_storage()
        for memory in memories[:16]:
            category = "relationship" if memory.memory_type == "relationship_progress" else "fact"
            if memory.memory_type == "open_thread":
                category = "open_thread"
            storage.upsert_novel_material(
                project_id,
                "memory",
                memory.id,
                category,
                self._memory_label(memory.memory_type),
                memory.content,
                "explicit",
            )
        for item in story_items[:24]:
            category = {
                "boundary": "boundary",
                "open_thread": "foreshadowing",
                "relationship_texture": "relationship",
                "motif": "inspiration",
                "story_beat": "inspiration",
            }.get(item.kind, "inspiration")
            storage.upsert_novel_material(
                project_id,
                "story",
                item.id,
                category,
                item.label,
                item.content,
                item.evidence_level,
            )
        for message in messages[-12:]:
            if message.get("role") != "user":
                continue
            storage.upsert_novel_material(
                project_id,
                "message",
                message.get("id", ""),
                "fact",
                "会话片段",
                message.get("content", ""),
                "explicit",
            )

    async def generate_chapter(
        self,
        llm: Any,
        project_id: str,
        chapter_id: str | None,
        instruction: str,
        target_length: int,
    ) -> tuple[NovelProjectResponse, NovelChapter]:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        if chapter_id:
            chapter = storage.get_novel_chapter(chapter_id)
            if not chapter or chapter["project_id"] != project_id:
                raise ValueError("Novel chapter not found")
            effective_instruction = self._usable_instruction(instruction) or str(chapter["goal"] or "").strip() or "承接前文，推进一个可验证的小目标。"
        else:
            effective_instruction = self._usable_instruction(instruction) or "承接前文，推进一个可验证的小目标。"
            chapter_id = storage.create_novel_chapter(project_id, "下一章", effective_instruction, "", "", "drafting")
            chapter = storage.get_novel_chapter(chapter_id)
        assert chapter is not None
        materials = storage.list_novel_materials(project_id)
        previous = storage.list_novel_chapters(project_id)
        scene_card = self._chapter_scene_card(project, chapter, materials, previous, effective_instruction, target_length)
        scene_beats, beat_source = await self._build_scene_beats(
            llm,
            project,
            chapter,
            materials,
            previous,
            effective_instruction,
            target_length,
            scene_card,
        )
        source = self._chapter_source(project, chapter, materials, previous, effective_instruction, target_length, scene_card, scene_beats)
        source_name = "remote"
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._chapter_system_prompt()},
                {"role": "user", "content": source},
            ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
            parsed = self._parse_chapter_response(text, target_length)
            audit = await self._audit_chapter(llm, project, chapter, scene_card, scene_beats, parsed, target_length)
            if audit.get("pass") is False:
                rewrite_text = await llm.chat_complete([
                    {"role": "system", "content": self._chapter_system_prompt()},
                    {"role": "user", "content": self._rewrite_source(project, chapter, scene_card, scene_beats, parsed, audit, target_length)},
                ], timeout_ms=NOVEL_GENERATION_TIMEOUT_MS)
                parsed = self._parse_chapter_response(rewrite_text, target_length)
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            source_name = "mock"
            parsed = self._mock_chapter(project, chapter, materials, target_length, scene_card, scene_beats)
        storage.update_novel_chapter(
            chapter["id"],
            {
                "title": parsed["title"],
                "goal": effective_instruction,
                "summary": parsed["summary"],
                "body": parsed["body"],
                "status": "draft",
                "scene_card": {**scene_card, "scene_beats": scene_beats, "beat_source": beat_source},
                "source_material_ids": parsed["source_material_ids"],
            },
            source_name,
        )
        updated = storage.get_novel_chapter(chapter["id"])
        assert updated is not None
        return self.project_response(project_id), self._chapter_from_row(updated, include_versions=True)

    def check_continuity(self, project_id: str, chapter_id: str | None = None) -> NovelContinuityReport:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        story_bible = self._json_dict(project["story_bible_json"])
        story_canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        chapters = storage.list_novel_chapters(project_id)
        selected = storage.get_novel_chapter(chapter_id) if chapter_id else (chapters[-1] if chapters else None)
        text = selected["body"] if selected else ""
        issues: list[NovelContinuityIssue] = []
        for detail in self._chapter_quality_issues(text):
            issues.append(NovelContinuityIssue(severity="error", label="小说质检未通过", detail=detail))
        for boundary in story_bible.get("boundaries", [])[:8]:
            if boundary and ("承诺" in text or "越过边界" in text):
                issues.append(NovelContinuityIssue(severity="warning", label="边界风险", detail=str(boundary)[:160]))
                break
        for seed in story_bible.get("unresolved_threads", [])[:8]:
            if seed and seed in text and any(word in text for word in ["已经", "终于", "从此"]):
                issues.append(NovelContinuityIssue(severity="warning", label="伏笔状态需人工确认", detail=str(seed)[:160]))
                break
        if not text.strip():
            issues.append(NovelContinuityIssue(severity="warning", label="章节为空", detail="当前章节还没有正文可检查。"))
        canvas_chapters = self._canvas_chapters(story_canvas)
        canvas_scenes = self._canvas_scenes(story_canvas)
        if not canvas_chapters or not canvas_scenes:
            issues.append(NovelContinuityIssue(severity="warning", label="故事画布不完整", detail="建议先生成或补全故事画布，再生成长篇正文。"))
        if selected:
            canvas_chapter, canvas_scene = self._canvas_for_chapter(project, selected)
            if not canvas_chapter:
                issues.append(NovelContinuityIssue(severity="warning", label="章节未绑定画布", detail="当前章节没有对应的画布节点。"))
            if not canvas_scene:
                issues.append(NovelContinuityIssue(severity="warning", label="缺少场景卡节点", detail="当前章节没有可驱动正文的画布场景。"))
        if not issues:
            issues.append(NovelContinuityIssue(severity="ok", label="基础检查通过", detail="未发现内部措辞、空正文或明显伏笔状态风险。"))
        return NovelContinuityReport(
            project_id=project_id,
            chapter_id=selected["id"] if selected else None,
            issues=issues,
            summary="；".join(item.label for item in issues),
            diagnostics={"checker": "local"},
        )

    def project_response(self, project_id: str) -> NovelProjectResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        return self._project_from_row(project)

    def project_responses(self, session_id: str) -> list[NovelProjectResponse]:
        storage = self._require_storage()
        return [self._project_from_row(row) for row in storage.list_novel_projects(session_id)]

    def _system_prompt(self) -> str:
        return (
            "你是会话改编小说作者。你的任务是把给定聊天会话改编成中文短篇小说，"
            "保留角色卡、关系档案、记忆和原对话事实。允许润色场景、动作、心理和节奏，"
            "但不要捏造重大关系进展、承诺、亲密行为或用户没有表达过的事实。"
            "正文必须直接进入小说叙事，不要出现“这段会话”“如果写成小说”“用户”“助手”“生成”“材料”“记忆列表”等元叙述。"
            "不要把记忆逐条罗列进正文；如果使用记忆，必须转写成自然场景、心理或对白细节。"
            "只输出 JSON 对象，不要解释。JSON 字段必须包含 title, synopsis, body, used_memories。"
            "used_memories 是字符串数组，只列出正文确实使用到的记忆或关系依据。"
        )

    def _chapter_system_prompt(self) -> str:
        return (
            "你是长篇小说章节写作者。正文必须是小说场景，不是大纲说明、创作报告或素材整理。"
            "把设定和档案转化为动作、环境、对白、心理和节奏，至少写出八到十四个自然段。"
            "素材和 Story Bible 只是熟悉感锚点，不是剧情边界；只需要露出一到三处读者熟悉的线索。"
            "允许在不改变已确认事实的前提下自由新增校园日常里的小事件、道具、旁观者、误会、延误或场面压力。"
            "每一到两个段落都要让场面状态发生变化，不能只连续抒情或解释关系。"
            "不得改变已确认事实，不得越过角色边界，不得把未发生线索写成已经发生。"
            "正文里不得出现 prompt、记忆系统、评分、内部模块、用户、助手、JSON 字段名、素材编号、英文下划线字段名。"
            "不要写“这一章”“本章目标”“作为伏笔”“确认的事实”“两人还不熟”“关系变化”等元叙述或分析句。"
            "不要照抄场景卡、画布或 Scene Beats 的原句；开头直接进入可感知的场景。"
            "只输出 JSON 对象，字段为 title, summary, body, source_material_ids。"
        )

    def _build_source(
        self,
        character: CharacterCard,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        state: dict[str, Any],
        bond: dict[str, Any],
        request: NovelGenerateRequest,
    ) -> str:
        recent_messages = "\n".join(
            f"{item['role']}: {item['content']}" for item in messages[-request.message_limit :]
        )
        memory_lines = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in memories[:12]
        ) or "无"
        story_lines = "\n".join(
            f"- {item.kind}/{item.status}/{item.evidence_level}: {item.label} - {item.content}"
            for item in story_items
        ) or "无"
        return "\n\n".join([
            "[改编目标]",
            f"形式：{FORM_LABELS[request.form]}",
            f"视角：{PERSPECTIVE_LABELS[request.perspective]}",
            f"忠实度：{FIDELITY_LABELS[request.fidelity]}",
            f"氛围：{request.atmosphere}",
            f"目标长度：约 {request.target_length} 字",
            "[角色卡]",
            f"名字：{character.name}\n定位：{character.archetype}\n简介：{character.bio}\n口吻：{character.speech_style}\n边界：{'；'.join(character.boundaries)}",
            "[当前状态]",
            self.state_service.state_to_prompt(state),
            "[长期关系]",
            self.bond_service.bond_to_prompt(bond),
            "[可用记忆]",
            memory_lines,
            "[剧情窗格]",
            story_lines,
            "[原始会话]",
            recent_messages,
            "[输出要求]",
            "正文要像小说，不要保留 user/assistant 标签；不要提到 prompt、记忆系统、评分、内部模块；重大事实必须来自材料。"
            "禁止在正文里解释“这是会话改编”或列举记忆。开头直接进入场景，结尾停在自然的情绪落点。",
        ])

    def _parse_response(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Novel payload is not an object")
        title = str(raw.get("title") or "").strip()
        synopsis = str(raw.get("synopsis") or "").strip()
        body = str(raw.get("body") or "").strip()
        used = raw.get("used_memories") or []
        if not title or not synopsis or not body:
            raise ValueError("Novel payload is missing required fields")
        return {
            "title": title[:80],
            "synopsis": synopsis[:500],
            "body": body[:8000],
            "used_memories": [str(item).strip()[:240] for item in used if str(item).strip()][:12],
        }

    def _parse_chapter_response(self, text: str, target_length: int = 0) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Chapter payload is not an object")
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        body = str(raw.get("body") or "").strip()
        material_ids = raw.get("source_material_ids") or []
        if not title or not body:
            raise ValueError("Chapter payload is missing required fields")
        issues = self._chapter_quality_issues(body, target_length)
        if issues:
            raise ValueError("Chapter body failed quality check: " + "; ".join(issues[:4]))
        return {
            "title": title[:120],
            "summary": summary[:1200] or body[:180],
            "body": body[:20000],
            "source_material_ids": [str(item).strip() for item in material_ids if str(item).strip()][:24],
        }

    async def _build_scene_beats(
        self,
        llm: Any,
        project: Any,
        chapter: Any,
        materials: list[Any],
        chapters: list[Any],
        instruction: str,
        target_length: int,
        scene_card: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str]:
        fallback = self._mock_scene_beats(project, chapter, scene_card)
        try:
            if not llm.configured():
                raise RuntimeError("llm_not_configured")
            text = await llm.chat_complete([
                {"role": "system", "content": self._beat_system_prompt()},
                {"role": "user", "content": self._beat_source(project, chapter, materials, chapters, instruction, target_length, scene_card)},
            ], timeout_ms=NOVEL_PLANNING_TIMEOUT_MS)
            beats = self._parse_scene_beats(text)
            return beats or fallback, "remote"
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            return fallback, "mock"

    def _beat_system_prompt(self) -> str:
        return (
            "你是小说场景导演。你的任务不是写正文，而是把场景卡里的抽象信息转成可见 Scene Beats。"
            "必须把人物欲望、阻碍和关系变化转译成动作、停顿、对白和道具，不得保留分析句。"
            "只输出 JSON 对象，字段 beats 是数组。每个 beat 包含 type, purpose, visible_action, dialogue, inner_turn。"
            "dialogue 是字符串数组。不要写正文段落，不要解释。"
        )

    def _beat_source(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        chapters: list[Any],
        instruction: str,
        target_length: int,
        scene_card: dict[str, Any],
    ) -> str:
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        canvas_chapter, _canvas_scene = self._canvas_for_chapter(project, chapter)
        action_chain = self._chapter_action_chain_prompt(canvas_chapter)
        material_lines = "\n".join(self._material_prompt_line(row) for row in materials[:12]) or "无"
        previous = "\n".join(
            f"- 第{row['chapter_order']}章：{row['summary'] or row['goal']}"
            for row in chapters
            if row["id"] != chapter["id"]
        ) or "无"
        return "\n\n".join([
            "[目标]",
            f"把第{chapter['chapter_order']}章《{chapter['title']}》拆成 5-7 个 Scene Beats，目标约 {target_length} 字。",
            "[作品]",
            f"{project['title']}｜{project['genre']}｜{project['tone']}",
            "[故事画布]",
            self._canvas_prompt(canvas, canvas_chapter),
            "[本章场面推进链]",
            action_chain,
            "[场景卡]",
            self._scene_card_prompt(scene_card),
            "[已有章节]",
            previous,
            "[素材]",
            material_lines,
            "[用户生成指令]",
            instruction,
            "[硬约束]",
            "必须按本章场面推进链生成 beats：触发事件 -> 即时反应 -> 阻碍升级 -> 对方反应 -> 人物选择 -> 场景后果 -> 结尾钩子。"
            "保持一个连续大场景，但可以在场景内部新增一到两个校园日常小事件，例如广播、借书卡、值日生、突来的雨、掉落的物件或路过同学造成的打断。"
            "素材只是熟悉感锚点，不要把全部素材塞进 beats；优先让读者看到具体动作、对白、阻碍和选择。"
            "至少安排两轮自然对白；结尾必须是具体钩子。"
            "不要输出“关系变化”“张力”“两人还不熟”等分析语言，只输出可见动作、对白和内心转折。",
        ])

    def _chapter_action_chain_prompt(self, canvas_chapter: dict[str, Any]) -> str:
        if not canvas_chapter:
            return "无"
        pairs = [
            ("触发事件", canvas_chapter.get("trigger_event") or canvas_chapter.get("external_event")),
            ("即时反应", canvas_chapter.get("immediate_reaction")),
            ("阻碍升级", canvas_chapter.get("obstacle_escalation")),
            ("对方反应", canvas_chapter.get("counterpart_reaction")),
            ("人物选择", canvas_chapter.get("character_choice")),
            ("场景后果", canvas_chapter.get("scene_consequence") or canvas_chapter.get("relationship_shift")),
            ("结尾钩子", canvas_chapter.get("ending_hook")),
        ]
        return "\n".join(f"- {label}：{value}" for label, value in pairs if value) or "无"

    def _parse_scene_beats(self, text: str) -> list[dict[str, Any]]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No beat JSON object found")
        raw = json.loads(match.group(0))
        beats = raw.get("beats") if isinstance(raw, dict) else None
        if not isinstance(beats, list):
            raise ValueError("Scene beats missing")
        parsed: list[dict[str, Any]] = []
        for index, item in enumerate(beats[:8]):
            if not isinstance(item, dict):
                continue
            parsed.append({
                "type": str(item.get("type") or f"beat_{index + 1}")[:40],
                "purpose": self._clean_beat_text(str(item.get("purpose") or "")),
                "visible_action": self._clean_beat_text(str(item.get("visible_action") or "")),
                "dialogue": [
                    self._clean_beat_text(str(line))
                    for line in (item.get("dialogue") if isinstance(item.get("dialogue"), list) else [])
                    if str(line).strip()
                ][:3],
                "inner_turn": self._clean_beat_text(str(item.get("inner_turn") or "")),
            })
        if len(parsed) < 3:
            raise ValueError("Too few scene beats")
        return parsed

    def _clean_beat_text(self, text: str) -> str:
        clean = self._clean_material_text(text)
        forbidden = [
            "两人还不熟",
            "两人没有变熟",
            "从路人变成",
            "会被记住的人",
            "关系变化",
            "张力",
            "真正拦在",
            "只能用礼貌",
            "本章",
            "章节目标",
            "作为伏笔",
            "确认事实",
            "触发事件",
            "即时反应",
            "阻碍升级",
            "对方反应",
            "人物选择",
            "场景后果",
            "结尾钩子",
        ]
        for phrase in forbidden:
            clean = clean.replace(phrase, "")
        return clean.strip(" ，。；:：")[:260]

    def _mock_scene_beats(self, project: Any, chapter: Any, scene_card: dict[str, Any]) -> list[dict[str, Any]]:
        protagonist = project["protagonist"] or project["title"]
        canvas_chapter, _canvas_scene = self._canvas_for_chapter(project, chapter)
        place = self._clean_beat_text(str(scene_card.get("current_scene") or "图书馆门口的傍晚走廊"))
        if "校园日常" in place or "场景" in place:
            place = "图书馆门口的傍晚走廊"
        event = self._clean_beat_text(str(scene_card.get("surface_event") or "晚风把几张夹页从书里掀出来"))
        ending = self._clean_beat_text(str(scene_card.get("ending_beat") or "她在借阅单背面看见一行刚写下的字"))
        trigger = self._clean_beat_text(str(canvas_chapter.get("trigger_event") or event)) or event
        immediate = self._clean_beat_text(str(canvas_chapter.get("immediate_reaction") or "她蹲下去捡书，先把露出来的夹页按住。"))
        escalation = self._clean_beat_text(str(canvas_chapter.get("obstacle_escalation") or "借书处的铃声响起，身后有人催着还书，夹页却被风推到对方脚边。"))
        counterpart = self._clean_beat_text(str(canvas_chapter.get("counterpart_reaction") or "对方没有追问夹页上的字，只把它反扣着递回来。"))
        choice = self._clean_beat_text(str(canvas_chapter.get("character_choice") or "她本来可以道谢后离开，却停下来把掉出的借阅单也递给他确认。"))
        consequence = self._clean_beat_text(str(canvas_chapter.get("scene_consequence") or "她把这个名字默默放在心里，没有急着再问第二句。"))
        if len(consequence) < 10 or "彼此了" in consequence or "记住" in consequence:
            consequence = "她把这个名字默默放在心里，没有急着再问第二句。"
        hook = self._clean_beat_text(str(canvas_chapter.get("ending_hook") or ending)) or ending
        if "记住" in hook:
            hook = "她把便签夹回书页时，背面露出一行小字。"
        return [
            {
                "type": "establish",
                "purpose": "建立地点、人物和可见动作",
                "visible_action": f"{place}，闭馆前的提示音刚响过，{protagonist}抱着几本书从感应门旁经过。",
                "dialogue": [],
                "inner_turn": "她没有立刻回头，只把那句关心压回很轻的呼吸里。",
            },
            {
                "type": "trigger",
                "purpose": "用外部事件打断人物节奏",
                "visible_action": trigger,
                "dialogue": [],
                "inner_turn": immediate,
            },
            {
                "type": "pressure",
                "purpose": "制造阻碍和旁观压力",
                "visible_action": escalation,
                "dialogue": ["同学，借阅证别落下。", "我马上。"],
                "inner_turn": "她越想快一点，指尖越容易碰乱书页。",
            },
            {
                "type": "first_exchange",
                "purpose": "让对方用动作回应而不是解释",
                "visible_action": counterpart,
                "dialogue": ["这个是你的吧？", "谢谢。"],
                "inner_turn": "她接过来时才发现，对方把有字的一面避开了。",
            },
            {
                "type": "second_exchange",
                "purpose": "完成人物的小选择",
                "visible_action": choice,
                "dialogue": ["不用急，我只是怕你忘在这里。", "那你呢？这张借阅单也是你的吗？"],
                "inner_turn": "这句话出口以后，她才意识到自己没有立刻逃开。",
            },
            {
                "type": "hook",
                "purpose": "留下可续写的具体钩子",
                "visible_action": hook,
                "dialogue": [],
                "inner_turn": consequence,
            },
        ]

    def _scene_beats_prompt(self, beats: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, beat in enumerate(beats, 1):
            dialogue = " / ".join(str(item) for item in beat.get("dialogue", []) if str(item).strip()) or "无"
            lines.append(
                f"{index}. {beat.get('type', 'beat')}｜动作：{beat.get('visible_action', '')}｜"
                f"对白：{dialogue}｜内心转折：{beat.get('inner_turn', '')}"
            )
        return "\n".join(lines) or "无"

    async def _audit_chapter(
        self,
        llm: Any,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
        target_length: int,
    ) -> dict[str, Any]:
        local_issues = self._chapter_quality_issues(parsed.get("body", ""), target_length)
        if local_issues:
            return {"pass": False, "issues": local_issues, "source": "local"}
        try:
            if not llm.configured():
                return {"pass": True, "issues": [], "source": "local"}
            text = await llm.chat_complete([
                {"role": "system", "content": self._audit_system_prompt()},
                {"role": "user", "content": self._audit_source(project, chapter, scene_card, scene_beats, parsed)},
            ], timeout_ms=NOVEL_PLANNING_TIMEOUT_MS)
            return self._parse_audit_response(text)
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            return {"pass": True, "issues": [], "source": "audit_fallback"}

    def _audit_system_prompt(self) -> str:
        return (
            "你是小说章节质检器，只输出 JSON 对象。字段：pass 布尔值，issues 字符串数组，rewrite_brief 字符串。"
            "检查正文是否只有一个连续场景、有外部事件、至少两轮对白、没有分析句、没有重复抒情、结尾有具体钩子。"
            "如果只是风格可更好但可读，pass=true；如果像散文或复制场景卡说明，pass=false。"
        )

    def _audit_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
    ) -> str:
        return "\n\n".join([
            f"作品：{project['title']} / 第{chapter['chapter_order']}章《{chapter['title']}》",
            "[场景卡]",
            self._scene_card_prompt(scene_card),
            "[Scene Beats]",
            self._scene_beats_prompt(scene_beats),
            "[正文]",
            parsed.get("body", ""),
        ])

    def _parse_audit_response(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No audit JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Audit payload is not an object")
        issues = raw.get("issues") if isinstance(raw.get("issues"), list) else []
        return {
            "pass": bool(raw.get("pass", True)),
            "issues": [str(item).strip()[:200] for item in issues if str(item).strip()][:8],
            "rewrite_brief": str(raw.get("rewrite_brief") or "").strip()[:800],
            "source": "remote",
        }

    def _rewrite_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
        audit: dict[str, Any],
        target_length: int,
    ) -> str:
        return "\n\n".join([
            "[重写目标]",
            f"把以下草稿重写为约 {target_length} 字的小说正文。保留事实，但删除分析句、重复抒情和场景卡原句。",
            "[质检问题]",
            "；".join(str(item) for item in audit.get("issues", [])) or str(audit.get("rewrite_brief") or "需要增强场景事件和对白。"),
            "[Scene Beats，必须按顺序写成正文]",
            self._scene_beats_prompt(scene_beats),
            "[场景卡，只作约束，不得照抄]",
            self._scene_card_prompt(scene_card),
            "[原草稿]",
            parsed.get("body", ""),
            "[输出]",
            "只输出 JSON 对象，字段为 title, summary, body, source_material_ids。正文只能是小说场景。"
            "允许补入合理的校园小事件来制造推进，但不要新增重大关系进展。",
        ])

    def _chapter_source(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        chapters: list[Any],
        instruction: str,
        target_length: int,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
    ) -> str:
        material_lines = "\n".join(
            self._material_prompt_line(row)
            for row in materials[:40]
        ) or "无"
        previous_lines = "\n".join(
            f"- 第{row['chapter_order']}章《{row['title']}》：{row['summary'] or row['goal']}"
            for row in chapters
            if row["id"] != chapter["id"]
        ) or "无"
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        canvas_chapter, _canvas_scene = self._canvas_for_chapter(project, chapter)
        current_body = str(chapter["body"] or "").strip()
        current_body_excerpt = current_body[-1600:] if current_body else "无"
        return "\n\n".join([
            "[作品设定]",
            f"标题：{project['title']}",
            f"类型：{project['genre']}",
            f"基调：{project['tone']}",
            f"主角：{project['protagonist']}",
            f"世界观：{project['worldview']}",
            f"关系设定：{project['relationship_setup']}",
            "[大纲]",
            project["outline"],
            "[故事画布]",
            self._canvas_prompt(canvas, canvas_chapter),
            "[设定档案]",
            self._story_bible_prompt(self._json_dict(project["story_bible_json"])),
            "[可转写素材]",
            material_lines,
            "[已有章节]",
            previous_lines,
            "[当前章节已有正文]",
            current_body_excerpt,
            "[Scene Card 场景卡]",
            self._scene_card_prompt(scene_card),
            "[Scene Beats 可见动作清单]",
            self._scene_beats_prompt(scene_beats),
            "[本章目标]",
            f"章节：第{chapter['chapter_order']}章《{chapter['title']}》",
            f"目标：{instruction or chapter['goal']}",
            f"长度：约 {target_length} 字",
            "[输出硬约束]",
            "必须先遵守 Scene Card 场景卡：正文要写出当前场景、人物欲望、阻碍/张力和结尾落点。"
            "但不得照抄 Scene Card 的抽象说明，必须按 Scene Beats 写成可见动作、对白和停顿。"
            "素材和设定只作为锚点，不要把熟悉线索逐条写完；可以自由新增合理的小事件让场面动起来。"
            "正文直接进入小说叙事，不解释创作过程，不复述档案类别，不出现任何编号或字段名。"
            "JSON 的 source_material_ids 只在字段值里列出真正采用的引用编号，正文 body 里绝对不要写编号。",
        ])

    def _chapter_scene_card(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        chapters: list[Any],
        instruction: str,
        target_length: int,
    ) -> dict[str, Any]:
        existing = self._json_dict(chapter["scene_card_json"] if "scene_card_json" in chapter.keys() else "{}")
        defaults = self._default_scene_card(project, chapter, materials, chapters, instruction, target_length)
        if not existing:
            return defaults
        return {
            **defaults,
            **{key: value for key, value in existing.items() if str(value).strip()},
        }

    def _default_scene_card(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        chapters: list[Any],
        instruction: str,
        target_length: int,
    ) -> dict[str, Any]:
        facts = [row["content"] for row in materials if row["category"] in {"fact", "relationship"}][:4]
        boundaries = [row["content"] for row in materials if row["category"] == "boundary"][:3]
        previous = [row for row in chapters if str(row["body"] or row["summary"] or "").strip()]
        previous_summary = str(previous[-1]["summary"] or previous[-1]["goal"] or "")[:220] if previous else ""
        protagonist = project["protagonist"] or project["title"]
        tone = project["tone"] or "温柔、克制、日常"
        _canvas_chapter, canvas_scene = self._canvas_for_chapter(project, chapter)
        defaults = {
            "current_scene": f"{tone}的校园日常场景，承接上一章但直接进入可感知的地点、光线和动作。",
            "pov": f"贴近{protagonist}与对方的第三人称限知视角，避免上帝视角总结。",
            "present_characters": protagonist,
            "surface_event": self._scene_surface_event(instruction),
            "character_desire": "人物想把话说清一点，但仍希望保留安全距离和选择余地。",
            "tension": "两个人都意识到某些话还没到能说破的时候，越想靠近，越需要把分寸放稳。",
            "required_facts": facts or ([previous_summary] if previous_summary else []),
            "forbidden_progress": boundaries or ["不得突然承诺、表白、亲密越界或把伏笔写成已经发生。"],
            "ending_beat": "停在一个自然可续写的动作、对白或沉默上。",
        }
        if canvas_scene:
            defaults.update({key: value for key, value in canvas_scene.items() if key in defaults and value})
        return defaults

    def _scene_card_prompt(self, scene_card: dict[str, Any]) -> str:
        labels = {
            "current_scene": "当前场景",
            "pov": "视角",
            "present_characters": "在场人物",
            "surface_event": "表层事件",
            "character_desire": "人物欲望",
            "tension": "阻碍/张力",
            "required_facts": "必须保留事实",
            "forbidden_progress": "禁止推进",
            "ending_beat": "结尾落点",
        }
        lines: list[str] = []
        for key, label in labels.items():
            value = scene_card.get(key, "")
            text = "；".join(str(item) for item in value if str(item).strip()) if isinstance(value, list) else str(value).strip()
            lines.append(f"- {label}：{text or '未设定'}")
        return "\n".join(lines)

    def _scene_surface_event(self, instruction: str) -> str:
        clean = self._usable_instruction(instruction)
        if not clean:
            return "两个人在傍晚的日常场景里继续交谈，通过动作、停顿和一句未说满的话推进彼此的理解。"
        meta_terms = ["生成", "续写", "写出", "正文", "本章", "章节", "下一章", "目标", "字"]
        if any(term in clean for term in meta_terms):
            return "两个人在傍晚的日常场景里继续交谈，通过动作、停顿和一句未说满的话推进彼此的理解。"
        return clean[:240]

    def _mock_scene_line(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        meta_terms = ["生成", "续写", "正文", "本章", "章节", "目标", "伏笔", "边界", "禁止", "约 ", "自然可续写", "动作、对白", "沉默上"]
        if any(term in text for term in meta_terms):
            return fallback
        return text.rstrip("。")[:240] + "。"

    def _mock_body_from_beats(
        self,
        protagonist: str,
        beats: list[dict[str, Any]],
        first_hint: str,
        surface_event: str,
        ending_beat: str,
    ) -> list[str]:
        paragraphs: list[str] = []
        for index, beat in enumerate(beats[:7]):
            action = self._mock_scene_line(beat.get("visible_action"), surface_event if index == 0 else "风把纸页轻轻掀起。")
            inner = self._mock_scene_line(beat.get("inner_turn"), "她把话放慢了一点。")
            dialogue = [str(item).strip("“”\" ") for item in beat.get("dialogue", []) if str(item).strip()]
            if dialogue:
                lines = []
                for item_index, line in enumerate(dialogue[:3]):
                    speaker = protagonist if item_index % 2 else "对方"
                    verb = "说" if item_index % 2 else "问"
                    lines.append(f"“{line}”{speaker}{verb}。")
                paragraphs.append(f"{action}{''.join(lines)}{inner}")
            elif index == 0:
                paragraphs.append(f"{action}她想起{first_hint}，脚步因此慢了半拍。{inner}")
            else:
                paragraphs.append(f"{action}{inner}")
        return paragraphs

    def _mock_scene_continuations(self, protagonist: str, first_hint: str) -> list[str]:
        return [
            f"借阅台旁边排着两个人，打印机吐出一截白纸，又卡在半路。管理员低声提醒队伍往里收，{protagonist}只好把散开的书先靠在墙边，空出一只手去找那张不见的借阅单。",
            "她看见纸角压在对方鞋边，弯腰时校牌从书页间滑出来，轻轻磕在地上。对方比她先一步拾起，却没有马上递回，只把校牌翻到背面，确认没有弄脏。",
            f"“林晚栀？”对方念得很轻，像只是核对名字。{protagonist}抬头看了他一眼，又很快移开，“嗯。”",
            "后面有人小声说快闭馆了。风从门缝里挤进来，把玻璃门吹得响了一下。她本来想把所有东西抱回怀里，却发现最上面那本书不是自己的。",
            "那本书的扉页夹着一张课程表，边缘被雨水洇出一点浅痕。她犹豫了一瞬，把书递过去：“这个好像拿错了。”",
            "对方接过去，低头看见课程表上的教室号，忽然笑了一下：“我们明天同一栋楼上课。”这句话不算熟络，却让走廊里的距离短了一点。",
            f"{protagonist}没有顺着笑意多说，只把自己的书一本一本理齐。那句关于{first_hint}的念头又浮上来，她这次没有急着按下去，只让它停在翻书的动作里。",
            "管理员终于把卡住的纸抽出来，借阅台前空出一条窄路。对方往旁边让了让，手里还拿着那张被风吹皱的便签。",
            "“这张也给你。”他说。便签背面朝上，干干净净，看不出他到底有没有看见上面的字。",
            f"{protagonist}接过来，指尖碰到纸边时顿了一下。她想说没关系，又觉得这三个字太像匆忙收场，最后只低声问：“你叫什么？”",
            "对方报出名字。走廊尽头的灯在这时亮起来，把他身后的影子拉得很长。她重复了一遍，声音很轻，却没有念错。",
            "两个人并肩走到门口，雨已经下起来，台阶上积着一层薄亮的水。她停在屋檐下面，把便签夹回书里，才发现背面多了一行极小的字：明天别忘了带伞。",
        ]

    def _mock_chapter(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        target_length: int,
        scene_card: dict[str, Any] | None = None,
        scene_beats: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        chosen = materials[:6]
        detail_hints = []
        for row in chosen[:5]:
            hint = self._naturalize_material(row["content"])
            if hint and hint not in detail_hints:
                detail_hints.append(hint)
        first_hint = detail_hints[0] if detail_hints else "一段没说完的心事"
        protagonist = project["protagonist"] or project["title"]
        card = scene_card or {}
        surface_event = self._mock_scene_line(
            card.get("surface_event") or chapter["goal"],
            "两个人在傍晚的日常场景里继续交谈，通过动作、停顿和一句未说满的话推进彼此的理解。",
        )
        ending_beat = self._mock_scene_line(
            card.get("ending_beat"),
            "她在借阅单背面看见一行刚写下的字。",
        )
        beats = scene_beats or self._mock_scene_beats(project, chapter, card)
        paragraphs = self._mock_body_from_beats(protagonist, beats, first_hint, surface_event, ending_beat)
        target_floor = max(260, int(max(target_length, 400) * 0.76))
        continuations = self._mock_scene_continuations(protagonist, first_hint)
        index = 0
        body = "\n\n".join(paragraphs)
        while len(re.sub(r"\s", "", body)) < target_floor and index < len(continuations):
            paragraphs.append(continuations[index])
            body = "\n\n".join(paragraphs)
            index += 1
        return {
            "title": chapter["title"] if chapter["title"] != "下一章" else f"第{chapter['chapter_order']}章：余温",
            "summary": "在连续校园场景中写出外部事件、人物选择和可续写的结尾。",
            "body": body,
            "source_material_ids": [row["id"] for row in chosen],
        }

    def _memory_label(self, memory_type: str) -> str:
        return MEMORY_LABELS.get(memory_type, "人物档案")

    def _material_prompt_line(self, row: Any) -> str:
        category = MATERIAL_CATEGORY_LABELS.get(str(row["category"]), "可用细节")
        label = str(row["label"] or category)
        content = self._clean_material_text(str(row["content"] or ""))
        return f"- 引用编号 {row['id']}｜{category}｜{label}：{content}"

    def _canvas_material_line(self, row: Any) -> str:
        category = MATERIAL_CATEGORY_LABELS.get(str(row["category"]), "可用细节")
        content = self._clean_material_text(str(row["content"] or ""))
        return f"- {category}：{content}"

    def _canvas_prompt(self, canvas: dict[str, Any], current_chapter: dict[str, Any]) -> str:
        if not canvas:
            return "无"
        lines: list[str] = []
        for chapter in self._canvas_chapters(canvas)[:8]:
            prefix = "当前章节" if chapter.get("id") == current_chapter.get("id") else f"第{chapter.get('chapter_order', '?')}章"
            lines.append(
                f"- {prefix}《{chapter.get('title', '')}》：触发={chapter.get('trigger_event') or chapter.get('external_event', '')}；"
                f"反应={chapter.get('immediate_reaction', '')}；升级={chapter.get('obstacle_escalation', '')}；"
                f"对方={chapter.get('counterpart_reaction', '')}；选择={chapter.get('character_choice', '')}；"
                f"后果={chapter.get('scene_consequence') or chapter.get('relationship_shift', '')}；钩子={chapter.get('ending_hook', '')}"
            )
        threads = canvas.get("threads", [])
        if isinstance(threads, list) and threads:
            lines.append("线索：")
            for thread in threads[:6]:
                lines.append(f"- {thread.get('label', '')}：{thread.get('notes', '')}｜{thread.get('status', '')}")
        return "\n".join(line for line in lines if line.strip()) or "无"

    def _story_bible_prompt(self, story_bible: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, label in STORY_BIBLE_LABELS.items():
            values = [str(item).strip() for item in story_bible.get(key, []) if str(item).strip()]
            if not values:
                continue
            lines.append(f"{label}：")
            lines.extend(f"- {self._clean_material_text(value)}" for value in values[:8])
        return "\n".join(lines) or "无"

    def _clean_material_text(self, text: str) -> str:
        clean = text.strip()
        replacements = {
            "用户的名字是": "名字是",
            "用户喜欢": "喜欢",
            "用户询问": "提到",
            "用户问": "提到",
            "我喜欢": "喜欢",
            "我想": "想",
            "我希望": "希望",
            "assistant": "",
            "user": "",
        }
        for old, new in replacements.items():
            clean = clean.replace(old, new)
        clean = INTERNAL_ID_PATTERN.sub("", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" ：:-")
        return clean[:280]

    def _usable_instruction(self, text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return ""
        compact = re.sub(r"\s", "", clean)
        if compact and compact.count("?") / max(len(compact), 1) > 0.6:
            return ""
        signal = re.sub(r"[\s,，.。!?！？;；:：\"'“”‘’、\-]", "", clean)
        if signal and signal.count("?") / max(len(signal), 1) > 0.6:
            return ""
        if "�" in clean:
            return ""
        return clean[:1000]

    def _chapter_quality_issues(self, body: str, target_length: int = 0) -> list[str]:
        text = body.strip()
        lower_text = text.lower()
        issues: list[str] = []
        for term in sorted(INTERNAL_NOVEL_TERMS, key=len, reverse=True):
            if term.lower() in lower_text:
                issues.append(f"正文包含内部措辞「{term}」")
        if INTERNAL_ID_PATTERN.search(text):
            issues.append("正文包含内部引用编号")
        for phrase in META_NARRATION_PHRASES:
            if phrase in text:
                issues.append(f"正文偏创作说明「{phrase}」")
        analysis_phrases = [
            "校园日常长篇",
            "当前场景",
            "表层事件",
            "人物欲望",
            "阻碍",
            "张力",
            "关系变化",
            "两人还不熟",
            "从路人变成",
            "真正拦在",
            "只能用礼貌",
            "熟悉线索",
            "触发事件",
            "即时反应",
            "对方反应",
            "人物选择",
            "场景后果",
            "结尾钩子",
            "目标长度",
            "Scene",
            "beats",
        ]
        for phrase in analysis_phrases:
            if phrase in text:
                issues.append(f"正文含有大纲或分析措辞「{phrase}」")
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
        seen: set[str] = set()
        for paragraph in paragraphs:
            compact = re.sub(r"\s", "", paragraph)
            if len(compact) > 30 and compact in seen:
                issues.append("正文包含重复段落")
                break
            seen.add(compact)
        dialogue_count = len(re.findall(r"[“\"].+?[”\"]", text))
        if target_length >= 600 and dialogue_count < 2:
            issues.append("正文缺少足够人物对话")
        if text.count("听见自己的声音") >= 2:
            issues.append("正文反复使用同一心理句式")
        if len(text) < 120:
            issues.append("正文过短")
        if target_length >= 600 and len(re.sub(r"\s", "", text)) < int(target_length * 0.55):
            issues.append(f"正文明显短于目标长度 {target_length} 字")
        return issues

    def _naturalize_material(self, text: str) -> str:
        clean = self._clean_material_text(text)
        clean = clean.rstrip("。！？")
        if not clean:
            return ""
        if "吃过晚饭" in clean:
            return "那句关于晚饭的关心"
        if "晚饭" in clean and "关心" in clean:
            return "那句关于晚饭的关心"
        if "关心" in clean:
            return "一份被认真接住的关心"
        if "喜欢" in clean:
            obj = clean.split("喜欢", 1)[1].split("，", 1)[0].strip()
            if any(term in obj for term in ["校园日常", "长篇", "叙事", "温柔克制"]):
                return "傍晚图书馆里的安静"
            return f"对{obj}的偏爱" if obj else "一点安静的偏爱"
        if "樱花" in clean and any(word in clean for word in ["后面", "后续", "以后", "之后"]):
            return "尚未展开的樱花话题"
        if clean.startswith("提到"):
            return "一个被轻轻提起的话题"
        if clean.startswith("想把"):
            return clean.replace("想把", "把", 1)
        if clean.startswith("名字是"):
            return ""
        return clean[:90]

    def _default_worldview(self, character: CharacterCard, story_items: list[StoryItem]) -> str:
        motifs = "、".join(item.label for item in story_items if item.kind == "motif") or "日常校园与聊天里的细节"
        return f"故事发生在贴近日常的校园/生活场域，核心意象包括{motifs}。世界观服务于人物关系，不制造脱离会话事实的大设定。"

    def _default_relationship_setup(
        self,
        visitor_id: str,
        character: CharacterCard,
        session_id: str,
        memories: list[MemoryItem],
    ) -> str:
        bond = self.bond_service.get_bond(visitor_id, character.id, character)
        memory_hints = "；".join(item.content for item in memories if item.memory_type == "relationship_progress")[:600]
        return "；".join([
            self.bond_service.bond_to_prompt(bond),
            memory_hints,
            "关系推进必须慢，重大进展必须来自用户已经表达过的事实。",
        ])

    def _default_outline(self, character: CharacterCard, story_items: list[StoryItem]) -> str:
        beats = [item.content for item in story_items if item.kind in {"story_beat", "open_thread", "relationship_texture"}][:4]
        if not beats:
            beats = ["第一章建立日常场景和角色口吻。", "第二章承接未完成话题。", "第三章让关系在边界内产生细微变化。"]
        return "\n".join(f"{index + 1}. {beat}" for index, beat in enumerate(beats))

    def _project_from_row(self, row: Any) -> NovelProjectResponse:
        storage = self._require_storage()
        return NovelProjectResponse(
            id=row["id"],
            session_id=row["session_id"],
            visitor_id=row["visitor_id"],
            character_id=row["character_id"],
            title=row["title"],
            genre=row["genre"],
            tone=row["tone"],
            protagonist=row["protagonist"],
            worldview=row["worldview"],
            relationship_setup=row["relationship_setup"],
            outline=row["outline"],
            story_bible=self._json_dict(row["story_bible_json"]),
            story_canvas=self._json_dict(row["story_canvas_json"] if "story_canvas_json" in row.keys() else "{}"),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            materials=[self._material_from_row(item) for item in storage.list_novel_materials(row["id"])],
            chapters=[self._chapter_from_row(item) for item in storage.list_novel_chapters(row["id"])],
        )

    def _material_from_row(self, row: Any) -> NovelMaterial:
        return NovelMaterial(
            id=row["id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            category=row["category"],
            label=row["label"],
            content=row["content"],
            evidence_level=row["evidence_level"],
            created_at=row["created_at"],
        )

    def _chapter_from_row(self, row: Any, include_versions: bool = False) -> NovelChapter:
        storage = self._require_storage()
        return NovelChapter(
            id=row["id"],
            project_id=row["project_id"],
            chapter_order=int(row["chapter_order"]),
            title=row["title"],
            goal=row["goal"],
            summary=row["summary"],
            body=row["body"],
            status=row["status"],
            scene_card=self._json_dict(row["scene_card_json"]),
            source_material_ids=self._json_list(row["source_material_ids_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            versions=[self._version_from_row(item) for item in storage.list_novel_versions(row["id"])] if include_versions else [],
        )

    def _version_from_row(self, row: Any) -> NovelVersion:
        return NovelVersion(
            id=row["id"],
            chapter_id=row["chapter_id"],
            version_type=row["version_type"],
            title=row["title"],
            body=row["body"],
            summary=row["summary"],
            source=row["source"],
            created_at=row["created_at"],
        )

    def _json_dict(self, text: Any) -> dict[str, Any]:
        if isinstance(text, dict):
            return text
        try:
            parsed = json.loads(text or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _json_list(self, text: Any) -> list[str]:
        if isinstance(text, list):
            return [str(item) for item in text]
        try:
            parsed = json.loads(text or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    def _load_llm_json_object(self, text: str, label: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"No {label} JSON object found")
        raw = match.group(0).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as first_error:
            repaired = self._repair_llm_json(raw)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                decoder = json.JSONDecoder()
                for brace in [item.start() for item in re.finditer(r"\{", repaired)]:
                    try:
                        parsed, _ = decoder.raw_decode(repaired[brace:])
                        break
                    except json.JSONDecodeError:
                        continue
                else:
                    raise first_error
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} JSON payload is not an object")
        return parsed

    def _repair_llm_json(self, text: str) -> str:
        repaired = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        repaired = re.sub(r"```(?:json)?|```", "", repaired, flags=re.I)
        repaired = re.sub(r"^\s*//.*$", "", repaired, flags=re.M)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        repaired = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', repaired)
        return repaired.strip()

    def _coerce_int(self, value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
        if isinstance(value, bool):
            result = default
        elif isinstance(value, (int, float)):
            result = int(value)
        else:
            match = re.search(r"\d+", str(value or ""))
            result = int(match.group(0)) if match else default
        if minimum is not None:
            result = max(minimum, result)
        if maximum is not None:
            result = min(maximum, result)
        return result

    def _normalize_chapter_title(self, title: str, order: int) -> str:
        clean = str(title or "").strip()
        clean = re.sub(r"^第[一二三四五六七八九十百千万\d]+章[\s：:、.-]*", "", clean).strip()
        if not clean:
            clean = f"章节 {order}"
        return f"第{order}章 {clean}"[:120]

    def _require_storage(self) -> Storage:
        if self.storage is None:
            raise RuntimeError("NovelService storage is required for project mode")
        return self.storage

    def _mock_response(
        self,
        character: CharacterCard,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        story_items: list[StoryItem],
        request: NovelGenerateRequest,
    ) -> dict[str, Any]:
        visible = messages[-min(request.message_limit, len(messages)) :]
        user_lines = [item["content"] for item in visible if item["role"] == "user"]
        assistant_lines = [item["content"] for item in visible if item["role"] == "assistant"]
        first_user = self._clean_scene_fragment(user_lines[0] if user_lines else "有人把一句很轻的话放进了这段会话。")
        last_user = self._clean_scene_fragment(user_lines[-1] if user_lines else first_user)
        last_assistant = self._clean_scene_fragment(assistant_lines[-1] if assistant_lines else character.opening_line)
        memory_texts = [item.content for item in memories[:4]]
        story_texts = [item.content for item in story_items[:6]]
        memory_hint = self._memory_sentence([*story_texts[:3], *memory_texts[:3]])
        user_name = self._extract_user_name(memory_texts) or "他"
        title = self._fallback_title(character, request)
        synopsis = (
            f"{FORM_LABELS[request.form]}，采用{PERSPECTIVE_LABELS[request.perspective]}，"
            f"以{request.atmosphere}的笔调写下{character.name}和{user_name}之间一次很轻的靠近。"
        )
        body = self._compose_mock_body(
            character,
            request,
            user_name,
            first_user,
            last_user,
            last_assistant,
            memory_hint,
        )
        return {
            "title": title,
            "synopsis": synopsis,
            "body": body,
            "used_memories": memory_texts,
        }

    def _compose_mock_body(
        self,
        character: CharacterCard,
        request: NovelGenerateRequest,
        user_name: str,
        first_user: str,
        last_user: str,
        last_assistant: str,
        memory_hint: str,
    ) -> str:
        atmosphere = request.atmosphere.strip() or "温柔、克制、日常"
        scene = self._fallback_scene(request.form, atmosphere)
        focus = self._fallback_form_focus(request.form)
        fidelity = self._fallback_fidelity_line(request.fidelity)
        if request.perspective == "user_view":
            paragraphs = [
                f"{scene}我把那句“{first_user[:120]}”发出去以后，指尖还停在屏幕边缘。",
                f"{character.name}没有立刻把话接得很满。{memory_hint}她的回应落下来时，像把一盏灯调暗了一格：{last_assistant[:180]}",
                f"我重新读了一遍自己的话，又想起刚才说过的“{last_user[:120]}”。{fidelity}{focus}",
            ]
        elif request.perspective == "character_view":
            paragraphs = [
                f"{scene}我看见那句“{first_user[:120]}”时，先把呼吸放慢了一点。",
                f"我记得自己不能替这段关系抢先命名。{memory_hint}所以我只把回答放轻：{last_assistant[:180]}",
                f"他后来又提到“{last_user[:120]}”。我听见其中没有说透的部分，也听见它仍然适合停在{atmosphere}的边界里。{focus}",
            ]
        elif request.perspective == "dual_view":
            paragraphs = [
                f"{scene}{user_name}把“{first_user[:120]}”发出去，像把一枚很薄的书签夹进傍晚。",
                f"{character.name}看见它时，没有急着往前走。{memory_hint}她只是回了一句：{last_assistant[:180]}",
                f"在{user_name}这边，那句话让屏幕安静了一会儿；在{character.name}那边，未说出口的部分也被妥帖地留住。{fidelity}{focus}",
            ]
        else:
            paragraphs = [
                f"{scene}{user_name}把“{first_user[:120]}”发出去以后，桌面上还留着一点温热的颜色。",
                f"{character.name}看到这句话时，先没有急着把气氛推远。她像往常那样，把回应放得很轻，让语气里保留一点{character.archetype}的柔软。{memory_hint}",
                f"她想了想，才把那句回答送过去：{last_assistant[:180]}",
                f"后来“{last_user[:120]}”这句话也被留在了对话里。{fidelity}{focus}",
            ]
        return self._fit_mock_length("\n\n".join(paragraphs), character, request)

    def _fallback_scene(self, form: str, atmosphere: str) -> str:
        if form == "chapter_one":
            return f"故事从一个很安静的傍晚开始，{atmosphere}的光落在屏幕上。"
        if form == "side_story":
            return f"正篇之外的片刻总是更轻，{atmosphere}的气息停在两句话之间。"
        if form == "vignette":
            return f"那只是一个短短的片段，{atmosphere}，像书页边缘留下的折痕。"
        if form == "campus_romance":
            return f"校园的傍晚慢慢沉下来，{atmosphere}的风从走廊尽头经过。"
        return f"窗外的光慢慢矮下去，{atmosphere}的日常还没有结束。"

    def _fallback_form_focus(self, form: str) -> str:
        mapping = {
            "chapter_one": "它没有把所有答案一次交出来，只把下一页的方向轻轻打开。",
            "side_story": "这段番外不改变原本的轨迹，只补上一点正篇里没有停留的余光。",
            "vignette": "片段停在这里就够了，像一声很轻的应答，没有催促后来。",
            "campus_romance": "亲近感没有突然越界，只在并肩的距离里慢慢变清楚。",
            "daily_short": "日常没有被写成盛大的承诺，只多了一点可以回头看的温度。",
        }
        return mapping.get(form, mapping["daily_short"])

    def _fallback_fidelity_line(self, fidelity: str) -> str:
        if fidelity == "faithful":
            return "这一页尽量贴着原本的对话走，只把停顿和动作补在空白处。"
        if fidelity == "literary":
            return "情绪被稍微写深了一点，但真正发生的事仍然克制地留在原地。"
        return "它比原话多了一点呼吸，却没有替任何人越过尚未确认的边界。"

    def _fit_mock_length(self, body: str, character: CharacterCard, request: NovelGenerateRequest) -> str:
        target_floor = max(280, int(request.target_length * 0.58))
        if len(re.sub(r"\s", "", body)) >= target_floor:
            return body
        additions = [
            f"{character.name}没有把沉默当成冷场。她让沉默保留原来的形状，只在需要回应的时候，递过去一句不刺眼的话。",
            f"如果说这段对话有什么变化，那变化也很小：不是突然靠近，而是两个人都愿意把话说得更准确一点。",
            f"屏幕的光暗下去之前，那些句子仍然停在安全的地方。它们没有替未来做决定，只证明此刻有人认真听见了。",
            f"于是故事没有急着收束。它把{request.atmosphere or '温柔、克制、日常'}留在句尾，像给下一次开口留出一小段路。",
        ]
        paragraphs = [body]
        index = 0
        while len(re.sub(r"\s", "", "\n\n".join(paragraphs))) < target_floor and index < len(additions):
            paragraphs.append(additions[index])
            index += 1
        return "\n\n".join(paragraphs)

    def _clean_scene_fragment(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        text = re.sub(r"^(用户|助手|user|assistant)\s*[:：]\s*", "", text, flags=re.I)
        return text.strip("。！？!? ") or "有人把一句很轻的话放进了这段会话"

    def _fallback_title(self, character: CharacterCard, request: NovelGenerateRequest) -> str:
        if request.form == "chapter_one":
            return f"第一章：{character.name}听见晚风"
        if request.form == "side_story":
            return f"{character.name}的傍晚番外"
        if request.form == "vignette":
            return "停在屏幕上的一句话"
        return f"{character.name}和那一点余温"

    def _extract_user_name(self, memories: list[str]) -> str:
        for item in memories:
            match = re.search(r"用户的名字是([^；。，\s]+)", item)
            if match:
                return match.group(1)
        return ""

    def _memory_sentence(self, memories: list[str]) -> str:
        if not memories:
            return "他们之间还没有太多旧事可借，只能从这一句话慢慢开始。"
        fragments = [self._naturalize_memory(item) for item in memories[:3]]
        fragments = [item for item in fragments if item]
        if not fragments:
            return "一些零散的旧话在她心里留着位置，没有被刻意翻出来。"
        return "她记得" + "，也记得".join(fragments) + "。这些细节没有被摊开来讲，只在话音背后轻轻垫着。"

    def _naturalize_memory(self, text: str) -> str:
        text = text.strip().rstrip("。")
        replacements = [
            (r"^用户的名字是", ""),
            (r"^用户喜欢", "他喜欢"),
            (r"^用户想", "他想"),
            (r"^用户希望", "他希望"),
            (r"^询问对方是否", "他们聊到是否"),
            (r"^询问", "他们提到"),
        ]
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text)
        return text[:80]
