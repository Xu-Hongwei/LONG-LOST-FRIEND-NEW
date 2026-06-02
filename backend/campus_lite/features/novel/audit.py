from __future__ import annotations

import json
import re
from typing import Any

from .config import NOVEL_PLANNING_TIMEOUT_MS
from .continuity import continuity_ledger_prompt


class NovelAuditMixin:
    async def _audit_chapter(
        self,
        llm: Any,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
        target_length: int,
        local_check: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        local_check = local_check or self._chapter_local_check(parsed.get("body", ""), target_length)
        if local_check["blockers"]:
            return {
                "pass": False,
                "hard_fail": True,
                "rewrite_required": True,
                "issues": local_check["blockers"],
                "warnings": local_check["warnings"],
                "source": "local",
            }
        try:
            if not llm.configured():
                return {"pass": True, "hard_fail": False, "rewrite_required": False, "issues": [], "warnings": local_check["warnings"], "source": "local"}
            text = await llm.chat_complete([
                {"role": "system", "content": self._audit_checklist_system_prompt()},
                {"role": "user", "content": self._audit_checklist_source(project, chapter, scene_card, scene_beats, parsed, local_check)},
            ], timeout_ms=NOVEL_PLANNING_TIMEOUT_MS)
            audit = self._parse_audit_checklist_response(text)
            return {**audit, "warnings": [*local_check["warnings"], *audit.get("warnings", [])][:12]}
        except Exception as exc:
            llm.last_chat_error = type(exc).__name__
            return {"pass": True, "hard_fail": False, "rewrite_required": False, "issues": [], "warnings": local_check["warnings"], "source": "audit_fallback"}

    def _audit_system_prompt(self) -> str:
        return (
            "你是小说章节质检器，只输出 JSON 对象。字段：pass 布尔值，issues 字符串数组，rewrite_brief 字符串。"
            "检查正文是否只有一个连续场景、有外部事件、至少两轮对白、没有分析句、没有重复抒情、结尾有具体钩子。"
            "如果只是风格可更好但可读，pass=true；如果像散文或复制场景卡说明，pass=false。"
        )

    def _audit_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
    ) -> str:
        return "\n\n".join([
            f"作品：{project['title']} / 第{chapter['chapter_order']}章《{chapter['title']}》",
            "[场景卡]",
            self._scene_card_prompt(scene_card),
            "[Scene Beats]",
            self._scene_beats_prompt(scene_beats),
            "[正文]",
            parsed.get("body", ""),
        ])

    def _parse_audit_response(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No audit JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Audit payload is not an object")
        issues = raw.get("issues") if isinstance(raw.get("issues"), list) else []
        return {
            "pass": bool(raw.get("pass", True)),
            "issues": [str(item).strip()[:200] for item in issues if str(item).strip()][:8],
            "rewrite_brief": str(raw.get("rewrite_brief") or "").strip()[:800],
            "source": "remote",
        }

    def _audit_checklist_system_prompt(self) -> str:
        return (
            "你是小说章节审稿员，只输出 JSON 对象，不要打主观总分。"
            "字段必须包含：hard_fail, rewrite_required, checks, issues, rewrite_brief。"
            "checks 是对象，布尔字段包含 has_visible_event, has_character_choice, has_dialogue, has_ending_hook, "
            "uses_scene_card_terms, has_meta_narration, has_repeated_paragraphs, breaks_confirmed_facts, breaks_continuity_ledger, misses_required_continuation, repeats_resolved_thread, style_breaks_previous_chapter。"
            "你只判断这些可说明的问题，并为每个 issue 给出 evidence 和 rewrite_instruction。"
            "如果只是文风还可提升但正文已经可读，不要要求重写；如果缺少事件、对白、人物选择、结尾钩子，或泄露场景卡术语，才要求重写。"
        )

    def _audit_checklist_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
        local_check: dict[str, list[str]] | None = None,
    ) -> str:
        local_check = local_check or {"blockers": [], "warnings": [], "infos": []}
        try:
            novel_state = self._novel_state_until(project, int(chapter["chapter_order"]) - 1)
        except Exception:
            novel_state = {}
        return "\n\n".join([
            f"作品：{project['title']} / 第{chapter['chapter_order']}章《{chapter['title']}》",
            "[本地检查]",
            json.dumps(local_check, ensure_ascii=False),
            "[场景卡]",
            self._scene_card_prompt(scene_card),
            "[Scene Beats]",
            self._scene_beats_prompt(scene_beats),
            "[Continuity Ledger 连续性账本]",
            continuity_ledger_prompt(novel_state.get("continuity_ledger") if isinstance(novel_state, dict) else {}),
            "[正文]",
            parsed.get("body", ""),
            "[输出 JSON 示例]",
            json.dumps({
                "hard_fail": False,
                "rewrite_required": False,
                "checks": {
                    "has_visible_event": True,
                    "has_character_choice": True,
                    "has_dialogue": True,
                    "has_ending_hook": True,
                    "uses_scene_card_terms": False,
                    "has_meta_narration": False,
                    "has_repeated_paragraphs": False,
                    "breaks_confirmed_facts": False,
                    "breaks_continuity_ledger": False,
                    "misses_required_continuation": False,
                    "repeats_resolved_thread": False,
                    "style_breaks_previous_chapter": False,
                },
                "issues": [],
                "rewrite_brief": "",
            }, ensure_ascii=False),
        ])

    def _parse_audit_checklist_response(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No audit JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Audit payload is not an object")
        issues_raw = raw.get("issues") if isinstance(raw.get("issues"), list) else []
        issues: list[dict[str, str]] = []
        for item in issues_raw[:10]:
            if isinstance(item, dict):
                issues.append({
                    "type": str(item.get("type") or item.get("label") or "issue").strip()[:80],
                    "evidence": str(item.get("evidence") or item.get("detail") or "").strip()[:240],
                    "rewrite_instruction": str(item.get("rewrite_instruction") or item.get("instruction") or "").strip()[:240],
                })
            elif str(item).strip():
                issues.append({"type": "issue", "evidence": str(item).strip()[:240], "rewrite_instruction": ""})
        checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
        warnings = raw.get("warnings") if isinstance(raw.get("warnings"), list) else []
        return {
            "pass": bool(raw.get("pass", not raw.get("rewrite_required", False))),
            "hard_fail": bool(raw.get("hard_fail", False)),
            "rewrite_required": bool(raw.get("rewrite_required", False)),
            "checks": {str(key): bool(value) for key, value in checks.items()},
            "issues": issues,
            "warnings": [str(item).strip()[:200] for item in warnings if str(item).strip()][:8],
            "rewrite_brief": str(raw.get("rewrite_brief") or "").strip()[:800],
            "source": "remote",
        }

    def _audit_requires_rewrite(self, audit: dict[str, Any], target_length: int) -> bool:
        if audit.get("hard_fail") or audit.get("rewrite_required") or audit.get("pass") is False:
            return True
        checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
        if checks.get("has_meta_narration") or checks.get("uses_scene_card_terms") or checks.get("has_repeated_paragraphs"):
            return True
        if checks.get("breaks_confirmed_facts"):
            return True
        if checks.get("breaks_continuity_ledger") or checks.get("misses_required_continuation") or checks.get("repeats_resolved_thread"):
            return True
        if checks.get("has_visible_event") is False or checks.get("has_character_choice") is False:
            return True
        if target_length >= 800 and checks.get("has_dialogue") is False:
            return True
        issues = audit.get("issues") if isinstance(audit.get("issues"), list) else []
        return len(issues) >= 2

    def _audit_issue_text(self, audit: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in audit.get("issues", []) if isinstance(audit.get("issues"), list) else []:
            if isinstance(item, dict):
                evidence = str(item.get("evidence") or "").strip()
                instruction = str(item.get("rewrite_instruction") or "").strip()
                parts.append("；".join(part for part in [evidence, instruction] if part))
            elif str(item).strip():
                parts.append(str(item).strip())
        if parts:
            return "；".join(parts[:6])
        return str(audit.get("rewrite_brief") or "需要增强场景事件和对白。")

    def _rewrite_source(
        self,
        project: Any,
        chapter: Any,
        scene_card: dict[str, Any],
        scene_beats: list[dict[str, Any]],
        parsed: dict[str, Any],
        audit: dict[str, Any],
        target_length: int,
    ) -> str:
        return "\n\n".join([
            "[重写目标]",
            f"把以下草稿重写为约 {target_length} 字的小说正文。保留事实，但删除分析句、重复抒情和场景卡原句。",
            "[质检问题]",
            self._audit_issue_text(audit),
            "[Scene Beats，必须按顺序写成正文]",
            self._scene_beats_prompt(scene_beats),
            "[场景卡，只作约束，不得照抄]",
            self._scene_card_prompt(scene_card),
            "[原草稿]",
            parsed.get("body", ""),
            "[输出]",
            "只输出 JSON 对象，字段为 title, summary, body, source_material_ids。正文只能是小说场景。"
            "允许补入符合项目题材的小事件来制造推进，但不要新增重大关系进展。",
        ])

