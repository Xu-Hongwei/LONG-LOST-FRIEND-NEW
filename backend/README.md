# 后端说明

后端使用 FastAPI 和 SQLite。入口是 `backend/run.py`，应用在 `campus_lite/api.py` 创建。

导入 `campus_lite.api` 或 `campus_lite.app` 不创建数据库。实际启动时调用
`create_app()`，测试则显式注入临时 `Storage` 和假模型。原有 `python backend/run.py`
启动方式保持可用。若直接使用 Uvicorn，请在 `backend` 目录运行：

```powershell
python -m uvicorn campus_lite.api:create_app --factory --host 127.0.0.1 --port 8766
```

不再提供导入时立即初始化的 `campus_lite.api:app` 全局对象。

## 离线测试

常规测试继承 `tests/test_support.py` 的 `OfflineTestCase`：每项测试清除模型服务
环境配置，只允许访问该测试临时目录内的 SQLite 库（或内存库），并拦截 HTTPX
真实网络传输。FastAPI TestClient 和显式 MockTransport 仍可使用。
即使业务兜底捕获了拦截异常，清理阶段仍会让测试失败。

模型选择测试可以在测试内临时设置假环境变量；不要使用机器上的真实密钥。
新增测试应遵循相同隔离方式。导入副作用回归测试使用独立 Python 进程验证。

```powershell
python -B -m unittest discover -s tests
```

## 组合入口

- `campus_lite/api.py`：创建 Storage、角色库、chat/relationship/novel 服务和 LLM，然后注册路由。
- `campus_lite/schemas.py`：请求和响应模型，包含角色卡、聊天、关系、小说和事件池相关类型。
- `campus_lite/storage.py` + `storage_parts/`：SQLite schema、迁移补列和 CRUD。
- `campus_lite/llm.py` + `llm_parts/`：聊天补全、角色草稿、关系分析、小说远程 JSON、embedding 和 fallback。

`api.py` 只做组合和少量顶层角色 API。业务实现优先放 `campus_lite/features/<domain>/`。

## 业务域

- `features/chat/`：session、消息收发、Story Pane 读取/刷新和导出。
- `features/relationship/`：memory、state、bond、relationship events、memory 面板服务和聊天后处理。
- `features/novel/`：短篇、项目草稿、Story Bible、Story Canvas、项目事件池、章节生成、版本、审稿和 Novel State。

角色卡是横向能力：内置卡来自 `characters/*.json`，自建卡通过顶层 `/api/characters` 系列接口保存到 SQLite，并进入 chat、relationship 和 novel 链路。

## 兼容层

- `campus_lite/memory.py`
- `campus_lite/state.py`
- `campus_lite/bond.py`

这三个顶层文件保留兼容导出；真实实现位于 `features/relationship/`。新代码优先从 relationship 域导入。

## 横向服务

- `characters.py`：读取内置角色卡、管理自建角色卡、同步到 SQLite。
- `composer.py`：聊天 prompt slots 组装，默认身份是虚构聊天角色，不再把校园作为系统默认。
- `story.py`：从聊天、memory 和已有 story items 中提取剧情标签，供 Novel Studio 取材。
- `novel.py`：组合小说域 mixin。

## 公开接口边界

- 聊天和 relationship 仍使用既有 URL，不因为域拆分改变公开路径。
- 角色工坊使用 `/api/characters` 和 `/api/characters/draft`。
- 小说事件池编辑和绑定接口位于 `/api/novel/projects/{project_id}/event-pool/...` 与 `/api/novel/projects/{project_id}/chapters/{chapter_id}/event-pool-binding`。
- 新增字段优先兼容旧数据；旧 JSON 缺字段时由 schema、normalizer 或 response builder 补默认值。

## 修改检查点

- 不改公开 API 路径时，确认路由仍在原 URL 下返回原 response model。
- 新存储字段要同时覆盖 schema 初始化、迁移补列、response 序列化和恢复逻辑。
- 后台任务失败不能破坏已经返回给用户的消息、正文或版本。
- relationship 后处理是分阶段远程分析，memory/state/bond 诊断要能解释 `partial`。
- 小说版本快照不要混入生成进度、临时审稿和后台 postprocess 运行态。
- 事件池、画布、场景卡和生成指令的优先级是：已写正文/版本/Novel State > 当前章节画布 > 当前绑定事件契约 > 场景卡 > 生成指令。
