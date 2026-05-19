from __future__ import annotations

from ..schemas import CharacterCard


class LlmMockMixin:
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
