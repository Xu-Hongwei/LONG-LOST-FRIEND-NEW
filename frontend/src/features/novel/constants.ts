import type { NovelChapterStatus, NovelFidelity, NovelForm, NovelPerspective } from "../../types";

export type NovelProgressStage =
  | "idle"
  | "collecting"
  | "state"
  | "beats"
  | "drafting"
  | "local_check"
  | "reviewing"
  | "rewriting"
  | "fallback"
  | "handoff"
  | "replan"
  | "done"
  | "failed";

export type NovelPipelineStep = { id: NovelProgressStage; label: string; detail: string };
export type CanvasBuildStage = "idle" | "materials" | "structure" | "chapters" | "scenes" | "threads" | "done" | "failed";
export type CanvasActionKey =
  | "external_event"
  | "trigger_event"
  | "immediate_reaction"
  | "obstacle_escalation"
  | "counterpart_reaction"
  | "character_choice"
  | "scene_consequence"
  | "relationship_shift"
  | "ending_hook";

export const DEFAULT_CHAPTER_INSTRUCTION = "承接上一章，写出下一段自然推进，但不制造越界进展。";

export const novelDraftSteps: NovelPipelineStep[] = [
  { id: "collecting", label: "读取", detail: "读取章节、画布、素材和上一章尾段" },
  { id: "state", label: "本地状态", detail: "本地重建截至上一章的 Novel State" },
  { id: "beats", label: "远程场景", detail: "远程拆出 Scene Beats 和可见动作链" },
  { id: "drafting", label: "远程正文/本地正文", detail: "远程生成当前章；远程失败时返回本地正文草稿" }
];

export const novelReviewSteps: NovelPipelineStep[] = [
  { id: "local_check", label: "本地检查", detail: "只拦截内部字段、ID、空正文和重复段落" },
  { id: "reviewing", label: "远程审稿", detail: "用 checklist 判断事件、对白、选择和钩子" },
  { id: "rewriting", label: "远程重写/通过", detail: "需要时远程重写一次，否则直接通过" },
  { id: "handoff", label: "后台交接", detail: "正文已返回，后台生成交接单并本地增量更新 Novel State" },
  { id: "replan", label: "后台滚动", detail: "后台重规划后续两章画布和场景卡" }
];

export const novelPipelineSteps = [...novelDraftSteps, ...novelReviewSteps];

export const canvasBuildSteps: { id: Exclude<CanvasBuildStage, "idle" | "done" | "failed">; label: string; detail: string }[] = [
  { id: "materials", label: "取材", detail: "读取会话片段、记忆和剧情标签" },
  { id: "structure", label: "组装", detail: "整理作品阶段和章节骨架" },
  { id: "chapters", label: "章节", detail: "生成每章目标、事件和结尾钩子" },
  { id: "scenes", label: "场景", detail: "拆出具体场景卡和约束" },
  { id: "threads", label: "线索", detail: "标记伏笔、回收点和规划" }
];

export const novelChapterStatusOptions: { value: NovelChapterStatus; label: string }[] = [
  { value: "planned", label: "计划中" },
  { value: "draft", label: "草稿" },
  { value: "revised", label: "已修订" },
  { value: "affected", label: "受影响" },
  { value: "locked", label: "已锁定" }
];

export const novelChapterStatusLabels: Record<NovelChapterStatus, string> = {
  planned: "计划中",
  drafting: "生成中",
  draft: "草稿",
  revised: "已修订",
  affected: "受影响",
  locked: "已锁定"
};

export const novelVersionSourceLabels: Record<string, string> = {
  mock: "本地生成",
  remote: "AI 生成",
  manual: "手动保存",
  restore: "版本恢复",
  snapshot: "历史快照"
};

export const sceneCardFields: { key: string; label: string; rows: number }[] = [
  { key: "current_scene", label: "当前场景", rows: 2 },
  { key: "pov", label: "视角", rows: 2 },
  { key: "present_characters", label: "在场人物", rows: 1 },
  { key: "character_desire", label: "人物欲望", rows: 2 },
  { key: "required_facts", label: "必须保留事实", rows: 2 },
  { key: "forbidden_progress", label: "禁止推进", rows: 2 }
];

export const canvasActionChainFields: { key: CanvasActionKey; label: string }[] = [
  { key: "external_event", label: "外部事件" },
  { key: "trigger_event", label: "触发事件" },
  { key: "immediate_reaction", label: "即时反应" },
  { key: "obstacle_escalation", label: "阻碍升级" },
  { key: "counterpart_reaction", label: "对方反应" },
  { key: "character_choice", label: "人物选择" },
  { key: "scene_consequence", label: "场景后果" },
  { key: "relationship_shift", label: "关系变化" },
  { key: "ending_hook", label: "结尾钩子" }
];

export const novelFormLabels: Record<NovelForm, string> = {
  daily_short: "日常短篇",
  campus_romance: "校园恋爱短篇",
  vignette: "片段随笔",
  chapter_one: "第一章",
  side_story: "番外"
};

export const novelPerspectiveLabels: Record<NovelPerspective, string> = {
  third_person: "第三人称",
  user_view: "用户视角",
  character_view: "角色视角",
  dual_view: "双视角"
};

export const novelFidelityLabels: Record<NovelFidelity, string> = {
  faithful: "忠实记录",
  polished: "轻度润色",
  literary: "文学化"
};

export const storyKindLabels: Record<string, string> = {
  motif: "意象",
  story_beat: "瞬间",
  open_thread: "伏笔",
  relationship_texture: "质感",
  boundary: "边界"
};

export const storyStatusLabels: Record<string, string> = {
  active: "活跃",
  seed: "种子",
  developed: "已发展",
  archived: "归档"
};
