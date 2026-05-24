# Characters frontend domain

角色工坊负责用户自建 AI 角色。

- `api.ts`：自建角色创建、更新、删除。
- `useCharacterWorkshop.ts`：表单草稿、模板复制、保存和删除状态。
- `CharacterWorkshopPanel.vue`：角色工坊页面编排。
- `CharacterForm.vue`：标准 `CharacterCard` 表单。

自建角色保存后仍是标准角色卡，会进入现有聊天、relationship、memory 和 novel 链路。
内置角色只作为模板展示，不在前端直接编辑或删除。
