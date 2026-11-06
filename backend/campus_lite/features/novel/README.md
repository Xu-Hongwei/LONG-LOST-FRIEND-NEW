# Novel 后端域

小说域由 `backend/campus_lite/novel.py` 组合 mixin。当前目录保存短篇、长篇项目、Story Canvas、项目事件池、章节生成、版本和 Novel State 逻辑。

## 核心数据边界

- `story_bible`：项目规则、已确认事实、关系边界和素材摘要。
- `story_canvas`：项目级规划，包括 acts、chapters、scenes、threads、event_pool 和 diagnostics。
- `event_pool`：项目事件候选库，维持 active 事件，记录来源、时间锚点、主题标记、评分原因和绑定状态。
- `event_contract`：当前章节真正采用的项目事件契约，写在 canvas chapter 和章节 scene card 中。
- `chapter.scene_card`：章节演出层，描述场景、人物欲望、张力、禁推事项和结尾 beat。
- `novel_versions.planning_snapshot_json`：章节版本快照，保存当前章节相关画布、场景卡、绑定事件和契约。
- `novel_state`：全局可信状态，只从可信章节版本或可信 handoff 重建。

禁止把 `generation_progress`、后台 `postprocess`、临时 audit 和 active delta 写进版本规划快照。

## 文件职责

- `routes.py`：小说 API。
- `project.py`、`project_draft.py`：项目创建、项目草稿、Story Bible、素材初始化和项目响应。
- `shortform.py`：Quick Draft 短篇/番外。
- `canvas.py`：画布构建和扩展主流程。
- `canvas_prompting.py`、`canvas_parsing.py`、`canvas_planning.py`：画布 prompt、解析和滚动规划。
- `canvas_defaults.py`、`canvas_access.py`、`canvas_sync.py`：画布默认值、读取和章节同步。
- `event_pool.py`：事件池 normalization、评分、排重、滚动补池和章节自动绑定。
- `event_pool_edit.py`：事件新增、编辑、退休、删除、手动绑定、`event_contract` 和绑定后远程结构化同步。
- `generation.py`：章节生成主流程。
- `generation_context.py`、`generation_beats.py`：正文生成上下文和 scene beats，读取当前事件契约。
- `generation_postprocess.py`：章节正文返回后的 handoff、Novel State 更新和后续画布滚动。
- `generation_response.py`、`generation_mock.py`：正文响应和 fallback。
- `optimizer.py`：章节生成指令优化，读取当前绑定事件、画布和场景卡。
- `audit.py`、`quality.py`：审稿、连续性和本地质量检查。
- `handoff.py`、`state.py`：章节交接与 Novel State。
- `serialization.py`：数据库 row、JSON 和 response model 转换。
- `config.py`：小说生成、画布、规划和事件绑定相关 timeout。

## 长篇生成层级

长篇生成按固定优先级协作：

1. 已写正文、章节版本和可信 Novel State。
2. 当前章节 canvas chapter。
3. 当前章节 `event_contract`。
4. 当前章节 scene card。
5. 优化后的生成指令。

项目事件池只是候选库；未绑定事件不直接影响正文。用户手动绑定或系统自动绑定后，事件才进入 `event_contract` 并参与画布、场景卡、scene beats 和生成指令。

## 项目事件池

事件池 active 目标数量是 10 条。事件可来自：

- `character_seed`：角色 `story_seed_pool` 转译出的默认故事味道。
- `project`：项目设定、Story Bible 和用户补充。
- `remote`：画布滚动时 LLM 返回的结构化候选。
- `setting_profile`：全局题材兜底。
- `manual`：用户手动新增。

事件字段包括地点、时间锚点、外部事件、钩子、意象、`use_mode`、source reason、主题/基调 tags、selection score 和 reasons。本地评分器负责主题适配、章节相关性、素材熟悉感、关系节奏、连续性和新鲜度；LLM 不直接输出最终分数。

滚动画布时，`setting_profile` 只作为临时兜底。后端会用 `event_pool_replacement_stats()` 计算当前 active 来源占比，目标是让 `setting_profile` 最多保留 3 条；超过时，事件池 delta prompt 会要求远程至少返回 `replacement_needed` 条具体 `add` 候选，最多可补到 10 条。diagnostics 会记录：

- `event_pool_replacement_needed`：本轮需要替换的兜底数量。
- `event_pool_delta_add_count`：远程实际返回的 add 数量。
- `event_pool_update_missing`：需要补池但远程没有返回 add。
- `event_pool_update_underfilled`：远程返回了 add，但数量少于 replacement_needed。

已经使用或绑定过的事件不应被普通滚动替换。章节完成后，绑定事件会从 active 进入 retired，并保留 `used_chapter_ids` / `used_summary`；替换和排重同时查看 active 与 retired，避免用过的事件回流。仍在规划章节上绑定的 active 事件也会因为 `bound_chapter_orders` 被保护。

事件池编辑 API：

- `POST /api/novel/projects/{project_id}/event-pool/events`
- `PATCH /api/novel/projects/{project_id}/event-pool/events/{event_id}`
- `POST /api/novel/projects/{project_id}/event-pool/events/{event_id}/retire`
- `DELETE /api/novel/projects/{project_id}/event-pool/events/{event_id}`
- `POST /api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding`

删除只允许未绑定、未使用事件；历史相关事件应先退休。

## Event Contract 与绑定模式

绑定事件时，后端先写入 `event_contract`，再按模式同步章节画布和场景卡：

- `strict`：必须采用地点、时间、外部事件和钩子，可覆盖核心自动字段。
- `guide`：默认模式，作为主要方向；首次同步会填充画布和场景卡，后续保护用户手写字段。
- `flavor`：只借地点、意象、气氛或钩子，不覆盖主事件。
- `free`：只记录灵感，不自动同步，也不参与自动绑定。

绑定后会尝试远程结构化同步。远程只返回 `canvas_chapter_patch`、`scene_card_patch` 和 `sync_note`；本地代码校验字段、清理事件池元信息、按 use mode 应用。远程失败、未配置或超时时保留本地同步结果，并在 `event_sync.remote_status` 写入原因。

远程初版画布返回的章节状态会被清洗。若远程把尚未写正文的规划章节标成 `complete` / `completed`，解析阶段会恢复为 `planned`，避免事件池自动绑定把它误判为已完成章节而跳过。真实已有版本的完成章节仍保留完成状态。

## 生成指令优化

`optimizer.py` 只生成写作指令，不生成正文。它直接读取当前章节编辑器里的正文片段：正文开头最多 900 字，正文结尾最多 900 字，并统计当前字数，用来判断是“续写同一章”还是“补足长度和动作链”。

前面章节不会整篇全文塞入优化 prompt。前文承接通过压缩上下文进入：

- 上一章 `chapter_handoff`。
- 截至上一章的可信 `Novel State`。
- `Continuity Ledger`。
- 已完成章节的摘要和开放线索。
- 当前章节的 canvas chapter、`event_contract`、scene card 和质量诊断。

如果某个前文细节没有进入 handoff、Novel State 或 ledger，优化指令未必能知道；后续若要更强连续性，应在 Context Activator 中按关键词和当前事件召回相关正文片段，而不是无条件塞入全本正文。

## 版本与回退

章节版本是不可变记录。保存正文版本时，`planning_snapshot_json` 记录当前章节相关规划：

- `canvas_chapter`
- 当前第一张 `canvas_scene`
- `scene_card`
- 当前绑定事件、事件分数和原因
- `event_contract` 与 `event_use_mode`

恢复版本时只恢复当前章节相关画布、场景卡和事件绑定，不整张覆盖项目画布，避免误删后续章节和用户后续编辑。恢复后继续沿用现有逻辑标记后续章节 affected 并重建可信 Novel State。

## 修改原则

- 画布结构改动先放 canvas 系列文件。
- 事件池评分、绑定和编辑改动优先放 `event_pool.py` / `event_pool_edit.py`。
- 章节生成主链路放 generation 系列文件。
- 版本和可信状态改动同时检查 `storage_parts/novel_versions.py`、`storage_parts/novel_chapters.py` 和本目录 `state.py`。
- manual/mock/canvas/system/restore 默认不污染 Novel State，除非有可信 handoff。

## 第九批：滚动规划耗时与连贯性（2026-11-06）

本轮查阅了以下开源项目的一手资料，借鉴方法并按现有接口实现，没有引入其代码或新依赖：

| 参考项目 | 已核实的方法 | 本项目的采用边界 |
| --- | --- | --- |
| [Pagekin（原 AI Novel Writer）](https://github.com/EthanYoQ/Pagekin) | 写作上下文包含本章蓝图、相关人物、世界观、前文摘要和上一章正文；规划与正文分阶段。 | 现有系统已有类似分层，本轮重点保护模型返回的章节计划，避免本地整理再次覆盖剧情字段。 |
| [Show Me The Story：history_compression.go](https://github.com/Nigh/show-me-the-story/blob/f790187373f23dbaaffa0838197e972a394960d3/internal/story/history_compression.go) | 仅对较久的已接受章节分组压缩，以来源哈希复用摘要，编辑后只重算受影响部分。 | 借鉴按条件执行昂贵任务的思路：事件候选充分时跳过独立事件池刷新。这里没有新增摘要缓存，不能把候选复用说成来源哈希缓存。 |
| [Show Me The Story：outline_helpers.go](https://github.com/Nigh/show-me-the-story/blob/f790187373f23dbaaffa0838197e972a394960d3/internal/story/outline_helpers.go) | 用本地规则检查章节大纲长度，并约束场景、冲突、转折、人物和结尾。 | 加强有序章节解析与计划保存检查，不为每次本地整理增加额外审稿请求。 |
| [DOC](https://github.com/yangkevin2/doc-story-generation) | 通过细化大纲和生成控制提升大纲遵循；更强控制及候选搜索也有速度代价。 | 保留有序计划的思路适用；逐 token 控制器不适合直接接入当前托管聊天接口，本轮不引入。 |

### 当前行为

- 滚动规划先检查事件池：通用兜底数量超过既有阈值、候选已用完，或未被本地规则阻止的具体候选不足以覆盖规划章数时，仍先远程补充事件池；否则直接请求章节画布。规划请求仍可返回事件增量。
- 保留有效且不重复的显式事件绑定，不再仅因另一个候选分数更高就替换它。模型没有给出事件编号时，不继承兜底章节的编号；只有事件文本能明确匹配章节计划时才自动绑定。无法本地确认的改写保留为未绑定计划，可由作者后续绑定。
- 自动同步事件契约只补空字段，保留已有目标、动作链和场景；作者主动选择严格绑定时仍可覆盖相应字段。
- 模型数组顺序与唯一正整数 `chapter_order` 不一致时，先按明确编号排序，再映射章节和场景。提示词区分候选事件、未来计划和已发生事实，并要求前提先于后果。
- 画布诊断新增 `event_pool_refresh`、`timings_ms`、`remote_call_count`、`input_characters`，记录复用原因、远程阶段耗时和输入字符数。字符数不是 token 数，耗时不含最终数据库合并写入。原有项目修订检查继续保护模型等待期间的保存和恢复。

### 验证与限制

新增 11 项离线检查，覆盖候选复用、必要刷新、刷新失败、并发修改、事件评分重排、模型编号缺失、乱序数组、自动同步（含意象模式）和手动严格绑定。使用第八批的虚构小说数据库副本做一次 DashScope 真调用：规划两章，7 条具体候选可用，1 次请求，端到端约 34.2 秒。原业务数据库和已写第一章正文均未改变。

随后对本次模型响应做离线重放，确认所有已返回的目标、外部事件、阻碍、选择及钩子保持一致；模型漏写编号的两章不再被绑定到不相关事件。旧版本的独立副本能复现对应失败。记录位于被忽略的 `runtime/stage9/`，真实调用和录制响应重放分别记录，重放耗时不能当作模型速度。

最终检查通过：184 项后端测试、32 项前端测试、类型检查、生产构建及仓库忽略文件检查。

这里只能确认候选充分时少一次模型请求，单次 34.2 秒样本不能换算为稳定加速比例。首次建立事件池仍可能需要两次串行请求；正文生成、审稿和交接流程未删减。模型自行生成的语义矛盾仍可能存在，明确编号和文本匹配检查不能替代文学与因果审稿。后续可独立评估上下文预算、逐阶段取消，以及带来源与版本校验的摘要缓存。
