# 前端功能域说明

`src/features/` 按业务域收口前端代码。`src/App.vue` 负责页面编排和跨域数据传递，各域内部负责自己的请求、状态和组件。

## 功能域

- `characters/`：角色工坊、角色草稿、AI 扩写/整卡重写、模板复制、自建角色保存和删除。
- `chat/`：visitor、角色选择、session 恢复、消息发送、导出和聊天面板。
- `relationship/`：记忆面板、Prompt Stack、角色状态、长期 bond、postprocess diagnostics 和恋爱人格测试。
- `novel/`：Story Pane、短篇生成、长篇项目、Story Canvas、项目事件池、章节编辑、版本和连续性检查。

## 依赖方向

- `characters` 产出标准角色卡，chat、relationship 和 novel 都可以读取角色卡语境。
- `chat` 可以返回会话消息、当前 state/bond 和 memory pane，但不承载关系域编辑逻辑。
- `relationship` 读取当前会话上下文并维护记忆、状态展示和人格测试结果。
- `novel` 可以读取聊天、记忆、story items 和角色素材作为创作输入，但章节运行态只留在小说域。

## 放置规则

- 请求函数放对应域的 `api.ts`。
- 可复用状态流放 composable，例如 `useChatSession`、`useRelationshipMemory`、`useNovelProjectActions`、`useCharacterWorkshop`。
- 纯转换、字段定义和 label 放同域的 `canvas.ts`、`constants.ts` 或 `data.ts`。
- 不把新业务逻辑堆回 `App.vue`，也不把一个域的可编辑状态塞进另一个域组件。
