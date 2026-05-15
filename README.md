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
    llm.py
    memory.py
    schemas.py
    bond.py
    state.py
    storage.py
characters/
  lin_wanzhi.json
  xu_zhaomu.json
  shen_yan.json
  gu_yao.json
  zhou_ran.json
frontend/
  src/
```

## Run

One-shot local dev startup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1
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

Concat the above for a one-shot local dev startup:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1


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

## Novel Studio

The frontend includes a Novel Studio page with two tracks:

- Quick Draft keeps the original short-story flow for a short story, side story, vignette, or first chapter. It uses the selected message range plus the character card, memory pane, live state, and bond profile, and it can fall back to a local sample draft when no remote LLM is configured.
- Project Mode creates a lightweight long-form novel project from the active session. A project stores its title, genre, tone, worldview, relationship setup, editable outline, Story Bible, material library, chapters, and chapter versions. Chapters can be edited manually, generated or continued through the backend, restored from prior versions, exported as Markdown, and checked with a local continuity guard for internal wording, empty chapters, boundary risk, and seed/open-thread misuse.
