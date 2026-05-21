# Novel 后端域

小说域由 `backend/campus_lite/novel.py` 组合 mixin，当前目录保存短篇和长篇工作台逻辑。

## 核心数据边界

- `story_canvas`：项目级规划，如 acts、chapters、scenes、threads 和 source material ids。
- `chapter.scene_card`：章节规划和当前章节运行态，用户已编辑字段优先。
- `novel_versions`：不可变正文版本，保留正文、规划快照、可信 state delta 和来源。
- `novel_state`：全局可信状态，只从可信章节版本或可信 handoff 重建。

禁止把 `generation_progress`、后台 `postprocess`、临时 audit 和 active delta 写进版本规划快照。

## 文件职责

- `routes.py`：小说 API。
- `project.py`：项目创建、Story Bible、素材初始化和项目响应。
- `shortform.py`：Quick Draft 短篇/番外。
- `canvas.py`：画布构建和扩展主流程。
- `canvas_prompting.py`、`canvas_parsing.py`、`canvas_planning.py`：画布 prompt、解析、滚动规划。
- `canvas_defaults.py`、`canvas_access.py`、`canvas_sync.py`：画布默认值、读取和章节同步。
- `generation.py`：章节生成主流程。
- `generation_postprocess.py`：章节正文返回后的 handoff、Novel State 更新和后续画布滚动。
- `generation_beats.py`、`generation_context.py`、`generation_response.py`、`generation_mock.py`：章节生成上下文、正文响应和 fallback。
- `optimizer.py`：章节指令优化。
- `audit.py`、`quality.py`：审稿、连续性和本地质量检查。
- `handoff.py`、`state.py`：章节交接与 Novel State。
- `serialization.py`：数据库 row、JSON 和 response model 转换。
- `config.py`：小说生成相关超时配置。

## 主要流程

1. 项目创建把角色、消息、memory 和 story items 转成 Story Bible、素材、初始章节和默认状态。
2. 画布构建生成全局规划，再同步到章节 planning 字段。
3. 章节草稿保存走 `/api/novel/chapters/{chapter_id}/draft`，原子保存章节、规划片段和版本。
4. 章节生成读取画布、scene card、历史章节、Novel State 和 handoff，生成正文并审稿。
5. 正文返回后 postprocess 更新 handoff、可信状态和后续两章滚动画布。
6. 恢复版本只恢复正文和规划快照，再按可信规则重建后续状态。

## 修改原则

- 画布结构改动先放 canvas 系列文件。
- 章节生成主链路放 generation 系列文件。
- 版本和可信状态改动同时检查 `storage_parts/novel_versions.py`、`storage_parts/novel_chapters.py` 和本目录 `state.py`。
- manual/mock/canvas/system/restore 默认不污染 Novel State，除非有可信 handoff。
