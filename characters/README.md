# 角色卡说明

`characters/*.json` 是内置角色卡来源。后端启动时会读取这些文件，并把角色信息 upsert 到 SQLite。当前内置模板共 10 个，包含校园、职场、武侠修仙、悬疑、科幻和奇幻旅伴等题材。

## 角色卡内容

角色卡主要包含：

- 基础身份：`name`、`archetype`、`tagline`、`gender`。
- 题材类型：`setting_type` 和 `setting_notes`。
- 稳定人设：`bio`、`personality`、`scenario`、`backstory`。
- 对话风格：`speech_style`、`mes_example`、`voice`。
- 关系与边界：`relationship_pace`、`boundaries`、`likes`、`dislikes`。
- 行为策略：`interaction_policy`、`anti_patterns`。
- 小说素材：`story_seed_pool`。
- 视觉提示：`visual`。

## setting_type

`setting_type` 是角色和小说共用的上层题材概念。校园轻伴是 `setting_type=campus` 的模板类型，不是所有角色的默认世界观。

可用题材包括：

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

## story_seed_pool

`story_seed_pool` 是默认故事素材包，不是固定剧情。它可以包含：

- `places`：可转译场域。
- `event_seeds`：事件模式。
- `hook_seeds`：关系钩子。
- `motifs`：角色意象。
- `forbidden_defaults`：避免套用的默认项。

小说项目使用这些素材时，需要先按项目题材和世界观转译。比如校园里的“公告栏”和“便签”，在修仙项目中可以转成“山门告示碑”和“折角药方”，而不是原样塞进正文。

## 修改原则

- 修改内置角色卡后重启后端即可重新同步。
- 角色卡负责稳定人设，不负责固定每轮动作。
- 动态动作密度、提问方式、记忆方式等策略可以通过角色卡配置，但具体输出仍由上下文和 LLM 决定。
- 不要把单本小说的已发生剧情写进通用角色卡；这类事实应进入项目 Story Bible、Novel State 或章节版本。
