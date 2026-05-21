# 前端说明

前端使用 Vue 3、TypeScript 和 Vite。当前组合页仍是 `src/App.vue`，但业务状态已经按 `chat / relationship / novel` 拆到 `src/features/`。

## 入口

- `src/main.ts`：挂载 Vue 应用。
- `src/App.vue`：页面切换、三域 composable 初始化、组件编排和顶层错误展示。
- `src/styles.css`：全局样式。
- `src/types.ts`：前端使用的接口模型和共享类型。

## 功能域

- `src/features/chat/`：聊天面板、会话生命周期和消息收发。
- `src/features/relationship/`：memory、state、bond、Prompt Stack 和恋爱人格测试。
- `src/features/novel/`：剧情标签、短篇、长篇项目、画布、章节和版本。

先看 `src/features/README.md`，再进入对应域 README。

## 当前主流程

1. `useChatSession` 初始化 visitor、角色和 session。
2. chat send 返回消息以及当次响应里的 memory pane、state 和 bond 快照。
3. `useRelationshipMemory` 负责 memory 面板编辑与 postprocess 诊断展示；当前等待接口只刷新 memory pane 和 Prompt Stack，不额外拉取新的 state/bond。
4. Novel Studio 使用 session 消息、memory 和 story items 生成短篇或长篇项目。
5. 恋爱人格测试留在 relationship 域，本地保存答案，必要时把画像摘要写入 manual note。

## 状态边界

- chat 只管会话、消息、角色选择和等待后台 memory 刷新。
- relationship 管长期关系上下文和 memory 编辑，不接管消息发送。
- novel 管 Story Canvas、章节 draft、版本和生成进度，不把章节运行态塞回 chat。
- Story Pane 自动刷新按当前页面基线之后新增的用户消息累计，每 6 条触发一次；手动刷新后会重置基线并显示候选/写入结果。
- State 面板显示短期 `Live Resonance`，Bond 面板显示长期 `Bond Baseline`；两者来源和更新节奏不同，不需要数值一致。

## 修改原则

- 请求放对应域 `api.ts`。
- 域内状态流优先放 composable。
- 可测试转换逻辑留在域内纯函数文件。
- 改组件 props/events 时先看 `App.vue` 编排层，避免把域边界重新打散。
