from __future__ import annotations

import json
import re
from typing import Any


CONTINUITY_LEDGER_KEYS = [
    "locked_facts",
    "changed_states",
    "open_threads",
    "resolved_threads",
    "next_must_continue",
    "promises_made",
    "promises_paid",
    "avoid_repeating",
    "forbidden_contradictions",
]


def _clean_text(value: Any, limit: int = 260) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value: Any, limit: int = 12, item_limit: int = 220) -> list[str]:
    if isinstance(value, str):
        value = [part for part in re.split(r"[\n；;]+", value) if part.strip()]
    if not isinstance(value, list):
        return []
    return _unique_short_list([_clean_text(item, item_limit) for item in value if _clean_text(item, item_limit)], limit)


def _norm(value: Any) -> str:
    text = _clean_text(value, 260).lower()
    return re.sub(r"[\s,，。.!！?？:：;；、\-—_（）()\[\]【】\"'“”‘’]+", "", text)


def _unique_short_list(values: list[Any], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        key = _norm(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _subtract_resolved(values: list[str], resolved: list[str]) -> list[str]:
    resolved_norms = {_norm(item) for item in resolved if _norm(item)}
    if not resolved_norms:
        return values
    return [
        item for item in values
        if _norm(item) not in resolved_norms and not any(_norm(item) and (_norm(item) in resolved_key or resolved_key in _norm(item)) for resolved_key in resolved_norms)
    ]


def empty_continuity_ledger() -> dict[str, list[str]]:
    return {key: [] for key in CONTINUITY_LEDGER_KEYS}


def normalize_continuity_ledger(raw: Any, fallback: Any | None = None) -> dict[str, list[str]]:
    source = raw if isinstance(raw, dict) else {}
    base = fallback if isinstance(fallback, dict) else {}
    ledger = empty_continuity_ledger()
    for key in CONTINUITY_LEDGER_KEYS:
        values = _clean_list(source.get(key), 12, 220)
        if not values:
            values = _clean_list(base.get(key), 12, 220)
        ledger[key] = values
    ledger["open_threads"] = _subtract_resolved(ledger["open_threads"], ledger["resolved_threads"])
    ledger["promises_made"] = _subtract_resolved(ledger["promises_made"], ledger["promises_paid"])
    return ledger


def continuity_ledger_from_handoff(handoff: Any, extra_forbidden: Any | None = None) -> dict[str, list[str]]:
    source = handoff if isinstance(handoff, dict) else {}
    raw = source.get("continuity_ledger") if isinstance(source.get("continuity_ledger"), dict) else {}
    fallback = {
        "locked_facts": source.get("happened", []),
        "changed_states": source.get("relationship_delta", []),
        "open_threads": source.get("open_threads", []),
        "resolved_threads": source.get("resolved_threads", []),
        "next_must_continue": source.get("next_must_continue", []),
        "promises_made": [*(_clean_list(source.get("ending_hook"), 6, 220)), *(_clean_list(source.get("next_must_continue"), 6, 220))],
        "promises_paid": source.get("resolved_threads", []),
        "avoid_repeating": source.get("avoid_repeating", []),
        "forbidden_contradictions": extra_forbidden or [],
    }
    return normalize_continuity_ledger(raw, fallback)


def merge_continuity_ledgers(base: Any, ledgers: list[Any], limit: int = 16) -> dict[str, list[str]]:
    merged = normalize_continuity_ledger(base)
    for raw in ledgers:
        ledger = normalize_continuity_ledger(raw)
        for key in CONTINUITY_LEDGER_KEYS:
            merged[key] = _unique_short_list([*merged.get(key, []), *ledger.get(key, [])], limit)
    merged["open_threads"] = _subtract_resolved(merged["open_threads"], merged["resolved_threads"])
    merged["promises_made"] = _subtract_resolved(merged["promises_made"], merged["promises_paid"])
    return merged


def continuity_ledger_terms(raw: Any) -> dict[str, list[str]]:
    ledger = normalize_continuity_ledger(raw)
    return {
        "ledger_locked": ledger["locked_facts"],
        "ledger_changed": ledger["changed_states"],
        "ledger_open": ledger["open_threads"],
        "ledger_resolved": ledger["resolved_threads"],
        "ledger_must_continue": ledger["next_must_continue"],
        "ledger_promises": ledger["promises_made"],
        "ledger_paid": ledger["promises_paid"],
        "ledger_avoid": ledger["avoid_repeating"],
        "ledger_forbidden": ledger["forbidden_contradictions"],
    }


def continuity_ledger_prompt(raw: Any, limit: int = 10) -> str:
    ledger = normalize_continuity_ledger(raw)
    compact = {key: values[:limit] for key, values in ledger.items() if values}
    return json.dumps(compact, ensure_ascii=False, indent=2) if compact else "无"


def continuity_hits(text: Any, values: list[str], limit: int = 4) -> list[str]:
    source = _clean_text(text, 3000).lower()
    hits: list[str] = []
    for value in values:
        clean = _clean_text(value, 120)
        key = clean.lower()
        if len(key) < 2:
            continue
        if key in source or source in key:
            hits.append(clean)
        if len(hits) >= limit:
            break
    return hits
