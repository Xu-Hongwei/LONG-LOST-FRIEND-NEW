# Chat 后端域

chat 域负责会话和用户可见消息链路，前端入口在 `frontend/src/features/chat/`。

## 文件

- `routes.py`：注册 session、chat send、story pane、memory 兼容路由和 export 路由。
- `service.py`：创建/恢复会话、召回上下文、组装 prompt、生成主回复、排队 relationship postprocess。
- `time_awareness.py`：根据上一条消息时间生成轻量时间感上下文。

## 主流程

1. `POST /api/sessions` 以 `visitor_id + character_id` 创建或恢复 session。
2. `POST /api/chat/send` 保存用户消息。
3. chat service 召回 profile/recall memory，读取近期消息、当前 state 和长期 bond。
4. `ContextComposer` 组装 prompt slots。
5. `LlmClient` 返回远程回复，失败时使用 persona-shaped mock reply。
6. assistant 消息保存后立即返回前端。
7. 后台任务交给 `features/relationship/postprocess.py` 处理 memory、state 和 bond。

## API

- `POST /api/sessions`
- `POST /api/chat/send`
- `GET /api/sessions/{session_id}/story`
- `POST /api/sessions/{session_id}/story/refresh`
- `GET /api/sessions/{session_id}/export`

memory 路由仍在 chat 路由文件注册以保持 URL 不变，但处理者是 `RelationshipService`：

- `GET /api/sessions/{session_id}/memory`
- `GET /api/sessions/{session_id}/memory/wait`
- `PATCH /api/sessions/{session_id}/memory`
- `PATCH /api/sessions/{session_id}/memory/items/{memory_id}`
- `DELETE /api/sessions/{session_id}/memory/items/{memory_id}`

## 边界

- chat 域不实现 memory 编辑、state 评分或 bond reducer。
- 主回复不能等待 relationship 后处理结束。
- Story Pane 是聊天沉淀出的素材窗口，但章节、版本、事件池和 Novel State 不回写到 chat 状态。
- 角色卡题材和 persona slots 由 composer 使用；chat 域不直接生成或修改角色卡。
