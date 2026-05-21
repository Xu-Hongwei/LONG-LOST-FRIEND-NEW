from __future__ import annotations

import re
from typing import Any

from ...schemas import (
    CharacterCard,
    MemoryItem,
    NovelProjectCreateRequest,
    NovelProjectResponse,
    StoryItem,
)
from .quality import INTERNAL_ID_PATTERN


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


class NovelProjectMixin:
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

    def _default_novel_state(
        self,
        title: str,
        story_bible: dict[str, Any],
        story_canvas: dict[str, Any],
    ) -> dict[str, Any]:
        chapters = self._canvas_chapters(story_canvas)
        first_goal = str(chapters[0].get("goal") or chapters[0].get("external_event") or "").strip() if chapters else ""
        return {
            "version": 1,
            "title": title,
            "global_summary": first_goal or "作品刚创建，尚未生成正式章节。",
            "confirmed_facts": [str(item) for item in story_bible.get("confirmed_facts", [])[:8] if str(item).strip()],
            "character_states": [],
            "relationship_states": [str(item) for item in story_bible.get("relationships", [])[:6] if str(item).strip()],
            "open_threads": [str(item) for item in story_bible.get("foreshadowing", [])[:8] if str(item).strip()],
            "resolved_threads": [],
            "chapter_handoffs": [],
            "last_completed_chapter_order": 0,
            "updated_at": "",
        }

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
        story_canvas = self._compact_story_canvas(story_canvas)
        if not request.outline.strip():
            outline = self._canvas_outline(story_canvas)
        novel_state = self._default_novel_state(title, story_bible, story_canvas)
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
            novel_state,
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

    def project_response(self, project_id: str) -> NovelProjectResponse:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        return self._project_from_row(project)

    def project_responses(self, session_id: str) -> list[NovelProjectResponse]:
        storage = self._require_storage()
        return [self._project_from_row(row) for row in storage.list_novel_projects(session_id)]

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
        return clean[:4000]

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
        if any(word in clean for word in ["希望", "保留", "想要"]) and any(word in clean for word in ["图书馆", "便签", "周末", "校园"]):
            hints = [word for word in ["图书馆", "便签", "周末约定", "雨天", "借书卡", "樱花"] if word in clean]
            return "、".join(hints[:3]) or "一个被保留下来的日常线索"
        if "喜欢" in clean:
            obj = clean.split("喜欢", 1)[1].split("，", 1)[0].strip()
            if any(term in obj for term in ["校园日常", "长篇", "叙事", "温柔克制"]):
                return "傍晚图书馆里的安静"
            return f"对{obj}的偏爱" if obj else "一点安静的偏爱"
        if "周末约定" in clean or ("周末" in clean and "确认" in clean):
            return "还没有完全确认的周末约定"
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
