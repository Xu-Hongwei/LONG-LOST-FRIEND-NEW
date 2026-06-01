# Relationship 后端域

relationship 域维护聊天中的长期关系上下文：memory、短期 state、长期 bond、relationship events 和 turn 后处理。

## 文件

- `memory.py`：memory 列表、profile/recall、hybrid ranking、提取写入、embedding 存储和 pane 组装。
- `state.py`：当前 session 的角色即时状态和 behavior-facing prompt 文本。
- `bond.py`：`visitor_id + character_id` 的长期关系档案、事件 reducer、condition settling 和阶段迁移规则。
- `postprocess.py`：主回复返回后的分阶段分析任务。
- `service.py`：memory pane 读取、等待、冻结、manual note、memory 编辑和删除。

## 后处理流程

每次 chat send 返回后，后台按阶段处理：

1. `memory`：抽取可复用记忆，必要时更新 summary 和 embedding。
2. `state`：更新当前 session 的 mood、tone、focus、energy 和 behavior。
3. `bond`：抽取关系事件，再由本地规则更新长期阶段、trust、closeness、boundary safety、condition 和关系档案文本。

三个阶段独立记录 diagnostics；某一阶段超时或失败时整体状态可为 `partial`，已经成功的阶段不回滚。

## 数据边界

- global / character / session memory scope 不混用。
- state 属于当前 session。
- bond 属于 visitor 与角色组合，不属于单条消息。
- relationship event 记录明确证据和本地 delta，供 diagnostics、回放和阶段迁移使用。
- prompt 给主回复的是 behavior-facing state/bond 文本，不是原始评分。
- state 的 resonance 是短期互动值；bond 的 resonance baseline 是长期关系值，允许长期基线落后于当前会话热度。

## 结构化关系抽取

bond 不接受大模型直接输出关系分数或阶段。当前链路是：

1. 大模型只抽取 JSON：`{"events":[...]}`。
2. 事件只允许包含 `event_type`、`evidence_grade`、`evidence_text` 和来源信息。
3. 本地校验证据等级、证据文本、聊天上下文落点和重复事件。
4. 本地 reducer 按固定权重更新 `trust_level`、`closeness_level`、`boundary_safety`。
5. 本地根据历史事件、维度阈值和冻结状态判断阶段迁移。
6. 被采纳的事件写入 `relationship_events`，供 diagnostics、回放和后续阶段证据使用。

抽取器不得输出 `score`、`delta`、`stage`、`familiarity_stage`、`resonance` 或自由数值 `confidence`。

## 关系维度与阶段

新 bond 默认值：

| 字段 | 默认值 | 含义 |
| --- | ---: | --- |
| `trust_level` | `0.30` | 用户对当前角色的长期信任基线 |
| `closeness_level` | `0.20` | 长期靠近和共同关系感 |
| `boundary_safety` | `0.60` | 当前关系里边界是否被稳妥对待 |

`resonance_base` 继续表示长期默契基线，不等同于 `closeness_level`，也不是好感度。

阶段：

| `stage_code` | 展示文本 |
| --- | --- |
| `initial` | 初识 |
| `familiar` | 逐渐熟悉 |
| `trusted` | 建立信任 |
| `close` | 稳定靠近 |

condition 表示最近关系气候，不替代长期阶段：

| `condition_code` | 展示文本 | 触发 |
| --- | --- | --- |
| `steady` | 稳定 | 默认状态 |
| `warming` | 升温中 | 当前轮出现被采纳的正向事件，且关系未冻结 |
| `guarded` | 有保留 | 当前轮出现 `negative_feedback` |
| `strained` | 关系受损 | 当前轮出现 `boundary_violation` |
| `repairing` | 修复中 | 当前轮出现 `repair` |

`warming` 和 `repairing` 可在稳定无事件轮次后回到 `steady`；`guarded` 和 `strained` 需要明确 repair。

## 事件与证据等级

允许的关系事件：

- `shared_context`
- `preference_confirmed`
- `trust_signal`
- `emotional_disclosure`
- `boundary_respected`
- `negative_feedback`
- `boundary_violation`
- `repair`

证据等级：

| Evidence grade | 本地处理 |
| --- | --- |
| `explicit` | 采纳，映射 `local_confidence = 0.95` |
| `strong` | 采纳，映射 `local_confidence = 0.85` |
| `contextual` | v1 不计分，进入 diagnostics |
| `weak` | v1 不计分 |

额外采纳规则：

- 没有 `evidence_text` 的事件拒绝。
- `evidence_text` 必须能在聊天上下文中对上，不能只靠模型总结。
- `trust_signal` 必须来自用户明确表达，助手承诺或安慰自己不能算。
- 坏 JSON 按空事件处理；无关系价值的轮次应表现为 bond succeeded 但不更新。

## 权重、限幅与阶段迁移

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

阶段迁移由本地 reducer 判断：

- `initial -> familiar`：trust 和 closeness 达阈值，历史中至少 2 个被采纳的正向事件。
- `familiar -> trusted`：trust 和 boundary safety 达阈值，历史中存在 `trust_signal` 或 `boundary_respected`。
- `trusted -> close`：三维都达阈值，最近事件稳定正向，且没有未修复冻结。

v1 不自动降级阶段；负向事件通过三维值、condition 和 `progression_frozen` 表达。

## Diagnostics

bond diagnostics 应能说明：

- 抽取到多少事件。
- 采纳和拒绝了多少事件。
- 拒绝原因，例如证据等级、上下文不匹配或重复证据。
- 本轮 `applied_delta`。
- 阶段和 condition 是否变化。
- 是否处于 `progression_frozen`。

前端只展示阶段计数和 reducer 变化；事件 payload 保持在后端 diagnostics 和 `relationship_events` 中。

## 修改原则

- memory 写入保持保守，避免把一次性推断写成长久事实。
- state 调整短期互动节奏；bond 只接受长期价值变化。
- 大模型只抽取关系事件和证据等级；分数、限幅和阶段迁移由本地 reducer 决定。
- stage diagnostics 在 `postprocess.py`，远程分析调用和每阶段 timeout 在 `llm_parts/analysis.py`，不要把排错入口混在一起。
- 修改 memory recall 时同时检查 pane diagnostics、prompt assembly 和存储候选来源。
