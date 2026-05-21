# Relationship 前端域

关系域承接聊天之后需要长期维护和解释的上下文。

## 文件

- `api.ts`：memory pane 更新、单条 memory 编辑和删除。
- `ChatMemoryPanel.vue`：memory 列表、过滤、召回视图、Prompt Stack 和分析诊断。
- `CharacterInsightsPanel.vue`：当前 state 与长期 bond 展示。
- `useRelationshipMemory.ts`：memory 过滤、计数、诊断、冻结、note 保存、编辑/删除和展开状态。
- `personalityTest/`：恋爱人格测试题库、结果画像、本地存储和结果图导出。

## 状态边界

- memory、state 和 bond 都围绕当前 session 或当前 visitor + character 展示。
- memory 写改删属于 relationship，不属于消息发送链路。
- 人格测试保存在浏览器本地，并可把结果摘要写入当前会话 manual note。
- State 的 `Live Resonance` 是当前 session 的短期互动值；Bond 的 `Bond Baseline` 是长期关系基线，前端不应把它们当成同一个进度条。
- postprocess diagnostics 可以说明 memory/state/bond 哪个阶段成功或失败；memory wait 当前只补 pane 和 Prompt Stack，不补拉 state/bond。

## 不放这里

- 角色消息收发和 session 生命周期，归 `chat/`。
- Story Pane、小说项目、章节生成和版本，归 `novel/`。
