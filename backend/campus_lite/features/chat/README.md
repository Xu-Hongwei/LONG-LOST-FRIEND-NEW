# 聊天模块说明

聊天模块后端位于当前目录，前端接口位于 `frontend/src/features/chat/`。

## 后端文件

- `routes.py`：注册聊天相关 API。
- `service.py`：聊天主流程，包括创建会话、发送消息、后台分析、记忆面板、故事面板。

## 相关服务

- `CharacterStore`：从 `characters/*.json` 读取角色卡。
- `ContextComposer`：把角色、人设、记忆、状态、关系组装成 prompt slots。
- `MemoryService`：召回、抽取、编辑记忆。
- `CharacterStateService`：维护当前会话里的角色即时状态。
- `CharacterBondService`：维护 visitor + character 的长期关系。
- `StoryService`：维护从聊天里抽取出的故事条目。
- `LlmClient`：聊天补全、turn analysis、embedding。

## API

- `POST /api/sessions`：创建或恢复 visitor + character 的会话。
- `POST /api/chat/send`：发送消息，返回回复、记忆、prompt slots、状态和关系。
- `GET /api/sessions/{session_id}/memory`：读取记忆面板。
- `PATCH /api/sessions/{session_id}/memory`：更新会话记忆设置。
- `PATCH /api/sessions/{session_id}/memory/items/{memory_id}`：编辑单条记忆。
- `DELETE /api/sessions/{session_id}/memory/items/{memory_id}`：删除单条记忆。
- `GET /api/sessions/{session_id}/story`：读取故事面板。
- `POST /api/sessions/{session_id}/story/refresh`：刷新故事面板。
- `GET /api/sessions/{session_id}/export`：导出会话。

## 流程

1. 前端创建或恢复会话。
2. 发送用户消息。
3. 后端召回记忆、组装 prompt、请求 LLM 或 mock。
4. 立即返回用户可见回复。
5. 后台合并执行状态、关系、记忆分析。
6. 前端后续刷新记忆或故事面板。

## 修改原则

- 用户可见聊天回复不要等待所有后台分析完成。
- 记忆写入必须保守：低置信、无明确事实、临时情绪不要长期化。
- 故事面板可以服务小说工作台，但不要把小说章节运行态塞回聊天状态。
