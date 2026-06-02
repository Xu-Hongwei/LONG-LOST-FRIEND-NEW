# LLM 层说明

LLM 组合入口是 `backend/campus_lite/llm.py`，具体能力拆在当前目录。业务代码不直接写 provider 请求细节。

## 文件职责

- `providers.py`：选择聊天和 embedding provider，读取 LLM Router、DashScope、DeepSeek、ARK 相关环境变量。
- `chat.py`：统一 chat completion 请求。
- `embeddings.py`：embedding 配置和文本向量化。
- `prompts.py`：聊天后处理需要的系统 prompt，如记忆抽取、角色状态、关系、turn analysis。
- `analysis.py`：记忆抽取、角色状态评分、关系事件抽取、turn analysis、角色卡 AI 草稿。
- `parsing.py`：LLM JSON 解析、角色草稿 payload 清洗和字段规范化。
- `mock.py`：无远程 LLM 或调用失败时的本地角色化回复。

## Provider 顺序

聊天 provider 读取环境变量后选择可用配置：

1. `LLM_ROUTER_API_KEY` / `LLM_ROUTER_BASE_URL` / `LLM_ROUTER_MODEL`
2. `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `DASHSCOPE_MODEL`
3. `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`
4. `ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL`

`LLM_ROUTER_*` 配置存在时优先级最高，适合把聊天、关系分析、角色草稿和小说生成统一接到一个 OpenAI-compatible gateway。

Embedding 也走 provider 层。未配置或失败时，记忆召回退回 SQLite FTS 和关键词排序。

## 远程 JSON 调用边界

当前多处远程能力要求返回 JSON：

- 角色工坊 AI Draft：返回标准 `character` JSON，支持补全润色和整卡重写。
- relationship bond：返回 `{"events":[...]}`，只抽取事件，不给分。
- Novel Project Draft：把一句话项目方向扩写为结构化项目草稿。
- Story Canvas：生成或滚动章节画布。
- Event Pool Delta：滚动画布前补充项目事件池候选，只输出结构化 add/update/retire，不输出分数。当前策略会把 `setting_profile` 降级为临时兜底；当 active 中兜底超过 3 条时，prompt 会要求补到 `replacement_needed` 条以上。
- Event Binding Sync：绑定事件后返回 `canvas_chapter_patch`、`scene_card_patch` 和 `sync_note`。
- Handoff / Novel State：章节完成后抽取交接单和可信状态 delta。
- Instruction Optimizer：只返回优化后的写作指令；会读取当前章节正文片段、事件契约、场景卡、handoff、Novel State 和 Continuity Ledger，但不直接生成正文。

本地代码必须校验远程 JSON、裁剪字段、保留 fallback，并避免把远程未验证结论直接写成长久事实。

## Timeout

主要 timeout 在对应域配置或 provider 配置里：

- `NOVEL_GENERATION_TIMEOUT_MS`
- `NOVEL_CANVAS_TIMEOUT_MS`
- `NOVEL_PLANNING_TIMEOUT_MS`
- `NOVEL_EVENT_BINDING_TIMEOUT_MS`
- `LLM_ROUTER_TIMEOUT_MS`
- `LLM_ROUTER_EMBEDDING_TIMEOUT_MS`

relationship 分阶段分析的 timeout 和 diagnostics 在 `analysis.py` 与 `postprocess.py` 协作处理。

## 修改原则

- 新 provider 放 `providers.py`，不要散落在业务服务里。
- 新通用 prompt 放 `prompts.py`；小说专用 prompt 放 novel 域自己的 prompt 文件。
- 新 JSON 解析规则放 `parsing.py` 或对应领域的 serialization/parsing 文件。
- mock 只能作为 fallback，不应写入未验证的长期记忆。
