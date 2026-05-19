# Campus Pulse Lite

Campus Pulse Lite is a lightweight experiment focused on stable character personas, useful memory, and explainable context assembly.

It intentionally leaves out the heavy story/score systems from the older `chat` project:

- no affection score judging
- no plot pressure
- no QuickJudge
- no local high-value-turn rules
- no complex scene director

## Stack

- Backend: Python, FastAPI, SQLite
- Frontend: Vite, Vue 3, TypeScript
- LLM providers: DashScope, DeepSeek, ARK-compatible OpenAI chat APIs
- Retrieval fallback: SQLite FTS plus lightweight keyword ranking

## Layout

```text
backend/
  campus_lite/
    api.py
    app.py
    characters.py
    composer.py
    features/
      chat/
      novel/
    llm_parts/
    llm.py
    memory.py
    schemas.py
    bond.py
    state.py
    storage_parts/
    storage.py
characters/
  lin_wanzhi.json
  xu_zhaomu.json
  shen_yan.json
  gu_yao.json
  zhou_ran.json
frontend/
  src/
    features/
      chat/
      novel/
      personalityTest/
```

Detailed notes live beside each module. Start with `backend/README.md`,
`frontend/README.md`, and the README inside the feature folder you are changing.

## Core Features and Logic

项目最外层按三个用户可见功能理解：聊天、小说工作台、人格测试。三者共享同一个 Vue 入口和同一个 FastAPI 后端，但运行状态和数据边界要分开。

### Chat

聊天是基础体验层，负责角色对话、记忆召回、角色状态、关系成长和故事素材沉淀。

主要入口：

- Frontend: `frontend/src/App.vue`
- Frontend API: `frontend/src/features/chat/api.ts`
- Backend routes: `backend/campus_lite/features/chat/routes.py`
- Backend service: `backend/campus_lite/features/chat/service.py`
- Shared context: `backend/campus_lite/composer.py`
- Memory logic: `backend/campus_lite/memory.py`

运行逻辑：

1. 前端先解析或创建 visitor，然后选择角色。
2. `POST /api/sessions` 创建或恢复 `visitor_id + character_id` 会话。
3. 用户发送消息时，`POST /api/chat/send` 先保存用户消息。
4. 后端召回记忆、读取近期消息、角色即时状态和长期关系。
5. `ContextComposer` 把角色卡、记忆、状态、关系和用户消息组装成 prompt slots。
6. `LlmClient` 调远程模型；无配置或失败时使用本地 mock 回复。
7. 后端立刻保存并返回 assistant 回复，避免用户等待后台分析。
8. 后台 turn analysis 再更新角色状态、关系和可用记忆。
9. 故事面板可以手动刷新，也会按当前 `session_id` 的用户消息数自动刷新，供小说工作台取材。

聊天模块的核心原则是：主回复要快，记忆写入要保守，后台分析不能阻塞用户可见回复。

### Novel Studio

小说工作台负责把聊天、记忆和故事素材转成短篇或长篇项目。它分为 Quick Draft 和 Project Mode。

主要入口：

- Frontend state and UI: `frontend/src/App.vue`
- Frontend API: `frontend/src/features/novel/api.ts`
- Frontend canvas helpers: `frontend/src/features/novel/canvas.ts`
- Backend routes: `backend/campus_lite/features/novel/routes.py`
- Backend service composition: `backend/campus_lite/novel.py`
- Backend feature modules: `backend/campus_lite/features/novel/`
- Storage: `backend/campus_lite/storage_parts/novel_projects.py`, `novel_chapters.py`, `novel_versions.py`

Quick Draft 运行逻辑：

1. 前端选择消息范围、目标长度、视角、形式和润色强度。
2. `POST /api/sessions/{session_id}/novel/generate` 读取聊天消息、角色卡、记忆、故事条目、角色状态和关系。
3. 后端生成短篇、番外、片段或第一章。
4. 远程 LLM 不可用时，使用本地 sample draft fallback。

Project Mode 运行逻辑：

1. `POST /api/sessions/{session_id}/novel/projects` 从当前会话创建长篇项目。
2. 项目保存 title、genre、tone、worldview、relationship setup、outline、Story Bible、素材库、章节和 Story Canvas。
3. `POST /api/novel/projects/{project_id}/canvas/build` 生成或重建全局 `story_canvas`。
4. Story Canvas 只管全局规划；章节的 `scene_card` 只管章节规划和运行态。
5. 编辑章节时推荐走 `PATCH /api/novel/chapters/{chapter_id}/draft`，后端一次性同步画布片段、更新章节、创建版本、标记边界。
6. `POST /api/novel/projects/{project_id}/generate-chapter` 读取画布、章节 scene card、历史章节、Novel State 和 handoff 后生成正文。
7. 章节生成会创建不可变版本，并把可信 handoff 写成 `state_delta`。
8. `novel_state` 只从可信版本重建；manual/mock/canvas/system/restore 默认不污染全局状态。
9. 恢复版本时只恢复正文和规划快照，不恢复旧进度、postprocess 和临时审稿状态。
10. 连续性检查通过 `POST /api/novel/projects/{project_id}/check` 执行。

小说模块的核心原则是四层分明：`story_canvas` 管全局规划，`chapter.scene_card` 管章节规划/运行态，`novel_versions` 管不可变版本，`novel_state` 从可信版本重建。

### Personality Test

人格测试是纯前端功能，用来完成恋爱人格问卷、展示结果画像，并导出结果图。

主要入口：

- UI: `frontend/src/App.vue`
- Data: `frontend/src/features/personalityTest/data.ts`
- Local storage: `frontend/src/features/personalityTest/storage.ts`
- Result image export: `frontend/src/features/personalityTest/resultImage.ts`
- Public images: `frontend/public/personality/`

运行逻辑：

1. 题目、维度、画像类型和文案全部来自 `data.ts`。
2. 用户选择性别后开始答题。
3. 每题答案按当前 visitor 保存到 localStorage。
4. localStorage key 带 visitor 和题库版本，避免不同访客或旧题库互相污染。
5. 全部题目完成前不展示最终结果。
6. 完成后按维度得分匹配画像，并展示对应男女版本图片和说明。
7. 导出图片时，`resultImage.ts` 临时隐藏按钮区域，用 `html2canvas` 截取结果弹窗为 PNG。

人格测试模块不写入后端数据库；它只依赖前端状态、本地存储和 public 图片资源。

## Run

One-shot local dev startup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Stop local dev servers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

Backend:

```powershell
python -m pip install -r backend\requirements.txt
python backend\run.py
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The backend defaults to `http://127.0.0.1:8766`.

Backend tests from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-backend.ps1
```

## Environment

The provider layer checks these variables in order:

- `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- `ARK_API_KEY`, `ARK_BASE_URL`, `ARK_MODEL`

Embedding uses the same provider layer when available:

- `DASHSCOPE_EMBEDDING_MODEL`, defaults to `text-embedding-v4` when `DASHSCOPE_API_KEY` is present.
- `ARK_EMBEDDING_MODEL` when using an ARK embedding endpoint.
- `DEEPSEEK_EMBEDDING_MODEL` only if you explicitly configure a compatible embedding endpoint.

If no provider is configured or a request fails, the app falls back to a local persona-shaped mock reply and does not write unverified LLM-extracted memories.

## Memory Model

Durable memory is scoped by type:

- `stable_user_info` and `user_preference` are global to the visitor and can be recalled across characters.
- `relationship_progress` is scoped to the visitor plus current character.
- `open_thread` and `recent_emotion` stay scoped to the current session.

Each memory stores `memory_scope`, `confidence`, `importance`, and a normalized key for conservative deduplication. Replies always receive a small profile set first, then query-relevant recall, and the frontend shows both the memory pane and the prompt stack used for the current turn.

Recall is hybrid:

- profile memories are always considered first
- SQLite FTS and keyword matching handle exact or near-exact references
- embeddings are stored in SQLite when the embedding provider works
- semantic cosine similarity is merged with keyword, scope, type, importance, and confidence scores
- if embedding fails, FTS and keyword recall continue normally

The frontend memory pane supports filtering by `global`, `character`, `session`, and last recall. Individual memories can be edited or deleted, including scope, type, content, and importance.

## Character Cards

Character JSON files follow a lightweight SillyTavern-inspired shape:

- `bio` / `personality` for durable identity and temperament
- `scenario` for the current conversational setting
- `mes_example` for style examples
- `creator_notes`, `system_prompt`, and `post_history_instructions` for behavior control
- `interaction_policy` for dynamic action density, action style, comfort style, question style, and memory style
- `anti_patterns` for things the role should avoid, such as repeated props or fixed gestures
- `voice` and `backstory` for concrete speech rhythm, habits, places, and boundaries

The backend maps these fields into separate persona context slots instead of merging everything into one prompt block.
Scene actions are intentionally not fixed in the character cards. The model may generate at most one light action per turn from the current context, and it can also use no action when direct dialogue is better.

## Character State and Bond

The app keeps short-term state and long-term growth separate:

- `sessions.character_state_json` stores the current turn-level state: mood, tone, focus, energy, behavior mapping, and the latest evidence.
- `character_bonds` stores durable `visitor_id + character_id` growth: familiarity stage, long-term resonance baseline, trust notes, boundaries, interaction preferences, and milestones.

The LLM scores both with explicit rubrics. Local code only validates JSON, clamps deltas, and persists the result. Main reply prompts do not receive raw scores. They receive behavior-facing slots:

- `persona.live_state` for current pacing and initiative.
- `persona.relationship_memory` for long-term relationship context.

Per chat turn, the backend now returns after the main reply call and queues one combined post-turn analysis task. The combined analysis returns `state`, `bond`, and `memories` in a single JSON payload, so state scoring, bond scoring, and memory extraction do not require three separate chat-completion calls or block the user-facing reply.

When a visitor reopens a character, `POST /api/sessions` restores the latest messages for that existing `visitor_id + character_id` session. The fixed character opening line is only used to initialize a truly empty session, so refreshes do not reset the visible chat back to the opening message.
