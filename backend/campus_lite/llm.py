from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .schemas import CharacterCard, MemoryItem, MemoryType


class LlmClient:
    def __init__(self) -> None:
        self.provider = self._select_provider()
        self.embedding_provider = self._select_embedding_provider()

    def configured(self) -> bool:
        return self.provider is not None

    def embedding_configured(self) -> bool:
        return self.embedding_provider is not None

    def embedding_provider_name(self) -> str | None:
        if not self.embedding_provider:
            return None
        return f"{self.embedding_provider['name']}:{self.embedding_provider['model']}"

    def memory_extraction_system_prompt(self) -> str:
        return (
            "你是保守但不健忘的聊天记忆抽取器。抽取关于“用户”的、未来可复用的事实、偏好、状态、承诺、关系进展，"
            "也可以保留对接下来几轮有帮助的短期上下文。"
            "长期记忆要严格，短期 session 上下文要宽松。"
            "stable_user_info、user_preference、relationship_progress 不要保存助手单方面说了什么、问了什么、建议了什么。"
            "open_thread、recent_emotion 属于 session 上下文，可以保存对接下来几轮有用的对话状态、临时话题、地点建议、待确认事项或用户正在回应的助手建议。"
            "如果用户没有明确表达可复用信息，输出 []。只输出 JSON 数组，不要解释。"
            "\n\nmemory_type 只能是："
            "\n- stable_user_info：稳定身份、长期背景、长期习惯，例如专业、常住地、长期作息。"
            "\n- user_preference：用户明确喜欢/不喜欢/偏好的互动方式或事物。"
            "\n- open_thread：session 级上下文。可以记录之后要继续、要做、要回来看、还没完成的话题，也可以记录接下来几轮需要承接的临时上下文。"
            "\n- recent_emotion：session 级上下文。记录用户当前或最近的情绪状态，也可记录会影响接下来几轮语气的短期状态。"
            "\n- relationship_progress：用户和当前角色之间明确发生的关系变化、信任、边界或承诺。"
            "\n\nconfidence 评分："
            "\n- 0.90-1.00：用户直接、明确、无歧义地说出。"
            "\n- 0.70-0.89：用户表达较明确，但有一点语境依赖。"
            "\n- 0.40-0.69：只是弱暗示或需要推断；只有对接下来几轮很有帮助时才保存。"
            "\n- 0.00-0.39：不可靠，不要输出。"
            "\n\nimportance 评分："
            "\n- 0.85-1.00：长期强影响，未来多次对话都应优先参考，例如强偏好、重要边界、长期身份。"
            "\n- 0.65-0.84：中高价值，相关话题应召回，例如兴趣偏好、仍要继续的计划。"
            "\n- 0.35-0.64：session 短期上下文有用，只影响接下来几轮，例如今天的情绪、临时安排、地点建议、刚形成的待续话题。"
            "\n- 0.00-0.34：完全无承接价值的一次性闲聊或普通寒暄，不要输出。"
            "\n\n输出要求："
            "\n- 每项包含 memory_type, content, confidence, importance。"
            "\n- 对 global/character 价值的内容，content 必须以用户为主体。"
            "\n- 对 session 上下文，content 可以写成“当前会话正在讨论/待确认/刚提到...”，允许保留必要上下文。"
            "\n- 可保存的记忆 importance 通常不要低于 0.35；低于 0.35 的内容直接不输出。"
            "\n- 最多输出 5 条。宁可少记，也不要把普通流水账当长期记忆。"
        )

    def character_state_system_prompt(self) -> str:
        return (
            "你是校园陪伴聊天的轻量角色状态评分器。你只根据给定对话和证据判断当前互动状态，"
            "不要创作回复，不要推进剧情，不要把助手单方面建议当作关系进展。只输出 JSON 对象。"
            "\n\n你需要输出字段："
            "\n- mood：角色当前心境标签，短句。"
            "\n- tone：下一轮适合的语气倾向，短句。"
            "\n- distance：当前互动距离，短句。"
            "\n- focus：下一轮最该关注的互动重点。"
            "\n- energy：0 到 1，表示回复活跃度。"
            "\n- resonance_delta：本轮默契度变化，必须很小，建议 -0.03 到 0.05。"
            "\n- behavior：对象，包含 pace、initiative、warmth、memory_use、avoid。"
            "\n- evidence：一句话说明评分证据。"
            "\n\n评分 rubric："
            "\n- 用户接住角色、延续共同话题：resonance_delta 可小幅上升。"
            "\n- 用户表达偏好、边界、困惑：主要影响 tone/focus/behavior，不自动推高关系。"
            "\n- 用户只是在问技术、规则、实现：energy 可中低，resonance 通常保持稳定。"
            "\n- 助手单方面建议、寒暄、地点提议：不能单独算作关系进展。"
            "\n- 临时气氛：可以影响 mood/tone/energy，但不直接改变长期默契。"
            "\n- 明确负反馈或用户退让：resonance_delta 可小幅下降，同时降低主动程度。"
            "\n- 高置信共同记忆被自然使用并得到用户接续：resonance_delta 可小幅上升。"
            "\n\n行为映射要求："
            "\n- 不要在 behavior 里写分数，要写可执行表现。"
            "\n- behavior.pace 描述回复节奏。"
            "\n- behavior.initiative 描述主动程度和追问策略。"
            "\n- behavior.warmth 描述亲近感边界。"
            "\n- behavior.memory_use 描述如何使用共同记忆。"
            "\n- behavior.avoid 描述下一轮应避免什么。"
        )

    def character_bond_system_prompt(self) -> str:
        return (
            "你是校园陪伴聊天的长期角色关系档案评估器。你的任务是判断本轮是否值得更新“用户 × 当前角色”的长期关系档案。"
            "不要创作回复，不要推进剧情，不要把临时心情或助手单方面建议写成长期关系。只输出 JSON 对象。"
            "\n\n输出字段："
            "\n- should_update：布尔值。没有长期价值就 false。"
            "\n- familiarity_stage：熟悉阶段短标签，例如 初识、逐渐熟悉、稳定熟悉、形成默契。"
            "\n- resonance_base_delta：长期默契基线变化，必须非常小，建议 -0.01 到 0.02。"
            "\n- trust_notes：信任来源，只写用户明确接住、认可或持续形成的可靠互动。"
            "\n- boundary_notes：用户在这个角色面前表达过的边界或禁忌。"
            "\n- interaction_preferences：这个用户和这个角色之间稳定形成的互动偏好。"
            "\n- milestone：本轮如果有值得长期记录的关键节点，写一句；没有则空字符串。"
            "\n- evidence：一句话说明为什么更新或为什么不更新。"
            "\n\n更新 rubric："
            "\n- 用户多次或明确认可某种互动方式、解释方式、陪伴节奏，可以更新 interaction_preferences。"
            "\n- 用户明确表达边界、抗拒、喜欢或不喜欢当前角色的某种互动方式，可以更新 boundary_notes 或 trust_notes。"
            "\n- 用户和角色共同记忆被自然使用，并且用户接续或认可，可以小幅提高 resonance_base_delta。"
            "\n- 用户只是问技术、规则、实现，通常 should_update=false；除非用户表达了长期互动偏好。"
            "\n- 助手单方面建议、寒暄、地点提议、动作描写，不能单独作为长期成长依据。"
            "\n- 临时情绪和本轮状态只影响 character_state，不应进入长期 bond，除非用户把它表述成长期偏好或边界。"
            "\n- 明确负反馈、被冒犯、用户后退，可以小幅降低 resonance_base_delta，并更新边界。"
            "\n\n保守原则：宁可不更新，也不要制造关系进展。"
        )

    def turn_analysis_system_prompt(self) -> str:
        return (
            "你是校园陪伴聊天的一体化后处理分析器。你只做结构化分析，不创作角色回复。"
            "一次性输出 JSON 对象，包含 state、bond、memories 三个字段，不要输出解释文字。"
            "\n\n顶层 JSON 结构必须是："
            "\n{"
            "\n  \"state\": {...},"
            "\n  \"bond\": {...},"
            "\n  \"memories\": [...]"
            "\n}"
            "\n\nstate 字段用于短期当前状态，必须包含："
            "\n- mood, tone, distance, focus, energy, resonance_delta, behavior, evidence。"
            "\n- behavior 必须包含 pace, initiative, warmth, memory_use, avoid。"
            "\n- energy 为 0 到 1；resonance_delta 必须很小，建议 -0.03 到 0.05。"
            "\n- 技术/规则/实现问题通常 energy 中低，resonance 通常保持稳定。"
            "\n- 用户表达偏好、边界、困惑时，主要改变 tone/focus/behavior，不自动推高关系。"
            "\n\nbond 字段用于长期用户×角色关系档案，必须包含："
            "\n- should_update, familiarity_stage, resonance_base_delta, trust_notes, boundary_notes, interaction_preferences, milestone, evidence。"
            "\n- 没有长期价值时 should_update=false，其他字段沿用旧档案或写空变化。"
            "\n- resonance_base_delta 必须非常小，建议 -0.01 到 0.02。"
            "\n- 用户只是问技术、规则、实现，通常 should_update=false；除非用户明确表达长期互动偏好。"
            "\n- 助手单方面建议、寒暄、地点提议、动作描写，不能作为长期成长依据。"
            "\n\nmemories 字段用于可复用记忆，输出 JSON 数组，最多 5 条。每条包含 memory_type, content, confidence, importance。"
            "\n- memory_type 只能是 stable_user_info, user_preference, open_thread, recent_emotion, relationship_progress。"
            "\n- stable_user_info/user_preference/relationship_progress 必须以用户明确表达为依据，不保存助手单方面说了什么。"
            "\n- open_thread/recent_emotion 是 session 上下文，可以保存接下来几轮有用的临时话题、待确认事项或短期情绪。"
            "\n- confidence: 0.90-1.00 用户直接明确；0.70-0.89 较明确；0.40-0.69 弱暗示但短期有用；低于 0.40 不输出。"
            "\n- importance: 0.85-1.00 长期强影响；0.65-0.84 中高价值；0.35-0.64 短期上下文；低于 0.35 不输出。"
            "\n\n共同原则：宁可少写，也不要制造关系进展、记忆或状态证据。不要把任何分数写给主回复模型；分数只服务结构化存储。"
        )

    async def chat_complete(self, messages: list[dict[str, str]]) -> str:
        if not self.provider:
            raise RuntimeError("No remote LLM provider configured")
        body = {
            "model": self.provider["model"],
            "temperature": 0.82,
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {self.provider['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = self.provider["timeout_ms"] / 1000
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.provider['base_url'].rstrip('/')}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()

    async def extract_memories(self, user_message: str, assistant_reply: str) -> list[dict[str, Any]]:
        if not self.provider:
            return []
        system = self.memory_extraction_system_prompt()
        user = f"用户消息：{user_message}\n角色回复：{assistant_reply}"
        try:
            text = await self.chat_complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            return self._parse_memory_json(text)
        except Exception:
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
            ])
            return self._parse_state_json(text)
        except Exception:
            return None

    async def score_character_bond(
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
                {"role": "system", "content": self.character_bond_system_prompt()},
                {"role": "user", "content": user},
            ])
            return self._parse_bond_json(text)
        except Exception:
            return None

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
            return self._parse_turn_analysis_json(text)
        except Exception:
            return {"state": None, "bond": None, "memories": []}

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.strip() for text in texts if text and text.strip()]
        if not clean_texts or not self.embedding_provider:
            return []
        body = {
            "model": self.embedding_provider["model"],
            "input": clean_texts,
        }
        headers = {
            "Authorization": f"Bearer {self.embedding_provider['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = self.embedding_provider["timeout_ms"] / 1000
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.embedding_provider['base_url'].rstrip('/')}/embeddings",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
            vectors = [item["embedding"] for item in sorted(payload.get("data", []), key=lambda item: item.get("index", 0))]
            return [[float(value) for value in vector] for vector in vectors]
        except Exception:
            return []

    def mock_reply(self, character: CharacterCard, user_message: str, recalled: list[str]) -> str:
        message = user_message.strip()
        voice = character.voice or {}
        openings = voice.get("openings") or ["嗯。"]
        first = openings[abs(hash(message)) % len(openings)]
        if "记得" in message or "还记得" in message:
            if recalled:
                return f"{first} 我记得，{recalled[0]}。不是把它当成资料存着，是你说过以后，我会把它放在心上。"
            return f"{first} 我会认真记你说过的话。现在还没有太多旧事可翻，但这一句我会从这里接住。"
        if "累" in message or "压力" in message or "难受" in message:
            return f"{first} 先别急着把状态撑得很好。你可以把最重的那一点先放到我这里，我们慢慢说。"
        if "喜欢" in message or "想你" in message:
            return f"{first} 这句话我听见了，而且不会装作只是普通闲聊。你可以再靠近一点，我会用我的方式接住。"
        if "?" in message or "？" in message or "吗" in message:
            return f"{first} 我先认真回答你：这件事对我来说是值得听完的。你不用把问题整理得很漂亮，直接说也可以。"
        if recalled:
            return f"{first} 你刚才这句我接住了，也想起你之前说过：{recalled[0]}。我们不用急着推进什么，就顺着这一句聊下去。"
        return f"{first} 你这句我听到了。我们先不急着把它变成什么剧情，就从你现在最在意的地方继续。"

    def _select_provider(self) -> dict[str, Any] | None:
        configs = [
            {
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "base_url": os.getenv("DASHSCOPE_BASE_URL") or os.getenv("DASHSCOPE_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": os.getenv("DASHSCOPE_MODEL") or "qwen-plus-character",
                "timeout_ms": int(os.getenv("DASHSCOPE_TIMEOUT_MS") or "12000"),
            },
            {
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com",
                "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
                "timeout_ms": int(os.getenv("DEEPSEEK_TIMEOUT_MS") or "12000"),
            },
            {
                "api_key": os.getenv("ARK_API_KEY"),
                "base_url": os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3",
                "model": os.getenv("ARK_MODEL") or "",
                "timeout_ms": int(os.getenv("ARK_TIMEOUT_MS") or "12000"),
            },
        ]
        for config in configs:
            if config["api_key"] and config["model"]:
                return config
        return None

    def _select_embedding_provider(self) -> dict[str, Any] | None:
        configs = [
            {
                "name": "dashscope",
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "base_url": os.getenv("DASHSCOPE_EMBEDDING_BASE_URL")
                or os.getenv("DASHSCOPE_BASE_URL")
                or os.getenv("DASHSCOPE_BASE")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": os.getenv("DASHSCOPE_EMBEDDING_MODEL") or "text-embedding-v4",
                "timeout_ms": int(os.getenv("DASHSCOPE_EMBEDDING_TIMEOUT_MS") or os.getenv("DASHSCOPE_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "ark",
                "api_key": os.getenv("ARK_API_KEY"),
                "base_url": os.getenv("ARK_EMBEDDING_BASE_URL") or os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3",
                "model": os.getenv("ARK_EMBEDDING_MODEL") or "",
                "timeout_ms": int(os.getenv("ARK_EMBEDDING_TIMEOUT_MS") or os.getenv("ARK_TIMEOUT_MS") or "12000"),
            },
            {
                "name": "deepseek",
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": os.getenv("DEEPSEEK_EMBEDDING_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_BASE") or "https://api.deepseek.com",
                "model": os.getenv("DEEPSEEK_EMBEDDING_MODEL") or "",
                "timeout_ms": int(os.getenv("DEEPSEEK_EMBEDDING_TIMEOUT_MS") or os.getenv("DEEPSEEK_TIMEOUT_MS") or "12000"),
            },
        ]
        for config in configs:
            if config["api_key"] and config["model"]:
                return config
        return None

    def _parse_memory_json(self, text: str) -> list[dict[str, Any]]:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        raw = json.loads(match.group(0))
        return self._clean_memory_items(raw)

    def _clean_memory_items(self, raw: Any) -> list[dict[str, Any]]:
        allowed: set[MemoryType] = {
            "stable_user_info",
            "user_preference",
            "open_thread",
            "recent_emotion",
            "relationship_progress",
            "manual_note",
        }
        cleaned: list[dict[str, Any]] = []
        if not isinstance(raw, list):
            return []
        for item in raw:
            if not isinstance(item, dict):
                continue
            memory_type = item.get("memory_type")
            content = str(item.get("content") or "").strip()
            if memory_type not in allowed or not content:
                continue
            cleaned.append({
                "memory_type": memory_type,
                "content": content[:420],
                "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.6))),
                "importance": max(0.0, min(1.0, float(item.get("importance") or 0.5))),
            })
        return cleaned[:5]

    def _parse_state_json(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return None
        required = {"mood", "tone", "distance", "focus", "energy", "resonance_delta", "behavior", "evidence"}
        if not required.issubset(raw.keys()):
            return None
        if not isinstance(raw.get("behavior"), dict):
            return None
        return raw

    def _parse_bond_json(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return None
        if "should_update" not in raw or "evidence" not in raw:
            return None
        return raw

    def _parse_turn_analysis_json(self, text: str) -> dict[str, Any]:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"state": None, "bond": None, "memories": []}
        raw = json.loads(match.group(0))
        if not isinstance(raw, dict):
            return {"state": None, "bond": None, "memories": []}
        state = raw.get("state")
        bond = raw.get("bond")
        memories = self._clean_memory_items(raw.get("memories") or [])
        return {
            "state": state if self._valid_state_payload(state) else None,
            "bond": bond if self._valid_bond_payload(bond) else None,
            "memories": memories,
        }

    def _valid_state_payload(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required = {"mood", "tone", "distance", "focus", "energy", "resonance_delta", "behavior", "evidence"}
        return required.issubset(value.keys()) and isinstance(value.get("behavior"), dict)

    def _valid_bond_payload(self, value: Any) -> bool:
        return isinstance(value, dict) and "should_update" in value and "evidence" in value
