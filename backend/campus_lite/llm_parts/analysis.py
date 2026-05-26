from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from ..setting_types import normalize_setting_type, setting_guidance
from ..schemas import CharacterCard, MemoryItem


logger = logging.getLogger(__name__)

RELATIONSHIP_STAGE_TIMEOUT_MS = 12_000
BOND_STAGE_TIMEOUT_MS = 24_000
CHARACTER_DRAFT_TIMEOUT_MS = int(os.getenv("CHARACTER_DRAFT_TIMEOUT_MS") or "60000")
CHARACTER_DRAFT_CORE_PROMPT = (
    "Expand a short idea into the CORE persona fields of a fictional AI chat character. "
    "Return strict JSON only: {\"character\": {...}}. Include only these character keys: "
    "name, archetype, tagline, gender, setting_type, setting_notes, bio, personality, scenario, "
    "speech_style, relationship_pace, opening_line, boundaries, anti_patterns. "
    "Use natural Chinese for user-facing fields. gender must be Chinese display text. "
    "setting_type is fixed by the request. Do not write style samples or story_seed_pool here."
)
CHARACTER_DRAFT_PACK_PROMPT = (
    "Expand a short idea into the STYLE AND SEED PACK fields of a fictional AI chat character. "
    "Return strict JSON only: {\"character\": {...}}. Include only these character keys: "
    "likes, dislikes, mes_example, creator_notes, system_prompt, post_history_instructions, "
    "interaction_policy, story_seed_pool, voice, visual. "
    "interaction_policy must include initiative_level, action_density, action_style, comfort_style, "
    "question_style, and memory_style. action_density must be a concrete Chinese behavior-density sentence, "
    "not low/medium/high; explain when actions appear, what kind of actions fit, and what repetition to avoid. "
    "voice must include sentence_rhythm, 4 to 6 signature_moves, 4 to 6 avoid items, and 4 to 6 sample_lines. "
    "story_seed_pool is a default translatable material pack, not fixed plot and not mandatory scenes. "
    "Include 4 to 8 compact places, 4 to 8 visible event_seeds, 4 to 8 relationship hook_seeds, "
    "3 to 6 motifs, and 3 to 6 forbidden_defaults. Make every item concrete, reusable, and translatable; "
    "do not lock a future novel chapter or decide what happens next. Use natural Chinese."
)
RELATIONSHIP_EVENT_STRUCTURED_PROMPT = (
    "Extract relationship events between the user and the current character from the provided chat context. "
    "Return one JSON object only: {\"events\":[...]}. Use {\"events\":[]} only when no relationship event is present. "
    "Each event may contain only event_type, evidence_grade, and evidence_text. "
    "Allowed event_type values are shared_context, preference_confirmed, trust_signal, emotional_disclosure, "
    "boundary_respected, negative_feedback, boundary_violation, and repair. "
    "Allowed evidence_grade values are explicit, strong, contextual, and weak. "
    "Evidence text must be an exact contiguous substring copied from the supplied user message whenever the evidence "
    "comes from the user. Do not summarize, paraphrase, normalize, shorten, translate, or prefix it with phrases such "
    "as 'the user said' or '用户表示'. If no exact user-message substring supports the event, return contextual/weak "
    "or omit the event. "
    "Never output relationship stages, scores, score deltas, resonance values, or free numeric confidence. "
    "Use explicit when the user directly confirms trust, a boundary, a relationship-facing preference, "
    "a concrete shared pact, a violation, or an accepted repair. "
    "Use strong only for direct text evidence with very little inference. "
    "Use contextual or weak for indirect hints. "
    "Assistant-only reassurance, ordinary acknowledgements, topic switches, scheduling, and casual chat are not enough. "
    "For overlapping evidence keep the single highest-priority event: boundary_violation before negative_feedback, "
    "and repair before shared_context or trust_signal."
)

CHARACTER_DRAFT_STRUCTURED_PROMPT = (
    "You expand a short user idea into a safe fictional AI chat character card. "
    "Return one JSON object only with key \"character\". The character object must use these keys: "
    "name, archetype, tagline, gender, bio, personality, scenario, speech_style, relationship_pace, "
    "opening_line, likes, dislikes, boundaries, mes_example, creator_notes, system_prompt, "
    "post_history_instructions, interaction_policy, anti_patterns, story_seed_pool, voice, visual. "
    "interaction_policy must include initiative_level, action_density, action_style, comfort_style, "
    "question_style, memory_style. voice must include sentence_rhythm, signature_moves, avoid, sample_lines. "
    "visual must include accent and portrait_hint. "
    "gender must be written in Chinese for user-facing display, such as 女, 男, 非二元, or 未设定. "
    "interaction_policy.action_density must be generated as one concrete Chinese behavior-density sentence tailored "
    "to this character. Do not choose from fixed labels or enums such as low/medium/high. Mention when actions appear, "
    "what kinds of actions fit the character, and what repetition or intensity to avoid. "
    "story_seed_pool must include places, event_seeds, hook_seeds, motifs, and forbidden_defaults. "
    "It is a default translatable story material pack for future novel canvas generation, not the character core "
    "identity, not a fixed plot, and not a list of mandatory scenes. Novel projects may translate or override it "
    "according to their own genre, worldview, story bible, and rolling event pool. "
    "Generate 4 to 8 compact translatable places, 4 to 8 visible event-pattern seeds, 4 to 8 relationship or "
    "continuation hooks, 3 to 6 motifs, "
    "and 3 to 6 forbidden defaults that should not leak into this character's stories. "
    "Strict story_seed_pool rules: places are only location or scene names, such as 'rainy bus stop' or "
    "'old archive room'; never put character bios, personality, relationship setup, or full sentences in places. "
    "event_seeds should describe reusable event patterns that can be translated across settings, such as an external "
    "change forcing cooperation; avoid over-specific one-off plot beats unless they are essential to the character. "
    "Never put character bios or chapter outlines there. hook_seeds are unresolved next-step questions or choices, "
    "not endings. motifs are short noun "
    "images, usually 2 to 8 words, not explanatory sentences. forbidden_defaults are short constraints. "
    "The character object must also include setting_type and setting_notes. "
    "setting_type must be one of campus, modern_daily, workplace, xianxia_wuxia, urban_fantasy, "
    "mystery, sci_fi, historical, fantasy_adventure, custom. "
    "setting_notes must not be empty: infer 1 concise Chinese sentence or 3 to 5 short phrases that summarize "
    "the concrete world, era, relationship context, and genre constraints for this role. "
    "Make the examples rich enough to be useful: sample_lines should contain 4 to 6 short reusable lines; "
    "mes_example should contain 2 to 3 user/character exchanges showing greeting, emotional support, memory use, "
    "and boundary or relationship pacing where relevant. "
    "likes, dislikes, boundaries, anti_patterns, and signature_moves should usually contain 3 to 6 concrete items. "
    "If a template is provided, treat it as an editable draft, not as a final answer: preserve clearly intentional "
    "user-written specifics, but fill every empty field and rewrite placeholder, generic, too-short, or low-quality "
    "fields. Do not return the template unchanged. "
    "Do not create a real-person impersonation, do not include private personal data, and keep the role fictional. "
    "Write natural Chinese fields unless the user explicitly asks otherwise. "
    "The card must follow the requested setting type instead of defaulting to campus, and setting_type is fixed by "
    "the request. Infer gender, relationship pacing, interaction tags, voice, and visual accent from the idea and "
    "the selected setting. "
    "Avoid forcing intimacy or fixed actions every turn."
)


class LlmAnalysisMixin:
    async def generate_character_draft(
        self,
        prompt: str,
        template: dict[str, Any] | None = None,
        setting_type: str = "modern_daily",
        setting_notes: str = "",
        draft_mode: str = "complete",
    ) -> dict[str, Any]:
        normalized_setting = normalize_setting_type(setting_type)
        normalized_mode = "rewrite" if draft_mode == "rewrite" else "complete"
        effective_template = self._rewrite_anchor_template(template) if normalized_mode == "rewrite" else template
        self.last_analysis_error = None
        self.last_character_draft_diagnostics = {}
        mode_instruction = (
            "生成模式：整卡重写。只保留模板里的角色名、题材类型和题材补充作为锚点；"
            "用户粗设定是新的核心。其他旧字段不要沿用，可以大幅重写成完整角色卡。"
            if normalized_mode == "rewrite"
            else
            "生成模式：补全润色。保留模板中明确且高质量的用户自写内容；"
            "补齐空字段，重写占位、模板化、过短或低质量字段。"
        )
        user = (
            f"用户粗设定：{prompt}\n"
            f"题材类型：{setting_guidance(normalized_setting, setting_notes)}\n"
            f"{mode_instruction}\n"
            f"可参考模板：{json.dumps(effective_template or {}, ensure_ascii=False)}\n"
            "如果参考模板的世界观、地点、道具、称呼或职业与题材类型冲突，请只保留兼容的人格核心，"
            "并按题材类型重写 scenario、personality、speech_style、relationship_pace、opening_line、"
            "boundaries、interaction_policy、voice 和 visual。请扩写成完整角色卡 JSON。不要保存角色，只返回草稿。"
        )
        if not self.provider:
            self.last_character_draft_diagnostics = {
                "source": "fallback",
                "core_source": "fallback",
                "pack_source": "fallback",
                "error": "llm_not_configured",
                "timeout_ms": CHARACTER_DRAFT_TIMEOUT_MS,
            }
            return self._fallback_character_draft(prompt, effective_template, normalized_setting, setting_notes)
        fallback = self._fallback_character_draft(prompt, effective_template, normalized_setting, setting_notes)
        core_task = self._generate_character_draft_part(
            "core",
            CHARACTER_DRAFT_CORE_PROMPT,
            user,
            {"name", "archetype", "tagline", "gender", "setting_type", "setting_notes", "bio", "personality", "scenario", "speech_style", "relationship_pace", "opening_line", "boundaries", "anti_patterns"},
        )
        pack_task = self._generate_character_draft_part(
            "pack",
            CHARACTER_DRAFT_PACK_PROMPT,
            user,
            {"likes", "dislikes", "mes_example", "creator_notes", "system_prompt", "post_history_instructions", "interaction_policy", "story_seed_pool", "voice", "visual"},
        )
        core_part, pack_part = await asyncio.gather(core_task, pack_task)
        core_source = core_part["source"]
        pack_source = pack_part["source"]
        merged = {
            **fallback,
            **core_part["character"],
            **pack_part["character"],
            "setting_type": normalized_setting,
        }
        merged["setting_notes"] = self._fallback_setting_notes(
            normalized_setting,
            prompt,
            str(merged.get("setting_notes") or setting_notes or ""),
        )
        seed_pool = merged.get("story_seed_pool") if isinstance(merged.get("story_seed_pool"), dict) else {}
        merged["story_seed_pool"] = self._complete_story_seed_pool(
            seed_pool,
            normalized_setting,
            prompt,
            setting_notes,
        )
        merged = self._complete_character_draft_fields(merged, prompt, effective_template, normalized_setting, setting_notes)
        errors = [str(item["error"]) for item in [core_part, pack_part] if item.get("error")]
        if core_source == "remote" and pack_source == "remote":
            source = "remote"
        elif core_source == "remote" or pack_source == "remote":
            source = "partial"
        else:
            source = "fallback"
        self.last_analysis_error = None if source in {"remote", "partial"} else (errors[0] if errors else "CharacterDraftFallback")
        self.last_character_draft_diagnostics = {
            "source": source,
            "core_source": core_source,
            "pack_source": pack_source,
            "core_error": core_part.get("error") or "",
            "pack_error": pack_part.get("error") or "",
            "error": "; ".join(errors),
            "timeout_ms": CHARACTER_DRAFT_TIMEOUT_MS,
            "parallel": True,
            "provider": self.provider_name(),
        }
        return merged

    async def _generate_character_draft_part(
        self,
        part: str,
        system_prompt: str,
        user_prompt: str,
        allowed_keys: set[str],
    ) -> dict[str, Any]:
        try:
            text = await self.chat_complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout_ms=CHARACTER_DRAFT_TIMEOUT_MS,
                response_format={"type": "json_object"},
                temperature=0.55,
            )
            parsed = self._parse_character_draft_json(text)
            if not parsed:
                return {"part": part, "source": "fallback", "error": "InvalidCharacterDraftJson", "character": {}}
            return {
                "part": part,
                "source": "remote",
                "error": "",
                "character": self._character_draft_part_fields(parsed, allowed_keys),
            }
        except Exception as exc:
            logger.warning("character draft %s generation failed: %s", part, exc)
            return {"part": part, "source": "fallback", "error": type(exc).__name__, "character": {}}

    def _character_draft_part_fields(self, parsed: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in allowed_keys:
            value = parsed.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str) and self._draft_text_is_weak(value):
                continue
            if key == "visual" and isinstance(value, dict):
                filtered_visual = {item_key: item_value for item_key, item_value in value.items() if item_value}
                if filtered_visual:
                    result[key] = filtered_visual
                continue
            result[key] = value
        return result

    def _fallback_character_draft(
        self,
        prompt: str,
        template: dict[str, Any] | None = None,
        setting_type: str = "modern_daily",
        setting_notes: str = "",
    ) -> dict[str, Any]:
        base = template if isinstance(template, dict) else {}
        seed = (prompt or "").strip()
        normalized_setting = normalize_setting_type(setting_type or base.get("setting_type"))
        base_setting = normalize_setting_type(base.get("setting_type"), normalized_setting)
        preserve_setting_fields = base_setting == normalized_setting
        effective_notes = self._fallback_setting_notes(
            normalized_setting,
            seed,
            setting_notes or (str(base.get("setting_notes") or "") if preserve_setting_fields else ""),
        )
        guidance = setting_guidance(normalized_setting, effective_notes)
        seed_gender = "未设定"
        if any(token in seed for token in ["女", "少女", "姐姐", "女侠", "她"]):
            seed_gender = "女"
        elif any(token in seed for token in ["男", "少年", "哥哥", "他"]):
            seed_gender = "男"
        elif any(token in seed.lower() for token in ["nonbinary", "非二元", "无性别"]):
            seed_gender = "非二元"
        seed_pace = "根据聊天自然推进，不突然越界。"
        if any(token in seed for token in ["慢", "克制", "冷淡", "疏离", "边界"]):
            seed_pace = "慢热克制，先确认边界和信任，再自然靠近。"
        elif any(token in seed for token in ["热情", "主动", "亲近"]):
            seed_pace = "可以更主动地表达关心，但仍尊重用户节奏和边界。"
        seed_initiative = 0.45
        if any(token in seed for token in ["主动", "热情", "外向"]):
            seed_initiative = 0.65
        elif any(token in seed for token in ["冷淡", "寡言", "慢", "克制", "安静"]):
            seed_initiative = 0.30
        seed_density = self._fallback_action_density(normalized_setting, seed)
        accent_by_setting = {
            "campus": "#8ac6d1",
            "modern_daily": "#9fb6d7",
            "workplace": "#c8b38d",
            "xianxia_wuxia": "#9bbb8f",
            "urban_fantasy": "#b18bd6",
            "mystery": "#9a9a8f",
            "sci_fi": "#6eb6d9",
            "historical": "#c49a6c",
            "fantasy_adventure": "#8abf7a",
            "custom": "#9fb6d7",
        }
        name = str(base.get("name") or "").strip() or "自定义角色"
        archetype = str(base.get("archetype") or "").strip() or "自定义人格"
        raw = {
            **base,
            "name": name,
            "archetype": archetype,
            "gender": str((base.get("gender") if preserve_setting_fields else "") or seed_gender),
            "setting_type": normalized_setting,
            "setting_notes": str(effective_notes).strip()[:800],
            "tagline": str(base.get("tagline") or f"由设定「{seed[:40] or '自定义'}」扩写出的角色"),
            "bio": str((base.get("bio") if preserve_setting_fields else "") or f"这个角色围绕用户设定展开：{seed}"),
            "personality": str((base.get("personality") if preserve_setting_fields else "") or f"核心设定：{seed}。保持稳定、具体、不过度表演，并符合题材：{guidance}"),
            "scenario": str((base.get("scenario") if preserve_setting_fields else "") or f"当前关系处在{guidance}的角色语境中，地点和动作跟随上下文自然生成。"),
            "speech_style": str((base.get("speech_style") if preserve_setting_fields else "") or "自然、具体、少说教，优先回应用户当下的话。"),
            "likes": (base.get("likes") if preserve_setting_fields else None) or ["清楚表达", "稳定回应", "自然的共同记忆"],
            "dislikes": (base.get("dislikes") if preserve_setting_fields else None) or ["突然越界", "空泛说教", "固定动作循环"],
            "boundaries": (base.get("boundaries") if preserve_setting_fields else None) or ["不强行推进亲密关系", "不冒充真人", "遇到危险或违法话题时温和拒绝"],
            "relationship_pace": str((base.get("relationship_pace") if preserve_setting_fields else "") or seed_pace),
            "opening_line": str((base.get("opening_line") if preserve_setting_fields else "") or f"你好，我是{name}。你刚刚那个设定，我已经记住了。"),
            "mes_example": str(base.get("mes_example") or "\n".join([
                "用户：今天有点不知道从哪里开始。",
                f"{name}：那就先不用急着讲完整。你给我一个最小的开头就好，我会接住。",
                "",
                "用户：你会记得我之前说过的事吗？",
                f"{name}：会。但我不会像读档案一样念出来，只会在刚好需要的时候轻轻提一下。",
                "",
                "用户：我不太喜欢被催着表态。",
                f"{name}：明白。那我会放慢一点，先确认你的节奏，不替你做决定。",
            ])),
            "creator_notes": str(base.get("creator_notes") or "这是本地 fallback 草稿；远程模型不可用或返回格式无效时生成。"),
            "anti_patterns": (base.get("anti_patterns") if preserve_setting_fields else None) or ["不要突然告白", "不要每轮重复同一个动作", "不要把安慰写成训话"],
            "interaction_policy": {
                "initiative_level": seed_initiative,
                "action_density": seed_density,
                "action_style": "动作轻量、跟随语境，不固定道具或场景。",
                "comfort_style": "先回应用户感受，再给一个具体落点。",
                "question_style": "少量追问，优先接住用户已经说出的内容。",
                "memory_style": "自然提起相关记忆，不像读档案。",
            },
            "story_seed_pool": {
                "places": self._fallback_seed_places(normalized_setting, seed),
                "event_seeds": self._fallback_seed_events(normalized_setting, seed),
                "hook_seeds": self._fallback_seed_hooks(normalized_setting, seed),
                "motifs": self._fallback_seed_motifs(normalized_setting, seed, effective_notes),
                "forbidden_defaults": self._fallback_seed_forbidden(),
            },
            "voice": {
                "sentence_rhythm": "句子自然，有节奏但不过度文学化。",
                "signature_moves": ["顺着用户当前话题回应", "把抽象感受落成具体态度", "在合适时自然提起旧话题"],
                "avoid": ["系统腔", "固定动作循环", "突然推进亲密", "长篇说教"],
                "sample_lines": [
                    f"我大概懂你想要的感觉：{seed[:60] or '稳定、自然、具体'}。",
                    "我们可以先从最小的那句话开始，不用一下子讲完。",
                    "这件事我会记得，但不会拿它压着你。",
                    "如果你不想现在回答，我就先陪你停在这里。",
                    "我会慢一点靠近，不抢你的节奏。",
                ],
            },
            "visual": {"accent": accent_by_setting.get(normalized_setting, "#9fb6d7"), "portrait_hint": f"{guidance}中的自定义角色"},
        }
        return self._clean_character_draft(raw)

    def _rewrite_anchor_template(self, template: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(template, dict):
            return None
        anchor: dict[str, Any] = {}
        for key in ["name", "setting_type", "setting_notes"]:
            value = template.get(key)
            if str(value or "").strip():
                anchor[key] = value
        return anchor or None

    def _complete_character_draft_fields(
        self,
        draft: dict[str, Any],
        prompt: str,
        template: dict[str, Any] | None,
        setting_type: str,
        setting_notes: str,
    ) -> dict[str, Any]:
        fallback = self._fallback_character_draft(prompt, template, setting_type, setting_notes)
        completed = dict(draft)
        text_fields = [
            "name",
            "archetype",
            "tagline",
            "gender",
            "bio",
            "personality",
            "scenario",
            "speech_style",
            "relationship_pace",
            "opening_line",
            "mes_example",
            "creator_notes",
            "system_prompt",
            "post_history_instructions",
        ]
        for key in text_fields:
            if self._draft_text_is_weak(completed.get(key)):
                completed[key] = fallback.get(key, "")
        for key in ["likes", "dislikes", "boundaries", "anti_patterns"]:
            if not completed.get(key):
                completed[key] = fallback.get(key, [])
        interaction = completed.get("interaction_policy") if isinstance(completed.get("interaction_policy"), dict) else {}
        fallback_interaction = fallback.get("interaction_policy") if isinstance(fallback.get("interaction_policy"), dict) else {}
        completed["interaction_policy"] = {
            **fallback_interaction,
            **{key: value for key, value in interaction.items() if not self._draft_text_is_weak(value)},
        }
        voice = completed.get("voice") if isinstance(completed.get("voice"), dict) else {}
        fallback_voice = fallback.get("voice") if isinstance(fallback.get("voice"), dict) else {}
        completed["voice"] = {
            **fallback_voice,
            **{key: value for key, value in voice.items() if value},
        }
        visual = completed.get("visual") if isinstance(completed.get("visual"), dict) else {}
        fallback_visual = fallback.get("visual") if isinstance(fallback.get("visual"), dict) else {}
        completed["visual"] = {
            **fallback_visual,
            **{key: value for key, value in visual.items() if not self._draft_text_is_weak(value)},
        }
        if visual.get("accent") == "#9fb6d7" and fallback_visual.get("accent") != "#9fb6d7":
            completed["visual"]["accent"] = fallback_visual.get("accent")
        return completed

    def _draft_text_is_weak(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return True
        lowered = text.lower()
        weak_values = {"unknown", "low", "todo", "tbd", "n/a", "none", "未设定", "待补充", "自定义角色", "自定义人格"}
        return lowered in weak_values

    def _fallback_setting_notes(self, setting_type: str, seed: str, existing: str = "") -> str:
        current = str(existing or "").strip()
        if current:
            return current[:800]
        seed_hint = str(seed or "").strip()[:40]
        by_setting = {
            "campus": "校园日常、社团与课后场景、慢热同伴关系",
            "modern_daily": "现代都市日常、生活化场景、自然推进关系",
            "workplace": "成人职场、合作与边界、现实压力下的关系推进",
            "xianxia_wuxia": "低魔江湖或修仙门派、医修/剑修等身份、克制慢热关系",
            "urban_fantasy": "现代城市异常、隐秘组织或规则、日常与超自然交错",
            "mystery": "悬疑调查、线索与误会、克制协作关系",
            "sci_fi": "近未来城市、数据/义体/调查线索、冷静克制关系",
            "historical": "古风时代、家族/官署/江湖约束、礼法边界",
            "fantasy_adventure": "奇幻旅途、遗迹与同行选择、冒险中的信任建立",
            "custom": "自定义世界观、角色可转译故事素材、按用户设定约束展开",
        }
        base = by_setting.get(normalize_setting_type(setting_type), by_setting["modern_daily"])
        return f"{base}；核心设定：{seed_hint}"[:800] if seed_hint else base

    def _fallback_action_density(self, setting_type: str, seed: str) -> str:
        text = str(seed or "")
        if any(token in text for token in ["活泼", "外向", "主动", "动作多", "冒险"]):
            return "可以更主动地用动作带动节奏，例如走近、递物或观察环境，但每轮只保留一个重点动作。"
        if any(token in text for token in ["冷淡", "寡言", "克制", "慢热", "安静"]):
            return "动作保持克制，只在情绪转折或需要确认边界时出现，用停顿、抬眼或后退半步表达变化。"
        by_setting = {
            "xianxia_wuxia": "动作偏克制，适合用收针、拂袖、停剑、避开视线等细节承接情绪，不连续堆叠武打动作。",
            "sci_fi": "动作偏冷静，适合用查看终端、调整投影、停在安全距离外等细节，不把回复写成动作戏。",
            "mystery": "动作服务线索和氛围，适合短暂停顿、翻看证物或确认环境，每轮避免超过一个调查动作。",
            "workplace": "动作贴近现实职场，适合整理文件、停下会议记录或递出选择，不用夸张肢体表达。",
            "campus": "动作轻量生活化，适合停在走廊、递过笔记或放慢脚步，不反复使用同一道具。",
        }
        return by_setting.get(setting_type, "动作跟随对话自然出现，优先使用一个轻量细节承接情绪，避免每轮都写固定姿态。")

    def _complete_story_seed_pool(
        self,
        seed_pool: dict[str, Any],
        setting_type: str,
        seed: str,
        setting_notes: str = "",
    ) -> dict[str, list[str]]:
        return {
            "places": list(seed_pool.get("places") or []) or self._fallback_seed_places(setting_type, seed),
            "event_seeds": list(seed_pool.get("event_seeds") or []) or self._fallback_seed_events(setting_type, seed),
            "hook_seeds": list(seed_pool.get("hook_seeds") or []) or self._fallback_seed_hooks(setting_type, seed),
            "motifs": list(seed_pool.get("motifs") or []) or self._fallback_seed_motifs(setting_type, seed, setting_notes),
            "forbidden_defaults": list(seed_pool.get("forbidden_defaults") or []) or self._fallback_seed_forbidden(),
        }

    def _fallback_seed_places(self, setting_type: str, seed: str) -> list[str]:
        by_setting = {
            "xianxia_wuxia": ["山门药庐", "雨夜驿站", "秘境入口", "江边渡口"],
            "sci_fi": ["旧城区事务所", "空轨站台", "数据交易所", "仿生人诊所"],
            "mystery": ["旧档案室", "雨夜公交站", "展馆后台", "河堤路灯下"],
            "workplace": ["会议室", "路演后台", "深夜办公室", "客户楼下"],
            "urban_fantasy": ["旧城区巷口", "午夜便利店", "异常管理处", "封锁线外"],
            "historical": ["官署廊下", "茶楼雅间", "旧宅花厅", "渡口马车旁"],
            "fantasy_adventure": ["边境酒馆", "森林小径", "遗迹入口", "飞空船甲板"],
            "campus": ["图书馆门口", "教学楼公告栏前", "社团教室外", "操场看台"],
        }
        places = by_setting.get(setting_type, ["街角咖啡店", "雨后人行道", "社区书店", "公寓楼下"])
        return places

    def _fallback_seed_events(self, setting_type: str, seed: str) -> list[str]:
        label = seed[:24] or "当前角色设定"
        return [
            f"围绕“{label}”出现一个外部事件，迫使双方先处理眼前问题。",
            "一次临时变更让原本普通的会面变成共同协作。",
            "旧话题以可见物件或地点重新出现，双方需要重新确认边界。",
            "外部压力让主角必须在解释、隐瞒和求助之间做小选择。",
        ]

    def _fallback_seed_hooks(self, setting_type: str, seed: str) -> list[str]:
        return [
            "关键线索被暂时留下，没有立刻解释。",
            "对方把选择权交还给主角，关系没有被强行推进。",
            "一个旧约定被改写成下一次见面的理由。",
            "事件解决了，但真正的问题刚露出边缘。",
        ]

    def _fallback_seed_motifs(self, setting_type: str, seed: str, setting_notes: str = "") -> list[str]:
        by_setting = {
            "xianxia_wuxia": ["药香", "雨夜灯火", "旧剑穗", "未寄出的符纸"],
            "sci_fi": ["蓝色霓虹", "故障投影", "冷光雨幕", "旧数据芯片"],
            "mystery": ["旧档案袋", "雨痕", "录音杂音", "半张票根"],
            "workplace": ["会议灯光", "未发送邮件", "空杯咖啡", "合同折角"],
            "urban_fantasy": ["午夜路灯", "封条", "异常回声", "旧城区雨水"],
            "historical": ["檐下雨线", "旧信笺", "茶盏余温", "铜铃声"],
            "fantasy_adventure": ["地图边角", "篝火余烬", "风化石碑", "银色星轨"],
            "campus": ["雨后公告栏", "半凉饮料", "折角便签", "操场灯影"],
        }
        return by_setting.get(setting_type, ["雨后路灯", "半凉饮料", "折角便签", "未说完的话"])

    def _fallback_seed_forbidden(self) -> list[str]:
        return ["不套用无关默认场景", "不提前写死章节剧情", "不把关系突然推进到既定结局"]

    async def extract_memories(self, user_message: str, assistant_reply: str) -> list[dict[str, Any]]:
        if not self.provider:
            return []
        system = self.memory_extraction_system_prompt()
        user = f"用户消息：{user_message}\n角色回复：{assistant_reply}"
        try:
            text = await self.chat_complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], timeout_ms=RELATIONSHIP_STAGE_TIMEOUT_MS)
            return self._parse_memory_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("memory extraction failed: %s", exc)
            return []

    async def score_character_state(
        self,
        character: CharacterCard,
        previous_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any] | None:
        if not self.provider:
            return None
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧状态：{json.dumps(previous_state, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": self.character_state_system_prompt()},
                {"role": "user", "content": user},
            ], timeout_ms=RELATIONSHIP_STAGE_TIMEOUT_MS)
            return self._parse_state_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("character state scoring failed: %s", exc)
            return None

    async def extract_relationship_events(
        self,
        character: CharacterCard,
        previous_bond: dict[str, Any],
        current_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any] | None:
        if not self.provider:
            return None
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧长期关系档案：{json.dumps(previous_bond, ensure_ascii=False)}\n"
            f"当前短期状态：{json.dumps(current_state, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": RELATIONSHIP_EVENT_STRUCTURED_PROMPT},
                {
                    "role": "system",
                    "content": (
                        'Structured output contract: return one JSON object only, shaped as {"events":[...]}. '
                        'Use {"events":[]} when there is no relationship event. '
                        "Each event may contain only event_type, evidence_grade, and evidence_text. "
                        "The evidence_text must be copied exactly from the current user message as a contiguous "
                        "substring. Do not output summaries like 'the user said ...' or '用户表示...'. "
                        "Do not return an empty events array when the user explicitly says they trust this character, "
                        "names a boundary violation, states a relationship-facing interaction preference, "
                        "accepts a repair after harm, or names a concrete shared pact. "
                        'Example trust output: {"events":[{"event_type":"trust_signal","evidence_grade":"explicit",'
                        '"evidence_text":"I trust you to take what I say seriously."}]}. '
                        'Example boundary output: {"events":[{"event_type":"boundary_violation","evidence_grade":"explicit",'
                        '"evidence_text":"You crossed a line just now; do not keep questioning me like that."}]}.'
                    ),
                },
                {"role": "user", "content": user},
            ],
                timeout_ms=BOND_STAGE_TIMEOUT_MS,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return self._parse_relationship_events_json(text)
        except Exception as exc:
            self.last_chat_error = type(exc).__name__
            logger.warning("relationship event extraction failed: %s", exc)
            return []

    async def score_character_bond(
        self,
        character: CharacterCard,
        previous_bond: dict[str, Any],
        current_state: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> list[dict[str, Any]]:
        return await self.extract_relationship_events(
            character,
            previous_bond,
            current_state,
            recent_messages,
            user_message,
            assistant_reply,
            recalled_memories,
        )

    async def analyze_turn(
        self,
        character: CharacterCard,
        previous_state: dict[str, Any],
        previous_bond: dict[str, Any],
        recent_messages: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        recalled_memories: list[MemoryItem],
    ) -> dict[str, Any]:
        if not self.provider:
            return {"state": None, "bond": None, "memories": []}
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages[-8:])
        memories = "\n".join(
            f"- {item.memory_scope}/{item.memory_type}: {item.content}"
            for item in recalled_memories[:6]
        ) or "无"
        user = (
            f"角色：{character.name} / {character.archetype}\n"
            f"旧短期状态：{json.dumps(previous_state, ensure_ascii=False)}\n"
            f"旧长期关系档案：{json.dumps(previous_bond, ensure_ascii=False)}\n"
            f"最近对话：\n{recent}\n"
            f"本轮用户消息：{user_message}\n"
            f"本轮角色回复：{assistant_reply}\n"
            f"本轮召回记忆：\n{memories}"
        )
        try:
            text = await self.chat_complete([
                {"role": "system", "content": self.turn_analysis_system_prompt()},
                {"role": "user", "content": user},
            ])
            self.last_analysis_error = None
            return self._parse_turn_analysis_json(text)
        except Exception as exc:
            self.last_analysis_error = type(exc).__name__
            logger.warning("turn analysis failed: %s", exc)
            return {"state": None, "bond": None, "memories": []}
