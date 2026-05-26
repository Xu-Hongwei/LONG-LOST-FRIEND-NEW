from __future__ import annotations

import json
from typing import Any

from .event_pool import story_event_pool_prompt
from .setting_profiles import character_story_seed_pool, infer_novel_setting_type, novel_setting_guidance, project_story_seed_pool


class NovelCanvasPromptMixin:
    def _canvas_system_prompt(self) -> str:
        return (
            "你是长篇小说 Story Canvas 规划师。你的任务是根据作品设定、Story Bible 和素材，"
            "生成结构化故事画布，不写正文。画布必须让后续章节能写成有事件、有阻碍、有选择、有钩子的小说。"
            "素材只作为熟悉感锚点，可以自由新增符合项目题材的日常事件、道具、误会和场面压力；"
            "不得改变已确认事实，不得把未发生线索写成已经发生。"
            "只输出严格 JSON 对象，不要 Markdown，不要注释，不要代码块，不要省略双引号。"
            "字段必须包含 version, mode, acts, chapters, scenes, threads, quality_rules, diagnostics。"
            "chapters 每项必须包含 id, act_id, chapter_order, title, goal, external_event, trigger_event, immediate_reaction, "
            "obstacle_escalation, counterpart_reaction, character_choice, scene_consequence, relationship_shift, ending_hook, "
            "target_length, status, emotion_curve, scene_ids。"
            "chapter.goal 是“本章剧情概述”，不是写作指令；必须写成 1-2 句具体剧情梗概，包含外部事件、人物欲望或阻碍、人物选择、关系变化和结尾边界，避免“推进关系”“建立印象”这类空泛表达。"
            "scenes 每项必须包含 id, chapter_id, scene_order, current_scene, pov, present_characters, surface_event, "
            "character_desire, tension, required_facts, forbidden_progress, ending_beat, linked_material_ids。"
            "不要输出任何数字评分、冲突等级或低/中/高标签；所有张力都必须写成具体可见的文字原因。"
            "画布和正文规划中禁止使用“用户”“助手”“AI”作为人物名或视角名，必须使用作品设定里的真实人物名。"
        )

    def _canvas_extend_system_prompt(self) -> str:
        return (
            "你是长篇小说滚动规划师。你的任务不是重写全书画布，而是基于已经发生的正文状态，"
            "规划下一组连续章节。必须承接 Novel State、上一章交接单和上一章结尾，不推翻已写章节。"
            "输出严格 JSON 对象，字段同 Story Canvas：version, mode, acts, chapters, scenes, threads, quality_rules, diagnostics。"
            "可以额外输出 event_pool_delta 对项目活动事件池进行 add/update/retire；不要把它写成正文。"
            "chapters 每项必须包含 id, act_id, chapter_order, title, goal, external_event, trigger_event, immediate_reaction, "
            "obstacle_escalation, counterpart_reaction, character_choice, scene_consequence, relationship_shift, ending_hook, "
            "target_length, status, emotion_curve, scene_ids。"
            "chapter.goal 是“本章剧情概述”，不是写作指令；必须写成 1-2 句具体剧情梗概，说明本章发生什么、角色想要什么、被什么阻碍、做出什么小选择、关系停在什么边界。"
            "scenes 每项必须包含 id, chapter_id, scene_order, current_scene, pov, present_characters, surface_event, "
            "character_desire, tension, required_facts, forbidden_progress, ending_beat, linked_material_ids。"
            "不要输出任何数字评分、冲突等级或低/中/高标签；scene.tension 必须写具体阻碍，例如外部打断、"
            "时间压力、信息差或人物不能立刻开口的原因。"
            "画布和正文规划中禁止使用“用户”“助手”“AI”作为人物名或视角名，必须使用作品设定里的真实人物名。"
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
            self._canvas_identity_mapping(project),
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
            "[题材事件池]",
            self._canvas_setting_guidance(project),
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
            "素材只允许作为 1-2 个熟悉锚点、道具、地点或伏笔，其余剧情必须自由创作符合题材的具体外部事件。"
            "优先使用题材事件池中的场域和可见事件承载关系推进；只有校园题材才使用图书馆、公告栏、社团和课程误会。"
            f"角色名必须准确，主角只能写作“{project['protagonist']}”；不要写错别字或相近名字。"
            "场景卡必须写可见事件，不要写“关系变近”“两人还不熟”这类分析句。"
            "acts, chapters, scenes, threads 必须是数组。diagnostics.source 写 remote。",
        ])

    def _initial_canvas_source(
        self,
        project: Any,
        story_bible: dict[str, Any],
        materials: list[Any],
    ) -> str:
        material_lines = "\n".join(self._canvas_material_line(row) for row in materials[:8]) or "无"
        empty_state = self._empty_novel_state(project["title"])
        return "\n\n".join([
            "[作品设定]",
            f"标题：{project['title']}",
            f"类型：{project['genre']}",
            f"基调：{project['tone']}",
            f"主角：{project['protagonist']}",
            self._canvas_identity_mapping(project),
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
            "[题材事件池]",
            self._canvas_setting_guidance(project),
            "[Story Bible]",
            self._story_bible_prompt(story_bible),
            "[Novel State 长期摘要]",
            self._novel_state_prompt(empty_state),
            "[可用素材]",
            material_lines,
            "[结构要求]",
            self._canvas_schema_hint(),
            "[初始滚动规划目标]",
            "请使用和滚动规划完全一致的 Story Canvas 结构，从第 1 章开始连续规划 4 章。chapter_order 必须依次为 1 到 4。",
            "每章都必须像可直接写正文的章节交接单：有具体外部事件、即时反应、阻碍升级、对方反应、人物选择、场景后果、关系变化和结尾钩子。",
            "每章 goal 必须比一句目标更具体：用 60-140 字写出本章剧情概述，至少包含“场面/事件 + 主角想法或需求 + 具体阻碍 + 小选择 + 关系落点”，不能写成生成指令。",
            "每章至少绑定 1 张 scene card；scene.tension 必须是具体阻碍文字，不允许数字、等级或抽象标签。",
            "素材只作为熟悉感锚点，最多露出一到两个线索；剧情可以自由新增符合题材的事件，不要把聊天素材按顺序改成流水账。",
            "第一章也要按滚动章节的密度写：不要写总纲，不要写阶段说明，不要写关系分析句。",
            "diagnostics.source 写 remote，diagnostics.mode 写 initial_rolling。",
        ])

    def _canvas_schema_hint(self) -> str:
        return (
            "acts: 4 个阶段对象；chapters: 4-6 个章节对象，chapter_order 必须为 1..N；"
            "scenes: 至少每章 1 个场景对象，chapter_id 必须指向章节 id；"
            "threads: 线索对象数组，可为空；quality_rules: 字符串数组；"
            "event_pool_delta: 可选对象，字段 add/update/retire，用来维护项目活动事件池。"
        )

    def _event_pool_delta_system_prompt(self) -> str:
        return (
            "You maintain a long-form novel project event pool. Return strict JSON only. "
            "Do not write chapters or prose. Output an object with event_pool_delta: "
            "{add: [], update: [], retire: []}. Each add/update item should include id when updating, "
            "place, time_anchor, event, hook, motifs, source_reason, and tags. Retire items should include id. "
            "time_anchor must be specific, for example 'Saturday 18:40, before the lake lights turn on'. "
            "tags must be an object: {event_type: string[], anchors: string[], theme_markers: string[], "
            "tone_markers: string[], relationship_motion: string[], boundary_risk: 'low'|'medium'|'high', "
            "freshness: string[], continuity: string[], forbidden_defaults: string[]}. "
            "Every add/update must include at least 2 theme_markers and at least 1 tone_markers. "
            "Events must express the project genre, tone, worldview, and relationship_setup through visible details. "
            "Priority is fixed: written prose and Novel State first, current project event pool second, Project/Story Bible third, character story_seed_pool only as translatable flavor, global setting profile last. "
            "The character story_seed_pool must not decide what happens next, overwrite bound chapters, or drag the project back to the character's default setting. "
            "Do not output numeric scores, confidence, or deltas. "
            "Avoid generic events such as ordinary misunderstanding, vague chat, or random cafe unless the project is explicitly modern daily and the event has a concrete thematic anchor. "
            "Suggest concrete visible events only; do not repeat retired or already used events."
        )

    def _event_pool_delta_source(
        self,
        project: Any,
        current_canvas: dict[str, Any],
        chapters: list[Any],
        from_order: int,
        count: int,
        instruction: str,
    ) -> str:
        story_bible = self._json_dict(project["story_bible_json"])
        novel_state = self._novel_state_until(project, from_order)
        materials = self._require_storage().list_novel_materials(str(project["id"]))[:12]
        material_lines = "\n".join(self._canvas_material_line(row) for row in materials) or "None"
        active_pool = story_event_pool_prompt(current_canvas.get("event_pool")) if isinstance(current_canvas.get("event_pool"), dict) else "None"
        character_seed_lines = self._event_pool_character_seed_prompt(project)
        recent_chapters = "\n".join(
            f"- chapter {row['chapter_order']}: {self._clean_material_text(row['summary'] or row['goal'])}"
            for row in chapters
            if int(row["chapter_order"]) <= from_order
        ) or "None"
        return "\n\n".join([
            "[Project]",
            f"title: {project['title']}",
            f"genre: {project['genre']}",
            f"tone: {project['tone']}",
            f"protagonist: {project['protagonist']}",
            f"worldview: {self._clean_material_text(project['worldview'])}",
            f"relationship_setup: {self._clean_material_text(project['relationship_setup'])}",
            "[Story Bible]",
            self._story_bible_prompt(story_bible),
            "[Novel State]",
            self._novel_state_prompt(novel_state),
            "[Current Active Event Pool]",
            active_pool,
            "[Character Story Seed Pool - translatable flavor only]",
            character_seed_lines,
            "[Materials]",
            material_lines,
            "[Recent Written Chapters]",
            recent_chapters,
            "[Rolling Target]",
            f"Plan support events for chapters {from_order + 1} to {from_order + count}.",
            instruction or "Keep continuity with the completed chapter, add fresh visible external events, and avoid replaying old scenes.",
            "[Rules]",
            "Prefer events that can carry action, obstacle, choice, and ending hook. "
            "Each add/update must include a concrete time_anchor and tags.theme_markers/tone_markers derived from Project genre/tone/worldview/relationship_setup. "
            "Do not add generic reusable incidents; make the time, place, object, and pressure specific to this project. "
            "Use written chapters, Novel State, and handoff as hard continuity; use Story Bible as hard constraints; use Materials as light familiar anchors; use character story_seed_pool only to create translated variants when the active pool is thin, stale, duplicated, or off-theme. "
            "Never copy character default places/events directly when they conflict with the project setting. "
            "If existing active events are still useful, do not update them. Add only genuinely useful fresh candidates. "
            "If an active event is stale, duplicate, or conflicts with boundaries, retire it by id.",
        ])

    def _event_pool_character_seed_prompt(self, project: Any) -> str:
        try:
            character_id = str(project["character_id"] or "").strip()
            visitor_id = str(project["visitor_id"] or "").strip()
        except Exception:
            return "None"
        if not character_id:
            return "None"
        try:
            card = self._require_storage().get_character_card(character_id, visitor_id)
        except Exception:
            card = None
        if not card:
            return "None"
        setting_type = infer_novel_setting_type(project, card)
        seed_pool, seed_source = project_story_seed_pool(card, setting_type)
        raw_pool = character_story_seed_pool(card)
        if not seed_pool and not raw_pool:
            return "None"
        return json.dumps({
            "role": "flavor_only",
            "seed_pool_source": seed_source,
            "project_setting_type": setting_type,
            "usable_translated_seed_pool": seed_pool,
            "raw_character_seed_pool": raw_pool,
            "rules": [
                "Do not let this decide the next chapter.",
                "Do not overwrite written prose, Novel State, Story Bible, or bound project events.",
                "Use it only for motifs, translated event variants, and character-specific flavor.",
            ],
        }, ensure_ascii=False)

    def _canvas_setting_guidance(self, project: Any) -> str:
        setting_type = infer_novel_setting_type(project)
        try:
            canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        except Exception:
            canvas = {}
        pool = story_event_pool_prompt(canvas.get("event_pool")) if isinstance(canvas.get("event_pool"), dict) else ""
        if not pool:
            return novel_setting_guidance(setting_type)
        return "\n".join([
            novel_setting_guidance(setting_type),
            "项目活动事件池固定维护 10 条 active 事件；优先从这些事件中选择、变体或推进，不要照搬成流水账。",
            pool,
            "如果新增了更贴合当前前文的事件，请在 event_pool_delta.add 中结构化返回；如果事件已经用完或不再适合，请在 event_pool_delta.retire 中标记。",
        ])

    def _canvas_identity_mapping(self, project: Any) -> str:
        protagonist = str(project["protagonist"] or project["title"] or "主角").strip()
        character_name = self._project_character_name(project)
        lines = [
            "[身份映射]",
            f"用户小说名/主角名：{protagonist}",
        ]
        if character_name:
            lines.append(f"AI角色名：{character_name}")
        lines.append("禁止在 chapters、scenes、threads 中把人物写成“用户”“助手”“AI”；如果素材里出现这些内部称呼，必须改写成上面的真实人物名。")
        if character_name and character_name != protagonist:
            lines.append(f"present_characters 必须使用“{protagonist}、{character_name}”这类真实姓名组合，不要写“{protagonist}、用户”。")
        else:
            lines.append(f"视角和人物欲望必须围绕“{protagonist}”等真实姓名表达，不要写“用户视角”或“用户想要”。")
        return "\n".join(lines)

    def _project_character_name(self, project: Any) -> str:
        try:
            character_id = str(project["character_id"] or "").strip()
            visitor_id = str(project["visitor_id"] or "").strip()
        except Exception:
            return ""
        if not character_id:
            return ""
        try:
            card = self._require_storage().get_character_card(character_id, visitor_id)
        except Exception:
            card = None
        return str((card or {}).get("name") or "").strip()

    def _canvas_extend_source(
        self,
        project: Any,
        current_canvas: dict[str, Any],
        chapters: list[Any],
        from_order: int,
        count: int,
        instruction: str,
    ) -> str:
        story_bible = self._json_dict(project["story_bible_json"])
        novel_state = self._novel_state_until(project, from_order)
        last_chapter = next((row for row in reversed(chapters) if int(row["chapter_order"]) <= from_order), None)
        last_tail = str(last_chapter["body"] or "")[-1200:] if last_chapter else "无"
        last_handoff = self._previous_or_current_handoff_prompt(novel_state, chapters, from_order)
        preserved_future = "\n".join(
            f"- 第{row['chapter_order']}章《{row['title']}》：status={row['status']}；"
            f"已有正文={'是' if str(row['body'] or '').strip() else '否'}；"
            f"摘要/目标={self._clean_material_text(row['summary'] or row['goal'])}"
            for row in chapters
            if int(row["chapter_order"]) > from_order
        ) or "无"
        existing_plan = "\n".join(
            f"- 第{item.get('chapter_order')}章《{item.get('title')}》：{item.get('goal')} / 钩子：{item.get('ending_hook')}"
            for item in self._canvas_chapters(current_canvas)[-6:]
        ) or "无"
        return "\n\n".join([
            "[作品设定]",
            f"标题：{project['title']}",
            f"类型：{project['genre']}",
            f"基调：{project['tone']}",
            f"主角：{project['protagonist']}",
            self._canvas_identity_mapping(project),
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
            "[题材事件池]",
            self._canvas_setting_guidance(project),
            "[Story Bible]",
            self._story_bible_prompt(story_bible),
            "[可信前文边界]",
            f"可信前文只截至第 {from_order} 章。Novel State 和上一章交接单只能代表第 {from_order} 章及以前已经发生的事实、关系变化、未解决钩子和禁止重复点。",
            "如果这是删除章节后的滚动重规划，被删除章节及其之后旧路径产生的 handoff/state_delta 都不可信，不得当作已经发生。",
            "[Novel State 长期摘要]",
            self._novel_state_prompt(novel_state),
            "[最近画布]",
            existing_plan,
            "[上一章交接单]",
            last_handoff,
            "[上一章尾段]",
            last_tail or "无",
            "[后续已保留章节约束]",
            preserved_future,
            "[结构要求]",
            self._canvas_schema_hint(),
            "[滚动规划目标]",
            f"从第 {from_order + 1} 章开始，连续规划后续 {count} 章。chapter_order 必须依次为 {from_order + 1} 到 {from_order + count}。",
            instruction or "承接已写正文，规划下一组有事件、有协作、有轻微阻碍和具体钩子的题材内章节。",
            "[硬约束]",
            "不要重写第 1 章到当前章节，不要让后续章节重复已经发生的偶遇、找话题或相同打断。"
            "每章必须从上一章未解决问题或结尾钩子里自然生长。"
            "后续已保留章节只能作为不要直接覆盖正文、需要重新接合的约束；不得把它们的旧交接单当作可信前文。"
            "每章 goal 必须写成 60-140 字的本章剧情概述，包含场面/事件、人物需求、阻碍、选择、关系落点；不要写成“生成/扩写/续写”指令。"
            "每章只能推进一个小关系变化，必须通过外部事件、动作、对白和选择体现。"
            "允许自由新增符合题材的外部事件，但熟悉线索只露出一小部分，不要把素材列表流水账化。"
            "diagnostics.source 写 remote，diagnostics.mode 写 rolling_extend。",
        ])

    def _previous_or_current_handoff_prompt(self, state: dict[str, Any], chapters: list[Any], order: int) -> str:
        for item in reversed(state.get("chapter_handoffs", []) if isinstance(state.get("chapter_handoffs"), list) else []):
            if isinstance(item, dict) and self._coerce_int(item.get("chapter_order"), 0, 0, 999) == order:
                return json.dumps(item, ensure_ascii=False)
        row = next((item for item in reversed(chapters) if int(item["chapter_order"]) == order), None)
        if not row:
            return "无"
        scene_card = self._json_dict(row["scene_card_json"] if "scene_card_json" in row.keys() else "{}")
        handoff = scene_card.get("chapter_handoff") if isinstance(scene_card.get("chapter_handoff"), dict) else {}
        return json.dumps(handoff, ensure_ascii=False) if handoff else "无"
