from __future__ import annotations

import json
import re
from typing import Any


class NovelGenerationResponseMixin:
    def _chapter_system_prompt(self) -> str:
        return (
            "你是长篇小说章节写作者。正文必须是小说场景，不是大纲说明、创作报告或素材整理。"
            "把设定和档案转化为动作、环境、对白、心理和节奏，至少写出八到十四个自然段。"
            "素材和 Story Bible 只是熟悉感锚点，不是剧情边界；只需要露出一到三处读者熟悉的线索。"
            "允许在不改变已确认事实的前提下自由新增符合项目题材的小事件、道具、旁观者、误会、延误或场面压力。"
            "每一到两个段落都要让场面状态发生变化，不能只连续抒情或解释关系。"
            "不得改变已确认事实，不得越过角色边界，不得把未发生线索写成已经发生。"
            "正文里不得出现 prompt、记忆系统、评分、内部模块、用户、助手、JSON 字段名、素材编号、英文下划线字段名。"
            "不要写“这一章”“本章目标”“作为伏笔”“确认的事实”“两人还不熟”“关系变化”等元叙述或分析句。"
            "不要照抄场景卡、画布或 Scene Beats 的原句；开头直接进入可感知的场景。"
            "只输出 JSON 对象，字段为 title, summary, body, source_material_ids。"
        )

    def _parse_chapter_response(self, text: str, target_length: int = 0) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object found")
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            raise ValueError("Chapter payload is not an object")
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        body = str(raw.get("body") or "").strip()
        material_ids = raw.get("source_material_ids") or []
        if not title or not body:
            raise ValueError("Chapter payload is missing required fields")
        return {
            "title": title[:120],
            "summary": summary[:1200] or body[:180],
            "body": body[:20000],
            "source_material_ids": [str(item).strip() for item in material_ids if str(item).strip()][:24],
        }
