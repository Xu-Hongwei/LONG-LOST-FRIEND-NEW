# Characters 前端域

角色工坊负责用户自建 AI 角色。保存后的自建角色仍是标准 `CharacterCard`，会进入聊天、relationship、memory 和 novel 链路。

## 文件

- `api.ts`：自建角色创建、更新、删除和 AI 草稿生成。
- `useCharacterWorkshop.ts`：表单草稿、模板复制、AI 扩写、保存和删除状态。
- `CharacterWorkshopPanel.vue`：角色工坊页面编排、模板列表和 AI Draft 面板。
- `CharacterForm.vue`：标准角色卡表单。

内置角色只作为模板展示，不在前端直接编辑或删除。

## AI 扩写模式

角色工坊支持两种 AI 草稿模式：

- `complete`：补全润色。参考当前表单已有内容，尽量填补空字段并保留用户已写设定。
- `rewrite`：整卡重写。只保留名字、题材和用户一句话核心，允许大幅重写整张角色卡。

AI 草稿请求会携带 `setting_type`、`setting_notes` 和当前 template。返回结果填入表单，但用户仍可手动编辑所有文本字段。

## 题材类型

角色卡包含 `setting_type` 和 `setting_notes`。题材用于聊天 prompt、角色草稿、小说项目和故事素材转译。校园轻伴只是 `campus` 题材模板，不是无 scenario 角色的默认世界观。

当前题材类型包括：

- `campus`
- `modern_daily`
- `workplace`
- `xianxia_wuxia`
- `urban_fantasy`
- `mystery`
- `sci_fi`
- `historical`
- `fantasy_adventure`
- `custom`

## 可编辑内容

表单覆盖稳定角色卡核心字段：

- 基础设定：名字、定位、一句话、性别、强调色、题材补充、简介。
- 人格与关系：性格底色、场景语境、说话风格、关系节奏、开场白、喜欢、不喜欢、边界、反模式。
- 默认故事素材包：可转译场域、事件模式、关系钩子、角色意象、避免套用。
- 行为策略：主动程度、动作密度、动作风格、安慰方式、追问方式、记忆方式。
- 声音样例：句式节奏、标志动作、避免项和样例台词。

`story_seed_pool` 只是角色默认灵感素材。创建小说时可以被项目化转译，不应直接锁死某本小说的剧情。
