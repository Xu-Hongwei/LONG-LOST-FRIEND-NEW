from __future__ import annotations

import json
from typing import Any


class NovelCanvasPromptMixin:
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
            "target_length, status, emotion_curve, scene_ids。"
            "chapter.goal 是“本章剧情概述”，不是写作指令；必须写成 1-2 句具体剧情梗概，包含外部事件、人物欲望或阻碍、人物选择、关系变化和结尾边界，避免“推进关系”“建立印象”这类空泛表达。"
            "scenes 每项必须包含 id, chapter_id, scene_order, current_scene, pov, present_characters, surface_event, "
            "character_desire, tension, required_facts, forbidden_progress, ending_beat, linked_material_ids。"
            "不要输出任何数字评分、冲突等级或低/中/高标签；所有张力都必须写成具体可见的文字原因。"
        )

    def _canvas_extend_system_prompt(self) -> str:
        return (
            "你是长篇小说滚动规划师。你的任务不是重写全书画布，而是基于已经发生的正文状态，"
            "规划下一组连续章节。必须承接 Novel State、上一章交接单和上一章结尾，不推翻已写章节。"
            "输出严格 JSON 对象，字段同 Story Canvas：version, mode, acts, chapters, scenes, threads, quality_rules, diagnostics。"
            "chapters 每项必须包含 id, act_id, chapter_order, title, goal, external_event, trigger_event, immediate_reaction, "
            "obstacle_escalation, counterpart_reaction, character_choice, scene_consequence, relationship_shift, ending_hook, "
            "target_length, status, emotion_curve, scene_ids。"
            "chapter.goal 是“本章剧情概述”，不是写作指令；必须写成 1-2 句具体剧情梗概，说明本章发生什么、角色想要什么、被什么阻碍、做出什么小选择、关系停在什么边界。"
            "scenes 每项必须包含 id, chapter_id, scene_order, current_scene, pov, present_characters, surface_event, "
            "character_desire, tension, required_facts, forbidden_progress, ending_beat, linked_material_ids。"
            "不要输出任何数字评分、冲突等级或低/中/高标签；scene.tension 必须写具体阻碍，例如外部打断、"
            "时间压力、信息差或人物不能立刻开口的原因。"
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
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
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
            "素材只作为熟悉感锚点，最多露出一到两个线索；剧情可以自由新增合理校园事件，不要把聊天素材按顺序改成流水账。",
            "第一章也要按滚动章节的密度写：不要写总纲，不要写阶段说明，不要写关系分析句。",
            "diagnostics.source 写 remote，diagnostics.mode 写 initial_rolling。",
        ])

    def _canvas_schema_hint(self) -> str:
        return (
            "acts: 4 个阶段对象；chapters: 4-6 个章节对象，chapter_order 必须为 1..N；"
            "scenes: 至少每章 1 个场景对象，chapter_id 必须指向章节 id；"
            "threads: 线索对象数组，可为空；quality_rules: 字符串数组。"
        )

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
            f"世界观：{self._clean_material_text(project['worldview'])}",
            f"关系设定：{self._clean_material_text(project['relationship_setup'])}",
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
            instruction or "承接已写正文，规划下一组有事件、有协作、有轻微阻碍和具体钩子的校园日常章节。",
            "[硬约束]",
            "不要重写第 1 章到当前章节，不要让后续章节重复已经发生的偶遇、找话题或相同打断。"
            "每章必须从上一章未解决问题或结尾钩子里自然生长。"
            "后续已保留章节只能作为不要直接覆盖正文、需要重新接合的约束；不得把它们的旧交接单当作可信前文。"
            "每章 goal 必须写成 60-140 字的本章剧情概述，包含场面/事件、人物需求、阻碍、选择、关系落点；不要写成“生成/扩写/续写”指令。"
            "每章只能推进一个小关系变化，必须通过外部事件、动作、对白和选择体现。"
            "允许自由新增校园事件，但熟悉线索只露出一小部分，不要把素材列表流水账化。"
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
