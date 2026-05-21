# 后端说明

后端使用 FastAPI 和 SQLite。入口是 `backend/run.py`，应用在 `campus_lite/api.py` 创建。

## 组合入口

- `campus_lite/api.py`：创建 Storage、角色、relationship 服务依赖、novel 服务和 LLM，然后注册路由。
- `campus_lite/schemas.py`：请求和响应模型。
- `campus_lite/storage.py` + `storage_parts/`：SQLite schema、迁移补列和 CRUD。
- `campus_lite/llm.py` + `llm_parts/`：聊天补全、分析 prompt、embedding、JSON 解析和 mock fallback。

`api.py` 只做组合。业务实现优先放 `campus_lite/features/<domain>/`。

## 三域

- `features/chat/`：session、消息收发、story pane 读取/刷新和导出。
- `features/relationship/`：memory、state、bond、memory 面板服务和聊天后处理。
- `features/novel/`：短篇、项目、Story Canvas、章节生成、版本、审稿和 Novel State。

## 兼容层

- `campus_lite/memory.py`
- `campus_lite/state.py`
- `campus_lite/bond.py`

这三个顶层文件保留兼容导出；真实实现位于 `features/relationship/`。新代码优先从 relationship 域导入。

## 横向服务

- `characters.py`：读取 `characters/*.json` 角色卡。
- `composer.py`：聊天 prompt slots 组装。
- `story.py`：从聊天、memory 和已有 story items 中提取剧情标签，供 Novel Studio 取材。
- `novel.py`：组合小说域 mixin。

## 修改检查点

- 不改公开 API 路径时，先看路由是否仍在原 URL 下返回原 response model。
- 新存储字段要同时覆盖 schema 初始化和迁移补列。
- 后台任务失败不能破坏已经返回给用户的消息、正文或版本。
- relationship 后处理是分阶段远程分析，memory/state/bond 诊断要能解释 partial。
- 小说版本快照不要混入生成进度、临时审稿和后台 postprocess 运行态。
