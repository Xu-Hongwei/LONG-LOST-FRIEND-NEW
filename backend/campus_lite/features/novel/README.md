# 小说工作台说明

小说功能由 `backend/campus_lite/novel.py` 组合，当前目录只放小说领域逻辑。

## 核心数据边界

- `story_canvas`：全局规划，只保存项目级结构，如 acts、chapters、scenes、threads、source material ids。
- `chapter.scene_card`：章节规划和当前章节运行态。画布可以提供默认值，但用户已编辑的章节字段优先。
- `novel_versions`：不可变正文版本。正文、规划快照、可信状态 delta、来源都应作为版本事实保留。
- `novel_state`：全局可信状态，只从可信章节版本或可信 handoff 重建。

禁止把 `generation_progress`、`postprocess`、临时 audit、active delta 等运行态写进版本规划快照。

## 文件职责

- `routes.py`：小说 API 路由。
- `project.py`：项目创建、Story Bible、素材初始化、项目响应组装。
- `shortform.py`：快速短篇/番外生成。
- `canvas.py`：画布构建和扩展主流程。
- `canvas_prompting.py`：画布 prompt 和 source 文本。
- `canvas_parsing.py`：画布 LLM 响应解析和规整。
- `canvas_planning.py`：画布扩展、合并、压缩和完成章节回写。
- `canvas_defaults.py`：默认画布和默认场景。
- `canvas_access.py`：读取画布里的章节、场景、outline。
- `canvas_sync.py`：画布到章节 scene card 的同步，保护用户已编辑字段。
- `generation.py`：章节生成主流程和 postprocess 入口。
- `generation_response.py`：章节正文 prompt 和响应解析。
- `generation_beats.py`：scene beats、历史章节、Novel State、handoff 上下文。
- `generation_context.py`：章节 source、scene card、默认 scene card。
- `generation_mock.py`：无 LLM 时的章节 mock。
- `optimizer.py`：章节生成指令优化。
- `quality.py`：连续性和本地质量检查。
- `audit.py`：章节审稿、检查清单和必要改写。
- `handoff.py`：章节交接信息生成与清洗。
- `state.py`：Novel State 更新、重建、边界标记。
- `serialization.py`：数据库 row 到 response model 的转换、JSON 修复。
- `config.py`：小说功能的环境配置辅助。

## 主要流程

1. 创建项目：`project.py` 生成 Story Bible、默认 Novel State、素材和初始章节。
2. 构建画布：`canvas.py` 调用 LLM 或默认逻辑，解析后同步到章节。
3. 保存章节草稿：推荐走 `/api/novel/chapters/{chapter_id}/draft`，后端一次性同步画布片段、更新章节、创建版本、标记边界。
4. 生成章节：`generation.py` 取项目、章节、画布、历史章节、Novel State 和 handoff，生成正文、审稿、版本和状态 delta。
5. 恢复版本：恢复正文和规划快照，不恢复旧进度、postprocess 和临时审稿态，然后标记后续章节受影响并重建 Novel State。

## 修改原则

- 与画布结构有关的逻辑放 canvas 系列文件。
- 与章节生成有关的逻辑放 generation 系列文件。
- 与版本不可变、状态可信重建有关的逻辑要同时检查 `storage_parts/novel_versions.py`、`storage_parts/novel_chapters.py` 和 `features/novel/state.py`。
- manual/mock/canvas/system/restore 默认不污染 Novel State，除非明确有可信 handoff。
