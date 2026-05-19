# 前端说明

前端是 Vue 3 + TypeScript + Vite。主页面仍在 `src/App.vue`，但功能相关的 API、常量、纯函数和本地存储已经拆到 `src/features/`。

## 入口

- `src/main.ts`：挂载 Vue 应用。
- `src/App.vue`：页面状态、交互编排、模板和当前主要 UI。
- `src/styles.css`：全局样式。
- `src/types.ts`：前后端共享的前端类型定义。

## 功能目录

- `src/features/chat/`：聊天接口请求。
- `src/features/novel/`：小说接口、画布纯函数、状态标签、流程常量。
- `src/features/personalityTest/`：人格测试题库、结果画像、本地存储、结果图片导出。

## 状态边界

- 聊天 busy/error 与小说项目 busy/error 分开维护，避免跨页面串台。
- 故事自动刷新计数按 `session_id` 保存，不使用全局单计数。
- 人格测试答案按 visitor 维度落 localStorage，不同访客互不覆盖。
- 小说章节草稿、画布草稿和生成进度要分开，不把后台运行态写进规划快照。

## 修改原则

- API 请求放进对应功能的 `api.ts`。
- 纯数据和 label 常量放进 `constants.ts` 或 `data.ts`。
- 画布、scene card 等可测试转换逻辑放进 `features/novel/canvas.ts`。
- `App.vue` 可以继续作为当前组合页，但不要再把新功能的基础工具函数塞回去。
