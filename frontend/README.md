# 前端说明

前端使用 Vue 3、TypeScript 和 Vite。组合页仍是 `src/App.vue`，但主要业务状态已经拆到 `src/features/`。

验证环境为 Node.js 24 / npm 11。在本目录用 `npm ci` 按 `package-lock.json` 安装。
`vue` 和 `html2canvas` 是运行依赖；Vite、Vue 插件、TypeScript、类型检查器和测试打包用的
`esbuild` 是直接声明的开发依赖。开发、测试和构建时需安装开发依赖。
`node_modules`、`dist` 和缓存不入库；图片原文件来自 `public/`。

普通安装不修改锁文件。主动更新依赖时使用 `npm install`，审查 `package.json` 与
`package-lock.json` 的差异，并在干净目录用 `npm ci`、`npm test` 和 `npm run build` 验证。

`npm run dev` 默认监听 127.0.0.1:5176；构建后的 `npm run preview` 默认监听
127.0.0.1:4176。二者均将 `/api` 代理至 `CAMPUS_BACKEND_PORT`（默认 8766）。
前端端口可通过 `CAMPUS_FRONTEND_PORT` / `CAMPUS_PREVIEW_PORT` 设置，端口占用时直接失败。
PowerShell 启动脚本会加载根目录 `config.local.ps1`；直接 npm 命令只读取继承环境。
Vite 缓存写入根目录 `runtime/vite-cache/`，模型密钥不得使用 `VITE_*` 命名。

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

## 请求超时与回归检查

公共请求层区分连接失败、超时、HTTP 错误和无法解析的响应，不将后端原始 JSON/HTML 错误直接显示给用户。
普通读取默认 30 秒，普通写操作默认 120 秒；后台记忆等待额外预留 10 秒。
小说写操作可能串联多次模型调用，单独保留 15 分钟预算。前端超时只停止等待，不能保证取消服务端任务；
超时后先核对已有数据，不自动重试。自定义模型超时较长时，需一并评估这些客户端预算。

`npm test` 验证异步状态和错误处理；`npm run build` 验证类型与构建。
完整浏览器交互检查与模型输出质量验证仍是独立步骤。

## 草稿与异步结果保护

- 长篇章节的标题、目标、摘要、正文、状态、场景卡和写作指令在编辑时同步暂存到浏览器 localStorage；键按服务端返回的访客、会话、项目和章节隔离。刷新或关闭后重新打开同一章节会恢复，并标记“本机草稿”，不会自动写入项目数据库。
- 暂存失败（空间不足、浏览器禁用存储等）保留当前输入并明确提示；未成功暂存的章节在关闭时仍触发离开提醒。损坏或未知版本的记录不进入编辑器，也不自动删除。多个页面编辑时比较最后读取的暂存内容，旧页面发现变化会停止覆盖并提示保存或复制。
- 恢复时若服务端章节与草稿起点不同，会提示核对，不自动覆盖服务端。页面内确认“放弃草稿”后载入最近读取的已保存章节；保存成功、版本恢复和删除章节/项目会清理对应草稿。保留的其他章节不受影响。
- 本机暂存仅在同一浏览器及同一地址（含端口）可恢复；清除网站数据或隐私模式结束可能丢失，仍须正式保存以长期保留。项目设定、独立画布编辑、短篇结果、角色卡和记忆备注不在本轮跨页面恢复范围内。
- 写作指令从已保存的 `scene_card.generation_instruction` 恢复；明确恢复版本时使用该版本的指令。保存成功和确认删除后清理对应草稿状态。
- 指令优化、短篇生成及角色扩写按当前请求和编辑对象接收结果。切换后到达的旧结果或错误不能覆盖当前内容、释放新请求的忙碌状态；优化等待期间的手动输入也会保留。
- 后台记忆刷新保留正在编辑的手工备注；不同会话分别暂存未保存备注。

## 修改原则

- 请求放对应域 `api.ts`。
- 域内状态流优先放 composable。
- 可测试转换逻辑留在域内纯函数文件。
- 改组件 props/events 时先看 `App.vue` 编排层，避免把域边界重新打散。
- 新增 UI 状态时优先在对应域内可视化 diagnostics，不把后端内部 JSON 直接塞到无关面板。
