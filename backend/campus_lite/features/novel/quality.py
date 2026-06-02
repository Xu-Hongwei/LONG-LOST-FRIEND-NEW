from __future__ import annotations

import re

from ...schemas import NovelContinuityIssue, NovelContinuityReport
from .continuity import continuity_hits, normalize_continuity_ledger


INTERNAL_NOVEL_TERMS = {
    "prompt",
    "记忆系统",
    "评分",
    "内部模块",
    "用户/助手",
    "user/assistant",
    "recent_emotion",
    "stable_user_info",
    "user_preference",
    "relationship_progress",
    "open_thread",
    "memory_type",
    "source_material_ids",
    "Story Bible",
    "story_bible",
    "confirmed_facts",
    "foreshadowing",
    "unresolved_threads",
    "relationships",
    "boundaries",
    "inspirations",
}

INTERNAL_ID_PATTERN = re.compile(r"\b(?:mat|mem|msg|story|chapter|novel|ver)_[0-9a-f]{6,}\b", re.I)

META_NARRATION_PHRASES = [
    "这一章",
    "本章",
    "素材",
    "材料",
    "确认的事实",
    "已经确认的事实",
    "作为伏笔",
    "未完成线索",
    "关系推进",
    "创作过程",
    "生成",
    "用户喜欢",
    "用户询问",
]


class NovelQualityMixin:
    def check_continuity(self, project_id: str, chapter_id: str | None = None) -> NovelContinuityReport:
        storage = self._require_storage()
        project = storage.get_novel_project(project_id)
        if not project:
            raise ValueError("Novel project not found")
        story_bible = self._json_dict(project["story_bible_json"])
        story_canvas = self._json_dict(project["story_canvas_json"] if "story_canvas_json" in project.keys() else "{}")
        chapters = storage.list_novel_chapters(project_id)
        selected = storage.get_novel_chapter(chapter_id) if chapter_id else (chapters[-1] if chapters else None)
        text = selected["body"] if selected else ""
        issues: list[NovelContinuityIssue] = []
        for detail in self._chapter_quality_issues(text):
            issues.append(NovelContinuityIssue(severity="error", label="小说质检未通过", detail=detail))
        for boundary in story_bible.get("boundaries", [])[:8]:
            if boundary and ("承诺" in text or "越过边界" in text):
                issues.append(NovelContinuityIssue(severity="warning", label="边界风险", detail=str(boundary)[:160]))
                break
        for seed in story_bible.get("unresolved_threads", [])[:8]:
            if seed and seed in text and any(word in text for word in ["已经", "终于", "从此"]):
                issues.append(NovelContinuityIssue(severity="warning", label="伏笔状态需人工确认", detail=str(seed)[:160]))
                break
        if not text.strip():
            issues.append(NovelContinuityIssue(severity="warning", label="章节为空", detail="当前章节还没有正文可检查。"))
        canvas_chapters = self._canvas_chapters(story_canvas)
        canvas_scenes = self._canvas_scenes(story_canvas)
        if not canvas_chapters or not canvas_scenes:
            issues.append(NovelContinuityIssue(severity="warning", label="故事画布不完整", detail="建议先生成或补全故事画布，再生成长篇正文。"))
        if selected:
            canvas_chapter, canvas_scene = self._canvas_for_chapter(project, selected)
            if not canvas_chapter:
                issues.append(NovelContinuityIssue(severity="warning", label="章节未绑定画布", detail="当前章节没有对应的画布节点。"))
            if not canvas_scene:
                issues.append(NovelContinuityIssue(severity="warning", label="缺少场景卡节点", detail="当前章节没有可驱动正文的画布场景。"))
            previous_state = self._novel_state_until(project, int(selected["chapter_order"]) - 1)
            ledger = normalize_continuity_ledger(previous_state.get("continuity_ledger"))
            body_text = str(text or "")
            must_hits = continuity_hits(body_text, ledger["next_must_continue"], 4)
            if ledger["next_must_continue"] and not must_hits and body_text.strip():
                issues.append(NovelContinuityIssue(
                    severity="warning",
                    label="未承接账本",
                    detail=f"上一章要求承接：{ledger['next_must_continue'][0][:160]}",
                ))
            avoid_hits = continuity_hits(body_text, ledger["avoid_repeating"], 3)
            if avoid_hits:
                issues.append(NovelContinuityIssue(
                    severity="warning",
                    label="重复已避免内容",
                    detail="；".join(avoid_hits)[:200],
                ))
            resolved_hits = continuity_hits(body_text, ledger["resolved_threads"], 3)
            if resolved_hits:
                issues.append(NovelContinuityIssue(
                    severity="warning",
                    label="重复已回收线索",
                    detail="；".join(resolved_hits)[:200],
                ))
            forbidden_hits = continuity_hits(body_text, ledger["forbidden_contradictions"], 3)
            if forbidden_hits:
                issues.append(NovelContinuityIssue(
                    severity="error",
                    label="违反连续性禁区",
                    detail="；".join(forbidden_hits)[:200],
                ))
        if not issues:
            issues.append(NovelContinuityIssue(severity="ok", label="基础检查通过", detail="未发现内部措辞、空正文或明显伏笔状态风险。"))
        return NovelContinuityReport(
            project_id=project_id,
            chapter_id=selected["id"] if selected else None,
            issues=issues,
            summary="；".join(item.label for item in issues),
            diagnostics={
                "checker": "local",
                "continuity_ledger": normalize_continuity_ledger(
                    self._novel_state_until(project, int(selected["chapter_order"]) - 1).get("continuity_ledger")
                ) if selected else {},
            },
        )

    def _chapter_local_check(self, body: str, target_length: int = 0) -> dict[str, list[str]]:
        text = body.strip()
        lower_text = text.lower()
        blockers: list[str] = []
        warnings: list[str] = []
        infos: list[str] = []
        if not text:
            blockers.append("正文为空")
        for term in sorted(INTERNAL_NOVEL_TERMS, key=len, reverse=True):
            if term.lower() in lower_text:
                blockers.append(f"正文包含内部字段或术语「{term}」")
        if INTERNAL_ID_PATTERN.search(text):
            blockers.append("正文包含内部引用编号")
        hard_meta_patterns = [
            r"根据.{0,12}(素材|材料|设定|提示|prompt)",
            r"(素材|材料|记忆|设定).{0,8}(列表|如下|提供|生成)",
            r"(作为AI|作为 AI|我是AI|我是 AI)",
            r"(system|assistant|user)\s*:",
        ]
        for pattern in hard_meta_patterns:
            if re.search(pattern, text, re.I):
                blockers.append("正文包含明显元叙述或提示词泄露")
                break
        ambiguous_meta = {"素材", "材料", "本章", "关系", "张力", "伏笔", "线索", "当前"}
        for phrase in META_NARRATION_PHRASES:
            if phrase in text:
                if phrase in ambiguous_meta:
                    warnings.append(f"正文出现可能正常也可能元叙述的词「{phrase}」")
                else:
                    blockers.append(f"正文偏创作说明「{phrase}」")
        analysis_phrases = [
            "校园日常长篇",
            "当前场景",
            "表层事件",
            "人物欲望",
            "阻碍",
            "张力",
            "关系变化",
            "两人还不熟",
            "从路人变成",
            "真正拦在",
            "只能用礼貌",
            "熟悉线索",
            "触发事件",
            "即时反应",
            "对方反应",
            "人物选择",
            "场景后果",
            "结尾钩子",
            "目标长度",
            "Scene",
            "beats",
        ]
        for phrase in analysis_phrases:
            if phrase in text:
                warnings.append(f"正文可能含有大纲或分析措辞「{phrase}」")
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
        seen: set[str] = set()
        for paragraph in paragraphs:
            compact = re.sub(r"\s", "", paragraph)
            if len(compact) > 30 and compact in seen:
                blockers.append("正文包含重复段落")
                break
            seen.add(compact)
        dialogue_count = len(re.findall(r"[“\"].+?[”\"]", text))
        if target_length >= 600 and dialogue_count < 2:
            infos.append("正文可能缺少足够人物对话")
        if text.count("听见自己的声音") >= 2:
            warnings.append("正文反复使用同一心理句式")
        if len(text) < 120:
            blockers.append("正文过短")
        if target_length >= 600 and len(re.sub(r"\s", "", text)) < int(target_length * 0.55):
            infos.append(f"正文明显短于目标长度 {target_length} 字")
        return {
            "blockers": self._unique_short_list(blockers, 12),
            "warnings": self._unique_short_list(warnings, 12),
            "infos": self._unique_short_list(infos, 12),
        }

    def _chapter_quality_issues(self, body: str, target_length: int = 0) -> list[str]:
        check = self._chapter_local_check(body, target_length)
        return [*check["blockers"], *check["warnings"], *check["infos"]]
        text = body.strip()
        lower_text = text.lower()
        issues: list[str] = []
        for term in sorted(INTERNAL_NOVEL_TERMS, key=len, reverse=True):
            if term.lower() in lower_text:
                issues.append(f"正文包含内部措辞「{term}」")
        if INTERNAL_ID_PATTERN.search(text):
            issues.append("正文包含内部引用编号")
        for phrase in META_NARRATION_PHRASES:
            if phrase in text:
                issues.append(f"正文偏创作说明「{phrase}」")
        analysis_phrases = [
            "校园日常长篇",
            "当前场景",
            "表层事件",
            "人物欲望",
            "阻碍",
            "张力",
            "关系变化",
            "两人还不熟",
            "从路人变成",
            "真正拦在",
            "只能用礼貌",
            "熟悉线索",
            "触发事件",
            "即时反应",
            "对方反应",
            "人物选择",
            "场景后果",
            "结尾钩子",
            "目标长度",
            "Scene",
            "beats",
        ]
        for phrase in analysis_phrases:
            if phrase in text:
                issues.append(f"正文含有大纲或分析措辞「{phrase}」")
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
        seen: set[str] = set()
        for paragraph in paragraphs:
            compact = re.sub(r"\s", "", paragraph)
            if len(compact) > 30 and compact in seen:
                issues.append("正文包含重复段落")
                break
            seen.add(compact)
        dialogue_count = len(re.findall(r"[“\"].+?[”\"]", text))
        if target_length >= 600 and dialogue_count < 2:
            issues.append("正文缺少足够人物对话")
        if text.count("听见自己的声音") >= 2:
            issues.append("正文反复使用同一心理句式")
        if len(text) < 120:
            issues.append("正文过短")
        if target_length >= 600 and len(re.sub(r"\s", "", text)) < int(target_length * 0.55):
            issues.append(f"正文明显短于目标长度 {target_length} 字")
        return issues
