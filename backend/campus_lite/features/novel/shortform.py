from __future__ import annotations

import json
import re
from typing import Any

from ...schemas import CharacterCard, MemoryItem, NovelGenerateRequest, NovelGenerateResponse, StoryItem
from .config import NOVEL_GENERATION_TIMEOUT_MS


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


class NovelShortformMixin:
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
