# Relationship 后端域

relationship 域维护聊天中的长期关系上下文：memory、短期 state、长期 bond 和 turn 后处理。

## 文件

- `memory.py`：memory 列表、profile/recall、hybrid ranking、提取写入、embedding 存储和 pane 组装。
- `state.py`：当前 session 的角色即时状态和 behavior-facing prompt 文本。
- `bond.py`：`visitor_id + character_id` 的长期关系档案、事件 reducer 和阶段迁移规则。
- `postprocess.py`：主回复返回后的分阶段分析任务。
- `service.py`：memory pane 读取、等待、冻结、manual note、memory 编辑和删除。

## 后处理

每次 chat send 返回后，后台按阶段处理：

1. `memory`：抽取可复用记忆、必要时更新 summary 和 embedding。
2. `state`：更新当前 session 的 mood、tone、focus、energy 和 behavior。
3. `bond`：抽取关系事件，再由本地规则更新长期阶段、trust、closeness、boundary safety 和关系档案文本。

三个阶段独立记录 diagnostics；某一阶段超时或失败时整体状态可为 `partial`，已经成功的阶段不回滚。

## 数据边界

- global / character / session memory scope 不混用。
- state 属于当前 session。
- bond 属于 visitor 与角色组合，不属于单条消息。
- relationship event 记录明确证据和本地 delta，供 diagnostics、回放和阶段迁移使用。
- prompt 里给主回复的是 behavior-facing state/bond 文本，不是原始评分。
- state 的 resonance 是短期互动值；bond 的 resonance baseline 是长期关系值，允许长期基线落后于当前会话热度。

## Bond 规则

### 流程边界

bond 不接受大模型直接输出关系分数或阶段。当前链路是：

1. 大模型只抽取关系事件：`event_type`、`evidence_grade`、`evidence_text`。
2. 本地校验证据等级、证据文本、聊天上下文落点和重复事件。
3. 本地 reducer 按固定权重更新 `trust_level`、`closeness_level`、`boundary_safety`。
4. 本地根据历史事件、维度阈值和冻结状态判断阶段迁移。
5. 被采纳的事件写入 `relationship_events`，供 diagnostics、回放和后续阶段证据使用。

事件抽取器不得输出 `score`、`delta`、`stage`、`familiarity_stage`、`resonance` 或自由数值 `confidence`。

### 关系维度、阶段与 condition

新 bond 默认值：

| 字段 | 默认值 | 含义 |
| --- | ---: | --- |
| `trust_level` | `0.30` | 用户对当前角色的长期信任基线 |
| `closeness_level` | `0.20` | 长期靠近和共同关系感 |
| `boundary_safety` | `0.60` | 当前关系里边界是否被稳妥对待 |

`resonance_base` 继续表示长期默契基线，不等同于 `closeness_level`，也不是好感度。

阶段表：

| `stage_code` | 展示文本 |
| --- | --- |
| `initial` | 初识 |
| `familiar` | 逐渐熟悉 |
| `trusted` | 建立信任 |
| `close` | 稳定靠近 |

长期阶段和最近关系状态分开维护。`stage_code` 回答“长期走到哪里”，`condition_code` 回答“最近这段关系现在舒服不舒服”。

condition 表：

| `condition_code` | 展示文本 | 触发 |
| --- | --- | --- |
| `steady` | 稳定 | 新 bond 默认状态 |
| `warming` | 升温中 | 当前轮出现被采纳的正向事件，且关系未冻结 |
| `guarded` | 有保留 | 当前轮出现 `negative_feedback` |
| `strained` | 关系受损 | 当前轮出现 `boundary_violation` |
| `repairing` | 修复中 | 当前轮出现 `repair` |

condition 只表达最近关系气候，不直接替代长期阶段。比如已经 `trusted` 的关系出现一次越界时，可以保持阶段为“建立信任”，同时 condition 变为“关系受损”。

### 事件与证据等级

允许的关系事件：

| Event | 用途 |
| --- | --- |
| `shared_context` | 用户承接共同经历、共同约定或明确共享上下文 |
| `preference_confirmed` | 用户确认与当前角色互动时的稳定偏好 |
| `trust_signal` | 用户明确表达信任、托付或认可角色可靠 |
| `emotional_disclosure` | 用户向角色披露有关系意义的情绪或脆弱信息 |
| `boundary_respected` | 边界被提出并在当前互动中被尊重 |
| `negative_feedback` | 用户明确表达失望、后退或拒绝当前互动方式 |
| `boundary_violation` | 出现明确越界、冒犯或用户指出边界被踩 |
| `repair` | 负向互动后用户明确接受修复、调整或重新达成边界共识 |

证据等级：

| Evidence grade | 本地处理 |
| --- | --- |
| `explicit` | 采纳，映射 `local_confidence = 0.95` |
| `strong` | 采纳，映射 `local_confidence = 0.85` |
| `contextual` | v1 不计分，记录到 diagnostics 的拒绝原因 |
| `weak` | v1 不计分 |

额外采纳规则：

- 没有 `evidence_text` 的事件拒绝。
- `evidence_text` 必须能在给定聊天上下文中对上，不能只靠模型总结。
- 模糊的“刚才那样也挺好”不足以作为 explicit `shared_context`。
- `trust_signal` 必须来自用户明确表达，助手承诺或安慰自己不能算。
- 坏 JSON 按空事件处理；无关系价值的轮次应表现为 bond succeeded 但不更新。

### 权重与限幅

事件权重：

| Event | Trust | Closeness | Boundary Safety |
| --- | ---: | ---: | ---: |
| `shared_context` | `+0.01` | `+0.02` | `0` |
| `preference_confirmed` | `+0.01` | `+0.01` | `+0.01` |
| `trust_signal` | `+0.04` | `+0.01` | `0` |
| `emotional_disclosure` | `+0.03` | `+0.03` | `0` |
| `boundary_respected` | `+0.02` | `0` | `+0.04` |
| `negative_feedback` | `-0.03` | `-0.02` | `-0.02` |
| `boundary_violation` | `-0.05` | `-0.03` | `-0.08` |
| `repair` | `+0.02` | `+0.01` | `+0.03` |

每轮限幅：

| Dimension | 负向下限 | 正向上限 |
| --- | ---: | ---: |
| `trust_level` | `-0.08` | `+0.05` |
| `closeness_level` | `-0.06` | `+0.05` |
| `boundary_safety` | `-0.10` | `+0.04` |

维度更新后统一 clamp 到 `[0, 1]`。

### 去重、阶段与修复

去重规则：

- 同一事件类型和同一证据重复时拒绝。
- 同一证据被抽成多种事件时，只保留优先级更高的事件。
- 当前优先级从高到低是：`boundary_violation`、`repair`、`boundary_respected`、`trust_signal`、`emotional_disclosure`、`preference_confirmed`、`shared_context`、`negative_feedback`。

阶段迁移：

- `initial -> familiar`
  - `trust_level >= 0.38`
  - `closeness_level >= 0.28`
  - 历史中至少有 2 个被采纳的正向事件
- `familiar -> trusted`
  - `trust_level >= 0.52`
  - `boundary_safety >= 0.62`
  - 历史中存在 `trust_signal` 或 `boundary_respected`
- `trusted -> close`
  - `trust_level >= 0.68`
  - `closeness_level >= 0.60`
  - `boundary_safety >= 0.68`
  - 最近 12 个事件里至少有 4 个正向事件
  - 这些正向事件至少来自 2 个 message source

冻结与修复：

- `negative_feedback` 或 `boundary_violation` 会冻结继续升级。
- `repair` 会解除冻结。
- v1 不自动降级阶段；负向事件通过三维值和冻结状态表达关系受损。
- condition 与阶段分离：普通负反馈进入 `guarded`，明确越界进入 `strained`，修复后进入 `repairing`，后续正向事件可重新进入 `warming`。

### 文本档案与 diagnostics

事件 reducer 还会更新 bond 文本字段：

- `trust_notes`：`trust_signal`、`emotional_disclosure`、`boundary_respected`、`repair`。
- `boundary_notes`：`boundary_respected`、`negative_feedback`、`boundary_violation`、`repair`。
- `interaction_preferences`：`preference_confirmed`。
- `milestones`：仅在阶段变化时追加阶段节点。

bond stage diagnostics 应至少能说明：

- 抽取到多少事件。
- 采纳和拒绝了多少事件。
- 拒绝原因，例如证据等级、上下文不匹配或重复证据。
- 本轮 `applied_delta`。
- 阶段是否变化。
- condition 是否变化。
- 是否处于 `progression_frozen`。

## 修改原则

- memory 写入保持保守，避免把一次性推断写成长久事实。
- state 调整短期互动节奏；bond 只接受长期价值变化。
- 大模型只抽取关系事件和证据等级；分数、限幅和阶段迁移由本地 reducer 决定。
- stage diagnostics 在 `postprocess.py`，远程分析调用和每阶段 timeout 在 `llm_parts/analysis.py`，不要把排错入口混在一起。
- 修改 memory recall 时同时检查 pane diagnostics、prompt assembly 和存储候选来源。
## Condition settling

`condition_code` is recent relationship weather, not a permanent stage.

- `warming` returns to `steady` after two consecutive postprocess turns with no accepted relationship event.
- `repairing` returns to `steady` after two consecutive stable turns without a new negative event or another `repair`.
- `guarded` and `strained` do not auto-settle; they stay visible until the reducer sees an explicit repair path.
- `character_bonds.condition_settle_turns` stores the tiny settling streak so a no-event turn can still be replayed and diagnosed.

Positive event extraction stays conservative:

- Scored evidence must be grounded in the user's chat text, not an assistant-only continuation.
- A plain acknowledgement, topic switch, short continuation, or schedule change is usually not a relationship event.
- `boundary_respected` needs an explicit boundary signal or an explicit user acknowledgement of the respected adjustment.
- `shared_context` needs a concrete shared fact, pact, or recalled event rather than a generic follow-up.

Bond diagnostics also keep event previews for the latest postprocess turn:

- `extracted_events` shows the relationship events returned by extraction.
- `accepted_events` shows the events that passed local validation and changed the reducer input.
- `rejected_events` shows rejected event type, evidence, and the local rejection reason.
- `backend/tests/fixtures/relationship_event_cases.json` is the calibration set for ordinary chat, technical questions, explicit relationship signals, weak atmosphere, boundary handling, and repair.

## Structured relationship extraction

- Relationship extraction requests JSON object mode from the remote chat provider.
- The extractor contract is `{"events":[...]}` and the empty result is `{"events":[]}`.
- The parser still accepts the older bare event array so old fixtures and mixed provider replies fail soft during the transition.
- The local frontend panel shows stage counts and reducer changes only; event payloads remain in backend diagnostics and `relationship_events`.
