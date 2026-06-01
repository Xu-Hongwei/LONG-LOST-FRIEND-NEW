from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from ...setting_types import normalize_setting_type
from .setting_profiles import novel_setting_profile


STORY_EVENT_POOL_SIZE = 10
EVENT_USE_MODES = {"strict", "guide", "flavor", "free"}
_VAGUE_TIME_ANCHORS = {"某天", "之后", "后来", "不久", "有一天", "下次", "some day", "someday", "later", "afterward", "next time"}
_CONCRETE_TIME_PATTERN = re.compile(
    r"(\d{1,2}[:：]\d{2}|\d{1,2}\s*(?:am|pm)|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"清晨|早晨|上午|午后|下午|傍晚|黄昏|夜里|深夜|凌晨|雨后|雪后|放学后|下班后|晚饭后|"
    r"morning|afternoon|evening|night|dawn|dusk|after rain|before midnight)"
)
_GENERIC_EVENT_TERMS = {
    "推进关系",
    "加深理解",
    "产生互动",
    "增进感情",
    "关系升温",
    "交流",
    "互动",
    "relationship",
    "understanding",
    "interaction",
}
_RISK_TERMS = {"表白", "亲密", "同居", "亲吻", "拥抱", "告白", "强迫", "越界", "confession", "kiss", "intimacy"}
_INTERNAL_NAME_TERMS = {"用户", "助手", "AI", "assistant"}
_CAMPUS_DEFAULT_TERMS = {"图书馆", "社团", "公告栏", "课程误会", "教学楼", "自习室", "library", "club", "class"}


def _clean_text(value: Any, limit: int = 260) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value: Any, limit: int = 8, item_limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item, item_limit) for item in value if _clean_text(item, item_limit)][:limit]


def _clean_tags(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    tags: dict[str, Any] = {}
    for key in [
        "event_type",
        "anchors",
        "theme_markers",
        "tone_markers",
        "relationship_motion",
        "continuity",
        "freshness",
        "forbidden_defaults",
    ]:
        cleaned = _clean_list(value.get(key), 12, 80)
        if cleaned:
            tags[key] = cleaned
    boundary_risk = _clean_text(value.get("boundary_risk"), 40)
    if boundary_risk:
        tags["boundary_risk"] = boundary_risk
    return tags


def normalize_event_use_mode(value: Any, default: str = "guide") -> str:
    mode = _clean_text(value, 40) or default
    return mode if mode in EVENT_USE_MODES else default


def _source_lists(setting_type: str, seed_pool: dict[str, list[str]] | None = None) -> tuple[list[str], list[str], list[str], list[str]]:
    profile = novel_setting_profile(setting_type)
    seed_pool = seed_pool or {}
    places = seed_pool.get("places") or profile["places"]
    events = seed_pool.get("event_seeds") or profile["events"]
    hooks = seed_pool.get("hook_seeds") or profile["endings"]
    motifs = seed_pool.get("motifs") or []
    return places or ["scene"], events or ["event"], hooks or ["hook"], motifs


def _seed_pool_has_core(seed_pool: dict[str, list[str]] | None = None) -> bool:
    seed_pool = seed_pool or {}
    return any(seed_pool.get(key) for key in ("places", "event_seeds", "hook_seeds"))


def _event_key(entry: dict[str, Any]) -> str:
    return "|".join([
        _clean_text(entry.get("place"), 120),
        _clean_text(entry.get("event"), 180),
        _clean_text(entry.get("hook"), 180),
    ])


def _variant_text(text: str, index: int, kind: str) -> str:
    clean = _clean_text(text, 220)
    variant_no = max(1, index + 1)
    if kind == "event":
        return _clean_text(f"{clean} 变体{variant_no}：压力来自新的时间限制、旁观者或信息差。", 360)
    if kind == "hook":
        return _clean_text(f"{clean} 变体{variant_no}：留下另一层未确认的选择。", 260)
    return clean


def _fallback_event(
    setting_type: str,
    index: int,
    seed_pool: dict[str, list[str]] | None = None,
    existing_keys: set[str] | None = None,
) -> dict[str, Any]:
    setting_type = normalize_setting_type(setting_type)
    places, events, hooks, motifs = _source_lists(setting_type, seed_pool)
    existing_keys = existing_keys or set()
    if _seed_pool_has_core(seed_pool):
        source_label = "character_seed"
    elif seed_pool and any(seed_pool.values()):
        source_label = "character_seed_translated"
    else:
        source_label = "setting_profile"
    for offset in range(max(len(places), len(events), len(hooks), STORY_EVENT_POOL_SIZE) * 2):
        slot = index + offset
        entry = {
            "id": f"evt_{setting_type}_{index + 1 + offset}",
            "place": _clean_text(places[slot % len(places)]),
            "event": _clean_text(events[slot % len(events)], 360),
            "hook": _clean_text(hooks[slot % len(hooks)], 260),
            "motifs": [_clean_text(motifs[slot % len(motifs)], 80)] if motifs else [],
            "status": "fresh",
            "source": source_label,
            "used_chapter_ids": [],
            "use_mode": "guide",
        }
        if _event_key(entry) not in existing_keys:
            return entry
    slot = index
    variant = {
        "id": f"evt_{setting_type}_{index + 1}",
        "place": _clean_text(places[index % len(places)]),
        "event": _variant_text(events[slot % len(events)], index, "event"),
        "hook": _variant_text(hooks[slot % len(hooks)], index, "hook"),
        "motifs": [_clean_text(motifs[index % len(motifs)], 80)] if motifs else [],
        "status": "fresh",
        "source": source_label,
        "used_chapter_ids": [],
        "use_mode": "guide",
    }
    return variant


def _normalize_event_entry(raw: Any, fallback: dict[str, Any], index: int) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    event = _clean_text(source.get("event") or source.get("text") or source.get("label") or fallback["event"], 360)
    place = _clean_text(source.get("place") or source.get("location") or fallback["place"], 180)
    hook = _clean_text(source.get("hook") or source.get("ending") or source.get("ending_hook") or fallback["hook"], 260)
    event_id = _clean_text(source.get("id") or fallback["id"] or f"evt_{index + 1}", 80)
    status = _clean_text(source.get("status") or fallback.get("status") or "fresh", 40)
    if status not in {"fresh", "planned", "used", "mutated", "retired"}:
        status = "fresh"
    return {
        "id": event_id,
        "place": place,
        "event": event,
        "hook": hook,
        "time_anchor": _clean_text(source.get("time_anchor") or fallback.get("time_anchor"), 120),
        "motifs": _clean_list(source.get("motifs") or fallback.get("motifs"), 6, 80),
        "status": status,
        "source": _clean_text(source.get("source") or fallback.get("source") or "setting_profile", 40),
        "use_mode": normalize_event_use_mode(source.get("use_mode") or fallback.get("use_mode")),
        "used_chapter_ids": _clean_list(source.get("used_chapter_ids") or fallback.get("used_chapter_ids"), 20, 80),
        "bound_chapter_orders": _clean_list(source.get("bound_chapter_orders") or fallback.get("bound_chapter_orders"), 20, 20),
        "bound_chapter_titles": _clean_list(source.get("bound_chapter_titles") or fallback.get("bound_chapter_titles"), 20, 80),
        "tags": _clean_tags(source.get("tags") or fallback.get("tags")),
        "source_reason": _clean_text(source.get("source_reason") or fallback.get("source_reason"), 220),
        "selection_score": int(source.get("selection_score") or fallback.get("selection_score") or 0),
        "selection_reasons": _clean_list(source.get("selection_reasons") or fallback.get("selection_reasons"), 8, 120),
        "selection_penalties": _clean_list(source.get("selection_penalties") or fallback.get("selection_penalties"), 8, 120),
    }


def _ensure_unique_event_id(entry: dict[str, Any], used_ids: set[str], index: int) -> dict[str, Any]:
    event_id = _clean_text(entry.get("id"), 80) or f"evt_{index + 1}"
    if event_id not in used_ids:
        entry["id"] = event_id
        used_ids.add(event_id)
        return entry
    suffix = 2
    while f"{event_id}_v{suffix}" in used_ids:
        suffix += 1
    entry["id"] = f"{event_id}_v{suffix}"
    used_ids.add(entry["id"])
    return entry


def _replaceable_active_index(active: list[dict[str, Any]]) -> int:
    replacement_tiers = [
        {"setting_profile"},
        {"character_seed_translated"},
    ]
    for sources in replacement_tiers:
        for index in range(len(active) - 1, -1, -1):
            item = active[index]
            if item.get("bound_chapter_orders") or item.get("used_chapter_ids"):
                continue
            if item.get("status") not in {"fresh", "", None}:
                continue
            if item.get("source") not in sources:
                continue
            if item.get("source") == "character_seed_translated" and (item.get("selection_score") or item.get("source_reason")):
                continue
            return index
    for index in range(len(active) - 1, -1, -1):
        item = active[index]
        if item.get("bound_chapter_orders") or item.get("used_chapter_ids"):
            continue
        if item.get("status") in {"fresh", "", None} and int(item.get("selection_score") or 0) < 50:
            return index
    for index in range(len(active) - 1, -1, -1):
        item = active[index]
        if not item.get("bound_chapter_orders") and not item.get("used_chapter_ids") and item.get("status") != "planned":
            return index
    return -1


def event_pool_source_counts(pool: Any) -> dict[str, int]:
    source = pool if isinstance(pool, dict) else {}
    active = source.get("active") if isinstance(source.get("active"), list) else []
    counts: dict[str, int] = {}
    for item in active:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("source"), 40) or "setting_profile"
        counts[label] = counts.get(label, 0) + 1
    return counts


def normalize_story_event_pool(
    raw: Any,
    setting_type: str = "modern_daily",
    seed_pool: dict[str, list[str]] | None = None,
    target_size: int = STORY_EVENT_POOL_SIZE,
) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    setting_type = normalize_setting_type(_clean_text(source.get("setting_type")) or setting_type)
    retired_raw = source.get("retired") if isinstance(source.get("retired"), list) else []
    retired: list[dict[str, Any]] = []
    retired_keys: set[str] = set()
    used_ids: set[str] = set()
    for index, item in enumerate(retired_raw[:40]):
        fallback = _fallback_event(setting_type, index + target_size, seed_pool)
        entry = _normalize_event_entry(item, fallback, index)
        entry["status"] = "retired"
        entry = _ensure_unique_event_id(entry, used_ids, index)
        retired_keys.add(_event_key(entry))
        retired.append(entry)
    active_raw = source.get("active") if isinstance(source.get("active"), list) else []
    active: list[dict[str, Any]] = []
    keys: set[str] = set(retired_keys)
    for index, item in enumerate(active_raw[:target_size]):
        fallback = _fallback_event(setting_type, index, seed_pool, keys)
        entry = _normalize_event_entry(item, fallback, index)
        key = _event_key(entry)
        if key and key in keys:
            continue
        entry = _ensure_unique_event_id(entry, used_ids, index)
        keys.add(key)
        active.append(entry)
    while len(active) < target_size:
        entry = _fallback_event(setting_type, len(active), seed_pool, keys)
        entry = _ensure_unique_event_id(entry, used_ids, len(active))
        keys.add(_event_key(entry))
        active.append(entry)
    return {
        "version": 1,
        "target_active": target_size,
        "setting_type": setting_type,
        "active": active[:target_size],
        "retired": retired[-40:],
        "updated_at": _clean_text(source.get("updated_at")) or datetime.now(timezone.utc).isoformat(),
    }


def build_story_event_pool(
    setting_type: str,
    seed_pool: dict[str, list[str]] | None = None,
    target_size: int = STORY_EVENT_POOL_SIZE,
) -> dict[str, Any]:
    return normalize_story_event_pool({}, setting_type, seed_pool, target_size)


def story_event_for_order(
    pool: Any,
    chapter_order: int,
    setting_type: str = "modern_daily",
    seed_pool: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_story_event_pool(pool, setting_type, seed_pool)
    active = normalized.get("active") or []
    fresh = [item for item in active if item.get("status") != "used"] or active
    if not fresh:
        return _fallback_event(setting_type, max(chapter_order - 1, 0), seed_pool)
    return fresh[max(chapter_order - 1, 0) % len(fresh)]


def story_event_for_chapter(
    pool: Any,
    chapter: dict[str, Any],
    setting_type: str = "modern_daily",
    seed_pool: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_story_event_pool(pool, setting_type, seed_pool)
    active = normalized.get("active") or []
    retired = normalized.get("retired") or []
    event_id = _clean_text(chapter.get("event_pool_id"), 80)
    if event_id:
        matched = next((item for item in active if str(item.get("id") or "") == event_id), None)
        if matched:
            return matched
        matched = next((item for item in retired if str(item.get("id") or "") == event_id), None)
        if matched:
            return matched
    try:
        order = int(chapter.get("chapter_order") or 0)
    except Exception:
        order = 0
    if order:
        order_text = str(order)
        matched = next(
            (
                item for item in active
                if order_text in [str(value) for value in item.get("bound_chapter_orders", [])]
            ),
            None,
        )
        if matched:
            return matched
        matched = next(
            (
                item for item in retired
                if order_text in [str(value) for value in item.get("bound_chapter_orders", [])]
            ),
            None,
        )
        if matched:
            return matched
    return story_event_for_order(normalized, order, setting_type, seed_pool)


def _clear_event_bindings(active: list[dict[str, Any]]) -> None:
    for item in active:
        item["bound_chapter_orders"] = []
        item["bound_chapter_titles"] = []
        item["selection_score"] = 0
        item["selection_reasons"] = []
        item["selection_penalties"] = []


def _record_event_binding(bound: dict[str, Any], chapter: dict[str, Any], scored: dict[str, Any] | None = None) -> None:
    try:
        order = int(chapter.get("chapter_order") or 0)
    except Exception:
        order = 0
    if order <= 0:
        return
    orders = [str(item) for item in bound.get("bound_chapter_orders", []) if str(item).strip()]
    titles = [str(item) for item in bound.get("bound_chapter_titles", []) if str(item).strip()]
    order_text = str(order)
    if order_text not in orders:
        orders.append(order_text)
    title = _clean_text(chapter.get("title"), 80)
    if title and title not in titles:
        titles.append(title)
    bound["bound_chapter_orders"] = orders[-20:]
    bound["bound_chapter_titles"] = titles[-20:]
    score_source = scored or {}
    bound["selection_score"] = int(score_source.get("score") or chapter.get("event_pool_score") or 0)
    bound["selection_reasons"] = _clean_list(score_source.get("reasons") or chapter.get("event_pool_reasons"), 8, 120)
    bound["selection_penalties"] = _clean_list(score_source.get("penalties") or chapter.get("event_pool_penalties"), 8, 120)


def sync_story_event_pool_display_bindings(
    raw: Any,
    chapters: list[dict[str, Any]],
    setting_type: str = "modern_daily",
) -> dict[str, Any]:
    pool = normalize_story_event_pool(raw, setting_type)
    active = pool.get("active") or []
    if not active:
        return pool
    _clear_event_bindings(active)
    by_id = {str(item.get("id") or ""): item for item in active}
    for chapter in chapters:
        if str(chapter.get("status") or "").lower() in {"complete", "completed"}:
            continue
        event_id = _clean_text(chapter.get("event_pool_id"), 80)
        bound = by_id.get(event_id)
        if bound:
            _record_event_binding(bound, chapter)
            if bound.get("status") == "fresh":
                bound["status"] = "planned"
    pool["active"] = active
    return pool


def advance_story_event_pool(
    raw: Any,
    setting_type: str,
    chapter_order: int,
    event_id: str,
    chapter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pool = normalize_story_event_pool(raw, setting_type)
    chapter = chapter or {}
    active = pool.get("active") or []
    retired = pool.get("retired") or []
    match_index = next((index for index, item in enumerate(active) if str(item.get("id")) == event_id), -1)
    if match_index < 0:
        event_text = _clean_text(chapter.get("external_event") or chapter.get("trigger_event"), 180)
        match_index = next((index for index, item in enumerate(active) if event_text and event_text in str(item.get("event") or "")), -1)
    if match_index < 0:
        fallback_event = story_event_for_order(pool, chapter_order, setting_type)
        fallback_id = _clean_text(fallback_event.get("id"), 80)
        match_index = next((index for index, item in enumerate(active) if fallback_id and str(item.get("id")) == fallback_id), -1)
    if match_index >= 0:
        used = json.loads(json.dumps(active.pop(match_index), ensure_ascii=False))
        used["status"] = "retired"
        used["used_chapter_ids"] = [*used.get("used_chapter_ids", []), f"chapter_{chapter_order}"][-20:]
        used["used_summary"] = _clean_text(chapter.get("completed_summary") or chapter.get("goal") or chapter.get("external_event"), 360)
        retired.append(used)
    pool["active"] = active
    pool["retired"] = retired[-40:]
    pool["updated_at"] = datetime.now(timezone.utc).isoformat()
    return normalize_story_event_pool(pool, setting_type)


def apply_story_event_pool_delta(raw: Any, delta: Any, setting_type: str = "modern_daily") -> dict[str, Any]:
    pool = normalize_story_event_pool(raw, setting_type)
    if not isinstance(delta, dict):
        return pool
    active = pool.get("active") or []
    retired = pool.get("retired") or []
    by_id = {str(item.get("id")): item for item in active}
    seen_keys = {_event_key(item) for item in [*active, *retired] if _event_key(item)}
    for item in delta.get("retire", []) if isinstance(delta.get("retire"), list) else []:
        event_id = _clean_text(item.get("id") if isinstance(item, dict) else item, 80)
        if event_id and event_id in by_id:
            removed = by_id.pop(event_id)
            active = [entry for entry in active if str(entry.get("id")) != event_id]
            removed["status"] = "retired"
            retired.append(removed)
            seen_keys.add(_event_key(removed))
    for item in delta.get("update", []) if isinstance(delta.get("update"), list) else []:
        if not isinstance(item, dict):
            continue
        event_id = _clean_text(item.get("id"), 80)
        if event_id and event_id in by_id:
            updated = _normalize_event_entry(item, by_id[event_id], len(active))
            updated_key = _event_key(updated)
            original_key = _event_key(by_id[event_id])
            if updated_key == original_key or updated_key not in seen_keys:
                seen_keys.discard(original_key)
                by_id[event_id].update(updated)
                seen_keys.add(_event_key(by_id[event_id]))
    for item in delta.get("add", []) if isinstance(delta.get("add"), list) else []:
        if not isinstance(item, dict):
            continue
        fallback = _fallback_event(setting_type, len(active))
        entry = _normalize_event_entry(item, fallback, len(active))
        if entry.get("source_reason") and entry.get("source") == "setting_profile":
            entry["source"] = "remote"
        entry_key = _event_key(entry)
        if entry_key and entry_key not in seen_keys:
            if len(active) >= STORY_EVENT_POOL_SIZE:
                replace_index = _replaceable_active_index(active)
                if replace_index >= 0:
                    removed = active.pop(replace_index)
                    by_id.pop(str(removed.get("id")), None)
                    seen_keys.discard(_event_key(removed))
                    if removed.get("source") == "setting_profile":
                        entry["selection_reasons"] = _clean_list([*(entry.get("selection_reasons") or []), "替换题材兜底"], 8, 120)
            active.append(entry)
            by_id[str(entry.get("id"))] = entry
            seen_keys.add(entry_key)
    pool["active"] = active[:STORY_EVENT_POOL_SIZE]
    pool["retired"] = retired[-40:]
    pool["updated_at"] = datetime.now(timezone.utc).isoformat()
    return normalize_story_event_pool(pool, setting_type)


def _chapter_event_text(chapter: dict[str, Any]) -> str:
    return " ".join(
        _clean_text(chapter.get(key), 360)
        for key in ["external_event", "trigger_event", "goal", "ending_hook"]
        if _clean_text(chapter.get(key), 360)
    )


def _lower_text(value: Any) -> str:
    return _clean_text(value, 2000).lower()


def _contains_any(text: str, values: list[str], limit: int = 4) -> list[str]:
    lowered = _lower_text(text)
    hits: list[str] = []
    for value in values:
        clean = _clean_text(value, 80)
        if len(clean) < 2:
            continue
        needle = clean.lower()
        if needle and (needle in lowered or lowered in needle):
            hits.append(clean)
        if len(hits) >= limit:
            break
    return hits


def _compact_terms(text: str) -> list[str]:
    clean = _lower_text(text)
    terms = re.findall(r"[a-z0-9_]{3,}|[\u4e00-\u9fff]{2,}", clean)
    return [term for term in terms if term not in _GENERIC_EVENT_TERMS][:16]


def _has_concrete_time_anchor(value: Any) -> bool:
    clean = _clean_text(value, 120)
    if not clean:
        return False
    lowered = clean.lower().strip(" ，,。.；;")
    if lowered in _VAGUE_TIME_ANCHORS:
        return False
    if _CONCRETE_TIME_PATTERN.search(lowered):
        return True
    compact = _compact_terms(clean)
    return len(compact) >= 2 and not any(term in lowered for term in _VAGUE_TIME_ANCHORS)


def _profile_terms(value: Any, limit: int = 24) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_profile_terms(item, limit))
        return _clean_list(items, limit, 80)
    if isinstance(value, dict):
        return _profile_terms(json.dumps(value, ensure_ascii=False), limit)
    text = _clean_text(value, 1200)
    parts = [
        part.strip()
        for part in re.split(r"[\s,，。；;、/|:：()（）\[\]{}]+", text)
        if len(part.strip()) >= 2
    ]
    return _clean_list([*parts, *_compact_terms(text)], limit, 80)


def _row_value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except Exception:
        return row.get(key) if isinstance(row, dict) else None


def _scoring_context(context: dict[str, Any] | None, retired: list[dict[str, Any]]) -> dict[str, list[str]]:
    context = context if isinstance(context, dict) else {}
    story_bible = context.get("story_bible") if isinstance(context.get("story_bible"), dict) else {}
    novel_state = context.get("novel_state") if isinstance(context.get("novel_state"), dict) else {}
    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    character = context.get("character") if isinstance(context.get("character"), dict) else {}
    materials = context.get("materials") if isinstance(context.get("materials"), list) else []
    recent_chapters = context.get("recent_chapters") if isinstance(context.get("recent_chapters"), list) else []

    facts = [
        *[str(item) for item in story_bible.get("confirmed_facts", []) if str(item).strip()],
        *[str(item) for item in novel_state.get("confirmed_facts", []) if str(item).strip()],
    ]
    relationships = [
        *[str(item) for item in story_bible.get("relationships", []) if str(item).strip()],
        *[str(item) for item in novel_state.get("relationship_states", []) if str(item).strip()],
    ]
    boundaries = [
        *[str(item) for item in story_bible.get("boundaries", []) if str(item).strip()],
        *[str(item) for item in context.get("boundaries", []) if str(item).strip()],
    ]
    open_threads = [
        *[str(item) for item in story_bible.get("foreshadowing", []) if str(item).strip()],
        *[str(item) for item in story_bible.get("unresolved_threads", []) if str(item).strip()],
        *[str(item) for item in novel_state.get("open_threads", []) if str(item).strip()],
    ]
    material_facts: list[str] = []
    material_relationships: list[str] = []
    material_anchors: list[str] = []
    material_boundaries: list[str] = []
    for row in materials:
        category = _clean_text(_row_value(row, "category"), 40)
        content = _clean_text(_row_value(row, "content"), 240)
        label = _clean_text(_row_value(row, "label"), 80)
        if not content:
            continue
        material_anchors.append(content)
        if label:
            material_anchors.append(label)
        if category == "fact":
            material_facts.append(content)
        elif category == "relationship":
            material_relationships.append(content)
        elif category == "boundary":
            material_boundaries.append(content)
    recent_text = [
        _clean_text(_row_value(row, "summary") or _row_value(row, "goal") or _row_value(row, "body"), 400)
        for row in recent_chapters[-4:]
    ]
    last_handoff = []
    handoffs = novel_state.get("chapter_handoffs") if isinstance(novel_state.get("chapter_handoffs"), list) else []
    if handoffs:
        last_handoff = [json.dumps(handoffs[-1], ensure_ascii=False)]
    theme_terms = _profile_terms([
        project.get("title"),
        project.get("genre"),
        project.get("worldview"),
        project.get("relationship_setup"),
        project.get("outline"),
        project.get("setting_type"),
        context.get("theme_markers"),
        facts,
        relationships,
        material_anchors[:12],
    ], 42)
    tone_terms = _profile_terms([
        project.get("tone"),
        context.get("tone_markers"),
    ], 16)
    character_seed = character.get("story_seed_pool") if isinstance(character.get("story_seed_pool"), dict) else {}
    character_seed_terms = _profile_terms([
        character_seed.get("motifs", []),
        character_seed.get("hook_seeds", []),
        character_seed.get("event_seeds", []),
        character.get("setting_notes"),
    ], 18)
    return {
        "facts": _clean_list(facts, 20, 160),
        "relationships": _clean_list(relationships, 20, 160),
        "boundaries": _clean_list([*boundaries, *material_boundaries], 20, 160),
        "open_threads": _clean_list(open_threads, 20, 160),
        "material_facts": _clean_list(material_facts, 20, 160),
        "material_relationships": _clean_list(material_relationships, 20, 160),
        "material_anchors": _clean_list(material_anchors, 30, 160),
        "recent_text": _clean_list(recent_text, 6, 240),
        "last_handoff": _clean_list(last_handoff, 2, 400),
        "retired_keys": [_event_key(item) for item in retired],
        "retired_text": [_clean_text(f"{item.get('place')} {item.get('event')} {item.get('hook')}", 500) for item in retired[-12:]],
        "theme_terms": theme_terms,
        "tone_terms": tone_terms,
        "character_seed_terms": character_seed_terms,
    }


def _event_text(event: dict[str, Any]) -> str:
    tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
    tag_text = " ".join(
        " ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        for value in tags.values()
    )
    return " ".join([
        _clean_text(event.get("place"), 180),
        _clean_text(event.get("time_anchor"), 120),
        _clean_text(event.get("event"), 360),
        _clean_text(event.get("hook"), 260),
        " ".join(_clean_list(event.get("motifs"), 6, 80)),
        _clean_text(event.get("source_reason"), 220),
        tag_text,
    ])


def _has_generic_event(event: dict[str, Any]) -> bool:
    text = _lower_text(event.get("event"))
    return any(term.lower() in text for term in _GENERIC_EVENT_TERMS)


def _has_internal_role_name(text: str) -> bool:
    if "用户" in text or "助手" in text:
        return True
    lowered = _lower_text(text)
    return bool(re.search(r"\b(ai|assistant|user)\b", lowered))


def _event_source_priority(event: dict[str, Any]) -> int:
    source = _clean_text(event.get("source"), 40)
    if source in {"manual", "project"}:
        return 4
    if source in {"remote", "llm"}:
        return 3
    if source in {"character_seed", "character_seed_translated", "character"}:
        return 2
    if source == "setting_profile":
        return 0
    return 1


def score_story_event(
    event: dict[str, Any],
    chapter: dict[str, Any],
    context: dict[str, Any] | None = None,
    setting_type: str = "modern_daily",
) -> dict[str, Any]:
    setting_type = normalize_setting_type(setting_type)
    retired = context.get("retired_events", []) if isinstance(context, dict) and isinstance(context.get("retired_events"), list) else []
    ctx = _scoring_context(context, retired)
    text = _event_text(event)
    chapter_text = _chapter_event_text(chapter)
    priority_reasons: list[str] = []
    reasons: list[str] = []
    penalties: list[str] = []
    blocked = False
    score = 0

    tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
    boundary_risk = _clean_text(tags.get("boundary_risk"), 40).lower()
    forbidden_defaults = _clean_list(tags.get("forbidden_defaults"), 8, 80)
    theme_markers = _clean_list(tags.get("theme_markers"), 12, 80)
    tone_markers = _clean_list(tags.get("tone_markers"), 8, 80)

    if _event_key(event) in set(ctx["retired_keys"]):
        blocked = True
        penalties.append("duplicate retired event")
    if boundary_risk in {"high", "unsafe", "blocked"}:
        blocked = True
        penalties.append("high boundary risk tag")
    if _contains_any(text, ctx["boundaries"], 2) and any(term in _lower_text(text) for term in _RISK_TERMS):
        blocked = True
        penalties.append("boundary conflict")
    if _has_internal_role_name(text):
        blocked = True
        penalties.append("internal role name")
    if setting_type != "campus" and (_contains_any(text, list(_CAMPUS_DEFAULT_TERMS), 1) or forbidden_defaults):
        blocked = True
        penalties.append("campus default in non-campus setting")

    theme_text = " ".join([text, " ".join(theme_markers), " ".join(tone_markers)])
    theme_hits = _contains_any(theme_text, ctx["theme_terms"], 5)
    tone_hits = _contains_any(theme_text, ctx["tone_terms"], 3)
    if theme_hits:
        score += min(14, 5 + len(theme_hits) * 3)
        priority_reasons.append(f"命中主题：{', '.join(theme_hits[:4])}")
    elif theme_markers:
        score += min(4, len(theme_markers))
    elif _clean_text(event.get("source"), 40) in {"remote", "llm"}:
        score -= 4
        penalties.append("missing project theme markers")
    if tone_hits:
        score += min(6, 2 + len(tone_hits) * 2)
        priority_reasons.append(f"命中基调：{', '.join(tone_hits[:3])}")
    elif tone_markers:
        score += 1

    time_anchor = _clean_text(event.get("time_anchor"), 120)
    if time_anchor and _has_concrete_time_anchor(time_anchor):
        score += 6
        priority_reasons.append(f"具体时间：{time_anchor}")
    elif time_anchor:
        penalties.append("vague time anchor")

    if _clean_text(event.get("place"), 80):
        score += 5
        reasons.append("place present")
    if _clean_text(event.get("event"), 80) and not _has_generic_event(event):
        score += 10
        reasons.append("concrete event")
    else:
        penalties.append("generic event")
    if _clean_text(event.get("hook"), 80):
        score += 5
        reasons.append("hook present")
    source_label = _clean_text(event.get("source"), 40)
    if source_label in {"project", "manual"}:
        score += 7
        reasons.append("project/manual candidate")
    elif source_label in {"remote", "llm"}:
        remote_bonus = 5
        if event.get("source_reason"):
            remote_bonus += 2
        if theme_markers:
            remote_bonus += 2
        if time_anchor and _has_concrete_time_anchor(time_anchor):
            remote_bonus += 2
        score += min(11, remote_bonus)
        reasons.append("滚动新增候选")
    elif source_label not in {"setting_profile"} and event.get("source_reason"):
        score += 5
        reasons.append("sourced candidate")
    elif source_label in {"character", "character_seed", "character_seed_translated"}:
        score += 2
        reasons.append("character flavor seed")
    elif source_label == "setting_profile":
        penalties.append("setting profile fallback")

    if _event_matches_chapter(event, chapter):
        score += 10
        reasons.append("matches chapter text")
    chapter_terms = _compact_terms(chapter_text)
    event_terms = set(_compact_terms(text))
    term_hits = [term for term in chapter_terms if term in event_terms][:4]
    if term_hits:
        score += min(10, 3 * len(term_hits))
        reasons.append(f"chapter terms: {', '.join(term_hits[:3])}")
    ending_hits = _contains_any(event.get("hook"), [chapter.get("ending_hook", ""), *ctx["open_threads"]], 2)
    if ending_hits:
        score += 6
        reasons.append("matches hook or open thread")
    if _clean_text(event.get("place"), 40) and _contains_any(chapter_text, [_clean_text(event.get("place"), 80)], 1):
        score += 5
        reasons.append("place fits chapter")
    if _clean_text(chapter.get("status"), 40) in {"planned", "draft", ""}:
        score += 4

    fact_hits = _contains_any(text, ctx["facts"], 2)
    material_fact_hits = _contains_any(text, ctx["material_facts"], 2)
    material_relationship_hits = _contains_any(text, ctx["material_relationships"], 2)
    anchor_hits = _contains_any(text, ctx["material_anchors"], 2)
    material_score = min(8, len(fact_hits) * 4) + min(6, len(material_fact_hits) * 3) + min(6, len(material_relationship_hits) * 3) + min(4, len(anchor_hits) * 2)
    if material_score:
        score += min(15, material_score)
        reasons.append("uses bible/material anchors")
    character_seed_hits = _contains_any(text, ctx["character_seed_terms"], 2)
    if character_seed_hits:
        score += min(4, len(character_seed_hits) * 2)
        reasons.append("uses character seed flavor")

    relationship_hits = _contains_any(text, ctx["relationships"], 2)
    motion = _clean_list(tags.get("relationship_motion"), 8, 80)
    if relationship_hits or motion:
        score += 6
        reasons.append("fits relationship state")
    if _contains_any(text, ["协作", "选择", "共同", "等待", "确认", "solve", "choice", "shared"], 2):
        score += 4
        reasons.append("supports choice or cooperation")
    if boundary_risk in {"", "low", "safe"}:
        score += 3
    if _contains_any(text, ["余地", "保留", "未说完", "unresolved", "open"], 1):
        score += 2
        reasons.append("leaves room")
    if any(term in _lower_text(text) for term in _RISK_TERMS):
        score -= 12
        penalties.append("relationship jump risk")

    if _contains_any(text, ctx["last_handoff"], 1):
        score += 4
        reasons.append("continues handoff")
    if _contains_any(text, ctx["open_threads"], 2):
        score += 4
        reasons.append("continues open thread")
    if _contains_any(text, ctx["recent_text"], 1):
        score += 2

    recent_place_hit = _contains_any(event.get("place"), ctx["recent_text"], 1)
    retired_hit = _contains_any(text, ctx["retired_text"], 1)
    if not recent_place_hit:
        score += 3
        reasons.append("fresh place")
    else:
        score -= 5
        penalties.append("recent place repeated")
    if not retired_hit:
        score += 7
        reasons.append("not close to retired")
    else:
        score -= 25
        penalties.append("similar to retired")

    score = max(0, min(100, int(score)))
    if blocked:
        score = 0
    return {
        "event_id": _clean_text(event.get("id"), 80),
        "score": score,
        "reasons": [*priority_reasons, *reasons][:8],
        "penalties": penalties[:8],
        "blocked": blocked,
    }


def select_story_event_for_chapter(
    active: list[dict[str, Any]],
    chapter: dict[str, Any],
    context: dict[str, Any] | None,
    setting_type: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    context = context if isinstance(context, dict) else {}
    excluded_event_ids = {str(item) for item in context.get("excluded_event_ids", []) if str(item).strip()}
    best_event: dict[str, Any] | None = None
    best_score: dict[str, Any] = {"score": -1, "reasons": [], "penalties": [], "blocked": True}
    event_id = _clean_text(chapter.get("event_pool_id"), 80)
    existing = next((item for item in active if str(item.get("id")) == event_id), None)
    existing_score = score_story_event(existing, chapter, context, setting_type) if existing and existing.get("use_mode") != "free" else None
    for item in active:
        if str(item.get("id") or "") in excluded_event_ids:
            continue
        if item.get("use_mode") == "free":
            continue
        scored = score_story_event(item, chapter, context, setting_type)
        if scored["blocked"]:
            continue
        if (
            scored["score"] > best_score["score"]
            or (
                scored["score"] >= best_score["score"] - 8
                and _event_source_priority(item) > _event_source_priority(best_event or {})
            )
        ):
            best_event = item
            best_score = scored
    if (
        existing
        and existing.get("use_mode") != "free"
        and str(existing.get("id") or "") not in excluded_event_ids
        and existing_score
        and not existing_score["blocked"]
        and _event_matches_chapter(existing, chapter)
    ):
        if existing_score["score"] >= 60 and existing_score["score"] >= int(best_score.get("score", 0)) - 12:
            return existing, existing_score
    return best_event, best_score


def _event_matches_chapter(event: dict[str, Any], chapter: dict[str, Any]) -> bool:
    chapter_text = _chapter_event_text(chapter)
    if not chapter_text:
        return False
    for key in ["event", "hook", "place"]:
        value = _clean_text(event.get(key), 180)
        if len(value) >= 8 and (value in chapter_text or chapter_text in value):
            return True
    return False


def bind_story_event_pool_to_chapters(
    raw: Any,
    chapters: list[dict[str, Any]],
    setting_type: str = "modern_daily",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pool = normalize_story_event_pool(raw, setting_type)
    active = pool.get("active") or []
    if not active:
        return pool
    context = {**(context or {}), "retired_events": pool.get("retired") or []}
    bind_after_order = 0
    try:
        bind_after_order = int(context.get("bind_after_order") or 0)
    except Exception:
        bind_after_order = 0
    selected_event_ids: set[str] = set()
    if bind_after_order:
        selected_event_ids.update(
            _clean_text(item.get("event_pool_id"), 80)
            for item in chapters
            if int(item.get("chapter_order") or 0) <= bind_after_order and _clean_text(item.get("event_pool_id"), 80)
        )
    by_id = {str(item.get("id")): item for item in active}
    _clear_event_bindings(active)
    ordered_chapters = sorted(chapters, key=lambda item: int(item.get("chapter_order") or 0))
    for chapter in ordered_chapters:
        order = int(chapter.get("chapter_order") or 0)
        if order <= 0:
            continue
        existing_bound = by_id.get(_clean_text(chapter.get("event_pool_id"), 80))
        if bind_after_order and order <= bind_after_order:
            if existing_bound:
                _record_event_binding(existing_bound, chapter)
            continue
        if str(chapter.get("status") or "").lower() in {"complete", "completed"}:
            continue
        bind_context = {**context, "excluded_event_ids": selected_event_ids}
        event_id = _clean_text(chapter.get("event_pool_id"), 80)
        event = by_id.get(event_id)
        if event and event.get("use_mode") == "free":
            scored = {
                "event_id": str(event.get("id") or ""),
                "score": int(chapter.get("event_pool_score") or event.get("selection_score") or 0),
                "reasons": _clean_list(chapter.get("event_pool_reasons") or event.get("selection_reasons") or ["manual free binding"], 8, 120),
                "penalties": _clean_list(chapter.get("event_pool_penalties") or event.get("selection_penalties"), 8, 120),
                "blocked": False,
            }
            selected_event_ids.add(str(event.get("id") or ""))
            _record_event_binding(event, chapter, scored)
            chapter["event_pool_score"] = event["selection_score"]
            chapter["event_pool_reasons"] = event["selection_reasons"]
            chapter["event_pool_penalties"] = event["selection_penalties"]
            if event.get("status") == "fresh":
                event["status"] = "planned"
            continue
        if not event or not _event_matches_chapter(event, chapter):
            event = next((item for item in active if item.get("use_mode") != "free" and str(item.get("id") or "") not in selected_event_ids and _event_matches_chapter(item, chapter)), None)
            if not event:
                event, scored = select_story_event_for_chapter(active, chapter, bind_context, setting_type)
                if not event:
                    candidates = [item for item in active if item.get("use_mode") != "free" and str(item.get("id") or "") not in selected_event_ids] or [item for item in active if item.get("use_mode") != "free"]
                    if not candidates:
                        chapter["event_pool_id"] = ""
                        continue
                    event = candidates[(order - 1) % len(candidates)]
                    scored = score_story_event(event, chapter, bind_context, setting_type)
            else:
                scored = score_story_event(event, chapter, bind_context, setting_type)
            chapter["event_pool_id"] = str(event.get("id") or "")
        else:
            selected, scored = select_story_event_for_chapter(active, chapter, bind_context, setting_type)
            current_score = score_story_event(event, chapter, bind_context, setting_type)
            if selected and (str(event.get("id") or "") in selected_event_ids or scored.get("score", 0) >= current_score.get("score", 0) + 12):
                event = selected
                chapter["event_pool_id"] = str(event.get("id") or "")
            else:
                scored = current_score
        bound = by_id.get(str(chapter.get("event_pool_id") or ""))
        if not bound:
            continue
        if int(scored.get("score") or 0) < 40 and not _event_matches_chapter(bound, chapter):
            chapter["event_pool_id"] = ""
            chapter["event_pool_score"] = int(scored.get("score") or 0)
            chapter["event_pool_reasons"] = _clean_list(scored.get("reasons"), 8, 120)
            chapter["event_pool_penalties"] = _clean_list(scored.get("penalties"), 8, 120)
            continue
        selected_event_ids.add(str(bound.get("id") or ""))
        _record_event_binding(bound, chapter, scored)
        chapter["event_pool_score"] = bound["selection_score"]
        chapter["event_pool_reasons"] = bound["selection_reasons"]
        chapter["event_pool_penalties"] = bound["selection_penalties"]
        if bound.get("status") == "fresh":
            bound["status"] = "planned"
    pool["active"] = active
    return pool


def story_event_pool_prompt(pool: Any) -> str:
    normalized = normalize_story_event_pool(pool)
    lines = []
    for index, item in enumerate((normalized.get("active") or [])[:STORY_EVENT_POOL_SIZE], start=1):
        lines.append(
            f"{index}. id={item.get('id')} use_mode={item.get('use_mode', 'guide')} place={item.get('place')} event={item.get('event')} hook={item.get('hook')} status={item.get('status')}"
        )
    return "\n".join(lines)
