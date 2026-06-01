# 前端说明

前端使用 Vue 3、TypeScript 和 Vite。组合页仍是 `src/App.vue`，但主要业务状态已经拆到 `src/features/`。

## 入口

- `src/main.ts`：挂载 Vue 应用。
- `src/App.vue`：页面切换、跨域 composable 初始化、组件编排和顶层错误展示。
- `src/styles.css`：全局样式。
- `src/types.ts`：前端使用的接口模型和共享类型。

## 功能域

- `src/features/characters/`：角色工坊、自建角色、AI 扩写、题材类型和角色卡表单。
- `src/features/chat/`：聊天面板、会话生命周期、角色切换和消息收发。
- `src/features/relationship/`：memory、state、bond、Prompt Stack、postprocess diagnostics 和恋爱人格测试。
- `src/features/novel/`：剧情标签、短篇、长篇项目、Story Canvas、项目事件池、章节、版本和连续性检查。

先看 `src/features/README.md`，再进入对应域 README。

## 当前主流程

1. `characters` 允许复制内置模板或自建角色；AI 扩写会生成标准 `CharacterCard`。
2. `useChatSession` 初始化 visitor、角色和 session。
3. chat send 返回消息以及当次响应里的 memory pane、state 和 bond 快照。
4. `useRelationshipMemory` 负责 memory 面板编辑与 postprocess 诊断展示；等待接口只刷新 memory pane 和 Prompt Stack。
5. Novel Studio 使用 session 消息、memory、story items、角色 `story_seed_pool` 和项目设定生成短篇或长篇。
6. 长篇章节生成前，用户或系统先绑定项目事件，再同步画布、场景卡和优化生成指令。

## 状态边界

- characters 只管角色卡草稿、保存、删除、AI 扩写和模板展示，不接管会话运行态。
- chat 只管 visitor、session、角色选择、消息和等待后台 memory 刷新。
- relationship 管长期关系上下文和 memory 编辑，不接管消息发送。
- novel 管 Story Canvas、项目事件池、章节 draft、版本和生成进度，不把章节运行态塞回 chat。
- Story Pane 自动刷新按当前页面基线之后新增的用户消息累计，每 6 条触发一次；手动刷新会重置基线并显示候选/写入结果。
- State 的 `Live Resonance` 和 Bond 的 `Bond Baseline` 来源不同，不要求数值一致。

## 修改原则

- 请求放对应域 `api.ts`。
- 域内状态流优先放 composable。
- 可测试转换逻辑留在域内纯函数文件。
- 改组件 props/events 时先看 `App.vue` 编排层，避免把域边界重新打散。
- 新增 UI 状态时优先在对应域内可视化 diagnostics，不把后端内部 JSON 直接塞到无关面板。
