# Campus Pulse Lite

Campus Pulse Lite 是一个本地优先的角色聊天、长期关系记忆和小说工坊实验项目。当前结构可以按“四块能力”理解：

- `characters`：角色卡和角色工坊，负责自建 AI 角色、题材类型和可转译故事素材。
- `chat`：会话、消息收发、prompt slots 和 Story Pane 入口。
- `relationship`：memory、短期 state、长期 bond、关系事件 reducer 和 postprocess diagnostics。
- `novel`：短篇草稿、长篇项目、Story Canvas、项目事件池、章节版本和 Novel State。

项目不是只服务校园题材。校园轻伴是内置模板之一，新的自建角色和小说项目可以使用现代日常、职场、武侠修仙、悬疑、科幻、奇幻旅伴等题材。

## Stack

- Backend: Python, FastAPI, SQLite
- Frontend: Vite, Vue 3, TypeScript
- LLM: OpenAI-compatible router first, then DashScope / DeepSeek / ARK-compatible providers
- Retrieval fallback: SQLite FTS plus keyword ranking; embeddings are optional

## Layout

```text
backend/
  campus_lite/
    api.py
    characters.py
    composer.py
    features/
      chat/
      novel/
      relationship/
    llm_parts/
    storage_parts/
characters/
  *.json
frontend/
  src/
    features/
      characters/
      chat/
      novel/
      relationship/
scripts/
data/
```

Detailed notes live beside each module. Start with `backend/README.md`, `frontend/README.md`, then the README inside the feature folder you are changing.

## Main Flows

1. Character Workshop creates or edits standard `CharacterCard` JSON, including `setting_type`, `setting_notes`, behavior policy, voice, and `story_seed_pool`.
2. Chat creates or restores a `visitor_id + character_id` session, recalls memory, composes prompt slots, saves the assistant reply, and returns quickly.
3. Relationship postprocess runs in background stages: memory, state, and bond. Bond uses remote JSON extraction only for relationship events; local reducer decides scores, stages, and freezing.
4. Story Pane turns chat into reusable story material. Novel Studio consumes chat, memory, story items, character seeds, and project settings.
5. Long-form novel generation first chooses or binds a project event, builds an `event_contract`, syncs chapter canvas and scene card, optimizes the generation instruction, then generates body text.

## Read Next

- Frontend domains: `frontend/README.md`, `frontend/src/features/README.md`
- Backend domains: `backend/README.md`
- Chat: `frontend/src/features/chat/README.md`, `backend/campus_lite/features/chat/README.md`
- Relationship: `frontend/src/features/relationship/README.md`, `backend/campus_lite/features/relationship/README.md`
- Novel: `frontend/src/features/novel/README.md`, `backend/campus_lite/features/novel/README.md`
- Character cards: `characters/README.md`, `frontend/src/features/characters/README.md`

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

The backend defaults to `http://127.0.0.1:8766`; the frontend dev server uses `http://127.0.0.1:5176`.

## Test

Backend tests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-backend.ps1
```

Frontend build:

```powershell
cd frontend
npm run build
```

## Environment

The provider layer checks chat providers in this order:

- `LLM_ROUTER_API_KEY`, `LLM_ROUTER_BASE_URL`, `LLM_ROUTER_MODEL`
- `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- `ARK_API_KEY`, `ARK_BASE_URL`, `ARK_MODEL`

When `LLM_ROUTER_*` is configured it wins over direct providers, so chat, story extraction, relationship analysis, character draft generation, and novel generation can share one OpenAI-compatible gateway. `/api/health` reports selected chat and embedding provider names.

Embedding is optional:

- `LLM_ROUTER_EMBEDDING_MODEL` uses the router embedding endpoint.
- `DASHSCOPE_EMBEDDING_MODEL` defaults to `text-embedding-v4` when `DASHSCOPE_API_KEY` is present.
- `ARK_EMBEDDING_MODEL` and `DEEPSEEK_EMBEDDING_MODEL` can be configured for compatible endpoints.

If no embedding provider works, memory recall continues with SQLite FTS and keyword ranking.

## Character Cards

Character cards follow a lightweight SillyTavern-inspired shape plus project-specific fields:

- Stable identity: `name`, `archetype`, `bio`, `personality`, `scenario`.
- Setting: `setting_type`, `setting_notes`.
- Conversation behavior: `speech_style`, `relationship_pace`, `opening_line`, `interaction_policy`, `anti_patterns`.
- Story support: `story_seed_pool` as a default translatable material pack, not fixed plot.
- Voice and visual: `voice`, `visual`, `mes_example`.

The backend maps character card sections into separate prompt slots. Novel Studio may translate `story_seed_pool` into project-specific events, but project state and chapter contracts still decide what happens in the current novel.

## Relationship Model

The app separates short-term state and long-term relationship growth:

- `sessions.character_state_json` stores current turn-level mood, tone, focus, energy, and behavior mapping.
- `character_bonds` stores durable `visitor_id + character_id` relationship context.
- `relationship_events` records accepted relationship events and local deltas.

Remote LLM extraction may return structured relationship events, but local code validates evidence, applies fixed weights, clamps dimensions, decides stage changes, and records diagnostics. Frontend panels show stage counts and reducer effects; raw event payloads remain in structured backend diagnostics and storage.

## Novel Model

Long-form projects use layered planning:

- Story Bible and materials preserve stable facts from chat and memory.
- Story Canvas stores acts, chapters, scenes, threads, and project event pool.
- Project event pool stores active candidates with score reasons, time anchors, theme markers, and use modes.
- A chapter `event_contract` records the event actually adopted by the current chapter.
- Scene card stages how the chapter plays out.
- Generation instruction compiles the current canvas, event contract, scene card, handoff, and Novel State.

Chapter versions are immutable. `planning_snapshot` stores the current chapter planning state, including canvas chapter, scene card, bound event, and event contract, so restoring a version can roll back the chapter plan without replacing the whole project canvas.
