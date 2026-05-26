from __future__ import annotations

import json
import re
from typing import Any

from .config import NOVEL_PLANNING_TIMEOUT_MS
from .event_pool import story_event_for_chapter, sync_story_event_pool_display_bindings
from .setting_profiles import infer_novel_setting_type, novel_setting_profile


class NovelGenerationBeatsMixin:
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
        history = self._history_chapters(chapters, chapter)
        previous = "\n".join(
            f"- 第{row['chapter_order']}章：{row['summary'] or row['goal']}"
            for row in history[-4:]
        ) or "无"
        novel_state = self._novel_state_until(project, int(chapter["chapter_order"]) - 1)
        previous_handoff = self._previous_handoff_prompt(novel_state, chapters, chapter, allow_scene_fallback=False)
        previous_tail = self._previous_chapter_tail(chapters, chapter, novel_state)
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
            "[上一章交接单]",
            previous_handoff,
            "[上一章尾段]",
            previous_tail,
            "[素材]",
            material_lines,
            "[用户生成指令]",
            instruction,
            "[硬约束]",
            "必须按本章场面推进链生成 beats：触发事件 -> 即时反应 -> 阻碍升级 -> 对方反应 -> 人物选择 -> 场景后果 -> 结尾钩子。"
            "第一拍必须自然承接上一章尾段或上一章交接单的未解决点，不要重演上一章已经完成的动作。"
            "保持一个连续大场景，但可以在场景内部新增一到两个符合项目题材的小事件、道具、旁观者、误会、延误或场面压力。"
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

    def _history_chapters(self, chapters: list[Any], chapter: Any) -> list[Any]:
        order = int(chapter["chapter_order"])
        return [row for row in chapters if int(row["chapter_order"]) < order]

    def _previous_chapter_row(self, chapters: list[Any], chapter: Any) -> Any | None:
        history = self._history_chapters(chapters, chapter)
        return history[-1] if history else None

    def _previous_chapter_tail(self, chapters: list[Any], chapter: Any, state: dict[str, Any] | None = None) -> str:
        previous = self._previous_chapter_row(chapters, chapter)
        if not previous:
            return "无"
        if state is not None and int(state.get("last_completed_chapter_order") or 0) < int(previous["chapter_order"]):
            return "无"
        body = str(previous["body"] or "")
        return body[-1000:] if body else str(previous["summary"] or previous["goal"] or "无")[:500]

    def _novel_state_prompt(self, state: dict[str, Any]) -> str:
        if not state:
            return "无"
        compact = {
            "global_summary": state.get("global_summary", ""),
            "confirmed_facts": state.get("confirmed_facts", [])[:10],
            "relationship_states": state.get("relationship_states", [])[:8],
            "open_threads": state.get("open_threads", [])[:8],
            "resolved_threads": state.get("resolved_threads", [])[:6],
            "last_completed_chapter_order": state.get("last_completed_chapter_order", 0),
        }
        return json.dumps(compact, ensure_ascii=False)

    def _previous_handoff_prompt(
        self,
        state: dict[str, Any],
        chapters: list[Any],
        chapter: Any,
        allow_scene_fallback: bool = True,
    ) -> str:
        previous = self._previous_chapter_row(chapters, chapter)
        if not previous:
            return "无"
        previous_order = int(previous["chapter_order"])
        for item in reversed(state.get("chapter_handoffs", []) if isinstance(state.get("chapter_handoffs"), list) else []):
            if isinstance(item, dict) and self._coerce_int(item.get("chapter_order"), 0, 0, 999) == previous_order:
                return json.dumps(item, ensure_ascii=False)
        if not allow_scene_fallback:
            return "无"
        scene_card = self._json_dict(previous["scene_card_json"] if "scene_card_json" in previous.keys() else "{}")
        handoff = scene_card.get("chapter_handoff") if isinstance(scene_card.get("chapter_handoff"), dict) else {}
        return json.dumps(handoff, ensure_ascii=False) if handoff else "无"

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
        setting_type = infer_novel_setting_type(project)
        profile = novel_setting_profile(setting_type)
        canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        event_pool = sync_story_event_pool_display_bindings(canvas.get("event_pool"), self._canvas_chapters(canvas), setting_type)
        pool_event = story_event_for_chapter(event_pool, canvas_chapter or {"chapter_order": int(chapter["chapter_order"]), "event_pool_id": ""}, setting_type)
        fallback_place = pool_event.get("place") or profile["places"][0]
        fallback_event = pool_event.get("event") or profile["events"][0]
        fallback_ending = pool_event.get("hook") or profile["endings"][0]
        place = self._clean_beat_text(str(scene_card.get("current_scene") or fallback_place))
        if "场景" in place:
            place = fallback_place
        event = self._clean_beat_text(str(scene_card.get("surface_event") or fallback_event))
        ending = self._clean_beat_text(str(scene_card.get("ending_beat") or fallback_ending))
        trigger = self._clean_beat_text(str(canvas_chapter.get("trigger_event") or event)) or event
        immediate = self._clean_beat_text(str(canvas_chapter.get("immediate_reaction") or "主角先处理眼前变化，没有急着解释自己的在意。"))
        escalation = self._clean_beat_text(str(canvas_chapter.get("obstacle_escalation") or "时间压力和信息差一起压过来，让人物不能把话说完整。"))
        counterpart = self._clean_beat_text(str(canvas_chapter.get("counterpart_reaction") or "对方没有替主角做决定，只用一个具体动作把局面接住。"))
        choice = self._clean_beat_text(str(canvas_chapter.get("character_choice") or "主角本来可以退开，却停下来完成一个不越界的小选择。"))
        consequence = self._clean_beat_text(str(canvas_chapter.get("scene_consequence") or "这次选择让两人多了一件可回望的共同经历。"))
        if len(consequence) < 10 or "彼此了" in consequence or "记住" in consequence:
            consequence = "这次选择让两人多了一件可回望的共同经历。"
        hook = self._clean_beat_text(str(canvas_chapter.get("ending_hook") or ending)) or ending
        if "记住" in hook:
            hook = fallback_ending
        return [
            {
                "type": "establish",
                "purpose": "建立地点、人物和可见动作",
                "visible_action": f"{place}，{protagonist}进入这场外部事件之前，周围的声音和光线先把气氛压低了一点。",
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
                "dialogue": ["先别急。", "我知道。"],
                "inner_turn": "越想快一点，细节越容易出错。",
            },
            {
                "type": "first_exchange",
                "purpose": "让对方用动作回应而不是解释",
                "visible_action": counterpart,
                "dialogue": ["这个交给你决定。", "谢谢。"],
                "inner_turn": "主角接过选择权时，才意识到对方没有越过边界。",
            },
            {
                "type": "second_exchange",
                "purpose": "完成人物的小选择",
                "visible_action": choice,
                "dialogue": ["不用现在回答。", "那就先把眼前这一步做完。"],
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
