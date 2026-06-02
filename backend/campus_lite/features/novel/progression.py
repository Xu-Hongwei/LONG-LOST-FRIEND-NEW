from __future__ import annotations

import json
from typing import Any


PROMISE_KEYS = ["core_experience", "genre_contract", "relationship_engine", "tone_commitment"]
PROTOCOL_LIST_KEYS = ["chapter_rules", "progression_tools", "drift_guards", "style_directives"]
PROTOCOL_TEXT_KEYS = ["driver", "relationship_rule", "source"]


def _value(source: Any, key: str, default: str = "") -> str:
    if source is None:
        return default
    try:
        value = source[key]
    except Exception:
        value = source.get(key, default) if isinstance(source, dict) else default
    return str(value or default).strip()


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_list(value: Any, limit: int = 8, item_limit: int = 160) -> list[str]:
    items: list[str] = []
    if isinstance(value, str):
        raw_items = value.replace("；", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    for item in raw_items:
        text = _clean_text(item, item_limit)
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def default_story_promise(project: Any | None = None) -> dict[str, str]:
    title = _value(project, "title", "长篇项目")
    genre = _value(project, "genre", "现代日常长篇")
    tone = _value(project, "tone", "温柔、克制、日常")
    worldview = _value(project, "worldview", "")
    relationship = _value(project, "relationship_setup", "")
    return {
        "core_experience": f"围绕《{title}》形成一个可连续推进的{genre}体验，每章都用可见事件推动人物选择。",
        "genre_contract": f"章节事件必须兑现类型承诺：{genre}。{worldview[:160]}".strip(),
        "relationship_engine": relationship[:220] or "关系变化必须附着在共同处理事件、信息差、选择和边界感上，不能只靠闲聊变熟。",
        "tone_commitment": f"保持{tone}，避免突然跳到过度亲密、过度解释或与项目类型无关的普通流水账。",
    }


def default_progression_protocol(project: Any | None = None) -> dict[str, Any]:
    genre = _value(project, "genre", "现代日常长篇")
    tone = _value(project, "tone", "温柔、克制、日常")
    return {
        "driver": f"每章用一个符合{genre}的外部事件或信息变化推动人物选择。",
        "chapter_rules": [
            "每章必须有可观察的外部事件、阻碍升级、人物选择和结尾钩子。",
            "关系推进必须通过行动、对话、误会、协作或保留信息体现。",
            "不能只写普通聊天、普通转场或抽象关系总结。",
        ],
        "progression_tools": [
            "外部事件",
            "信息差",
            "路线或时间限制",
            "共同处理问题",
            "未解问题",
        ],
        "relationship_rule": "关系变化是事件的结果，不是章节的唯一事件。",
        "drift_guards": [
            "不要脱离项目类型写成纯日常闲聊。",
            "不要把未发生事实写成已经发生。",
            "不要突然表白、同居、强亲密或跳过边界。",
        ],
        "style_directives": [
            f"保持{tone}。",
            "用动作、物件、环境和停顿承载情绪。",
            "每章结尾留下一个具体、可继续写的钩子。",
        ],
        "source": "local_default",
        "manual_edited": False,
    }


def normalize_story_promise(raw: Any, project: Any | None = None) -> dict[str, str]:
    fallback = default_story_promise(project)
    source = raw if isinstance(raw, dict) else {}
    return {key: _clean_text(source.get(key) or fallback[key], 500) for key in PROMISE_KEYS}


def normalize_progression_protocol(raw: Any, project: Any | None = None) -> dict[str, Any]:
    fallback = default_progression_protocol(project)
    source = raw if isinstance(raw, dict) else {}
    protocol: dict[str, Any] = {}
    for key in PROTOCOL_TEXT_KEYS:
        protocol[key] = _clean_text(source.get(key) or fallback[key], 500)
    for key in PROTOCOL_LIST_KEYS:
        protocol[key] = _clean_list(source.get(key), 10, 180) or list(fallback[key])
    protocol["manual_edited"] = bool(source.get("manual_edited"))
    if not protocol["source"]:
        protocol["source"] = "remote" if source else "local_default"
    return protocol


def normalize_story_progression(canvas: dict[str, Any], project: Any | None = None) -> dict[str, Any]:
    next_canvas = dict(canvas) if isinstance(canvas, dict) else {}
    next_canvas["story_promise"] = normalize_story_promise(next_canvas.get("story_promise"), project)
    next_canvas["progression_protocol"] = normalize_progression_protocol(next_canvas.get("progression_protocol"), project)
    if isinstance(next_canvas.get("chapters"), list):
        protocol = next_canvas["progression_protocol"]
        role_cycle = ["setup", "pressure", "choice", "aftermath", "bridge", "escalation"]
        normalized_chapters: list[Any] = []
        for index, chapter in enumerate(next_canvas["chapters"]):
            if not isinstance(chapter, dict):
                normalized_chapters.append(chapter)
                continue
            try:
                chapter_order = int(chapter.get("chapter_order") or index + 1)
            except Exception:
                chapter_order = index + 1
            role = _clean_text(chapter.get("progression_role"), 40) or role_cycle[(chapter_order - 1) % len(role_cycle)]
            event = _clean_text(chapter.get("external_event") or chapter.get("trigger_event") or chapter.get("goal"), 180)
            drive = _clean_text(chapter.get("chapter_drive"), 360) or f"{protocol['driver']} 本章通过“{event or '一个可见事件'}”落实。"
            targets = _clean_list(chapter.get("promise_targets"), 5, 120) or protocol.get("progression_tools", [])[:3]
            normalized_chapters.append({
                **chapter,
                "chapter_drive": drive,
                "progression_role": role,
                "promise_targets": targets,
            })
        next_canvas["chapters"] = [
            *normalized_chapters
        ]
    return next_canvas


def progression_prompt(canvas: dict[str, Any], project: Any | None = None) -> str:
    normalized = normalize_story_progression(canvas, project)
    payload = {
        "story_promise": normalized.get("story_promise", {}),
        "progression_protocol": normalized.get("progression_protocol", {}),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def progression_terms(canvas_or_context: Any, project: Any | None = None) -> list[str]:
    canvas = canvas_or_context if isinstance(canvas_or_context, dict) else {}
    if "story_canvas" in canvas and isinstance(canvas.get("story_canvas"), dict):
        canvas = canvas["story_canvas"]
    normalized = normalize_story_progression(canvas, project)
    values: list[Any] = [
        *normalized["story_promise"].values(),
        normalized["progression_protocol"].get("driver"),
        normalized["progression_protocol"].get("relationship_rule"),
        normalized["progression_protocol"].get("chapter_rules", []),
        normalized["progression_protocol"].get("progression_tools", []),
        normalized["progression_protocol"].get("style_directives", []),
    ]
    terms: list[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = _clean_text(item, 80)
                if text and text not in terms:
                    terms.append(text)
        else:
            for part in _clean_text(value, 240).replace("，", "\n").replace("。", "\n").replace("；", "\n").splitlines():
                text = _clean_text(part, 80)
                if len(text) >= 2 and text not in terms:
                    terms.append(text)
        if len(terms) >= 32:
            break
    return terms


def chapter_progression_defaults(
    chapter: dict[str, Any],
    canvas: dict[str, Any],
    project: Any | None = None,
    order: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_story_progression(canvas, project)
    protocol = normalized["progression_protocol"]
    chapter_order = order or int(chapter.get("chapter_order") or 1)
    role_cycle = ["setup", "pressure", "choice", "aftermath", "bridge", "escalation"]
    role = _clean_text(chapter.get("progression_role"), 40) or role_cycle[(chapter_order - 1) % len(role_cycle)]
    event = _clean_text(chapter.get("external_event") or chapter.get("trigger_event") or chapter.get("goal"), 180)
    drive = _clean_text(chapter.get("chapter_drive"), 360) or f"{protocol['driver']} 本章通过“{event or '一个可见事件'}”落实。"
    targets = _clean_list(chapter.get("promise_targets"), 5, 120) or protocol.get("progression_tools", [])[:3]
    return {
        "chapter_drive": drive,
        "progression_role": role,
        "promise_targets": targets,
    }
