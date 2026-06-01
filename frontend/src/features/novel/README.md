# Novel 前端域

小说工作台把当前会话素材组织成短篇草稿或长篇项目。长篇模式围绕 Story Bible、Story Canvas、项目事件池、章节编辑、场景卡、生成指令和版本回退协作。

## 文件分工

- `api.ts`：短篇、项目、画布、事件池、章节、版本、连续性检查和指令优化请求。
- `useShortNovel.ts`：短篇参数、生成结果标签和 Markdown 导出。
- `useNovelProject.ts`：项目、章节、版本和编辑器派生状态。
- `useNovelProjectActions.ts`：创建/保存项目、章节增删、章节生成、版本恢复、连续性检查、画布保存和事件池操作。
- `useNovelInstruction.ts`：章节指令骨架、本地 helper 和远程指令优化。
- `useStoryCanvas.ts`、`canvas.ts`：Story Canvas、scene card、事件绑定和画布状态。
- `useNovelProgress.ts`：章节生成与短篇生成进度。
- `constants.ts`：字段、标签、进度步骤和默认配置。
- `CanvasFlowView.vue`：项目事件池可视化、事件编辑和绑定模式选择。
- `ProjectChapterEditor.vue`：章节草稿、当前章节采用事件、返回同步结果和场景卡编辑。

## 界面边界

- Quick Draft 只处理短篇参数、结果预览和导出。
- Project Mode 处理 Story Bible、素材、画布、事件池、章节草稿、版本和连续性。
- `story_canvas` 给章节提供规划默认值，但不能覆盖用户已编辑的章节字段。
- 项目事件池是候选库；只有绑定到当前章的事件才进入章节画布、场景卡和生成指令。
- 章节草稿、画布草稿、事件池草稿、生成进度和后台 postprocess 状态要分开维护。

## 项目事件池 UI

事件池卡片显示：

- 来源、状态、绑定章节和 `use_mode`。
- 时间锚点、地点、外部事件、钩子和来源说明。
- score、reasons、penalties 和主题/基调命中信息。

事件池支持轻量编辑：

- 新增事件。
- 编辑事件。
- 退休事件。
- 删除未绑定事件。
- 绑定到当前章或取消当前章绑定。

绑定本章时，前端选择的是“本章采用强度”，不会强行修改事件本身默认 `use_mode`。

## 绑定模式

- `strict`：必须采用地点、时间、外部事件和钩子。
- `guide`：默认，作为主要方向，首次同步画布和场景卡，之后保护用户手写字段。
- `flavor`：只借地点、意象、气氛或钩子。
- `free`：只作为灵感，不自动同步。

绑定后，前端在当前章节面板展示后端返回的 `event_contract` 和 `event_sync`，包括 source、remote status、写入画布字段和写入场景卡字段。

## 生成链路

长篇正文生成前，前端应尽量保持四者一致：

1. 当前章节采用事件。
2. 章节看板动作链。
3. 场景卡。
4. 优化生成指令。

优化生成指令会读取当前事件契约、canvas chapter、scene card、上一章 handoff 和 Novel State。若场景卡和事件契约冲突，以事件契约和章节画布决定“发生什么”，场景卡调整“怎么演出来”。

## 与其他域的关系

- 从 chat session 读取消息范围。
- 从 relationship 上下文读取 memory/state/bond 返回值作为素材。
- 从 characters 读取当前角色题材和 `story_seed_pool`，但角色素材只用于转译补味，不覆盖项目已写事实。
- Story Pane 服务小说取材，但剧情标签刷新 cadence 不应绑死章节生成流程。
