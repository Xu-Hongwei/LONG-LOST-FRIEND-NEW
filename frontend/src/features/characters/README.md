# Characters frontend domain

角色工坊负责用户自建 AI 角色。

- `api.ts`：自建角色创建、更新、删除。
- `useCharacterWorkshop.ts`：表单草稿、模板复制、保存和删除状态。
- `CharacterWorkshopPanel.vue`：角色工坊页面编排。
- `CharacterForm.vue`：标准 `CharacterCard` 表单。

自建角色保存后仍是标准角色卡，会进入现有聊天、relationship、memory 和 novel 链路。
内置角色只作为模板展示，不在前端直接编辑或删除。

## 题材类型

角色卡包含 `setting_type` 和 `setting_notes`。角色工坊会把它们随保存和 AI 扩写请求一起提交，用于让新角色、聊天 prompt 和小说工坊保持同一套题材语境。

内置模板按题材分组展示；校园轻伴只是其中一组，不应作为无 scenario 角色的系统默认值。
