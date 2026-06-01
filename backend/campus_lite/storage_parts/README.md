# 存储层说明

存储层使用 SQLite。组合入口是 `backend/campus_lite/storage.py`，具体表和领域操作拆在当前目录。

## 组合入口

`Storage` 通过多继承组合这些 mixin：

- `StorageBaseMixin`
- `StorageCharacterMixin`
- `StorageSessionMixin`
- `StorageMemoryMixin`
- `StorageStoryMixin`
- `StorageNovelProjectMixin`
- `StorageNovelChapterMixin`
- `StorageNovelVersionMixin`

调用方只依赖 `Storage`，不要直接实例化具体 mixin。

## 文件职责

- `base.py`：数据库连接、schema 初始化、补列迁移。
- `common.py`：数据库路径、通用异常、时间函数和 JSON 字段长度限制。
- `characters.py`：角色卡持久化、角色关系 bond、relationship events。
- `sessions.py`：visitor、session、message、prompt slots、角色即时状态。
- `memories.py`：记忆增删改查、scope、embedding 候选。
- `stories.py`：聊天故事条目。
- `novel_projects.py`：小说项目、Story Bible、Story Canvas 和素材。
- `novel_chapters.py`：小说章节、草稿保存、active version 创建、scene card 清洗。
- `novel_versions.py`：章节版本、规划快照、可信 state delta、恢复和删除。

## JSON 保存规则

- 写库前必须确认 JSON 可序列化。
- 不允许使用 `json.dumps(... )[:N]` 这种硬截断。
- 超过字段上限时抛出明确错误，让上层返回清楚失败原因。
- `story_canvas_json` 保存项目级画布、事件池和 diagnostics。
- `scene_card_json` 保存当前章节的场景卡、事件契约和同步结果。
- `planning_snapshot_json` 只保存可回退的规划字段，不保存运行态。
- `state_delta_json` 只保存可信版本对 Novel State 的影响。

## 角色与关系存储

- 内置角色和自建角色最终都存成完整 card JSON。
- 自建角色通过 visitor owner 隔离。
- `character_bonds` 保存长期关系维度、阶段、condition 和文本档案。
- `relationship_events` 保存被采纳的关系事件、证据等级、本地 delta 和来源信息。

## 小说版本快照

章节版本保存时，`planning_snapshot_json` 应包含当前章相关规划：

- 章节正文、摘要和 scene card。
- 当前 canvas chapter。
- 当前第一张 canvas scene。
- 当前绑定事件和 `event_contract`。
- event score、reasons、penalties 和 `event_use_mode`。

恢复版本时只恢复当前章节相关画布/场景/事件绑定，不整张覆盖项目画布。

## 修改原则

- 新表或新列先放 `base.py` schema，再在对应 mixin 提供操作。
- 事务性章节保存优先放在存储层原子方法里，避免前端或路由层做半同步。
- 版本语义相关修改必须同时考虑恢复、删除、列表展示和 Novel State 重建。
- JSON 字段上限调整时同步测试，避免悄悄截断画布或版本快照。
