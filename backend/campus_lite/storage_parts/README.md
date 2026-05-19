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
- `common.py`：数据库路径、通用异常、时间函数。
- `characters.py`：角色卡持久化、角色关系 bond。
- `sessions.py`：visitor、session、message、prompt slots、角色即时状态。
- `memories.py`：记忆增删改查、scope、embedding 候选。
- `stories.py`：聊天故事条目。
- `novel_projects.py`：小说项目和素材。
- `novel_chapters.py`：小说章节、草稿保存、active version 创建、scene card 清洗。
- `novel_versions.py`：章节版本、规划快照、可信 state delta、恢复和删除。

## JSON 保存规则

- 写库前必须确认 JSON 可序列化。
- 不允许使用 `json.dumps(... )[:N]` 这种硬截断。
- 超过字段上限时抛出明确错误，让上层返回清楚失败原因。
- `planning_snapshot` 只保存规划字段，不保存运行态。
- `state_delta` 只保存可信版本对 Novel State 的影响。

## 修改原则

- 新表或新列先放 `base.py` schema，再在对应 mixin 提供操作。
- 事务性章节保存优先放在存储层原子方法里，避免前端或路由层做半同步。
- 版本语义相关修改必须同时考虑恢复、删除、列表展示和 Novel State 重建。
