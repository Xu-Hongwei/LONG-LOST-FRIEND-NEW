from __future__ import annotations

import json
import re
from typing import Any

from .schemas import MemoryItem, StoryItem
from .storage import Storage


ALLOWED_KINDS = {"motif", "story_beat", "open_thread", "relationship_texture", "boundary"}
ALLOWED_EVIDENCE = {"explicit", "inferred", "weak"}
ALLOWED_STATUS = {"active", "seed", "developed", "archived"}


class StoryService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def list_items(self, session_id: str) -> list[StoryItem]:
        return [self._row_to_item(row) for row in self.storage.list_story_items(session_id)]

    async def refresh(
        self,
        llm: Any,
        session_id: str,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
    ) -> dict[str, Any]:
        existing = self.list_items(session_id)
        generated = await self._generate_items(llm, messages, memories, existing)
        stored = 0
        for item in generated[:2]:
            story_id = self.storage.upsert_story_item(
                session_id,
                item["kind"],
                item["label"],
                item["content"],
                item.get("evidence", ""),
                item.get("evidence_level", "inferred"),
                item.get("status", "active"),
                item.get("source_message_ids", []),
            )
            if story_id:
                stored += 1
        return {
            "source": "remote" if llm.configured() and generated else "fallback",
            "generated": len(generated[:2]),
            "stored": stored,
        }

    async def _generate_items(
        self,
        llm: Any,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        existing: list[StoryItem],
    ) -> list[dict[str, Any]]:
        if llm.configured():
            try:
                text = await llm.chat_complete([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": self._source(messages, memories, existing)},
                ])
                return self._parse_items(text)
            except Exception as exc:
                llm.last_chat_error = type(exc).__name__
        return self._fallback_items(messages, memories, existing)

    def _system_prompt(self) -> str:
        return (
            "你是剧情窗格整理器。你只从给定聊天、记忆和已有剧情标签中提取可用于后续小说创作的素材。"
            "最多输出 2 条。不要流水账，不要打分，不要编造新事实。"
            "未发生但可延展的内容只能标为 seed/open_thread，不能写成已经发生。"
            "只输出 JSON 数组。每项字段：kind, label, content, evidence, evidence_level, status, source_message_ids。"
            "kind 只能是 motif, story_beat, open_thread, relationship_texture, boundary。"
            "evidence_level 只能是 explicit, inferred, weak。status 只能是 active, seed, developed, archived。"
        )

    def _source(self, messages: list[dict[str, str]], memories: list[MemoryItem], existing: list[StoryItem]) -> str:
        message_lines = "\n".join(
            f"- {item.get('id', '')} {item['role']}: {item['content']}" for item in messages[-30:]
        )
        memory_lines = "\n".join(f"- {item.memory_scope}/{item.memory_type}: {item.content}" for item in memories[:12]) or "无"
        existing_lines = "\n".join(f"- {item.kind}/{item.label}: {item.content}" for item in existing[:20]) or "无"
        return "\n\n".join([
            "[最近会话]",
            message_lines,
            "[记忆]",
            memory_lines,
            "[已有剧情标签]",
            existing_lines,
            "[要求]",
            "只新增或更新最有故事价值的 1-2 条标签。普通寒暄不写。不要重复已有标签。",
        ])

    def _parse_items(self, text: str) -> list[dict[str, Any]]:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        raw = json.loads(match.group(0))
        if not isinstance(raw, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            label = str(item.get("label") or "").strip()
            content = str(item.get("content") or "").strip()
            if kind not in ALLOWED_KINDS or not label or not content:
                continue
            evidence_level = str(item.get("evidence_level") or "inferred").strip()
            status = str(item.get("status") or "active").strip()
            source_ids = item.get("source_message_ids") or []
            cleaned.append({
                "kind": kind,
                "label": label[:80],
                "content": content[:500],
                "evidence": str(item.get("evidence") or "").strip()[:500],
                "evidence_level": evidence_level if evidence_level in ALLOWED_EVIDENCE else "inferred",
                "status": status if status in ALLOWED_STATUS else "active",
                "source_message_ids": [str(value) for value in source_ids if str(value).strip()][:12],
            })
        return cleaned[:2]

    def _fallback_items(
        self,
        messages: list[dict[str, str]],
        memories: list[MemoryItem],
        existing: list[StoryItem],
    ) -> list[dict[str, Any]]:
        existing_labels = {item.label for item in existing}
        results: list[dict[str, Any]] = []
        for memory in memories:
            if any(word in memory.content for word in ["樱花", "一起", "下次", "继续"]):
                label = "未完成的共同话题"
                if label not in existing_labels:
                    results.append({
                        "kind": "open_thread",
                        "label": label,
                        "content": f"{memory.content.rstrip('。')}，可以作为后续剧情的伏笔。",
                        "evidence": memory.content,
                        "evidence_level": "explicit",
                        "status": "seed",
                        "source_message_ids": [memory.source_message_id] if memory.source_message_id else [],
                    })
                    break
        user_messages = [item for item in messages if item.get("role") == "user"]
        assistant_messages = [item for item in messages if item.get("role") == "assistant"]
        if user_messages and assistant_messages and "轻柔开口" not in existing_labels:
            results.append({
                "kind": "story_beat",
                "label": "轻柔开口",
                "content": "一次普通问候和温和回应，可以作为两人关系重新靠近的开场。",
                "evidence": user_messages[-1]["content"],
                "evidence_level": "inferred",
                "status": "active",
                "source_message_ids": [user_messages[-1].get("id", "")],
            })
        return results[:2]

    def _row_to_item(self, row: Any) -> StoryItem:
        try:
            source_ids = json.loads(row["source_message_ids_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            source_ids = []
        return StoryItem(
            id=row["id"],
            kind=row["kind"],
            label=row["label"],
            content=row["content"],
            evidence=row["evidence"],
            evidence_level=row["evidence_level"],
            status=row["status"],
            source_message_ids=source_ids,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
