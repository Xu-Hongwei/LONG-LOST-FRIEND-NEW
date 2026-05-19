# 后端说明

后端是 FastAPI + SQLite。入口是 `backend/run.py`，应用对象在 `backend/campus_lite/api.py` 里创建。

## 入口与组合

- `campus_lite/app.py`：导出应用入口。
- `campus_lite/api.py`：创建 `Storage`、角色、记忆、状态、关系、小说、LLM 等服务，然后注册聊天和小说路由。
- `campus_lite/schemas.py`：集中放请求/响应模型，避免路由层和服务层各自定义一套结构。

`api.py` 不承载业务逻辑。新增功能时，优先在 `campus_lite/features/<domain>/routes.py` 注册路由，在对应 service/mixin 里实现流程。

## 领域服务

- `campus_lite/features/chat/`：聊天会话、消息发送、记忆面板、故事面板。
- `campus_lite/features/novel/`：短篇生成、长篇项目、画布、章节生成、版本、审稿、状态重建。
- `campus_lite/characters.py`：加载 `characters/*.json` 角色卡。
- `campus_lite/composer.py`：组装聊天 prompt slot。
- `campus_lite/memory.py`：记忆提取、召回、编辑的领域逻辑。
- `campus_lite/state.py`：角色当前状态。
- `campus_lite/bond.py`：角色关系成长状态。

## 横向基础设施

- `campus_lite/storage.py` + `campus_lite/storage_parts/`：SQLite schema 和 CRUD。
- `campus_lite/llm.py` + `campus_lite/llm_parts/`：远程 LLM、embedding、prompt、JSON 解析和 mock fallback。

## 修改检查点

- 新路由是否有明确 response model。
- 新存储字段是否在 schema 初始化和迁移补列里都处理。
- JSON 写入是否先校验可序列化和长度，不允许硬截断。
- 后台任务失败是否不会破坏用户已经保存的正文、版本和状态。
