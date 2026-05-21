# Chat 前端域

聊天前端只负责把用户送进一段角色会话，并把消息收发链路跑顺。

## 文件

- `ChatPanel.vue`：聊天消息、输入框、角色切换和调试导出入口。
- `api.ts`：visitor、角色、session、chat send、story pane 和 export 请求。
- `useChatSession.ts`：visitor 初始化、角色本地存储 key、会话恢复、发送消息、滚动到底部和 memory postprocess 等待。

## 运行边界

1. 初始化 visitor 和角色列表。
2. 以 `visitor_id + character_id` 创建或恢复 session。
3. 发送用户消息，立即接收主回复。
4. 把后端返回的 memory pane、state、bond 快照交给对应展示层。
5. 主回复后等待 memory postprocess 诊断和 Prompt Stack 刷新，但不在 chat 域里编辑 memory，也不在这一步额外刷新 state/bond。

## 不放这里

- 记忆过滤、编辑、冻结和 Prompt Stack 展开，归 `relationship/`。
- 恋爱人格测试，归 `relationship/personalityTest/`。
- Story Canvas、章节和版本，归 `novel/`。
