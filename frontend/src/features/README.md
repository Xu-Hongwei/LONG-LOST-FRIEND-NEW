# 前端功能域说明

`src/features/` 按业务域收口前端代码，`src/App.vue` 只负责页面编排、三域 composable 初始化和顶层错误展示。

## 三域

- `chat/`：visitor、角色选择、会话恢复、消息发送、导出和聊天面板。
- `relationship/`：记忆面板、Prompt Stack、角色状态、长期 bond、恋爱人格测试。
- `novel/`：Story Pane、短篇生成、长篇项目、Story Canvas、章节编辑、版本和连续性检查。

## 依赖方向

- `chat` 可以返回会话消息、当前 state/bond 和 memory pane，但不承载关系域编辑逻辑。
- `relationship` 读取当前会话上下文并维护记忆、状态展示和人格测试结果。
- `novel` 可以读取聊天、记忆和 story items 作为素材，但章节运行态只留在小说域。

## 放置规则

- 请求函数放对应域的 `api.ts`。
- 可复用状态流放 composable，例如 `useChatSession`、`useRelationshipMemory`、`useNovelProjectActions`。
- 纯转换、字段定义和 label 放同域的 `canvas.ts`、`constants.ts` 或 `data.ts`。
- 不把新业务逻辑堆回 `App.vue`，也不把一个域的可编辑状态塞进另一个域的组件。
