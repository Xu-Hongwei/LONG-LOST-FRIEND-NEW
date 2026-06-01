# 人格测试模块说明

人格测试目前主要是前端功能，位于 relationship 域。它不参与 chat 主回复、bond reducer 或小说事件池，只能在用户确认后把结果摘要写入当前会话 manual note。

## 文件职责

- `data.ts`：题库、维度、画像类型、男女结果文案和图片路径。
- `storage.ts`：按 visitor 保存答题记录和性别选择。
- `resultImage.ts`：把结果弹窗导出为 PNG。
- `LoveTestPanel.vue`：答题、结果展示和导出 UI。
- `frontend/public/personality/`：结果页使用的本地画像图。

## 数据边界

- 测试答案不写入后端数据库。
- localStorage key 包含 visitor 和版本号，避免不同用户或旧题库互相污染。
- 结果只有在完成全部题目后展示，不在答题中途泄露最终类型。
- 写入 manual note 时，只写用户可确认的摘要，不写完整答题明细。

## 修改原则

- 新增题目后要同步检查题目数量、维度权重和结果类型覆盖。
- 新增结果类型时，要同时补齐 `data.ts` 中的画像数据和 public 图片。
- 导出结果图时，按钮区域和关闭按钮会临时隐藏，避免进入截图。
