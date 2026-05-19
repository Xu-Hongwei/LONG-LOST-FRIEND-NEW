# Chat Frontend Feature

这里封装聊天页面需要的后端请求。

## 文件

- `api.ts`：visitor、characters、sessions、chat send、memory、story pane、export。

## 原则

这里不保存 Vue 状态，只提供请求函数。页面状态仍由 `App.vue` 管理。
