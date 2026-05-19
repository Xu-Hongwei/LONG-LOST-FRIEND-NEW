# LLM 层说明

LLM 组合入口是 `backend/campus_lite/llm.py`，具体能力拆在当前目录。

## 文件职责

- `providers.py`：选择聊天和 embedding provider，读取 DashScope、DeepSeek、ARK 相关环境变量。
- `chat.py`：统一 chat completion 请求。
- `embeddings.py`：embedding 配置和文本向量化。
- `prompts.py`：聊天后处理需要的系统 prompt，如记忆抽取、角色状态、关系、turn analysis。
- `analysis.py`：记忆抽取、角色状态评分、关系评分、turn analysis。
- `parsing.py`：LLM JSON 解析和 payload 清洗。
- `mock.py`：无远程 LLM 或调用失败时的本地角色化回复。

## Provider 顺序

聊天 provider 读取环境变量后选择可用配置。当前支持：

- DashScope
- DeepSeek
- ARK-compatible OpenAI chat APIs

Embedding 也走 provider 层。未配置或失败时，记忆召回会退回 SQLite FTS 和关键词排序。

## 修改原则

- 新 provider 放 `providers.py`，不要散落在业务服务里。
- 新 prompt 放 `prompts.py` 或小说自己的 prompt 文件，避免把长 prompt 写进路由。
- 新 JSON 解析规则放 `parsing.py` 或对应领域的 serialization/parsing 文件。
- mock 只能作为 fallback，不应写入未验证的长期记忆。
