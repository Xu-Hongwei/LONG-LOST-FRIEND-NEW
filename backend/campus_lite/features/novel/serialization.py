from __future__ import annotations

import json
import re
from typing import Any

from ...schemas import NovelChapter, NovelMaterial, NovelProjectResponse, NovelVersion
from ...storage import Storage


class NovelSerializationMixin:
    def _project_from_row(self, row: Any) -> NovelProjectResponse:
        storage = self._require_storage()
        return NovelProjectResponse(
            id=row["id"],
            session_id=row["session_id"],
            visitor_id=row["visitor_id"],
            character_id=row["character_id"],
            title=row["title"],
            genre=row["genre"],
            tone=row["tone"],
            protagonist=row["protagonist"],
            worldview=row["worldview"],
            relationship_setup=row["relationship_setup"],
            outline=row["outline"],
            story_bible=self._json_dict(row["story_bible_json"]),
            story_canvas=self._json_dict(row["story_canvas_json"] if "story_canvas_json" in row.keys() else "{}"),
            novel_state=self._json_dict(row["novel_state_json"] if "novel_state_json" in row.keys() else "{}"),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            materials=[self._material_from_row(item) for item in storage.list_novel_materials(row["id"])],
            chapters=[self._chapter_from_row(item) for item in storage.list_novel_chapters(row["id"])],
        )

    def _material_from_row(self, row: Any) -> NovelMaterial:
        return NovelMaterial(
            id=row["id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            category=row["category"],
            label=row["label"],
            content=row["content"],
            evidence_level=row["evidence_level"],
            created_at=row["created_at"],
        )

    def _chapter_from_row(self, row: Any, include_versions: bool = False) -> NovelChapter:
        storage = self._require_storage()
        versions = storage.list_novel_versions(row["id"])
        return NovelChapter(
            id=row["id"],
            project_id=row["project_id"],
            chapter_order=int(row["chapter_order"]),
            title=row["title"],
            goal=row["goal"],
            summary=row["summary"],
            body=row["body"],
            status=row["status"],
            scene_card=self._json_dict(row["scene_card_json"]),
            source_material_ids=self._json_list(row["source_material_ids_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version_count=len(versions),
            versions=[self._version_from_row(item) for item in versions] if include_versions else [],
        )

    def _version_from_row(self, row: Any) -> NovelVersion:
        return NovelVersion(
            id=row["id"],
            chapter_id=row["chapter_id"],
            version_type=row["version_type"],
            title=row["title"],
            body=row["body"],
            summary=row["summary"],
            source=row["source"],
            state_delta=self._json_dict(row["state_delta_json"] if "state_delta_json" in row.keys() else "{}"),
            planning_snapshot=self._json_dict(row["planning_snapshot_json"] if "planning_snapshot_json" in row.keys() else "{}"),
            created_at=row["created_at"],
        )

    def _json_dict(self, text: Any) -> dict[str, Any]:
        if isinstance(text, dict):
            return text
        try:
            parsed = json.loads(text or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _json_list(self, text: Any) -> list[str]:
        if isinstance(text, list):
            return [str(item) for item in text]
        try:
            parsed = json.loads(text or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    def _load_llm_json_object(self, text: str, label: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"No {label} JSON object found")
        raw = match.group(0).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as first_error:
            repaired = self._repair_llm_json(raw)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                decoder = json.JSONDecoder()
                for brace in [item.start() for item in re.finditer(r"\{", repaired)]:
                    try:
                        parsed, _ = decoder.raw_decode(repaired[brace:])
                        break
                    except json.JSONDecodeError:
                        continue
                else:
                    raise first_error
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} JSON payload is not an object")
        return parsed

    def _repair_llm_json(self, text: str) -> str:
        repaired = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        repaired = re.sub(r"```(?:json)?|```", "", repaired, flags=re.I)
        repaired = re.sub(r"^\s*//.*$", "", repaired, flags=re.M)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        repaired = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', repaired)
        return repaired.strip()

    def _coerce_int(self, value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
        if isinstance(value, bool):
            result = default
        elif isinstance(value, (int, float)):
            result = int(value)
        else:
            match = re.search(r"\d+", str(value or ""))
            result = int(match.group(0)) if match else default
        if minimum is not None:
            result = max(minimum, result)
        if maximum is not None:
            result = min(maximum, result)
        return result

    def _normalize_chapter_title(self, title: str, order: int) -> str:
        clean = str(title or "").strip()
        clean = re.sub(r"^第[一二三四五六七八九十百千万\d]+章[\s：:、.-]*", "", clean).strip()
        return (clean or "未命名章节")[:120]

    def _require_storage(self) -> Storage:
        if self.storage is None:
            raise RuntimeError("NovelService storage is required for project mode")
        return self.storage

