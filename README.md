# Campus Pulse Lite

Campus Pulse Lite is a lightweight experiment focused on stable character personas, useful memory, and explainable context assembly.

It intentionally leaves out the heavier scoring and director machinery from the older `chat` project:

- no affection score judging
- no plot pressure
- no QuickJudge
- no local high-value-turn rules
- no complex scene director

## Stack

- Backend: Python, FastAPI, SQLite
- Frontend: Vite, Vue 3, TypeScript
- LLM providers: an OpenAI-compatible routing endpoint, DashScope, DeepSeek, or ARK-compatible OpenAI chat APIs
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
      relationship/
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
      relationship/
```

Detailed notes live beside each module. Start with `backend/README.md`,
`frontend/README.md`, and the README inside the feature folder you are changing.

## Domains

项目最外层按三个业务域理解。它们共享同一个 Vue 入口和同一个 FastAPI 后端，但状态和写入边界分开：

- `chat`：visitor、角色、session、消息收发、story pane 入口和 prompt composition。
- `relationship`：memory、当前 state、长期 bond、postprocess diagnostics 和恋爱人格测试。
- `novel`：剧情素材、Quick Draft、长篇项目、Story Canvas、章节、版本和 Novel State。

## Flow Sketch

1. Chat 创建或恢复 `visitor_id + character_id` session。
2. 用户消息先进入主回复链路：召回上下文、组装 prompt slots、保存 assistant 回复并立即返回前端。
3. Relationship postprocess 在后台分阶段处理 memory、state 和 bond，失败阶段只写 diagnostics。
4. Story Pane 把聊天沉淀成剧情素材，Novel Studio 再按短篇或长篇路径消费这些素材。

## Read Next

- Frontend composition and domain boundaries: `frontend/README.md`, `frontend/src/features/README.md`
- Backend composition and storage boundaries: `backend/README.md`, `backend/campus_lite/storage_parts/README.md`
- Chat details: `frontend/src/features/chat/README.md`, `backend/campus_lite/features/chat/README.md`
- Relationship details: `frontend/src/features/relationship/README.md`, `backend/campus_lite/features/relationship/README.md`
- Novel details: `frontend/src/features/novel/README.md`, `backend/campus_lite/features/novel/README.md`

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

The provider layer checks these chat variables in order:

- `LLM_ROUTER_API_KEY`, `LLM_ROUTER_BASE_URL`, `LLM_ROUTER_MODEL`
  - `LLM_ROUTER_MODEL` defaults to `auto`, so a gateway that accepts an automatic route name can be configured with only the key and base URL.
  - Set `LLM_ROUTER_MODEL` when the gateway expects a concrete model alias or route name.

- `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- `ARK_API_KEY`, `ARK_BASE_URL`, `ARK_MODEL`

When `LLM_ROUTER_*` is configured it wins over the direct chat providers, so chat, story, relationship analysis, and novel generation can all be routed by one OpenAI-compatible gateway without changing business code. `/api/health` reports the selected chat and embedding provider names.

Embedding uses the same provider layer when available:

- `LLM_ROUTER_EMBEDDING_MODEL` when the routing endpoint also exposes an OpenAI-compatible embeddings route. Optional `LLM_ROUTER_EMBEDDING_API_KEY`, `LLM_ROUTER_EMBEDDING_BASE_URL`, and `LLM_ROUTER_EMBEDDING_TIMEOUT_MS` override the chat router values.
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

The two visible resonance values intentionally mean different things:

- State `Live Resonance` is the current session's short-term interaction fit and can move after state scoring.
- Bond `Bond Baseline` is the slower `visitor_id + character_id` long-term relationship baseline and only moves after a worthwhile bond update.

They are not expected to match. A bond timeout or `should_update=false` can leave the long-term baseline behind a lively current session state.

Per chat turn, the backend returns after the main reply call and queues relationship postprocess work. The postprocess task runs `memory`, `state`, and `bond` as separate diagnostics stages, so a timeout in one stage can surface as `partial` without blocking the user-facing reply or discarding stages that already succeeded.

When a visitor reopens a character, `POST /api/sessions` restores the latest messages for that existing `visitor_id + character_id` session. The fixed character opening line is only used to initialize a truly empty session, so refreshes do not reset the visible chat back to the opening message.
