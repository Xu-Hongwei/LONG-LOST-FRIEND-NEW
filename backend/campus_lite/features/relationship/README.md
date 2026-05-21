# Relationship 后端域

relationship 域维护聊天中的长期关系上下文：memory、短期 state、长期 bond 和 turn 后处理。

## 文件

- `memory.py`：memory 列表、profile/recall、hybrid ranking、提取写入、embedding 存储和 pane 组装。
- `state.py`：当前 session 的角色即时状态和 behavior-facing prompt 文本。
- `bond.py`：`visitor_id + character_id` 的长期关系档案。
- `postprocess.py`：主回复返回后的分阶段分析任务。
- `service.py`：memory pane 读取、等待、冻结、manual note、memory 编辑和删除。

## 后处理

每次 chat send 返回后，后台按阶段处理：

1. `memory`：抽取可复用记忆、必要时更新 summary 和 embedding。
2. `state`：更新当前 session 的 mood、tone、focus、energy 和 behavior。
3. `bond`：更新长期 familiarity、trust、boundary、interaction preference 和 milestone。

三个阶段独立记录 diagnostics；某一阶段超时或失败时整体状态可为 `partial`，已经成功的阶段不回滚。

## 数据边界

- global / character / session memory scope 不混用。
- state 属于当前 session。
- bond 属于 visitor 与角色组合，不属于单条消息。
- prompt 里给主回复的是 behavior-facing state/bond 文本，不是原始评分。
- state 的 resonance 是短期互动值；bond 的 resonance baseline 是长期关系值，允许长期基线落后于当前会话热度。

## 修改原则

- memory 写入保持保守，避免把一次性推断写成长久事实。
- state 调整短期互动节奏；bond 只接受长期价值变化。
- stage diagnostics 在 `postprocess.py`，远程分析调用和每阶段 timeout 在 `llm_parts/analysis.py`，不要把排错入口混在一起。
- 修改 memory recall 时同时检查 pane diagnostics、prompt assembly 和存储候选来源。
