# Novel 前端域

小说工作台把当前会话素材组织成短篇草稿或长篇项目。

## 文件分工

- `api.ts`：短篇、项目、画布、章节、版本、连续性检查和指令优化请求。
- `useShortNovel.ts`：短篇参数、生成结果标签和 Markdown 导出。
- `useNovelProject.ts`：项目、章节、版本和编辑器派生状态。
- `useNovelProjectActions.ts`：创建/保存项目、章节增删、章节生成、版本恢复、连续性检查和画布保存。
- `useNovelInstruction.ts`：章节指令骨架、本地 helper 和远程指令优化。
- `useStoryCanvas.ts`、`canvas.ts`：Story Canvas、scene card 和画布状态。
- `useNovelProgress.ts`：章节生成与短篇生成进度。
- `constants.ts`：字段、标签、进度步骤和默认配置。

## 界面边界

- Quick Draft 只处理短篇参数、结果预览和导出。
- Project Mode 处理 Story Bible、素材、画布、章节草稿、版本和连续性。
- `story_canvas` 给章节提供规划默认值，但不能覆盖用户已编辑的章节字段。
- 章节草稿、画布草稿、生成进度和后台 postprocess 状态要分开维护。

## 与其他域的关系

- 从 chat session 读取消息范围。
- 从 relationship 上下文读取 memory/state/bond 返回值作为素材。
- Story Pane 服务小说取材，但剧情标签刷新 cadence 不应绑死章节生成流程。
