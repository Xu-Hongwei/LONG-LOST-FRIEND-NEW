from __future__ import annotations

from typing import Any

from .event_pool import story_event_for_chapter, sync_story_event_pool_display_bindings
from .continuity import continuity_ledger_prompt
from .progression import progression_prompt
from .setting_profiles import infer_novel_setting_type, novel_setting_profile


class NovelGenerationContextMixin:
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
            for row in self._history_chapters(chapters, chapter)[-6:]
        ) or "无"
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        novel_state = self._novel_state_until(project, int(chapter["chapter_order"]) - 1)
        canvas_chapter, _canvas_scene = self._canvas_for_chapter(project, chapter)
        event_contract = self._chapter_event_contract(canvas_chapter)
        current_body = str(chapter["body"] or "").strip()
        current_body_excerpt = current_body[-1600:] if current_body else "无"
        previous_tail = self._previous_chapter_tail(chapters, chapter, novel_state)
        previous_handoff = self._previous_handoff_prompt(novel_state, chapters, chapter, allow_scene_fallback=False)
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
            "[项目推进协议]",
            progression_prompt(canvas, project),
            "[当前章节事件契约]",
            self._event_contract_prompt(event_contract),
            "[设定档案]",
            self._story_bible_prompt(self._json_dict(project["story_bible_json"])),
            "[Novel State 长期摘要]",
            self._novel_state_prompt(novel_state),
            "[Continuity Ledger 连续性账本]",
            continuity_ledger_prompt(novel_state.get("continuity_ledger")),
            "[可转写素材]",
            material_lines,
            "[已有章节]",
            previous_lines,
            "[上一章交接单]",
            previous_handoff,
            "[上一章尾段]",
            previous_tail,
            "[当前章节已有正文]",
            current_body_excerpt,
            "[Scene Card 场景卡]",
            self._scene_card_prompt(scene_card),
            "[Scene Beats 可见动作清单]",
            self._scene_beats_prompt(scene_beats),
            "[本章剧情概述]",
            f"章节：第{chapter['chapter_order']}章《{chapter['title']}》",
            f"剧情概述：{chapter['goal']}",
            "[用户写作指令]",
            instruction or "按本章剧情概述、故事画布和 Scene Beats 写出当前章正文。",
            "[长度要求]",
            f"目标长度：约 {target_length} 字",
            "[信息优先级]",
            "Novel State、Continuity Ledger、上一章交接单和上一章尾段只用于承接已经发生的事实、情绪余波和未解决点；不得提前使用后续章节信息。"
            "Continuity Ledger 的 locked_facts 和 forbidden_contradictions 是硬约束；next_must_continue 和 promises_made 是本章优先承接项；avoid_repeating 和 resolved_threads 不要重复写成新悬念。"
            "项目推进协议决定整本书如何推进；本章剧情概述和事件契约决定这一章发生什么，故事画布和 Scene Beats 决定事件推进顺序，Scene Card 决定视角、人物欲望和边界。"
            "用户写作指令只决定写法、篇幅、节奏和质量补救；不得改写本章剧情概述、画布动作链和已确认事实。"
            "如果当前章节已有正文，必须承接现有正文末尾继续扩写或精修，不要从头重写为另一章。",
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
        setting_type = infer_novel_setting_type(project)
        profile = novel_setting_profile(setting_type)
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        canvas_chapter, canvas_scene = self._canvas_for_chapter(project, chapter)
        event_contract = self._chapter_event_contract(canvas_chapter)
        event_pool = sync_story_event_pool_display_bindings(canvas.get("event_pool"), self._canvas_chapters(canvas), setting_type)
        pool_event = story_event_for_chapter(event_pool, canvas_chapter or {"chapter_order": int(chapter["chapter_order"]), "event_pool_id": ""}, setting_type)
        contract_place = str(event_contract.get("place") or "").strip()
        contract_event = str(event_contract.get("external_event") or "").strip()
        contract_hook = str(event_contract.get("hook") or "").strip()
        defaults = {
            "current_scene": contract_place or pool_event.get("place") or f"{tone}的{profile['label']}场景，承接上一章但直接进入可感知的地点、光线和动作。",
            "pov": f"贴近{protagonist}与对方的第三人称限知视角，避免上帝视角总结。",
            "present_characters": protagonist,
            "surface_event": contract_event or (self._scene_surface_event(instruction) if self._usable_instruction(instruction) else (pool_event.get("event") or self._scene_surface_event(instruction))),
            "character_desire": "人物想把话说清一点，但仍希望保留安全距离和选择余地。",
            "tension": "两个人都意识到某些话还没到能说破的时候，越想靠近，越需要把分寸放稳。",
            "required_facts": facts or ([previous_summary] if previous_summary else []),
            "forbidden_progress": boundaries or ["不得突然承诺、表白、亲密越界或把伏笔写成已经发生。"],
            "ending_beat": contract_hook or "停在一个自然可续写的动作、对白或沉默上。",
        }
        if canvas_scene:
            defaults.update({key: value for key, value in canvas_scene.items() if key in defaults and value})
        return defaults

    def _chapter_event_contract(self, canvas_chapter: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(canvas_chapter, dict):
            return {}
        contract = canvas_chapter.get("event_contract")
        if isinstance(contract, dict):
            return contract
        event_id = str(canvas_chapter.get("event_pool_id") or "").strip()
        if not event_id:
            return {}
        return {
            "event_id": event_id,
            "use_mode": "guide",
            "external_event": str(canvas_chapter.get("external_event") or canvas_chapter.get("trigger_event") or ""),
            "hook": str(canvas_chapter.get("ending_hook") or ""),
            "score": int(canvas_chapter.get("event_pool_score") or 0),
            "reasons": canvas_chapter.get("event_pool_reasons") if isinstance(canvas_chapter.get("event_pool_reasons"), list) else [],
            "penalties": canvas_chapter.get("event_pool_penalties") if isinstance(canvas_chapter.get("event_pool_penalties"), list) else [],
        }

    def _event_contract_prompt(self, contract: dict[str, Any]) -> str:
        if not contract:
            return "无"
        motifs = contract.get("motifs") if isinstance(contract.get("motifs"), list) else []
        reasons = contract.get("reasons") if isinstance(contract.get("reasons"), list) else []
        return "\n".join([
            f"- event_id: {contract.get('event_id') or ''} / use_mode: {contract.get('use_mode') or 'guide'} / score: {contract.get('score') or 0}",
            f"- 地点: {contract.get('place') or '未设定'}",
            f"- 时间锚点: {contract.get('time_anchor') or '未设定'}",
            f"- 外部事件: {contract.get('external_event') or '未设定'}",
            f"- 结尾钩子: {contract.get('hook') or '未设定'}",
            f"- 本章推进方式: {contract.get('progression_role') or '未设定'} / {contract.get('chapter_drive') or '未设定'}",
            f"- 承诺命中: {'、'.join(str(item) for item in (contract.get('promise_markers') if isinstance(contract.get('promise_markers'), list) else []) if str(item).strip()) or '无'}",
            f"- 意象: {'、'.join(str(item) for item in motifs if str(item).strip()) or '无'}",
            f"- 选择原因: {'；'.join(str(item) for item in reasons if str(item).strip()) or '无'}",
            "- 优先级：事件契约决定本章发生什么；场景卡只补镜头、人物欲望和边界；生成指令只控制写法、篇幅和补救策略。",
        ])

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
