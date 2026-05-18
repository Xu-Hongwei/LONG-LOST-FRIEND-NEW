<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from "vue";
import html2canvas from "html2canvas";
import {
  buildStoryCanvas,
  checkNovelContinuity,
  createNovelChapter,
  createNovelProject,
  createSession,
  deleteMemoryItem,
  deleteNovelChapter,
  deleteNovelVersion,
  exportSession,
  generateNovel,
  generateProjectChapter,
  getNovelProject,
  getStoryPane,
  listCharacters,
  listNovelProjects,
  listNovelVersions,
  optimizeNovelInstruction,
  patchMemory,
  refreshStoryPane,
  resolveVisitor,
  restoreNovelVersion,
  sendMessage,
  updateMemoryItem,
  updateNovelChapter,
  updateNovelProject
} from "./api";
import { loveProfiles, loveQuestions } from "./loveTestData";
import type { LoveDimension, LoveGender } from "./loveTestData";
import type {
  CharacterBond,
  CharacterCard,
  CharacterState,
  ChatMessage,
  ContextSlot,
  MemoryItem,
  MemoryPane,
  MemoryPatch,
  NovelChapter,
  NovelChapterStatus,
  NovelContinuityReport,
  NovelFidelity,
  NovelForm,
  NovelGenerateResponse,
  NovelPerspective,
  NovelProject,
  NovelVersion,
  StoryCanvas,
  StoryCanvasChapter,
  StoryCanvasScene,
  StoryCanvasThread,
  StoryPane
} from "./types";

const VISITOR_KEY = "campus-pulse-lite-visitor";
const CHARACTER_KEY = "campus-pulse-lite-character";
const LOVE_TEST_KEY = "campus-pulse-lite-love-test";
const LOVE_TEST_VERSION = "love-test-v3-20q-6types-profile-images";
const STORY_AUTO_REFRESH_USER_INTERVAL = 6;

type PageKey = "chat" | "love-test" | "novel";
type NovelStudioMode = "select" | "quick" | "project";
type NovelWorkflowMode = Exclude<NovelStudioMode, "select">;
type NovelProgressStage = "idle" | "collecting" | "state" | "beats" | "drafting" | "local_check" | "reviewing" | "rewriting" | "fallback" | "handoff" | "replan" | "done" | "failed";
type NovelPipelineStep = { id: NovelProgressStage; label: string; detail: string };
type StoryCanvasView = "flow" | "chapters" | "scenes" | "threads";
type CanvasBuildStage = "idle" | "materials" | "structure" | "chapters" | "scenes" | "threads" | "done" | "failed";
type StoryRefreshOptions = { silent?: boolean };
type ChapterSceneCardDraft = Record<string, string>;
type CanvasActionKey =
  | "external_event"
  | "trigger_event"
  | "immediate_reaction"
  | "obstacle_escalation"
  | "counterpart_reaction"
  | "character_choice"
  | "scene_consequence"
  | "relationship_shift"
  | "ending_hook";
const DEFAULT_CHAPTER_INSTRUCTION = "承接上一章，写出下一段自然推进，但不制造越界进展。";
type NovelVersionDisplay = NovelVersion & {
  duplicateCount: number;
  restoreCount: number;
  sourceKeys: string[];
};
const currentPage = ref<PageKey>("chat");
const novelStudioMode = ref<NovelStudioMode>("select");
const visitorId = ref(localStorage.getItem(VISITOR_KEY) || "");
const loveAnswers = ref<Record<string, number>>(loadLoveAnswers(localStorage.getItem(VISITOR_KEY) || ""));
const loveGender = ref<LoveGender>(loadLoveGender(localStorage.getItem(VISITOR_KEY) || ""));
const showLoveResultModal = ref(false);
const messageListRef = ref<HTMLElement | null>(null);
const characters = ref<CharacterCard[]>([]);
const selectedCharacterId = ref("");
const activeCharacter = computed(() => characters.value.find((item) => item.id === selectedCharacterId.value) || null);
const sessionId = ref("");
const messages = ref<ChatMessage[]>([]);
const draft = ref("");
const busy = ref(false);
const error = ref("");
const memoryPane = ref<MemoryPane | null>(null);
const promptSlots = ref<ContextSlot[]>([]);
const characterState = ref<CharacterState | null>(null);
const characterBond = ref<CharacterBond | null>(null);
const manualNoteDraft = ref("");
const memoryFilter = ref<"all" | "global" | "character" | "session" | "recall">("all");
const editingMemoryId = ref("");
const memoryDraft = ref<MemoryPatch>({});
const expandedMemoryId = ref("");
const expandedSlotKey = ref("");
const stateExpanded = ref(false);
const bondExpanded = ref(false);
const novelMessageLimit = ref(40);
const novelTargetLength = ref(1200);
const novelPerspective = ref<NovelPerspective>("third_person");
const novelForm = ref<NovelForm>("daily_short");
const novelFidelity = ref<NovelFidelity>("polished");
const novelAtmosphere = ref("温柔、克制、日常");
const novelResult = ref<NovelGenerateResponse | null>(null);
const storyPane = ref<StoryPane | null>(null);
const storyBusy = ref(false);
const activeNovelWorkflowMode = ref<NovelWorkflowMode | null>(null);
const novelProgressStage = ref<NovelProgressStage>("idle");
const novelProgressPercent = ref(0);
const novelProgressVisible = ref(false);
const novelProgressWaitingSeconds = ref(0);
const novelProgressDetail = ref("");
const lastAutoStoryRefreshUserCount = ref(0);
const novelProjects = ref<NovelProject[]>([]);
const activeNovelProjectId = ref("");
const activeNovelChapterId = ref("");
const novelProjectBusy = ref(false);
const projectDraft = ref({
  title: "",
  genre: "校园日常长篇",
  tone: "温柔、克制、日常",
  protagonist: "",
  worldview: "",
  relationship_setup: "",
  outline: ""
});
const storyCanvasView = ref<StoryCanvasView>("flow");
const storyCanvasDraft = ref<StoryCanvas>(emptyStoryCanvas());
const canvasBuildStage = ref<CanvasBuildStage>("idle");
const canvasBuildPercent = ref(0);
const canvasBuildWaitingSeconds = ref(0);
const canvasBuildRunCount = ref(0);
const canvasBuildLastLabel = ref("");
const chapterDraft = ref({
  title: "",
  goal: "",
  summary: "",
  body: "",
  status: "planned" as NovelChapterStatus,
  scene_card: {} as ChapterSceneCardDraft
});
const chapterInstruction = ref(DEFAULT_CHAPTER_INSTRUCTION);
const chapterInstructionsById = ref<Record<string, string>>({});
const activeInstructionChapterId = ref("");
const projectChapterTargetLength = ref(1800);
const isOptimizingInstruction = ref(false);
const instructionOptimizationNote = ref("");
const continuityReport = ref<NovelContinuityReport | null>(null);
const chapterVersions = ref<NovelVersion[]>([]);
const novelFocusMode = ref(false);
const novelEditorFont = ref<"serif" | "sans">("serif");
let novelProgressTimers: number[] = [];
let novelProgressTicker: number | null = null;
let novelGenerationRunId = 0;
let canvasBuildTimers: number[] = [];
let canvasBuildTicker: number | null = null;

const novelDraftSteps: NovelPipelineStep[] = [
  { id: "collecting", label: "读取", detail: "读取章节、画布、素材和上一章尾段" },
  { id: "state", label: "本地状态", detail: "本地重建截至上一章的 Novel State" },
  { id: "beats", label: "远程场景", detail: "远程拆出 Scene Beats 和可见动作链" },
  { id: "drafting", label: "远程正文/本地正文", detail: "远程生成当前章；远程失败时返回本地正文草稿" }
];
const novelReviewSteps: NovelPipelineStep[] = [
  { id: "local_check", label: "本地检查", detail: "只拦截内部字段、ID、空正文和重复段落" },
  { id: "reviewing", label: "远程审稿", detail: "用 checklist 判断事件、对白、选择和钩子" },
  { id: "rewriting", label: "远程重写/通过", detail: "需要时远程重写一次，否则直接通过" },
  { id: "handoff", label: "后台交接", detail: "正文已返回，后台生成交接单并本地增量更新 Novel State" },
  { id: "replan", label: "后台滚动", detail: "后台重规划后续两章画布和场景卡" }
];
const novelPipelineSteps = [...novelDraftSteps, ...novelReviewSteps];

const canvasBuildSteps: { id: Exclude<CanvasBuildStage, "idle" | "done" | "failed">; label: string; detail: string }[] = [
  { id: "materials", label: "取材", detail: "读取会话片段、记忆和剧情标签" },
  { id: "structure", label: "组装", detail: "整理作品阶段和章节骨架" },
  { id: "chapters", label: "章节", detail: "生成每章目标、事件和结尾钩子" },
  { id: "scenes", label: "场景", detail: "拆出具体场景卡和约束" },
  { id: "threads", label: "线索", detail: "标记伏笔、回收点和规则" }
];

const novelChapterStatusOptions: { value: NovelChapterStatus; label: string }[] = [
  { value: "planned", label: "计划中" },
  { value: "draft", label: "草稿" },
  { value: "revised", label: "已修订" },
  { value: "affected", label: "受影响" },
  { value: "locked", label: "已锁定" }
];

const novelChapterStatusLabels: Record<NovelChapterStatus, string> = {
  planned: "计划中",
  drafting: "生成中",
  draft: "草稿",
  revised: "已修订",
  affected: "受影响",
  locked: "已锁定"
};

const novelVersionSourceLabels: Record<string, string> = {
  mock: "本地生成",
  remote: "AI 生成",
  manual: "手动保存",
  restore: "版本恢复",
  snapshot: "历史快照"
};
const sceneCardFields: { key: string; label: string; rows: number }[] = [
  { key: "current_scene", label: "当前场景", rows: 2 },
  { key: "pov", label: "视角", rows: 2 },
  { key: "present_characters", label: "在场人物", rows: 1 },
  { key: "character_desire", label: "人物欲望", rows: 2 },
  { key: "required_facts", label: "必须保留事实", rows: 2 },
  { key: "forbidden_progress", label: "禁止推进", rows: 2 }
];
const canvasActionChainFields: { key: CanvasActionKey; label: string }[] = [
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
const novelFormLabels: Record<NovelForm, string> = {
  daily_short: "日常短篇",
  campus_romance: "校园恋爱短篇",
  vignette: "片段随笔",
  chapter_one: "第一章",
  side_story: "番外"
};
const novelPerspectiveLabels: Record<NovelPerspective, string> = {
  third_person: "第三人称",
  user_view: "用户视角",
  character_view: "角色视角",
  dual_view: "双视角"
};
const novelFidelityLabels: Record<NovelFidelity, string> = {
  faithful: "忠实记录",
  polished: "轻度润色",
  literary: "文学化扩写"
};

const includedSlots = computed(() => promptSlots.value.filter((slot) => slot.included));
const excludedSlots = computed(() => promptSlots.value.filter((slot) => !slot.included));
const displayedChapterVersions = computed<NovelVersionDisplay[]>(() => {
  const grouped = new Map<string, NovelVersionDisplay>();
  const ordered: NovelVersionDisplay[] = [];
  for (const version of chapterVersions.value) {
    const key = [
      version.title.trim(),
      version.summary.trim(),
      version.body.trim()
    ].join("\n---\n");
    const sourceKey = version.source || version.version_type || "";
    const existing = grouped.get(key);
    if (existing) {
      existing.duplicateCount += 1;
      if (sourceKey === "restore") existing.restoreCount += 1;
      if (sourceKey && !existing.sourceKeys.includes(sourceKey)) {
        existing.sourceKeys.push(sourceKey);
      }
      continue;
    }
    const displayVersion: NovelVersionDisplay = {
      ...version,
      duplicateCount: 1,
      restoreCount: sourceKey === "restore" ? 1 : 0,
      sourceKeys: sourceKey ? [sourceKey] : []
    };
    grouped.set(key, displayVersion);
    ordered.push(displayVersion);
  }
  return ordered;
});
const novelResultSourceLabel = computed(() => {
  const source = String(novelResult.value?.diagnostics?.source || "");
  if (source === "remote") return "AI 生成";
  if (source === "mock") return "本地生成";
  return "生成结果";
});
const novelResultControlLabel = computed(() => {
  const diagnostics = novelResult.value?.diagnostics || {};
  const form = diagnostics.form as NovelForm | undefined;
  const perspective = diagnostics.perspective as NovelPerspective | undefined;
  const fidelity = diagnostics.fidelity as NovelFidelity | undefined;
  return [
    form ? novelFormLabels[form] : novelFormLabels[novelForm.value],
    perspective ? novelPerspectiveLabels[perspective] : novelPerspectiveLabels[novelPerspective.value],
    fidelity ? novelFidelityLabels[fidelity] : novelFidelityLabels[novelFidelity.value],
  ].filter(Boolean).join(" · ");
});
const filteredMemories = computed(() => {
  if (!memoryPane.value) return [];
  if (memoryFilter.value === "recall") return memoryPane.value.last_recall || [];
  if (memoryFilter.value === "all") return memoryPane.value.memories;
  return memoryPane.value.memories.filter((memory) => memory.memory_scope === memoryFilter.value);
});
const recallCount = computed(() => memoryPane.value?.last_recall?.length || 0);
const energyPercent = computed(() => Math.round((characterState.value?.energy || 0) * 100));
const resonancePercent = computed(() => Math.round((characterState.value?.resonance || 0) * 100));
const bondPercent = computed(() => Math.round((characterBond.value?.resonance_base || 0) * 100));
const loveProgress = computed(() => Object.keys(loveAnswers.value).length);
const loveProgressPercent = computed(() => Math.round((loveProgress.value / loveQuestions.length) * 100));
const loveDimensionLabels: Record<LoveDimension, string> = {
  warmth: "情绪温度",
  space: "边界留白",
  initiative: "主动推进",
  security: "安全确认",
  depth: "深度连接",
  playfulness: "轻盈火花"
};
const loveScores = computed<Record<LoveDimension, number>>(() => {
  const scores: Record<LoveDimension, number> = { warmth: 0, space: 0, initiative: 0, security: 0, depth: 0, playfulness: 0 };
  for (const question of loveQuestions) {
    const answerIndex = loveAnswers.value[question.id];
    const option = question.options[answerIndex];
    if (!option) continue;
    for (const [key, value] of Object.entries(option.scores)) {
      scores[key as LoveDimension] += value || 0;
    }
  }
  return scores;
});
const loveDimensionEntries = computed(() => Object.entries(loveScores.value) as [LoveDimension, number][]);
const loveDimensionMax = computed<Record<LoveDimension, number>>(() => {
  const maxScores: Record<LoveDimension, number> = { warmth: 0, space: 0, initiative: 0, security: 0, depth: 0, playfulness: 0 };
  for (const question of loveQuestions) {
    for (const dimension of Object.keys(maxScores) as LoveDimension[]) {
      maxScores[dimension] += Math.max(...question.options.map((option) => option.scores[dimension] || 0));
    }
  }
  return maxScores;
});
const profileRanks = computed(() => {
  const scores = loveScores.value;
  const ranks = [
    { id: "harbor", score: scores.security * 1.35 + scores.warmth * 0.7 + scores.depth * 0.35 },
    { id: "spark", score: scores.playfulness * 1.25 + scores.initiative * 1.05 + scores.warmth * 0.25 },
    { id: "garden", score: scores.space * 1.45 + scores.security * 0.35 + scores.depth * 0.25 },
    { id: "lantern", score: scores.warmth * 1.25 + scores.depth * 0.8 + scores.security * 0.25 },
    { id: "compass", score: scores.security * 0.85 + scores.initiative * 0.65 + scores.depth * 0.55 + scores.space * 0.25 },
    { id: "tide", score: scores.depth * 1.45 + scores.space * 0.5 + scores.warmth * 0.35 }
  ];
  return ranks.sort((left, right) => right.score - left.score);
});
const loveResult = computed(() => {
  if (loveProgress.value < loveQuestions.length) return null;
  const top = profileRanks.value[0]?.id || "harbor";
  return loveProfiles.find((profile) => profile.id === top) || loveProfiles[0];
});
const selectedLoveDetail = computed(() => {
  if (!loveResult.value) return "";
  return loveGender.value === "female" ? loveResult.value.femaleDetail : loveResult.value.maleDetail;
});
const loveProfileImageUrl = computed(() => {
  if (!loveResult.value) return "";
  const suffix = loveGender.value === "female" ? "女" : "男";
  return `/personality/${encodeURIComponent(`${loveResult.value.name}${suffix}.png`)}`;
});
const hasCompleteLoveTest = computed(() => loveProgress.value === loveQuestions.length);
const memoryCounts = computed(() => {
  const memories = memoryPane.value?.memories || [];
  return {
    all: memories.length,
    global: memories.filter((memory) => memory.memory_scope === "global").length,
    character: memories.filter((memory) => memory.memory_scope === "character").length,
    session: memories.filter((memory) => memory.memory_scope === "session").length,
    recall: recallCount.value
  };
});
const storyKindLabels: Record<string, string> = {
  motif: "意象",
  story_beat: "瞬间",
  open_thread: "伏笔",
  relationship_texture: "质感",
  boundary: "边界"
};
const storyStatusLabels: Record<string, string> = {
  active: "活跃",
  seed: "种子",
  developed: "已发展",
  archived: "归档"
};
const activeNovelStepIndex = computed(() => {
  if (novelProgressStage.value === "done") return novelPipelineSteps.length;
  if (novelProgressStage.value === "fallback") {
    return Math.max(0, novelPipelineSteps.findIndex((step) => step.id === "drafting"));
  }
  if (novelProgressStage.value === "failed") {
    return Math.max(0, novelPipelineSteps.findIndex((step) => step.id === "drafting"));
  }
  return novelPipelineSteps.findIndex((step) => step.id === novelProgressStage.value);
});
function novelStepClass(step: NovelPipelineStep) {
  const index = novelPipelineSteps.findIndex((item) => item.id === step.id);
  const activeIndex = activeNovelStepIndex.value;
  return {
    active: step.id === novelProgressStage.value || (novelProgressStage.value === "fallback" && step.id === "drafting"),
    done: novelProgressStage.value === "done" || (index >= 0 && index < activeIndex),
    failed: novelProgressStage.value === "failed" && index === activeIndex
  };
}
const activeCanvasBuildStepIndex = computed(() => {
  if (canvasBuildStage.value === "done") return canvasBuildSteps.length;
  if (canvasBuildStage.value === "failed") return Math.max(0, canvasBuildSteps.length - 1);
  return canvasBuildSteps.findIndex((step) => step.id === canvasBuildStage.value);
});
const initialCanvasVersionedChapterCount = computed(() =>
  activeNovelProject.value?.chapters
    .filter((chapter) => chapter.chapter_order <= 4 && Number(chapter.version_count || 0) > 0)
    .length || 0
);
const isInitialCanvasRebuildLocked = computed(() =>
  storyCanvasDraft.value.chapters.length > 0 && initialCanvasVersionedChapterCount.value > 0
);
const canvasBuildActionLabel = computed(() =>
  storyCanvasDraft.value.chapters.length ? "重建初版画布" : "生成初版画布"
);
const canvasFlowMetrics = computed(() => ({
  acts: storyCanvasDraft.value.acts.length,
  chapters: storyCanvasDraft.value.chapters.length,
  scenes: storyCanvasDraft.value.scenes.length,
  threads: storyCanvasDraft.value.threads.length,
  materials: activeNovelProject.value?.materials.length || 0
}));
const canvasSourceLabel = computed(() => {
  const source = String(storyCanvasDraft.value.diagnostics?.source || "");
  if (source === "remote") return "AI 生成";
  if (source === "local") return "本地生成";
  return "未生成";
});
const canvasBuildSummary = computed(() => {
  if (canvasBuildStage.value === "failed") return "画布生成失败，当前编辑内容已保留。";
  if (canvasBuildStage.value === "done") return `画布已生成 ${canvasBuildRunCount.value} 次${canvasBuildLastLabel.value ? ` · ${canvasBuildLastLabel.value}` : ""}`;
  if (canvasBuildStage.value !== "idle") return `${canvasBuildSteps[activeCanvasBuildStepIndex.value]?.detail || "正在生成画布"} · 已等待 ${canvasBuildWaitingSeconds.value}s`;
  if (isInitialCanvasRebuildLocked.value) return `前四章仍有 ${initialCanvasVersionedChapterCount.value} 章版本记录，初版画布已锁定；删除这些章节版本后可重建。`;
  if (storyCanvasDraft.value.chapters.length) return "画布会随章节生成自动滚动更新后续两章；这里可手动微调或大改重建。";
  return "还没有画布，先从素材生成章节、场景和线索。";
});
const isCanvasBuilding = computed(() => !["idle", "done", "failed"].includes(canvasBuildStage.value));
const canvasBuildProgressLabel = computed(() => {
  if (canvasBuildStage.value === "failed") return "生成失败";
  if (canvasBuildStage.value === "done") return "生成完成";
  if (isCanvasBuilding.value) return canvasBuildWaitingSeconds.value > 20
    ? "远程模型仍在规划画布，长篇结构通常需要 1-2 分钟"
    : "正在生成故事画布";
  return "等待生成";
});
const isNovelGenerating = computed(() =>
  !["idle", "done", "failed", "fallback"].includes(novelProgressStage.value)
);
const showActiveNovelProgress = computed(() =>
  activeNovelWorkflowMode.value === novelStudioMode.value
  && (novelProgressVisible.value || novelProgressStage.value === "failed")
);
const novelProgressLabel = computed(() => {
  if (novelProgressStage.value === "failed") return "生成失败";
  if (novelProgressStage.value === "fallback") return "远程正文未返回，已保存本地正文草稿";
  if (novelProgressStage.value === "done") return "正文、状态和后续画布已更新";
  const detail = novelProgressDetail.value || novelPipelineSteps[activeNovelStepIndex.value]?.detail || "等待开始";
  if (isNovelGenerating.value && novelProgressWaitingSeconds.value >= 8) {
    return `${detail} · 已等待 ${novelProgressWaitingSeconds.value}s`;
  }
  return detail;
});
function isTrustedNovelStateDelta(delta: Record<string, unknown> | undefined | null) {
  const source = String(delta?.source || "").trim();
  return !["mock", "manual", "create", "system", "canvas"].includes(source);
}

function chapterBoundHandoff(chapter: NovelChapter): Record<string, unknown> | null {
  const delta = chapter.scene_card?.active_state_delta;
  if (delta && typeof delta === "object" && isTrustedNovelStateDelta(delta as Record<string, unknown>)) {
    const source = String((delta as Record<string, unknown>).handoff_source || chapter.scene_card?.handoff_source || "");
    const handoff = (delta as Record<string, unknown>).chapter_handoff;
    if (handoff && typeof handoff === "object" && !["pending", "skipped_mock", "cleaned_mock"].includes(source)) {
      return handoff as Record<string, unknown>;
    }
  }
  const source = String(chapter.scene_card?.handoff_source || "");
  const handoff = chapter.scene_card?.chapter_handoff;
  if (handoff && typeof handoff === "object" && !["pending", "skipped_mock", "cleaned_mock"].includes(source)) {
    return handoff as Record<string, unknown>;
  }
  return null;
}
const activeNovelPriorStateEntries = computed(() => {
  const project = activeNovelProject.value;
  const currentOrder = activeNovelChapter.value?.chapter_order || 0;
  if (!project || currentOrder <= 1) return [];
  const entries: Array<{ chapter: NovelChapter; handoff: Record<string, unknown> }> = [];
  const chapters = [...project.chapters].sort((a, b) => a.chapter_order - b.chapter_order);
  for (const chapter of chapters) {
    if (chapter.chapter_order >= currentOrder) break;
    if (chapter.chapter_order !== entries.length + 1) break;
    const handoff = chapterBoundHandoff(chapter);
    if (!handoff || !chapter.body.trim() || chapter.status === "affected") break;
    entries.push({ chapter, handoff });
  }
  return entries;
});
const novelStateSummary = computed(() => {
  const entries = activeNovelPriorStateEntries.value;
  if (!entries.length) return "当前章节之前还没有全局摘要。";
  return entries
    .map(({ chapter, handoff }) => {
      const delta = chapter.scene_card?.active_state_delta as Record<string, unknown> | undefined;
      const summary = isTrustedNovelStateDelta(delta) ? String(delta?.summary_delta || chapter.summary || "") : "";
      const happened = Array.isArray(handoff.happened) ? handoff.happened.map((item) => String(item)).filter(Boolean).join("；") : "";
      return `第${chapter.chapter_order}章：${summary || happened}`;
    })
    .filter(Boolean)
    .join(" ");
});
const novelStateOpenThreads = computed(() => {
  const threads: string[] = [];
  for (const { handoff } of activeNovelPriorStateEntries.value) {
    if (Array.isArray(handoff.open_threads)) threads.push(...handoff.open_threads.map((item) => String(item)).filter(Boolean));
    if (Array.isArray(handoff.next_must_continue)) threads.push(...handoff.next_must_continue.map((item) => String(item)).filter(Boolean));
  }
  return [...new Set(threads)].slice(0, 5);
});
const novelStateLastHandoff = computed(() => {
  const entries = activeNovelPriorStateEntries.value;
  return entries.length ? entries[entries.length - 1].handoff : null;
});
const novelStateLastHandoffText = computed(() => {
  const handoff = novelStateLastHandoff.value;
  if (!handoff) return "还没有上一章交接单。";
  const parts = [
    ...(Array.isArray(handoff.happened) ? handoff.happened.map((item) => `已发生：${item}`) : []),
    ...(Array.isArray(handoff.next_must_continue) ? handoff.next_must_continue.map((item) => `下章承接：${item}`) : []),
    ...(Array.isArray(handoff.ending_hook) ? handoff.ending_hook.map((item) => `钩子：${item}`) : [])
  ];
  return parts.map((item) => String(item)).filter(Boolean).slice(0, 4).join("；") || "交接单为空。";
});
const activeNovelProject = computed(() =>
  novelProjects.value.find((project) => project.id === activeNovelProjectId.value) || null
);
const activeNovelChapter = computed(() =>
  activeNovelProject.value?.chapters.find((chapter) => chapter.id === activeNovelChapterId.value) || activeNovelProject.value?.chapters[0] || null
);
const activeCanvasChapter = computed<StoryCanvasChapter | null>(() => {
  const activeOrder = activeNovelChapter.value?.chapter_order || 1;
  return storyCanvasDraft.value.chapters.find((chapter) => chapter.chapter_order === activeOrder) || storyCanvasDraft.value.chapters[0] || null;
});
const activeCanvasScenes = computed<StoryCanvasScene[]>(() => {
  const chapterId = activeCanvasChapter.value?.id || "";
  return storyCanvasDraft.value.scenes.filter((scene) => scene.chapter_id === chapterId);
});
const activeCanvasActionChain = computed(() => {
  const chapter = activeCanvasChapter.value;
  if (!chapter) return [];
  return canvasActionChainFields
    .map((field) => ({ key: field.key, label: field.label, text: String(chapter[field.key] || "").trim() }));
});
const storyBibleEntries = computed(() => {
  const bible = activeNovelProject.value?.story_bible || {};
  return Object.entries(bible).filter(([, items]) => Array.isArray(items) && items.length);
});
const projectMaterialGroups = computed(() => {
  const groups: Record<string, NovelProject["materials"]> = {};
  for (const material of activeNovelProject.value?.materials || []) {
    groups[material.category] = [...(groups[material.category] || []), material];
  }
  return Object.entries(groups);
});
const novelProjectStats = computed(() => {
  const project = activeNovelProject.value;
  if (!project) return { chapters: 0, words: 0, materials: 0 };
  return {
    chapters: project.chapters.length,
    words: project.chapters.reduce((total, chapter) => total + chapter.body.length, 0),
    materials: project.materials.length
  };
});
const activeChapterWordCount = computed(() => chapterDraft.value.body.replace(/\s/g, "").length);
const chapterLengthRatio = computed(() => {
  if (!projectChapterTargetLength.value) return 0;
  return Math.round((activeChapterWordCount.value / projectChapterTargetLength.value) * 100);
});
const chapterLengthGuide = computed(() => {
  const ratio = chapterLengthRatio.value;
  if (!activeChapterWordCount.value) {
    return { tone: "empty", label: "尚未生成", detail: "生成时会按目标长度自动扩写。" };
  }
  if (ratio < 60) {
    return { tone: "short", label: "明显偏短", detail: "建议扩写场景、动作和对白。" };
  }
  if (ratio < 85) {
    return { tone: "near", label: "略短", detail: "可以补一到两个自然段。" };
  }
  if (ratio > 130) {
    return { tone: "long", label: "偏长", detail: "建议压缩重复描写。" };
  }
  return { tone: "ok", label: "接近目标", detail: "长度处在可用范围。" };
});
const chapterQualityDiagnosis = computed(() => {
  const body = chapterDraft.value.body.trim();
  const paragraphs = body.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  const dialogueCount = (body.match(/[“"][^”"]{1,80}[”"]/g) || []).length;
  const hasSceneCard = Object.values(chapterDraft.value.scene_card).some((value) => {
    if (Array.isArray(value)) return value.some((item) => String(item).trim());
    return String(value || "").trim();
  });
  return {
    word_count: activeChapterWordCount.value,
    target_length: projectChapterTargetLength.value,
    length_ratio: chapterLengthRatio.value,
    length_label: chapterLengthGuide.value.label,
    length_detail: chapterLengthGuide.value.detail,
    paragraph_count: paragraphs.length,
    dialogue_count: dialogueCount,
    has_scene_card: hasSceneCard,
    body_empty: !body,
    likely_needs: [
      !body ? "新写完整章节" : "",
      activeChapterWordCount.value > 0 && chapterLengthRatio.value < 70 ? "扩写同一章" : "",
      dialogueCount < 2 ? "补足自然对白" : "",
      paragraphs.length < 4 ? "增加可见动作和场景转折" : "",
      !hasSceneCard ? "先明确场景卡" : ""
    ].filter(Boolean)
  };
});
const editorUpdatedLabel = computed(() => {
  const updated = activeNovelChapter.value?.updated_at || activeNovelProject.value?.updated_at || "";
  return updated ? `已保存于 ${updated}` : "等待创建项目";
});

function loveBarWidth(dimension: LoveDimension, value: number) {
  const max = loveDimensionMax.value[dimension] || 1;
  return Math.min(100, Math.round((value / max) * 100));
}

function setPage(page: PageKey) {
  currentPage.value = page;
}

function answerLoveQuestion(questionId: string, optionIndex: number) {
  const wasComplete = hasCompleteLoveTest.value;
  loveAnswers.value = { ...loveAnswers.value, [questionId]: optionIndex };
  saveLoveAnswers();
  if (!wasComplete && Object.keys(loveAnswers.value).length === loveQuestions.length) {
    showLoveResultModal.value = true;
  }
}

function resetLoveTest() {
  loveAnswers.value = {};
  showLoveResultModal.value = false;
  localStorage.removeItem(loveStorageKey(visitorId.value));
}

function setLoveGender(gender: LoveGender) {
  loveGender.value = gender;
  localStorage.setItem(loveGenderStorageKey(visitorId.value), gender);
}

function loveStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:${id || "anonymous"}`;
}

function loveGenderStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:gender:${id || "anonymous"}`;
}

function characterStorageKey(id: string) {
  return `${CHARACTER_KEY}:${id || "anonymous"}`;
}

function saveLoveAnswers() {
  localStorage.setItem(loveStorageKey(visitorId.value), JSON.stringify({ version: LOVE_TEST_VERSION, answers: loveAnswers.value }));
}

function loadLoveAnswers(id: string) {
  try {
    const raw = localStorage.getItem(loveStorageKey(id));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as { version?: string; answers?: Record<string, number> };
    if (parsed.version !== LOVE_TEST_VERSION || !parsed.answers) return {};
    return Object.fromEntries(Object.entries(parsed.answers).filter(([questionId]) => loveQuestions.some((question) => question.id === questionId)));
  } catch {
    return {};
  }
}

function loadLoveGender(id: string): LoveGender {
  return localStorage.getItem(loveGenderStorageKey(id)) === "male" ? "male" : "female";
}

function refreshLoveTestForVisitor(id: string) {
  loveAnswers.value = loadLoveAnswers(id);
  loveGender.value = loadLoveGender(id);
  showLoveResultModal.value = false;
}

function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines = 8) {
  let line = "";
  let lines = 0;
  for (const char of text) {
    const testLine = line + char;
    if (ctx.measureText(testLine).width > maxWidth && line) {
      ctx.fillText(line, x, y);
      y += lineHeight;
      lines += 1;
      line = char;
      if (lines >= maxLines) return y;
    } else {
      line = testLine;
    }
  }
  if (line && lines < maxLines) {
    ctx.fillText(line, x, y);
    y += lineHeight;
  }
  return y;
}

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
}

async function saveLoveResultImage() {
  if (!loveResult.value) return;
  const profile = loveResult.value;
  try {
    const modalElement = document.querySelector('.love-modal') as HTMLElement | null;
    if (!modalElement) return;

    // 隐藏不想出现在截图里的按钮
    const actionsBlock = document.querySelector('.modal-actions') as HTMLElement | null;
    const closeBtn = document.querySelector('.modal-close') as HTMLElement | null;
    if (actionsBlock) actionsBlock.style.display = 'none';
    if (closeBtn) closeBtn.style.display = 'none';

    // 提升截屏区域样式保证完整度
    // 强制去除滚动条等会导致截图尺寸被截断的问题
    const oldMaxHeight = modalElement.style.maxHeight;
    const oldOverflow = modalElement.style.overflow;
    modalElement.style.maxHeight = 'none';
    modalElement.style.overflow = 'visible';

    const canvas = await html2canvas(modalElement, {
      backgroundColor: '#121511',
      scale: 2, // 高清渲染
      useCORS: true,
      logging: false
    });

    // 恢复原有样式
    modalElement.style.maxHeight = oldMaxHeight;
    modalElement.style.overflow = oldOverflow;
    if (actionsBlock) actionsBlock.style.display = '';
    if (closeBtn) closeBtn.style.display = '';

    const anchor = document.createElement("a");
    anchor.href = canvas.toDataURL("image/png");
    anchor.download = `${profile.name}-${loveGender.value === "female" ? "女" : "男"}-恋爱人格结果.png`;
    anchor.click();
  } catch(e) {
    console.error("生成图片失败: ", e);
  }
}

async function applyLoveProfileToMemory() {
  if (!sessionId.value || !memoryPane.value || !loveResult.value) return;
  const result = loveResult.value;
  const note = [
    memoryPane.value.manual_note,
    `[恋爱人格测试] ${result.memoryLine} 核心需求：${result.relationshipNeed} 角色互动建议：${result.partnerCue}`
  ].filter(Boolean).join("\n");
  manualNoteDraft.value = note;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await patchMemory(sessionId.value, { manual_note: note });
    currentPage.value = "chat";
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    const resolved = await resolveVisitor(visitorId.value);
    visitorId.value = resolved.visitor_id;
    localStorage.setItem(VISITOR_KEY, resolved.visitor_id);
    refreshLoveTestForVisitor(resolved.visitor_id);
    characters.value = await listCharacters();
    const storedCharacterId = localStorage.getItem(characterStorageKey(resolved.visitor_id)) || "";
    selectedCharacterId.value = characters.value.some((character) => character.id === storedCharacterId)
      ? storedCharacterId
      : characters.value[0]?.id || "";
    if (selectedCharacterId.value) {
      await openSession();
    }
  } catch (err) {
    error.value = readableError(err);
  }
});

async function openSession() {
  if (!selectedCharacterId.value || !visitorId.value) return;
  busy.value = true;
  error.value = "";
  try {
    refreshLoveTestForVisitor(visitorId.value);
    localStorage.setItem(characterStorageKey(visitorId.value), selectedCharacterId.value);
    const session = await createSession(visitorId.value, selectedCharacterId.value);
    visitorId.value = session.visitor_id;
    localStorage.setItem(VISITOR_KEY, session.visitor_id);
    localStorage.setItem(characterStorageKey(session.visitor_id), selectedCharacterId.value);
    sessionId.value = session.session_id;
    characterState.value = session.character_state;
    characterBond.value = session.character_bond;
    memoryPane.value = session.memory_pane;
    manualNoteDraft.value = session.memory_pane.manual_note || "";
    promptSlots.value = session.memory_pane.prompt_slots || [];
    messages.value = session.messages?.length
      ? session.messages
      : [{ id: "opening", role: "assistant", content: session.character.opening_line }];
    try {
      storyPane.value = await getStoryPane(session.session_id);
    } catch (err) {
      storyPane.value = {
        session_id: session.session_id,
        items: [],
        diagnostics: { error: readableError(err) },
      };
    }
    await loadNovelProjects();

    await nextTick();
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

function selectCharacter(characterId: string) {
  selectedCharacterId.value = characterId;
  if (visitorId.value) {
    localStorage.setItem(characterStorageKey(visitorId.value), characterId);
  }
  void openSession();
}

function emptyStoryCanvas(): StoryCanvas {
  return {
    version: 1,
    mode: "story_canvas",
    acts: [],
    chapters: [],
    scenes: [],
    threads: [],
    quality_rules: []
  };
}

function stringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  const text = String(value || "").trim();
  return text ? text.split(/[；;]\s*/).map((item) => item.trim()).filter(Boolean) : [];
}

function normalizeStoryCanvas(canvas: unknown): StoryCanvas {
  const raw = (canvas && typeof canvas === "object" ? canvas : {}) as Record<string, unknown>;
  const acts = Array.isArray(raw.acts) ? raw.acts : [];
  const chapters = Array.isArray(raw.chapters) ? raw.chapters : [];
  const scenes = Array.isArray(raw.scenes) ? raw.scenes : [];
  const threads = Array.isArray(raw.threads) ? raw.threads : [];
  return {
    version: Number(raw.version || 1),
    mode: String(raw.mode || "story_canvas"),
    acts: acts.map((item, index) => {
      const act = item as Record<string, unknown>;
      return {
        id: String(act.id || `act_${index + 1}`),
        order: Number(act.order || index + 1),
        title: String(act.title || `阶段 ${index + 1}`),
        purpose: String(act.purpose || ""),
        chapter_ids: stringArray(act.chapter_ids)
      };
    }),
    chapters: chapters.map((item, index) => {
      const chapter = item as Record<string, unknown>;
      return {
        id: String(chapter.id || `canvas_ch_${index + 1}`),
        act_id: String(chapter.act_id || "act_1"),
        chapter_order: Number(chapter.chapter_order || index + 1),
        title: String(chapter.title || `第 ${index + 1} 章`),
        goal: String(chapter.goal || ""),
        external_event: String(chapter.external_event || ""),
        trigger_event: String(chapter.trigger_event || chapter.external_event || ""),
        immediate_reaction: String(chapter.immediate_reaction || ""),
        obstacle_escalation: String(chapter.obstacle_escalation || ""),
        counterpart_reaction: String(chapter.counterpart_reaction || ""),
        character_choice: String(chapter.character_choice || chapter.relationship_shift || ""),
        scene_consequence: String(chapter.scene_consequence || chapter.relationship_shift || ""),
        relationship_shift: String(chapter.relationship_shift || ""),
        ending_hook: String(chapter.ending_hook || ""),
        target_length: Number(chapter.target_length || 1800),
        status: String(chapter.status || "planned") as StoryCanvasChapter["status"],
        emotion_curve: String(chapter.emotion_curve || ""),
        scene_ids: stringArray(chapter.scene_ids),
        completed_summary: String(chapter.completed_summary || ""),
        actual_word_count: Number(chapter.actual_word_count || 0),
        completed_at: String(chapter.completed_at || "")
      };
    }),
    scenes: scenes.map((item, index) => {
      const scene = item as Record<string, unknown>;
      return {
        id: String(scene.id || `scene_${index + 1}`),
        chapter_id: String(scene.chapter_id || ""),
        scene_order: Number(scene.scene_order || index + 1),
        current_scene: String(scene.current_scene || ""),
        pov: String(scene.pov || ""),
        present_characters: String(scene.present_characters || ""),
        surface_event: String(scene.surface_event || ""),
        character_desire: String(scene.character_desire || ""),
        tension: String(scene.tension || ""),
        required_facts: stringArray(scene.required_facts),
        forbidden_progress: stringArray(scene.forbidden_progress),
        ending_beat: String(scene.ending_beat || ""),
        linked_material_ids: stringArray(scene.linked_material_ids)
      };
    }),
    threads: threads.map((item, index) => {
      const thread = item as Record<string, unknown>;
      return {
        id: String(thread.id || `thread_${index + 1}`),
        kind: String(thread.kind || "foreshadowing"),
        label: String(thread.label || ""),
        setup_chapter_id: String(thread.setup_chapter_id || ""),
        payoff_chapter_id: String(thread.payoff_chapter_id || ""),
        status: String(thread.status || "seed"),
        notes: String(thread.notes || "")
      };
    }),
    quality_rules: stringArray(raw.quality_rules),
    diagnostics: (raw.diagnostics && typeof raw.diagnostics === "object" ? raw.diagnostics : {}) as Record<string, unknown>
  };
}

function syncStoryCanvasDraft(project: NovelProject | null) {
  storyCanvasDraft.value = normalizeStoryCanvas(project?.story_canvas);
}

function syncProjectDraft(project: NovelProject | null) {
  projectDraft.value = {
    title: project?.title || "",
    genre: project?.genre || "校园日常长篇",
    tone: project?.tone || "温柔、克制、日常",
    protagonist: project?.protagonist || activeCharacter.value?.name || "",
    worldview: project?.worldview || "",
    relationship_setup: project?.relationship_setup || "",
    outline: project?.outline || ""
  };
  syncStoryCanvasDraft(project);
}

function normalizeSceneCardDraft(sceneCard: Record<string, unknown> | null | undefined): ChapterSceneCardDraft {
  const draft: ChapterSceneCardDraft = {};
  for (const field of sceneCardFields) {
    const value = sceneCard?.[field.key];
    draft[field.key] = Array.isArray(value)
      ? value.map((item) => String(item).trim()).filter(Boolean).join("；")
      : String(value || "").trim();
  }
  return draft;
}

function derivedSceneCardFromCanvasChapter(chapter: StoryCanvasChapter | null | undefined): ChapterSceneCardDraft {
  if (!chapter) return {};
  return {
    surface_event: chapter.trigger_event || chapter.external_event || chapter.goal || "",
    tension: chapter.obstacle_escalation || "",
    ending_beat: chapter.ending_hook || ""
  };
}

function sceneCardDraftFromCanvas(scene: Record<string, unknown> | null | undefined, chapter: StoryCanvasChapter | null | undefined): ChapterSceneCardDraft {
  return {
    ...normalizeSceneCardDraft(scene),
    ...derivedSceneCardFromCanvasChapter(chapter)
  };
}

function currentSceneCardForSave(): ChapterSceneCardDraft {
  return {
    ...chapterDraft.value.scene_card,
    ...derivedSceneCardFromCanvasChapter(activeCanvasChapter.value)
  };
}

function canvasChapterForOrder(canvas: StoryCanvas, order: number) {
  return canvas.chapters.find((chapter) => chapter.chapter_order === order) || canvas.chapters[0] || null;
}

function canvasScenesForChapter(canvas: StoryCanvas, chapter: StoryCanvasChapter | null) {
  const chapterId = chapter?.id || "";
  return canvas.scenes.filter((scene) => scene.chapter_id === chapterId);
}

function canvasFieldText(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean).join("；") || "未设定";
  return String(value || "").trim() || "未设定";
}

function splitSceneDraftList(value: string) {
  return value
    .split(/[；;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function storyCanvasWithChapterDraft(canvas: StoryCanvas, chapter: NovelChapter | null, draft: typeof chapterDraft.value) {
  const nextCanvas = normalizeStoryCanvas(JSON.parse(JSON.stringify(canvas)) as StoryCanvas);
  const order = chapter?.chapter_order || activeCanvasChapter.value?.chapter_order || 1;
  let canvasChapter = canvasChapterForOrder(nextCanvas, order);
  if (!canvasChapter) {
    canvasChapter = {
      id: `canvas_ch_${order}`,
      act_id: nextCanvas.acts[0]?.id || "act_1",
      chapter_order: order,
      title: draft.title || `第${order}章`,
      goal: draft.goal,
      external_event: "",
      trigger_event: "",
      immediate_reaction: "",
      obstacle_escalation: "",
      counterpart_reaction: "",
      character_choice: "",
      scene_consequence: "",
      relationship_shift: "",
      ending_hook: "",
      target_length: projectChapterTargetLength.value,
      status: draft.status,
      emotion_curve: "",
      scene_ids: []
    };
    nextCanvas.chapters.push(canvasChapter);
  }
  canvasChapter.title = draft.title || canvasChapter.title;
  canvasChapter.goal = draft.goal || canvasChapter.goal;
  canvasChapter.target_length = projectChapterTargetLength.value || canvasChapter.target_length;
  canvasChapter.status = draft.status;

  let scene = canvasScenesForChapter(nextCanvas, canvasChapter)[0];
  if (!scene) {
    scene = {
      id: `scene_${order}`,
      chapter_id: canvasChapter.id,
      scene_order: 1,
      current_scene: "",
      pov: "",
      present_characters: "",
      surface_event: "",
      character_desire: "",
      tension: "",
      required_facts: [],
      forbidden_progress: [],
      ending_beat: "",
      linked_material_ids: []
    };
    nextCanvas.scenes.push(scene);
    canvasChapter.scene_ids = [...new Set([...canvasChapter.scene_ids, scene.id])];
  }
  scene.current_scene = draft.scene_card.current_scene || scene.current_scene;
  scene.pov = draft.scene_card.pov || scene.pov;
  scene.present_characters = draft.scene_card.present_characters || scene.present_characters;
  scene.surface_event = canvasChapter.trigger_event || canvasChapter.external_event || draft.goal || scene.surface_event;
  scene.character_desire = draft.scene_card.character_desire || scene.character_desire;
  scene.tension = canvasChapter.obstacle_escalation || scene.tension;
  scene.required_facts = splitSceneDraftList(draft.scene_card.required_facts || "").length
    ? splitSceneDraftList(draft.scene_card.required_facts || "")
    : scene.required_facts;
  scene.forbidden_progress = splitSceneDraftList(draft.scene_card.forbidden_progress || "").length
    ? splitSceneDraftList(draft.scene_card.forbidden_progress || "")
    : scene.forbidden_progress;
  scene.ending_beat = canvasChapter.ending_hook || scene.ending_beat;
  return nextCanvas;
}

async function activeSceneToChapterDraft() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const activeOrder = activeNovelChapter.value?.chapter_order || activeCanvasChapter.value?.chapter_order || 1;
    const savedProject = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
    });
    replaceNovelProject(savedProject);
    syncStoryCanvasDraft(savedProject);
    const savedCanvas = normalizeStoryCanvas(savedProject.story_canvas);
    const canvasChapter = canvasChapterForOrder(savedCanvas, activeOrder);
    const scene = canvasScenesForChapter(savedCanvas, canvasChapter)[0];
    if (!scene || !canvasChapter) return;
    const nextDraft = {
      ...chapterDraft.value,
      title: canvasChapter.title || chapterDraft.value.title,
      goal: canvasChapter.goal || chapterDraft.value.goal,
      scene_card: sceneCardDraftFromCanvas(scene as unknown as Record<string, unknown>, canvasChapter)
    };
    chapterDraft.value = nextDraft;
    projectChapterTargetLength.value = canvasChapter.target_length || projectChapterTargetLength.value;
    if (activeNovelChapter.value) {
      const project = await updateNovelChapter(activeNovelChapter.value.id, {
        title: nextDraft.title,
        goal: nextDraft.goal,
        scene_card: nextDraft.scene_card
      });
      replaceNovelProject(project);
      syncStoryCanvasDraft(project);
      syncChapterDraft(activeNovelChapter.value);
      await loadChapterVersions();
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

function canvasChapterTitle(chapterId: string) {
  return storyCanvasDraft.value.chapters.find((chapter) => chapter.id === chapterId)?.title || chapterId || "未绑定章节";
}

function isInstructionLikeGoal(text: string) {
  const value = text.trim();
  if (!value) return false;
  return [
    "生成模式：",
    "长度要求：",
    "最低可接受长度",
    "场景任务：",
    "扩写策略：",
    "禁止事项：",
    "不要出现“本章",
    "目标长度："
  ].some((marker) => value.includes(marker));
}

function chapterPlotGoal(chapter: NovelChapter | null) {
  const rawGoal = chapter?.goal || "";
  if (rawGoal && !isInstructionLikeGoal(rawGoal)) return rawGoal;
  const canvasGoal = storyCanvasDraft.value.chapters.find((item) => item.chapter_order === chapter?.chapter_order)?.goal || "";
  return canvasGoal || "";
}

function selectCanvasChapter(chapter: StoryCanvasChapter) {
  rememberChapterInstruction();
  const matched = activeNovelProject.value?.chapters.find((item) => item.chapter_order === chapter.chapter_order);
  if (matched) {
    activeNovelChapterId.value = matched.id;
    syncChapterDraft(matched);
  }
}

function rememberChapterInstruction() {
  if (activeInstructionChapterId.value) {
    chapterInstructionsById.value[activeInstructionChapterId.value] = chapterInstruction.value;
  }
}

function syncChapterInstruction(chapter: NovelChapter | null) {
  activeInstructionChapterId.value = chapter?.id || "";
  instructionOptimizationNote.value = "";
  chapterInstruction.value = chapter?.id
    ? chapterInstructionsById.value[chapter.id] || DEFAULT_CHAPTER_INSTRUCTION
    : DEFAULT_CHAPTER_INSTRUCTION;
}

function clearReorderedChapterInstructionCache(project: NovelProject, deletedChapterId: string, deletedOrder: number) {
  const nextCache = { ...chapterInstructionsById.value };
  delete nextCache[deletedChapterId];
  for (const chapter of project.chapters) {
    if (chapter.chapter_order >= deletedOrder) {
      delete nextCache[chapter.id];
    }
  }
  chapterInstructionsById.value = nextCache;
  activeInstructionChapterId.value = "";
  chapterInstruction.value = DEFAULT_CHAPTER_INSTRUCTION;
  instructionOptimizationNote.value = "";
}

function chapterDraftForApi() {
  const sceneCard = currentSceneCardForSave();
  const instruction = chapterInstruction.value.trim();
  if (instruction) {
    sceneCard.generation_instruction = instruction;
  }
  return {
    ...chapterDraft.value,
    scene_card: sceneCard
  };
}

function syncChapterDraft(chapter: NovelChapter | null) {
  rememberChapterInstruction();
  chapterDraft.value = {
    title: chapter?.title || "",
    goal: chapterPlotGoal(chapter),
    summary: chapter?.summary || "",
    body: chapter?.body || "",
    status: chapter?.status || "planned",
    scene_card: sceneCardDraftFromCanvas(chapter?.scene_card, activeCanvasChapter.value)
  };
  syncChapterInstruction(chapter);
}

async function loadNovelProjects() {
  if (!sessionId.value) return;
  try {
    novelProjects.value = await listNovelProjects(sessionId.value);
    if (!activeNovelProjectId.value || !novelProjects.value.some((project) => project.id === activeNovelProjectId.value)) {
      activeNovelProjectId.value = novelProjects.value[0]?.id || "";
    }
    if (!activeNovelChapterId.value || !activeNovelProject.value?.chapters.some((chapter) => chapter.id === activeNovelChapterId.value)) {
      activeNovelChapterId.value = activeNovelProject.value?.chapters[0]?.id || "";
    }
    syncProjectDraft(activeNovelProject.value);
    syncChapterDraft(activeNovelChapter.value);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  }
}

function selectNovelProject(projectId: string) {
  novelStudioMode.value = "project";
  activeNovelProjectId.value = projectId;
  activeNovelChapterId.value = activeNovelProject.value?.chapters[0]?.id || "";
  continuityReport.value = null;
  syncProjectDraft(activeNovelProject.value);
  syncChapterDraft(activeNovelChapter.value);
  void loadChapterVersions();
}

function setNovelStudioMode(mode: NovelStudioMode) {
  novelStudioMode.value = mode;
  if (mode !== "project") {
    novelFocusMode.value = false;
    return;
  }
  if (!activeNovelProjectId.value && novelProjects.value[0]) {
    selectNovelProject(novelProjects.value[0].id);
  }
}

function selectNovelChapter(chapterId: string) {
  activeNovelChapterId.value = chapterId;
  continuityReport.value = null;
  syncChapterDraft(activeNovelChapter.value);
  void loadChapterVersions();
}

function novelChapterStatusLabel(status?: NovelChapterStatus | string) {
  return status ? novelChapterStatusLabels[status as NovelChapterStatus] || status : "计划中";
}

function novelVersionSourceLabel(version: NovelVersion | NovelVersionDisplay) {
  const keys = "sourceKeys" in version && version.sourceKeys.length
    ? version.sourceKeys
    : [version.source || version.version_type || ""].filter(Boolean);
  const preferred = keys.find((key) => key !== "restore") || keys[0] || "";
  return novelVersionSourceLabels[preferred] || preferred || "历史版本";
}

function novelVersionFoldLabel(version: NovelVersionDisplay) {
  if (version.duplicateCount <= 1) return "";
  const restorePart = version.restoreCount ? `，含 ${version.restoreCount} 次恢复` : "";
  return `折叠 ${version.duplicateCount} 条${restorePart}`;
}

function canvasBuildStepClass(index: number) {
  return {
    active: index === activeCanvasBuildStepIndex.value && !["done", "failed", "idle"].includes(canvasBuildStage.value),
    done: canvasBuildStage.value === "done" || index < activeCanvasBuildStepIndex.value,
    failed: canvasBuildStage.value === "failed" && index === activeCanvasBuildStepIndex.value
  };
}

function compactInstructionText(text: string) {
  return text.replace(/\s+/g, " ").replace(/\?+/g, "").trim();
}

function sceneCardInstructionValue(key: string) {
  return compactInstructionText(chapterDraft.value.scene_card[key] || "");
}

function canvasActionInstructionValue(key: CanvasActionKey) {
  return compactInstructionText(String(activeCanvasChapter.value?.[key] || ""));
}

function instructionSection(title: string, lines: string[]) {
  const cleaned = lines.map((line) => line.trim()).filter(Boolean);
  return cleaned.length ? `${title}：\n${cleaned.join("\n")}` : "";
}

function optimizedChapterInstruction() {
  const goal = compactInstructionText(chapterDraft.value.goal) || "承接前文，完成一个具体事件中的关系推进";
  const current = activeChapterWordCount.value;
  const target = Math.max(400, Number(projectChapterTargetLength.value) || 1800);
  const minimum = Math.max(400, Math.round(target * 0.7));
  const ratio = chapterLengthRatio.value;
  const card = {
    currentScene: sceneCardInstructionValue("current_scene"),
    pov: sceneCardInstructionValue("pov"),
    presentCharacters: sceneCardInstructionValue("present_characters"),
    characterDesire: sceneCardInstructionValue("character_desire"),
    requiredFacts: sceneCardInstructionValue("required_facts"),
    forbiddenProgress: sceneCardInstructionValue("forbidden_progress")
  };
  const canvasAction = {
    externalEvent: canvasActionInstructionValue("external_event"),
    triggerEvent: canvasActionInstructionValue("trigger_event"),
    immediateReaction: canvasActionInstructionValue("immediate_reaction"),
    obstacleEscalation: canvasActionInstructionValue("obstacle_escalation"),
    counterpartReaction: canvasActionInstructionValue("counterpart_reaction"),
    characterChoice: canvasActionInstructionValue("character_choice"),
    sceneConsequence: canvasActionInstructionValue("scene_consequence"),
    relationshipShift: canvasActionInstructionValue("relationship_shift"),
    endingHook: canvasActionInstructionValue("ending_hook")
  };
  let mode = "精修当前章";
  let lengthDirective = `当前正文约 ${current} 字，接近目标区间。请保持已有节奏，补强场景连贯性和章节收束。`;
  if (!current) {
    mode = "新写完整章节";
    lengthDirective = "当前正文为空。请直接进入小说场景，写出完整章节，不要写大纲、说明或创作报告。";
  } else if (ratio < 70) {
    mode = "扩写当前章";
    lengthDirective = `当前正文约 ${current} 字，明显低于目标 ${target} 字。请在保留已有事实、语气和人物边界的基础上扩写同一章，不要另起新章，不要跳到后续剧情。`;
  } else if (ratio < 90) {
    mode = "续写并补足当前章";
    lengthDirective = `当前正文约 ${current} 字，略低于目标 ${target} 字。请承接现有正文继续写，并补足动作、对白和场景转折。`;
  } else if (ratio > 130) {
    mode = "压缩精修当前章";
    lengthDirective = `当前正文约 ${current} 字，超过目标 ${target} 字较多。请保留核心事实和最有画面感的动作、对白、情绪落点，压缩重复描写。`;
  }
  const sceneLines = [
    card.currentScene ? `当前场景：${card.currentScene}` : "",
    card.pov ? `视角：${card.pov}` : "",
    card.presentCharacters ? `在场人物：${card.presentCharacters}` : "",
    card.characterDesire ? `人物欲望：${card.characterDesire}` : "",
    card.requiredFacts ? `必须保留事实：${card.requiredFacts}` : "",
    card.forbiddenProgress ? `禁止推进：${card.forbiddenProgress}` : ""
  ];
  const canvasActionLines = [
    canvasAction.externalEvent ? `外部事件：${canvasAction.externalEvent}` : "",
    canvasAction.triggerEvent ? `触发事件：${canvasAction.triggerEvent}` : "",
    canvasAction.immediateReaction ? `即时反应：${canvasAction.immediateReaction}` : "",
    canvasAction.obstacleEscalation ? `阻碍升级：${canvasAction.obstacleEscalation}` : "",
    canvasAction.counterpartReaction ? `对方反应：${canvasAction.counterpartReaction}` : "",
    canvasAction.characterChoice ? `人物选择：${canvasAction.characterChoice}` : "",
    canvasAction.sceneConsequence ? `场景后果：${canvasAction.sceneConsequence}` : "",
    canvasAction.relationshipShift ? `关系变化：${canvasAction.relationshipShift}` : "",
    canvasAction.endingHook ? `结尾钩子：${canvasAction.endingHook}` : ""
  ];
  const sceneTaskLines = sceneLines.some(Boolean) ? sceneLines : [
    "围绕本章剧情概述和画布动作链展开一个连续、可见的校园日常场面。",
    "场景卡只负责镜头、人物欲望、事实边界和禁止推进，不负责另行改写剧情事件。"
  ];
  const actionTaskLines = canvasActionLines.some(Boolean) ? canvasActionLines : [
    "用一个具体外部事件打开场景。",
    "让人物遇到一个不能立刻解决的小阻碍。",
    "安排至少一个人物小选择，并用具体动作收束到可续写的钩子。"
  ];
  return [
    `生成模式：${mode}`,
    instructionSection("信息优先级", [
      "本章剧情概述决定这一章发生什么，是剧情事实和方向，不是写作命令。",
      "画布动作链决定事件推进顺序：先外部事件，再触发反应、阻碍升级、人物选择和结尾钩子。",
      "场景卡决定怎么贴近人物和场景来写：视角、在场人物、人物欲望、必须保留事实和禁止推进。",
      "生成指令只决定写法、篇幅、节奏和质量补救；不得改写本章剧情概述、画布动作链和已确认事实。"
    ]),
    instructionSection("长度要求", [
      `目标长度：${target} 字`,
      `最低可接受长度：${minimum} 字`,
      lengthDirective,
      "如果一次无法写满目标长度，也必须先达到最低可接受长度，并停在可继续续写的自然钩子上。"
    ]),
    instructionSection("本章剧情概述", [goal]),
    instructionSection("画布动作链", actionTaskLines),
    instructionSection("场景镜头与边界", sceneTaskLines),
    instructionSection("场景展开顺序", [
      "先按画布动作链里的外部事件或触发事件打开场景；如果画布缺失，再用雨势、铃声、旁人经过、物件掉落或时间被打断补足。",
      "再写人物的即时动作和克制反应，让读者看见她想处理什么、又为什么不能马上处理；不要把阻碍写成分析句。",
      "中段用短对白和动作来推进，不用解释关系变化；对白之间穿插物件、视线、距离和环境声。",
      "结尾优先收在画布动作链的结尾钩子上；如果缺失，再收在一个可继续写的动作、物件或未问出口的问题上。"
    ]),
    instructionSection("长度与节奏", [
      `正文目标约 ${target} 字，最低先达到 ${minimum} 字；如果当前只有 ${current} 字，优先扩写同一场景内部的动作链和对白，不另起新章。`,
      "建议把篇幅分给：场景进入约 20%，事件展开约 35%，对白与选择约 30%，结尾钩子约 15%。",
      "每 2-3 段必须有一个可见动作或环境变化，避免连续心理抒情。"
    ]),
    instructionSection("扩写策略", [
      "保留已有正文事实、语气和人物边界。",
      "增加 2-3 个可见动作节点，例如停顿、递还物品、整理书页、避开旁人、走廊里的短暂打断。",
      "增加至少 2 轮自然对白；对白要短，不要把人物心意说满。",
      "增加环境变化推动节奏，例如光线变化、铃声、脚步声、旁人经过、门被关上。",
      "让主角做一个小选择，例如没有立刻离开、主动补一句话、收好某个物件、回头确认对方反应。",
      canvasAction.endingHook ? "结尾必须停在画布动作链的结尾钩子附近。" : "结尾必须停在一个具体可续写的动作、物件或未说完的话上。"
    ]),
    "",
    instructionSection("禁止事项", [
      "不要出现“本章剧情概述”“场景卡”“人物欲望”“阻碍/张力”“作为伏笔”等元叙述。",
      "不要直接写“他们关系变近了”“两人还不熟”“这是后续剧情的伏笔”。",
      "不要突然表白、承诺、亲密越界。",
      "不要重复已有段落。",
      "不要把剧情标签、素材列表、内部字段名或编号写进正文。"
    ])
  ].filter(Boolean).join("\n\n");
}

async function applyOptimizedChapterInstruction() {
  const baseInstruction = optimizedChapterInstruction();
  chapterInstruction.value = baseInstruction;
  if (activeInstructionChapterId.value) {
    chapterInstructionsById.value[activeInstructionChapterId.value] = baseInstruction;
  }
  instructionOptimizationNote.value = "已生成本地硬约束骨架，正在请求远程导演优化。";
  if (!activeNovelProject.value || isOptimizingInstruction.value) {
    instructionOptimizationNote.value = activeNovelProject.value ? "正在优化中。" : "当前没有长篇项目，已使用本地骨架。";
    return;
  }
  isOptimizingInstruction.value = true;
  try {
    const result = await optimizeNovelInstruction(activeNovelProject.value.id, {
      chapter_id: activeNovelChapter.value?.id || null,
      base_instruction: baseInstruction,
      title: chapterDraft.value.title,
      goal: chapterDraft.value.goal,
      summary: chapterDraft.value.summary,
      body: chapterDraft.value.body,
      status: chapterDraft.value.status,
      scene_card: chapterDraft.value.scene_card,
      canvas_chapter: activeCanvasChapter.value ? { ...activeCanvasChapter.value } as unknown as Record<string, unknown> : {},
      previous_handoff: novelStateLastHandoff.value || {},
      prior_novel_state: {
        summary: novelStateSummary.value,
        open_threads: novelStateOpenThreads.value,
        completed_chapters: activeNovelPriorStateEntries.value.map(({ chapter }) => ({
          chapter_order: chapter.chapter_order,
          title: chapter.title,
          summary: chapter.summary,
          status: chapter.status
        }))
      },
      quality_diagnosis: chapterQualityDiagnosis.value,
      target_length: projectChapterTargetLength.value
    });
    chapterInstruction.value = result.instruction || baseInstruction;
    if (activeInstructionChapterId.value) {
      chapterInstructionsById.value[activeInstructionChapterId.value] = chapterInstruction.value;
    }
    instructionOptimizationNote.value = result.source === "remote"
      ? "远程导演优化已应用。"
      : `远程优化不可用，已保留本地骨架${result.diagnostics?.reason ? `：${result.diagnostics.reason}` : "。"}`;
  } catch (err) {
    chapterInstruction.value = baseInstruction;
    if (activeInstructionChapterId.value) {
      chapterInstructionsById.value[activeInstructionChapterId.value] = chapterInstruction.value;
    }
    instructionOptimizationNote.value = `远程优化失败，已保留本地骨架：${readableError(err)}`;
  } finally {
    isOptimizingInstruction.value = false;
  }
}

async function createLongNovelProject() {
  if (!sessionId.value || novelProjectBusy.value) return;
  novelStudioMode.value = "project";
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await createNovelProject(sessionId.value, {
      title: projectDraft.value.title || undefined,
      genre: projectDraft.value.genre,
      tone: projectDraft.value.tone,
      protagonist: projectDraft.value.protagonist || activeCharacter.value?.name || "",
      worldview: projectDraft.value.worldview,
      relationship_setup: projectDraft.value.relationship_setup,
      outline: projectDraft.value.outline,
      story_canvas: storyCanvasDraft.value
    });
    novelProjects.value = [project, ...novelProjects.value.filter((item) => item.id !== project.id)];
    selectNovelProject(project.id);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function saveNovelProject() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
    });
    replaceNovelProject(project);
    syncStoryCanvasDraft(project);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function rebuildStoryCanvas() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  if (isInitialCanvasRebuildLocked.value) {
    error.value = "已有正文后不能重建初版画布。请通过生成/续写当前章来滚动更新后续两章画布。";
    return;
  }
  novelProjectBusy.value = true;
  error.value = "";
  beginCanvasBuildFlow();
  try {
    const savedProject = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value
    });
    replaceNovelProject(savedProject);
    const project = await buildStoryCanvas(savedProject.id);
    replaceNovelProject(project);
    syncProjectDraft(project);
    syncChapterDraft(activeNovelChapter.value);
    finishCanvasBuildFlow();
  } catch (err) {
    clearCanvasBuildTimers();
    canvasBuildStage.value = "failed";
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function saveStoryCanvas() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
    });
    replaceNovelProject(project);
    syncStoryCanvasDraft(project);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function addNovelChapter() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelStudioMode.value = "project";
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await createNovelChapter(activeNovelProject.value.id, {
      title: "新章节",
      goal: "承接前文，完成一个具体事件中的关系推进。",
      status: "planned"
    });
    replaceNovelProject(project);
    activeNovelChapterId.value = project.chapters[project.chapters.length - 1]?.id || "";
    syncChapterDraft(activeNovelChapter.value);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function deleteActiveNovelChapter() {
  if (!activeNovelProject.value || !activeNovelChapter.value || novelProjectBusy.value) return;
  const chapter = activeNovelChapter.value;
  if (!window.confirm(`删除「${chapter.title || `第 ${chapter.chapter_order} 章`}」？章节正文和版本记录都会删除，后续章节会重新编号并标记受影响。`)) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const deletedOrder = chapter.chapter_order;
    const project = await deleteNovelChapter(chapter.id);
    replaceNovelProject(project);
    syncStoryCanvasDraft(project);
    clearReorderedChapterInstructionCache(project, chapter.id, deletedOrder);
    const nextChapter = project.chapters.find((item) => item.chapter_order >= deletedOrder) || project.chapters[project.chapters.length - 1] || null;
    activeNovelChapterId.value = nextChapter?.id || "";
    syncChapterDraft(activeNovelChapter.value);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function saveNovelChapter() {
  if (!activeNovelProject.value || !activeNovelChapter.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const syncedCanvas = storyCanvasWithChapterDraft(storyCanvasDraft.value, activeNovelChapter.value, chapterDraft.value);
    storyCanvasDraft.value = syncedCanvas;
    await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: syncedCanvas
    });
    const project = await updateNovelChapter(activeNovelChapter.value.id, chapterDraftForApi());
    replaceNovelProject(project);
    syncStoryCanvasDraft(project);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function generateActiveChapter() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  const runId = ++novelGenerationRunId;
  novelStudioMode.value = "project";
  novelProjectBusy.value = true;
  error.value = "";
  beginNovelProgress("project");
  try {
    const generatingChapterId = activeNovelChapter.value?.id || "";
    const savedProject = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
    });
    if (runId !== novelGenerationRunId) return;
    replaceNovelProject(savedProject);
    if (activeNovelChapter.value) {
      const syncedProject = await updateNovelChapter(activeNovelChapter.value.id, chapterDraftForApi());
      if (runId !== novelGenerationRunId) return;
      replaceNovelProject(syncedProject);
    }
    const liveChapterId = activeNovelChapter.value?.id || generatingChapterId;
    if (liveChapterId) {
      void pollLiveNovelProgress(runId, activeNovelProject.value.id, liveChapterId);
    }
    const project = await generateProjectChapter(
      activeNovelProject.value.id,
      activeNovelChapter.value?.id || null,
      chapterInstruction.value,
      projectChapterTargetLength.value
    );
    if (runId !== novelGenerationRunId) return;
    replaceNovelProject(project);
    syncProjectDraft(project);
    if (!activeNovelChapterId.value) {
      activeNovelChapterId.value = project.chapters[project.chapters.length - 1]?.id || "";
    }
    syncChapterDraft(activeNovelChapter.value);
    await loadChapterVersions();
    const generatedChapter = project.chapters.find((chapter) => chapter.id === (generatingChapterId || activeNovelChapterId.value)) || activeNovelChapter.value;
    applyChapterGenerationProgress(generatedChapter);
    if (chapterUsedLocalFallback(generatedChapter)) {
      clearNovelProgressTimers();
      setNovelProgress("fallback", 100);
    } else if (chapterHasBackgroundPostprocess(generatedChapter)) {
      setNovelProgress("handoff", 96);
      pollChapterPostprocess(project.id, generatedChapter?.id || activeNovelChapterId.value);
    } else {
      clearNovelProgressTimers();
      setNovelProgress("done", 100);
    }
  } catch (err) {
    if (runId !== novelGenerationRunId) return;
    error.value = readableError(err);
    clearNovelProgressTimers();
    setNovelProgress("failed", 100);
  } finally {
    if (runId === novelGenerationRunId) {
      novelProjectBusy.value = false;
    }
  }
}

async function checkActiveContinuity() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    continuityReport.value = await checkNovelContinuity(activeNovelProject.value.id, activeNovelChapter.value?.id || null);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function loadChapterVersions() {
  if (!activeNovelChapter.value) {
    chapterVersions.value = [];
    return;
  }
  try {
    chapterVersions.value = await listNovelVersions(activeNovelChapter.value.id);
  } catch {
    chapterVersions.value = [];
  }
}

async function pollChapterPostprocess(projectId: string, chapterId: string) {
  for (let attempt = 0; attempt < 24; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 5000));
    if (!activeNovelProject.value || activeNovelProject.value.id !== projectId) return;
    try {
      const project = await getNovelProject(projectId);
      replaceNovelProject(project);
      syncProjectDraft(project);
      const chapter = project.chapters.find((item) => item.id === chapterId);
      applyChapterGenerationProgress(chapter);
      const status = chapterPostprocessStatus(chapter);
      if (status === "handoff_done") {
        setNovelProgress("replan", Math.max(novelProgressPercent.value, 96), novelProgressDetail.value || "后台滚动重规划后续两章画布和场景卡");
      }
      if (status === "done") {
        clearNovelProgressTimers();
        setNovelProgress("done", 100, "正文、状态和后续画布已更新");
        syncChapterDraft(activeNovelChapter.value);
        await loadChapterVersions();
        return;
      }
      if (status === "failed") {
        clearNovelProgressTimers();
        setNovelProgress("failed", 100, novelProgressDetail.value);
        error.value = "正文已返回，但后台交接或滚动画布失败。可以稍后重新生成或刷新项目。";
        return;
      }
    } catch (err) {
      error.value = `正文已返回；后台状态刷新失败：${readableError(err)}`;
      return;
    }
  }
  error.value = "正文已返回；后台交接仍在运行，可以继续编辑或稍后刷新查看 Novel State。";
}

async function restoreVersion(versionId: string) {
  if (novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await restoreNovelVersion(versionId);
    replaceNovelProject(project);
    syncChapterDraft(activeNovelChapter.value);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function deleteVersion(versionId: string) {
  if (novelProjectBusy.value) return;
  if (!window.confirm("删除这个版本记录？当前章节正文不会被删除。")) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await deleteNovelVersion(versionId);
    replaceNovelProject(project);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

function replaceNovelProject(project: NovelProject) {
  const index = novelProjects.value.findIndex((item) => item.id === project.id);
  if (index >= 0) {
    novelProjects.value.splice(index, 1, project);
  } else {
    novelProjects.value.unshift(project);
  }
  activeNovelProjectId.value = project.id;
}

async function submit() {
  const text = draft.value.trim();
  if (!text || !sessionId.value || busy.value) return;
  const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: text };
  messages.value.push(optimistic);
  draft.value = "";
  busy.value = true;
  error.value = "";

  await nextTick();
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
  }

  try {
    const response = await sendMessage(visitorId.value, sessionId.value, text);
    messages.value.push(response.message);
    characterState.value = response.character_state;
    characterBond.value = response.character_bond;
    memoryPane.value = response.memory_pane;
    manualNoteDraft.value = response.memory_pane.manual_note || "";
    promptSlots.value = response.prompt_slots;
    void maybeAutoRefreshStoryTags();

    await nextTick();
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function saveMemoryNote() {
  if (!sessionId.value || !memoryPane.value) return;
  busy.value = true;
  try {
    memoryPane.value = await patchMemory(sessionId.value, { manual_note: manualNoteDraft.value });
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function toggleFreeze() {
  if (!sessionId.value || !memoryPane.value) return;
  busy.value = true;
  try {
    memoryPane.value = await patchMemory(sessionId.value, { frozen: !memoryPane.value.frozen });
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function clearNovelProgressTimers() {
  for (const timer of novelProgressTimers) {
    window.clearTimeout(timer);
  }
  novelProgressTimers = [];
  if (novelProgressTicker !== null) {
    window.clearInterval(novelProgressTicker);
    novelProgressTicker = null;
  }
}

function setNovelProgress(stage: NovelProgressStage, percent: number, detail = "") {
  novelProgressStage.value = stage;
  novelProgressPercent.value = percent;
  novelProgressDetail.value = detail;
}

function asNovelProgressStage(value: unknown): NovelProgressStage | null {
  const stage = String(value || "");
  return novelPipelineSteps.some((step) => step.id === stage) || ["idle", "fallback", "done", "failed"].includes(stage)
    ? stage as NovelProgressStage
    : null;
}

function applyChapterGenerationProgress(chapter: NovelChapter | null | undefined) {
  const progress = chapter?.scene_card?.generation_progress;
  if (!progress || typeof progress !== "object") return false;
  const raw = progress as Record<string, unknown>;
  const stage = asNovelProgressStage(raw.stage);
  if (!stage) return false;
  const percent = Number(raw.percent);
  const detail = typeof raw.detail === "string" ? raw.detail : "";
  setNovelProgress(stage, Number.isFinite(percent) ? Math.max(0, Math.min(100, Math.round(percent))) : novelProgressPercent.value, detail);
  return true;
}

async function pollLiveNovelProgress(runId: number, projectId: string, chapterId: string) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    if (runId !== novelGenerationRunId) return;
    if (["done", "fallback", "failed"].includes(novelProgressStage.value)) return;
    try {
      const project = await getNovelProject(projectId);
      if (runId !== novelGenerationRunId) return;
      replaceNovelProject(project);
      const chapter = project.chapters.find((item) => item.id === chapterId);
      applyChapterGenerationProgress(chapter);
    } catch {
      return;
    }
  }
}

function chapterUsedLocalFallback(chapter: NovelChapter | null | undefined) {
  const audit = chapter?.scene_card?.chapter_audit;
  return Boolean(
    audit
    && typeof audit === "object"
    && "global_state_skipped" in audit
    && (audit as Record<string, unknown>).global_state_skipped
  );
}

function chapterPostprocessStatus(chapter: NovelChapter | null | undefined) {
  const postprocess = chapter?.scene_card?.postprocess;
  if (!postprocess || typeof postprocess !== "object") return "";
  return String((postprocess as Record<string, unknown>).status || "");
}

function chapterHasBackgroundPostprocess(chapter: NovelChapter | null | undefined) {
  return ["pending", "running", "handoff_done"].includes(chapterPostprocessStatus(chapter));
}

function beginNovelProgress(mode: NovelWorkflowMode) {
  clearNovelProgressTimers();
  activeNovelWorkflowMode.value = mode;
  novelProgressVisible.value = true;
  novelProgressWaitingSeconds.value = 0;
  setNovelProgress("collecting", 12, mode === "project" ? "等待后端返回真实阶段" : "");
  if (mode === "quick") {
    novelProgressTimers.push(window.setTimeout(() => setNovelProgress("state", 22), 180));
    novelProgressTimers.push(window.setTimeout(() => setNovelProgress("drafting", 58), 520));
    novelProgressTimers.push(window.setTimeout(() => setNovelProgress("local_check", 78), 1200));
  }
  novelProgressTicker = window.setInterval(() => {
    novelProgressWaitingSeconds.value += 1;
  }, 1000);
}

function unlockNovelProgress() {
  novelGenerationRunId += 1;
  novelProjectBusy.value = false;
  clearNovelProgressTimers();
  setNovelProgress("failed", 100);
  error.value = "已解除前端生成锁定。如果后端稍后完成，刷新项目即可查看最新章节。";
}

function clearCanvasBuildTimers() {
  for (const timer of canvasBuildTimers) {
    window.clearTimeout(timer);
  }
  canvasBuildTimers = [];
  if (canvasBuildTicker !== null) {
    window.clearInterval(canvasBuildTicker);
    canvasBuildTicker = null;
  }
}

function beginCanvasBuildFlow() {
  clearCanvasBuildTimers();
  storyCanvasView.value = "flow";
  canvasBuildPercent.value = 8;
  canvasBuildWaitingSeconds.value = 0;
  canvasBuildStage.value = "materials";
  canvasBuildTimers.push(window.setTimeout(() => { canvasBuildStage.value = "structure"; canvasBuildPercent.value = 22; }, 220));
  canvasBuildTimers.push(window.setTimeout(() => { canvasBuildStage.value = "chapters"; canvasBuildPercent.value = 42; }, 700));
  canvasBuildTimers.push(window.setTimeout(() => { canvasBuildStage.value = "scenes"; canvasBuildPercent.value = 62; }, 1500));
  canvasBuildTimers.push(window.setTimeout(() => { canvasBuildStage.value = "threads"; canvasBuildPercent.value = 78; }, 2600));
  canvasBuildTicker = window.setInterval(() => {
    canvasBuildWaitingSeconds.value += 1;
    if (canvasBuildPercent.value < 94) {
      const step = canvasBuildWaitingSeconds.value < 20 ? 1.2 : 0.35;
      canvasBuildPercent.value = Math.min(94, Math.round((canvasBuildPercent.value + step) * 10) / 10);
    }
  }, 1000);
}

function finishCanvasBuildFlow() {
  clearCanvasBuildTimers();
  canvasBuildStage.value = "done";
  canvasBuildPercent.value = 100;
  canvasBuildRunCount.value += 1;
  canvasBuildLastLabel.value = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function startEditMemory(memory: MemoryItem) {
  editingMemoryId.value = memory.id;
  memoryDraft.value = {
    memory_type: memory.memory_type,
    memory_scope: memory.memory_scope,
    content: memory.content,
    confidence: memory.confidence,
    importance: memory.importance
  };
}

function cancelEditMemory() {
  editingMemoryId.value = "";
  memoryDraft.value = {};
}

async function saveMemoryItem(memoryId: string) {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await updateMemoryItem(sessionId.value, memoryId, memoryDraft.value);
    cancelEditMemory();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function removeMemoryItem(memoryId: string) {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await deleteMemoryItem(sessionId.value, memoryId);
    if (editingMemoryId.value === memoryId) cancelEditMemory();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

function toggleMemoryDetails(memoryId: string) {
  expandedMemoryId.value = expandedMemoryId.value === memoryId ? "" : memoryId;
}

function toggleSlotDetails(slotKey: string) {
  expandedSlotKey.value = expandedSlotKey.value === slotKey ? "" : slotKey;
}

async function exportDebugBundle() {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    const payload = await exportSession(sessionId.value);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `campus-pulse-${sessionId.value}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function generateNovelDraft() {
  if (!sessionId.value) return;
  novelStudioMode.value = "quick";
  busy.value = true;
  error.value = "";
  novelResult.value = null;
  beginNovelProgress("quick");
  try {
    novelResult.value = await generateNovel(sessionId.value, {
      message_limit: novelMessageLimit.value,
      perspective: novelPerspective.value,
      form: novelForm.value,
      fidelity: novelFidelity.value,
      atmosphere: novelAtmosphere.value,
      target_length: novelTargetLength.value
    });
    clearNovelProgressTimers();
    setNovelProgress("done", 100);
  } catch (err) {
    error.value = readableError(err);
    clearNovelProgressTimers();
    setNovelProgress("failed", 100);
  } finally {
    busy.value = false;
  }
}

function currentUserMessageCount() {
  return messages.value.filter((message) => message.role === "user").length;
}

async function maybeAutoRefreshStoryTags() {
  if (!sessionId.value || storyBusy.value) return;
  const userMessageCount = currentUserMessageCount();
  if (userMessageCount < STORY_AUTO_REFRESH_USER_INTERVAL) return;
  if (userMessageCount % STORY_AUTO_REFRESH_USER_INTERVAL !== 0) return;
  if (lastAutoStoryRefreshUserCount.value === userMessageCount) return;
  lastAutoStoryRefreshUserCount.value = userMessageCount;
  await refreshStoryTags({ silent: true });
}

async function refreshStoryTags(options: StoryRefreshOptions = {}) {
  if (!sessionId.value || storyBusy.value) return;
  storyBusy.value = true;
  if (!options.silent) {
    error.value = "";
  }
  try {
    storyPane.value = await refreshStoryPane(sessionId.value);
    lastAutoStoryRefreshUserCount.value = currentUserMessageCount();
  } catch (err) {
    if (!options.silent) {
      error.value = readableError(err);
    }
  } finally {
    storyBusy.value = false;
  }
}

function downloadNovelMarkdown() {
  if (!novelResult.value) return;
  const used = novelResult.value.used_memories.length
    ? novelResult.value.used_memories.map((item) => `- ${item}`).join("\n")
    : "- 暂无";
  const markdown = [
    `# ${novelResult.value.title}`,
    "",
    novelResult.value.synopsis,
    "",
    novelResult.value.body,
    "",
    "## 使用依据",
    used
  ].join("\n");
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${novelResult.value.title || "会话小说"}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadNovelProjectMarkdown() {
  if (!activeNovelProject.value) return;
  const project = activeNovelProject.value;
  const chapters = project.chapters.map((chapter) => [
    `## 第 ${chapter.chapter_order} 章 ${chapter.title}`,
    "",
    chapter.summary,
    "",
    chapter.body || "_未写正文_"
  ].join("\n")).join("\n\n");
  const markdown = [
    `# ${project.title}`,
    "",
    `类型：${project.genre}`,
    `基调：${project.tone}`,
    `主角：${project.protagonist}`,
    "",
    "## 世界观",
    project.worldview,
    "",
    "## 关系设定",
    project.relationship_setup,
    "",
    "## 大纲",
    project.outline,
    "",
    chapters
  ].join("\n");
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${project.title || "小说项目"}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <main class="shell" :class="{ 'test-shell': currentPage === 'love-test' || currentPage === 'novel', 'novel-focus-shell': currentPage === 'novel' && novelFocusMode }">
    <aside class="left-panel">
      <div class="brand">
        <span class="brand-mark"></span>
        <div>
          <h1>Campus Pulse Lite</h1>
          <p>persona memory lab</p>
        </div>
      </div>

      <nav class="page-nav">
        <button :class="{ active: currentPage === 'chat' }" @click="setPage('chat')">聊天</button>
        <button :class="{ active: currentPage === 'love-test' }" @click="setPage('love-test')">恋爱人格测试</button>
        <button :class="{ active: currentPage === 'novel' }" @click="setPage('novel')">小说工坊</button>
      </nav>

      <label v-if="currentPage === 'chat' || currentPage === 'novel'" class="field">
        <span>Visitor ID</span>
        <input v-model="visitorId" @change="openSession" spellcheck="false" />
      </label>

      <section v-if="currentPage === 'chat' || currentPage === 'novel'" class="character-list">
        <button
          v-for="character in characters"
          :key="character.id"
          class="character-row"
          :class="{ active: character.id === selectedCharacterId }"
          @click="selectCharacter(character.id)"
        >
          <span class="portrait" :style="{ '--accent': character.visual?.accent || '#8da2c8' }"></span>
          <span>
            <strong>{{ character.name }}</strong>
            <small>{{ character.archetype }}</small>
          </span>
        </button>
      </section>

      <section v-if="currentPage === 'chat' && activeCharacter" class="character-brief">
        <p class="eyebrow">Character Card</p>
        <h3>{{ activeCharacter.name }}</h3>
        <p>{{ activeCharacter.personality || activeCharacter.bio }}</p>
        <dl>
          <div>
            <dt>Scenario</dt>
            <dd>{{ activeCharacter.scenario || "校园轻陪伴聊天" }}</dd>
          </div>
          <div>
            <dt>Rhythm</dt>
            <dd>{{ activeCharacter.voice?.sentence_rhythm || activeCharacter.speech_style }}</dd>
          </div>
          <div>
            <dt>Dynamic Action</dt>
            <dd>{{ activeCharacter.interaction_policy?.action_style || "按当前语境动态生成，低密度，不抢话" }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="currentPage === 'love-test'" class="character-brief">
        <p class="eyebrow">Love Type</p>
        <h3>相处风格校准</h3>
        <p>这不是严肃诊断，也不会替角色推进剧情。它只把你的偏好转成可解释的互动建议。</p>
        <div class="gender-toggle">
          <button :class="{ active: loveGender === 'female' }" @click="setLoveGender('female')">女性画像</button>
          <button :class="{ active: loveGender === 'male' }" @click="setLoveGender('male')">男性画像</button>
        </div>
        <div v-if="loveResult" class="love-type-art" :style="{ backgroundImage: `url('${loveProfileImageUrl}')` }">
          <span>{{ loveResult.name }}</span>
        </div>
        <div v-else class="love-type-art pending">
          <span>答完后生成画像</span>
        </div>
        <dl>
          <div>
            <dt>Progress</dt>
            <dd>{{ loveProgress }} / {{ loveQuestions.length }}</dd>
          </div>
          <div>
            <dt>Apply</dt>
            <dd>完成后可写入手动记忆，让当前角色知道怎样靠近你更舒服。</dd>
          </div>
        </dl>
      </section>

      <section v-if="currentPage === 'novel' && activeCharacter" class="character-brief">
        <p class="eyebrow">Novel Studio</p>
        <h3>{{ activeCharacter.name }} · 会话改编</h3>
        <p>把当前角色会话改编成短篇、番外或章节开头。生成会参考角色卡、会话记录、记忆和关系档案。</p>
        <dl>
          <div>
            <dt>Source</dt>
            <dd>{{ messages.length }} 条消息 · {{ memoryPane?.memories.length || 0 }} 条记忆</dd>
          </div>
          <div>
            <dt>Boundary</dt>
            <dd>允许文学化氛围，不制造原会话没有发生的重大关系进展。</dd>
          </div>
        </dl>
      </section>
    </aside>

    <section v-if="currentPage === 'chat'" class="chat-panel">
      <header class="chat-header" v-if="activeCharacter">
        <div>
          <p class="eyebrow">{{ activeCharacter.archetype }}</p>
          <h2>{{ activeCharacter.name }}</h2>
          <span>{{ activeCharacter.tagline }}</span>
          <div v-if="characterBond" class="header-growth">
            <small>{{ characterBond.familiarity_stage }}</small>
            <small>Resonance {{ bondPercent }}%</small>
          </div>
        </div>
        <div class="header-actions">
          <button class="ghost muted" @click="exportDebugBundle">Export</button>
          <div class="status" :class="{ busy }">{{ busy ? "thinking" : "ready" }}</div>
        </div>
      </header>

      <div class="message-list" ref="messageListRef">
        <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <span>{{ message.role === "user" ? "你" : activeCharacter?.name || "角色" }}</span>
          <p>{{ message.content }}</p>
        </article>
      </div>

      <form class="composer" @submit.prevent="submit">
        <textarea
          v-model="draft"
          :disabled="busy"
          rows="3"
          placeholder="输入这一轮想说的话"
          @keydown.enter.exact.prevent="submit"
        />
        <button :disabled="busy || !draft.trim()">Send</button>
      </form>

      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section v-else-if="currentPage === 'love-test'" class="love-test-panel">
      <header class="love-hero" :class="{ 'no-progress': true }">
        <div>
          <p class="eyebrow">Love Type Calibration</p>
          <h2>恋爱人格测试</h2>
          <p>用 20 道轻量选择题，把“我希望怎样被靠近”变成角色能使用的相处偏好。</p>
        </div>
      </header>

      <section class="love-layout">
        <div class="love-questions">
          <article v-for="(question, index) in loveQuestions" :key="question.id" class="love-question">
            <div class="question-title">
              <span>{{ String(index + 1).padStart(2, "0") }}</span>
              <h3>{{ question.title }}</h3>
            </div>
            <div class="love-options">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="option.label"
                :class="{ selected: loveAnswers[question.id] === optionIndex }"
                @click="answerLoveQuestion(question.id, optionIndex)"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.text }}</small>
              </button>
            </div>
          </article>
        </div>

        <aside class="love-result">
          <div class="love-progress">
            <span>{{ loveProgressPercent }}%</span>
            <i><b :style="{ width: `${loveProgressPercent}%` }"></b></i>
          </div>
          <p class="eyebrow">Progress</p>
          <h3>{{ hasCompleteLoveTest ? "测试完成" : `还差 ${loveQuestions.length - loveProgress} 题` }}</h3>
          <p>结果会在全部答完后以弹窗展示，避免提前暴露类型影响选择。</p>
          <div class="dimension-bars">
            <label v-for="[dimension, value] in loveDimensionEntries" :key="dimension">
              <span>{{ loveDimensionLabels[dimension] }} {{ value }}</span>
              <i><b :style="{ width: `${loveBarWidth(dimension, value)}%` }"></b></i>
            </label>
          </div>
          <button v-if="hasCompleteLoveTest" class="wide" @click="showLoveResultModal = true">查看结果</button>
          <button class="ghost muted" @click="resetLoveTest">重新测试</button>
          <p v-if="error" class="error">{{ error }}</p>
        </aside>
      </section>
    </section>

    <section v-else class="novel-panel project-mode">
      <header class="novel-header">
        <div>
          <p class="eyebrow">Novel Studio</p>
          <h2>小说工坊</h2>
          <p>快速短篇保留原有入口；长篇项目会沉淀素材、规划章节、保存版本并做连续性检查。</p>
        </div>
        <div class="novel-header-tools">
          <div v-if="novelStudioMode !== 'select'" class="novel-mode-tabs" aria-label="小说模式">
            <button type="button" :class="{ active: novelStudioMode === 'quick' }" @click="setNovelStudioMode('quick')">短篇</button>
            <button type="button" :class="{ active: novelStudioMode === 'project' }" @click="setNovelStudioMode('project')">长篇</button>
            <button type="button" class="ghost muted" @click="setNovelStudioMode('select')">选择</button>
          </div>
          <div v-if="novelStudioMode === 'project'" class="novel-stats">
            <span>{{ novelProjectStats.chapters }} 章</span>
            <span>{{ novelProjectStats.materials }} 条素材</span>
            <span>{{ novelProjectStats.words }} 字</span>
          </div>
          <div v-if="novelStudioMode === 'project'" class="editor-toggles">
            <button type="button" class="ghost muted" :class="{ active: novelEditorFont === 'serif' }" @click="novelEditorFont = 'serif'">宋体</button>
            <button type="button" class="ghost muted" :class="{ active: novelEditorFont === 'sans' }" @click="novelEditorFont = 'sans'">黑体</button>
            <button type="button" class="ghost muted focus-toggle" @click="novelFocusMode = !novelFocusMode">
              {{ novelFocusMode ? "退出专注" : "专注" }}
            </button>
          </div>
        </div>
      </header>

      <section v-if="novelStudioMode === 'select'" class="novel-mode-select">
        <button type="button" class="novel-mode-card" @click="setNovelStudioMode('quick')">
          <span class="eyebrow">Quick Draft</span>
          <strong>生成短篇</strong>
          <em>只显示短篇参数、生成进度和成稿预览。适合把当前会话快速改成短篇、番外或第一章。</em>
          <i>进入短篇生成</i>
        </button>
        <button type="button" class="novel-mode-card accent" @click="setNovelStudioMode('project')">
          <span class="eyebrow">Project Mode</span>
          <strong>创作长篇</strong>
          <em>只显示项目、章节编辑、Story Bible、素材库和版本记录。适合连续写作与回滚。</em>
          <i>进入长篇项目</i>
        </button>
      </section>

      <section v-else class="novel-layout novel-project-layout" :class="`mode-${novelStudioMode}`">
        <aside class="novel-rail">
          <section v-if="novelStudioMode === 'quick'" class="quick-novel-block">
            <div class="story-pane-head">
              <div>
                <p class="eyebrow">Quick Draft</p>
                <h3>短篇生成</h3>
              </div>
              <button class="ghost muted" type="button" :disabled="busy || !sessionId || messages.length < 2" @click="generateNovelDraft">生成</button>
            </div>
            <label>
              <span>形式</span>
              <select v-model="novelForm">
                <option value="daily_short">日常短篇</option>
                <option value="campus_romance">校园恋爱短篇</option>
                <option value="vignette">片段随笔</option>
                <option value="chapter_one">第一章</option>
                <option value="side_story">番外</option>
              </select>
            </label>
            <label>
              <span>视角</span>
              <select v-model="novelPerspective">
                <option value="third_person">第三人称</option>
                <option value="user_view">用户视角</option>
                <option value="character_view">角色视角</option>
                <option value="dual_view">双视角</option>
              </select>
            </label>
            <label>
              <span>改编强度</span>
              <select v-model="novelFidelity">
                <option value="faithful">忠实记录</option>
                <option value="polished">轻度润色</option>
                <option value="literary">文学化扩写</option>
              </select>
            </label>
            <label>
              <span>氛围</span>
              <input v-model="novelAtmosphere" maxlength="80" />
            </label>
          </section>

          <section v-if="novelStudioMode === 'project'" class="project-list-block">
            <div class="story-pane-head">
              <div>
                <p class="eyebrow">Projects</p>
                <h3>长篇项目</h3>
              </div>
              <button class="ghost muted" type="button" :disabled="novelProjectBusy || !sessionId" @click="createLongNovelProject">新建</button>
            </div>
            <div class="project-list">
              <button
                v-for="project in novelProjects"
                :key="project.id"
                type="button"
                :class="{ active: project.id === activeNovelProjectId }"
                @click="selectNovelProject(project.id)"
              >
                <strong>{{ project.title }}</strong>
                <span>{{ project.genre }} · {{ project.chapters.length }} 章</span>
              </button>
              <p v-if="!novelProjects.length" class="empty">还没有长篇项目。会从当前会话、记忆和剧情标签生成初始 Story Bible。</p>
            </div>
          </section>

          <section v-if="novelStudioMode === 'project'" class="project-list-block">
            <div class="story-pane-head">
              <div>
                <p class="eyebrow">Chapters</p>
                <h3>章节</h3>
              </div>
              <button class="ghost muted" type="button" :disabled="novelProjectBusy || !activeNovelProject" @click="addNovelChapter">新增</button>
            </div>
            <div class="chapter-list">
              <button
                v-for="chapter in activeNovelProject?.chapters || []"
                :key="chapter.id"
                type="button"
                :class="{ active: chapter.id === activeNovelChapterId }"
                @click="selectNovelChapter(chapter.id)"
              >
                <b>{{ chapter.chapter_order }}</b>
                <span>{{ chapter.title }}</span>
                <small>{{ novelChapterStatusLabel(chapter.status) }}</small>
              </button>
            </div>
          </section>

        </aside>

        <article class="novel-desk" :class="{ 'quick-desk': novelStudioMode === 'quick' }">
          <section v-if="showActiveNovelProgress && novelStudioMode === 'quick'" class="novel-progress-card inline-progress">
            <div class="novel-progress-meter">
              <span>{{ novelProgressLabel }}</span>
              <strong>{{ novelProgressPercent }}%</strong>
              <i><b :style="{ width: `${novelProgressPercent}%` }"></b></i>
              <button v-if="novelProjectBusy" type="button" class="ghost muted progress-unlock" @click="unlockNovelProgress">解除卡住</button>
            </div>
            <div class="novel-step-list">
              <span
                v-for="(step, index) in novelPipelineSteps"
                :key="step.id"
                :class="novelStepClass(step)"
              >
                <b>{{ index + 1 }}</b>
                <em>{{ step.label }}</em>
              </span>
            </div>
          </section>

          <section v-if="novelStudioMode === 'quick' && novelResult" class="novel-preview compact-preview quick-result-panel">
            <div class="novel-title-row">
              <div>
                <p class="eyebrow">Quick Draft</p>
                <h3>{{ novelResult.title }}</h3>
                <div class="novel-result-meta">
                  <span>{{ novelResultSourceLabel }}</span>
                  <span>{{ novelResultControlLabel }}</span>
                </div>
              </div>
              <div class="chapter-actions">
                <button class="ghost muted" type="button" @click="downloadNovelMarkdown">Markdown</button>
                <button class="ghost muted" type="button" @click="novelResult = null">收起</button>
              </div>
            </div>
            <p class="novel-synopsis">{{ novelResult.synopsis }}</p>
            <div class="novel-body">{{ novelResult.body }}</div>
          </section>

          <section v-if="novelStudioMode === 'quick' && !novelResult && !showActiveNovelProgress" class="quick-empty-state">
            <p class="eyebrow">短篇工作台</p>
            <h3>左侧选择形式和语气，然后生成成稿</h3>
            <p>短篇模式不会加载长篇章节编辑器，生成结果会直接显示在这里，方便预览和导出 Markdown。</p>
            <div class="quick-empty-actions">
              <button type="button" :disabled="busy || !sessionId || messages.length < 2" @click="generateNovelDraft">
                生成短篇
              </button>
              <small>{{ messages.length < 2 ? "当前会话消息太少，先聊几轮再生成。" : "会使用当前会话、记忆和剧情标签作为素材。" }}</small>
            </div>
          </section>

          <div v-if="novelStudioMode === 'project' && !activeNovelProject" class="project-empty">
            <div class="project-empty-copy">
              <div>
                <p class="eyebrow">Project Mode</p>
                <h3>从长篇项目开始</h3>
                <p>先给作品一个方向，项目创建后再展开世界观、关系设定和章节大纲。</p>
              </div>
              <div class="project-empty-actions">
                <button type="button" :disabled="novelProjectBusy || !sessionId" @click="createLongNovelProject">新建项目</button>
                <button class="ghost muted" type="button" :disabled="storyBusy || !sessionId" @click="refreshStoryTags()">刷新剧情标签</button>
              </div>
            </div>
            <div class="project-seed-grid">
              <label>
                <span>作品标题</span>
                <input v-model="projectDraft.title" placeholder="新小说项目" />
              </label>
              <label>
                <span>类型</span>
                <input v-model="projectDraft.genre" />
              </label>
              <label>
                <span>基调</span>
                <input v-model="projectDraft.tone" />
              </label>
            </div>
          </div>

          <details v-if="novelStudioMode === 'project' && activeNovelProject" class="project-settings-drawer">
            <summary>
              <span>项目设定</span>
              <small>{{ projectDraft.genre }} · {{ projectDraft.tone }}</small>
            </summary>
            <section class="project-fields">
              <div class="project-title-row">
                <label>
                  <span>作品标题</span>
                  <input v-model="projectDraft.title" placeholder="新小说项目" />
                </label>
                <label>
                  <span>类型</span>
                  <input v-model="projectDraft.genre" />
                </label>
                <label>
                  <span>基调</span>
                  <input v-model="projectDraft.tone" />
                </label>
                <button type="button" :disabled="novelProjectBusy || !activeNovelProject" @click="saveNovelProject">保存设定</button>
              </div>
              <label>
                <span>世界观</span>
                <textarea v-model="projectDraft.worldview" rows="3" placeholder="项目创建后会自动从素材生成" />
              </label>
              <label>
                <span>关系设定</span>
                <textarea v-model="projectDraft.relationship_setup" rows="3" />
              </label>
              <label>
                <span>章节大纲</span>
                <textarea v-model="projectDraft.outline" rows="4" />
              </label>
            </section>
          </details>

          <section v-if="novelStudioMode === 'project' && activeNovelProject" class="story-canvas-panel">
            <div class="story-canvas-head">
              <div>
                <p class="eyebrow">Story Canvas</p>
                <h3>故事画布</h3>
                <small>{{ canvasBuildSummary }}</small>
              </div>
              <div class="story-canvas-actions">
                <button class="ghost muted" type="button" :disabled="novelProjectBusy || isInitialCanvasRebuildLocked" @click="rebuildStoryCanvas">{{ canvasBuildActionLabel }}</button>
                <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="saveStoryCanvas">保存画布</button>
                <button type="button" :disabled="novelProjectBusy || !activeCanvasScenes.length" @click="activeSceneToChapterDraft">应用到章节</button>
              </div>
            </div>
            <div class="story-canvas-tabs">
              <button type="button" :class="{ active: storyCanvasView === 'flow' }" @click="storyCanvasView = 'flow'">流程视图</button>
              <button type="button" :class="{ active: storyCanvasView === 'chapters' }" @click="storyCanvasView = 'chapters'">章节看板</button>
              <button type="button" :class="{ active: storyCanvasView === 'scenes' }" @click="storyCanvasView = 'scenes'">场景列表</button>
              <button type="button" :class="{ active: storyCanvasView === 'threads' }" @click="storyCanvasView = 'threads'">线索视图</button>
            </div>
            <div v-if="storyCanvasView === 'flow'" class="canvas-flow-view">
              <div class="canvas-flow-summary">
                <div>
                  <p class="eyebrow">Canvas Run</p>
                  <strong>{{ canvasBuildSummary }}</strong>
                </div>
                <div class="canvas-flow-metrics">
                  <span>{{ canvasFlowMetrics.materials }} 素材</span>
                  <span>{{ canvasFlowMetrics.acts }} 阶段</span>
                  <span>{{ canvasFlowMetrics.chapters }} 章</span>
                  <span>{{ canvasFlowMetrics.scenes }} 场景</span>
                  <span>{{ canvasFlowMetrics.threads }} 线索</span>
                  <span>{{ canvasSourceLabel }}</span>
                </div>
              </div>
              <div
                v-if="canvasBuildStage !== 'idle'"
                class="canvas-build-progress"
                :class="{ complete: canvasBuildStage === 'done', failed: canvasBuildStage === 'failed' }"
              >
                <div>
                  <span>{{ canvasBuildProgressLabel }}</span>
                  <strong>{{ Math.round(canvasBuildPercent) }}%</strong>
                </div>
                <i aria-hidden="true">
                  <b :style="{ width: `${canvasBuildPercent}%` }"></b>
                </i>
              </div>
              <ol class="canvas-flow-steps">
                <li
                  v-for="(step, index) in canvasBuildSteps"
                  :key="step.id"
                  :class="canvasBuildStepClass(index)"
                >
                  <i>{{ index + 1 }}</i>
                  <div>
                    <strong>{{ step.label }}</strong>
                    <span>{{ step.detail }}</span>
                  </div>
                </li>
              </ol>
              <div class="canvas-flow-note">
                <strong>自动滚动</strong>
                <span>每章生成后会整理交接单、更新 Novel State，并重规划后续两章；“重新生成画布”只适合开局大改。</span>
              </div>
              <div class="novel-state-panel">
                <article>
                  <p class="eyebrow">Novel State</p>
                  <strong>截至上一章摘要</strong>
                  <span>{{ novelStateSummary }}</span>
                </article>
                <article>
                  <p class="eyebrow">Last Handoff</p>
                  <strong>上一章交接单</strong>
                  <span>{{ novelStateLastHandoffText }}</span>
                </article>
                <article>
                  <p class="eyebrow">Open Threads</p>
                  <strong>未解决线索</strong>
                  <span v-if="!novelStateOpenThreads.length">暂无未解决线索。</span>
                  <span v-else>{{ novelStateOpenThreads.join("；") }}</span>
                </article>
              </div>
            </div>
            <div v-else-if="storyCanvasView === 'chapters'" class="canvas-card-grid">
              <article
                v-for="chapter in storyCanvasDraft.chapters"
                :key="chapter.id"
                class="canvas-card"
                :class="{ active: activeCanvasChapter?.id === chapter.id }"
                @click="selectCanvasChapter(chapter)"
              >
                <div class="canvas-card-title">
                  <strong>{{ chapter.chapter_order }}. {{ chapter.title }}</strong>
                  <span>{{ novelChapterStatusLabel(chapter.status) }} · {{ chapter.target_length }} 字</span>
                </div>
                <div class="canvas-read-grid">
                  <article>
                    <span>剧情概述</span>
                    <p>{{ canvasFieldText(chapter.goal) }}</p>
                  </article>
                  <article v-for="field in canvasActionChainFields" :key="field.key">
                    <span>{{ field.label }}</span>
                    <p>{{ canvasFieldText(chapter[field.key]) }}</p>
                  </article>
                </div>
              </article>
            </div>
            <div v-else-if="storyCanvasView === 'scenes'" class="canvas-scene-list">
              <article v-for="scene in storyCanvasDraft.scenes" :key="scene.id" class="canvas-card">
                <div class="canvas-card-title">
                  <strong>{{ canvasChapterTitle(scene.chapter_id) }} · 场景 {{ scene.scene_order }}</strong>
                  <span>{{ scene.linked_material_ids.length }} 条素材</span>
                </div>
                <div class="canvas-field-grid">
                  <article>
                    <span>当前场景</span>
                    <p>{{ canvasFieldText(scene.current_scene) }}</p>
                  </article>
                  <article>
                    <span>表层事件</span>
                    <p>{{ canvasFieldText(scene.surface_event) }}</p>
                  </article>
                  <article>
                    <span>人物欲望</span>
                    <p>{{ canvasFieldText(scene.character_desire) }}</p>
                  </article>
                  <article>
                    <span>阻碍 / 张力</span>
                    <p>{{ canvasFieldText(scene.tension) }}</p>
                  </article>
                  <article>
                    <span>禁止推进</span>
                    <p>{{ canvasFieldText(scene.forbidden_progress) }}</p>
                  </article>
                  <article>
                    <span>结尾落点</span>
                    <p>{{ canvasFieldText(scene.ending_beat) }}</p>
                  </article>
                </div>
              </article>
            </div>
            <div v-else-if="storyCanvasView === 'threads'" class="canvas-card-grid">
              <article v-for="thread in storyCanvasDraft.threads" :key="thread.id" class="canvas-card">
                <div class="canvas-card-title">
                  <strong>{{ thread.label || "未命名线索" }}</strong>
                  <span>{{ thread.kind }} · {{ thread.status }}</span>
                </div>
                <label>
                  <span>线索说明</span>
                  <textarea v-model="thread.notes" rows="3" />
                </label>
                <div class="canvas-thread-route">
                  <span>{{ canvasChapterTitle(thread.setup_chapter_id) }}</span>
                  <span>→</span>
                  <span>{{ canvasChapterTitle(thread.payoff_chapter_id) }}</span>
                </div>
              </article>
            </div>
          </section>

          <section v-if="showActiveNovelProgress && novelStudioMode === 'project'" class="novel-progress-card inline-progress chapter-progress-card">
            <div class="novel-progress-meter">
              <span>{{ novelProgressLabel }}</span>
              <strong>{{ novelProgressPercent }}%</strong>
              <i><b :style="{ width: `${novelProgressPercent}%` }"></b></i>
              <button v-if="novelProjectBusy" type="button" class="ghost muted progress-unlock" @click="unlockNovelProgress">解除卡住</button>
            </div>
            <div class="novel-step-groups">
              <div class="novel-step-group">
                <div class="novel-step-group-title">
                  <span>正文生成</span>
                  <small>决定这一章从远程正文还是本地草稿返回</small>
                </div>
                <div class="novel-step-list detailed">
                  <span
                    v-for="(step, index) in novelDraftSteps"
                    :key="step.id"
                    :class="novelStepClass(step)"
                  >
                    <b>{{ index + 1 }}</b>
                    <em>{{ step.label }}</em>
                    <small>{{ step.detail }}</small>
                  </span>
                </div>
              </div>
              <div class="novel-step-group">
                <div class="novel-step-group-title">
                  <span>质检与续写状态</span>
                  <small>正文返回后再审稿、必要时重写，并更新交接和滚动画布</small>
                </div>
                <div class="novel-step-list detailed review">
                  <span
                    v-for="(step, index) in novelReviewSteps"
                    :key="step.id"
                    :class="novelStepClass(step)"
                  >
                    <b>{{ novelDraftSteps.length + index + 1 }}</b>
                    <em>{{ step.label }}</em>
                    <small>{{ step.detail }}</small>
                  </span>
                </div>
              </div>
            </div>
            <p v-if="novelProgressStage === 'fallback'" class="progress-note warning">
              远程正文没有成功返回，本次只保留本地正文草稿；不会写入全局摘要、交接单或滚动画布。
            </p>
          </section>

          <section v-if="novelStudioMode === 'project' && activeNovelChapter" class="chapter-editor">
            <div class="chapter-editor-head">
              <div>
                <p class="eyebrow">Chapter {{ activeNovelChapter.chapter_order }}</p>
                <h3>{{ chapterDraft.title || "未命名章节" }}</h3>
              </div>
              <div class="chapter-actions">
                <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="checkActiveContinuity">检查</button>
                <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="saveNovelChapter">保存</button>
                <button type="button" class="ghost muted danger" :disabled="novelProjectBusy" @click="deleteActiveNovelChapter">删除</button>
                <button type="button" :disabled="novelProjectBusy" @click="generateActiveChapter">生成/续写</button>
              </div>
            </div>
            <div class="chapter-grid">
              <label>
                <span>章节名</span>
                <input v-model="chapterDraft.title" />
              </label>
              <label>
                <span>状态</span>
                <select v-model="chapterDraft.status">
                  <option v-for="option in novelChapterStatusOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
            </div>
            <label>
              <span>本章剧情概述</span>
              <textarea v-model="chapterDraft.goal" rows="3" />
            </label>
            <section class="scene-card-editor">
              <div class="scene-card-head">
                <div>
                  <p class="eyebrow">Scene Card</p>
                  <h4>场景卡</h4>
                </div>
                <small>生成前先约束场景、人物欲望、张力和结尾落点。</small>
              </div>
              <div v-if="activeCanvasChapter" class="canvas-link-editor">
                <div>
                  <p class="eyebrow">Canvas Link</p>
                  <strong>对应画布动作链</strong>
                  <small>剧情推进以这里为准，保存后会反向写回故事画布。</small>
                </div>
                <div class="canvas-action-grid">
                  <label v-for="item in activeCanvasActionChain" :key="item.label">
                    <span>{{ item.label }}</span>
                    <textarea v-model="activeCanvasChapter[item.key]" rows="3" />
                  </label>
                </div>
              </div>
              <div class="scene-card-grid">
                <label v-for="field in sceneCardFields" :key="field.key">
                  <span>{{ field.label }}</span>
                  <textarea v-model="chapterDraft.scene_card[field.key]" :rows="field.rows" />
                </label>
              </div>
            </section>
            <label>
              <span>生成指令</span>
              <textarea v-model="chapterInstruction" rows="10" />
            </label>
            <label class="range-field">
              <span>项目章节目标长度 {{ projectChapterTargetLength }} 字</span>
              <input v-model.number="projectChapterTargetLength" type="range" min="400" max="6000" step="200" />
            </label>
            <div class="chapter-length-panel" :class="`tone-${chapterLengthGuide.tone}`">
              <div>
              <strong>{{ activeChapterWordCount }} / {{ projectChapterTargetLength }} 字</strong>
              <span>{{ chapterLengthGuide.label }} · {{ chapterLengthRatio }}%</span>
            </div>
            <p>{{ chapterLengthGuide.detail }}</p>
              <button class="ghost muted" type="button" :disabled="novelProjectBusy || isOptimizingInstruction" @click="applyOptimizedChapterInstruction">
                {{ isOptimizingInstruction ? "远程优化中" : "优化生成指令" }}
              </button>
            </div>
            <p v-if="instructionOptimizationNote" class="instruction-optimization-note">{{ instructionOptimizationNote }}</p>
            <div class="writing-surface" :class="`font-${novelEditorFont}`">
              <label>
                <span>章节摘要</span>
                <textarea v-model="chapterDraft.summary" rows="3" />
              </label>
              <label class="chapter-body-label">
                <span>正文</span>
                <textarea
                  v-model="chapterDraft.body"
                  class="chapter-body-input"
                  rows="18"
                  placeholder="从这里开始写正文。AI 生成、续写和手动编辑都会落在这张写作纸面上。"
                />
              </label>
              <div class="editor-status-bar">
                <span>{{ activeChapterWordCount }} 字</span>
                <span>{{ novelChapterStatusLabel(activeNovelChapter?.status) }}</span>
                <span>{{ editorUpdatedLabel }}</span>
              </div>
            </div>
          </section>

          <p v-if="novelStudioMode === 'quick' && messages.length < 2" class="empty">当前会话消息太少，先聊几轮再生成。</p>
          <p v-if="error" class="error">{{ error }}</p>
        </article>

        <aside v-if="novelStudioMode === 'project'" class="story-bible-panel">
          <section class="story-pane-card">
            <div class="story-pane-head">
              <div>
                <p class="eyebrow">Story Pane</p>
                <h3>剧情标签 {{ storyPane?.items.length || 0 }}</h3>
                <small>每 {{ STORY_AUTO_REFRESH_USER_INTERVAL }} 条用户消息后台更新一次</small>
              </div>
              <button class="ghost muted" type="button" :disabled="storyBusy || !sessionId" @click="refreshStoryTags()">
                {{ storyBusy ? "更新中" : "刷新" }}
              </button>
            </div>
            <div v-if="storyPane?.items.length" class="story-tag-list">
              <article v-for="item in storyPane.items" :key="item.id" class="story-tag">
                <div>
                  <span>{{ storyKindLabels[item.kind] || item.kind }}</span>
                  <small>{{ storyStatusLabels[item.status] || item.status }} · {{ item.evidence_level }}</small>
                </div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.content }}</p>
              </article>
            </div>
            <p v-else class="empty">还没有剧情标签。可以先刷新一次，项目创建会把它们转成 Story Bible。</p>
          </section>

          <section class="story-pane-card">
            <div class="story-pane-head">
              <div>
                <p class="eyebrow">Story Bible</p>
                <h3>项目规则</h3>
              </div>
              <button class="ghost muted" type="button" :disabled="!activeNovelProject" @click="downloadNovelProjectMarkdown">导出</button>
            </div>
            <div v-if="storyBibleEntries.length" class="bible-list">
              <article v-for="[key, items] in storyBibleEntries" :key="key">
                <strong>{{ key }}</strong>
                <p v-for="item in items.slice(0, 5)" :key="item">{{ item }}</p>
              </article>
            </div>
            <p v-else class="empty">创建项目后会出现事实、伏笔、关系、边界和灵感。</p>
          </section>

          <section class="story-pane-card">
            <p class="eyebrow">Materials</p>
            <div v-if="projectMaterialGroups.length" class="material-list">
              <article v-for="[category, materials] in projectMaterialGroups" :key="category">
                <strong>{{ category }} · {{ materials.length }}</strong>
                <p v-for="material in materials.slice(0, 4)" :key="material.id">{{ material.label }}：{{ material.content }}</p>
              </article>
            </div>
            <p v-else class="empty">素材库为空。</p>
          </section>

          <section class="story-pane-card">
            <p class="eyebrow">Continuity</p>
            <div v-if="continuityReport" class="continuity-list">
              <article v-for="issue in continuityReport.issues" :key="`${issue.severity}-${issue.label}`" :class="issue.severity">
                <strong>{{ issue.label }}</strong>
                <p>{{ issue.detail }}</p>
              </article>
            </div>
            <p v-else class="empty">点击“检查”后会显示连续性、边界和内部措辞风险。</p>
          </section>

          <section class="story-pane-card">
            <p class="eyebrow">Versions</p>
            <div v-if="displayedChapterVersions.length" class="version-list">
              <article v-for="version in displayedChapterVersions.slice(0, 8)" :key="version.id">
                <strong>{{ version.title }}</strong>
                <small>
                  {{ novelVersionSourceLabel(version) }} · {{ version.created_at }}
                  <span v-if="novelVersionFoldLabel(version)" class="version-fold">{{ novelVersionFoldLabel(version) }}</span>
                </small>
                <div class="version-actions">
                  <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="restoreVersion(version.id)">恢复</button>
                  <button class="ghost muted danger" type="button" :disabled="novelProjectBusy" @click="deleteVersion(version.id)">删除</button>
                </div>
              </article>
            </div>
            <p v-else class="empty">保存或生成正文后会保留版本。</p>
          </section>

          <p v-if="messages.length < 2" class="empty">当前会话消息太少，先聊几轮再生成。</p>
          <p v-if="error" class="error">{{ error }}</p>
        </aside>
      </section>
    </section>

    <div v-if="showLoveResultModal && loveResult" class="modal-backdrop" @click.self="showLoveResultModal = false">
      <section class="love-modal">
        <button class="modal-close" @click="showLoveResultModal = false">Close</button>
        <div class="modal-art" :style="{ backgroundImage: `url('${loveProfileImageUrl}')` }"></div>
        <div class="modal-copy">
          <p class="eyebrow">Love Type Result</p>
          <h3>{{ loveResult.name }}</h3>
          <strong>{{ loveGender === "female" ? "女性画像" : "男性画像" }} · {{ loveResult.subtitle }}</strong>
          <p>{{ loveResult.description }}</p>
          <p>{{ selectedLoveDetail }}</p>
          <div class="result-cue">
            <span>恋爱核心需求</span>
            <p>{{ loveResult.relationshipNeed }}</p>
          </div>
          <div class="result-cue">
            <span>容易踩雷</span>
            <p>{{ loveResult.blindSpot }}</p>
          </div>
          <div class="result-cue">
            <span>理想关系动态</span>
            <p>{{ loveResult.idealDynamic }}</p>
          </div>
          <div class="result-cue">
            <span>角色互动建议</span>
            <p>{{ loveResult.partnerCue }}</p>
          </div>
          <div class="dimension-bars">
            <label v-for="[dimension, value] in loveDimensionEntries" :key="dimension">
              <span>{{ loveDimensionLabels[dimension] }} {{ value }}</span>
              <i><b :style="{ width: `${loveBarWidth(dimension, value)}%` }"></b></i>
            </label>
          </div>
        </div>
        <div class="modal-actions">
          <button class="wide" @click="saveLoveResultImage">保存结果图片</button>
          <button class="wide ghost" :disabled="busy || !sessionId" @click="applyLoveProfileToMemory">写入当前角色记忆</button>
        </div>
      </section>
    </div>

    <aside v-if="currentPage === 'chat'" class="right-panel">
      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">State</p>
            <h3>{{ characterState?.mood || "No state" }}</h3>
          </div>
          <button class="ghost muted" @click="stateExpanded = !stateExpanded">{{ stateExpanded ? "Hide" : "Detail" }}</button>
        </div>

        <section v-if="characterState" class="state-strip side-strip">
          <button class="state-summary" type="button" @click="stateExpanded = !stateExpanded">
            <span>
              <small>Tone</small>
              <strong>{{ characterState.tone }}</strong>
            </span>
            <span>
              <small>Distance</small>
              <strong>{{ characterState.distance }}</strong>
            </span>
            <span class="state-focus">
              <small>Focus</small>
              <strong>{{ characterState.focus }}</strong>
            </span>
          </button>
          <div class="state-bars">
            <label>
              <span>Energy {{ energyPercent }}%</span>
              <i><b :style="{ width: `${energyPercent}%` }"></b></i>
            </label>
            <label>
              <span>Resonance {{ resonancePercent }}%</span>
              <i><b :style="{ width: `${resonancePercent}%` }"></b></i>
            </label>
          </div>
          <dl v-if="stateExpanded" class="state-detail">
            <div>
              <dt>Pace</dt>
              <dd>{{ characterState.behavior.pace }}</dd>
            </div>
            <div>
              <dt>Initiative</dt>
              <dd>{{ characterState.behavior.initiative }}</dd>
            </div>
            <div>
              <dt>Warmth</dt>
              <dd>{{ characterState.behavior.warmth }}</dd>
            </div>
            <div>
              <dt>Memory Use</dt>
              <dd>{{ characterState.behavior.memory_use }}</dd>
            </div>
            <div>
              <dt>Avoid</dt>
              <dd>{{ characterState.behavior.avoid }}</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{{ characterState.last_shift || characterState.evidence }}</dd>
            </div>
          </dl>
        </section>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Bond</p>
            <h3>{{ characterBond?.familiarity_stage || "No bond" }}</h3>
          </div>
          <button class="ghost muted" @click="bondExpanded = !bondExpanded">{{ bondExpanded ? "Hide" : "Detail" }}</button>
        </div>

        <section v-if="characterBond" class="bond-strip side-strip">
          <button class="bond-summary" type="button" @click="bondExpanded = !bondExpanded">
            <span>
              <small>Base Resonance</small>
              <strong>{{ bondPercent }}%</strong>
            </span>
            <span class="bond-preference">
              <small>Preference</small>
              <strong>{{ characterBond.interaction_preferences }}</strong>
            </span>
          </button>
          <dl v-if="bondExpanded" class="bond-detail">
            <div>
              <dt>Trust</dt>
              <dd>{{ characterBond.trust_notes }}</dd>
            </div>
            <div>
              <dt>Boundary</dt>
              <dd>{{ characterBond.boundary_notes }}</dd>
            </div>
            <div>
              <dt>Milestones</dt>
              <dd>{{ characterBond.milestones.length ? characterBond.milestones.join(" / ") : "暂无关键节点" }}</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{{ characterBond.evidence }}</dd>
            </div>
          </dl>
        </section>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Memory</p>
            <h3>{{ memoryPane?.frozen ? "Frozen" : "Live" }}</h3>
          </div>
          <button class="ghost" @click="toggleFreeze">{{ memoryPane?.frozen ? "Unfreeze" : "Freeze" }}</button>
        </div>

        <textarea v-model="manualNoteDraft" class="note" rows="4" placeholder="手动记忆" />
        <button class="wide" @click="saveMemoryNote">Save note</button>

        <div class="memory-tabs">
          <button :class="{ active: memoryFilter === 'all' }" @click="memoryFilter = 'all'">All {{ memoryCounts.all }}</button>
          <button :class="{ active: memoryFilter === 'global' }" @click="memoryFilter = 'global'">Global {{ memoryCounts.global }}</button>
          <button :class="{ active: memoryFilter === 'character' }" @click="memoryFilter = 'character'">Role {{ memoryCounts.character }}</button>
          <button :class="{ active: memoryFilter === 'session' }" @click="memoryFilter = 'session'">Session {{ memoryCounts.session }}</button>
          <button :class="{ active: memoryFilter === 'recall' }" @click="memoryFilter = 'recall'">Recall {{ memoryCounts.recall }}</button>
        </div>

        <div class="memory-list">
          <div v-for="memory in filteredMemories" :key="memory.id" class="memory-item">
            <template v-if="editingMemoryId === memory.id">
              <div class="memory-edit-grid">
                <label>
                  <span>Scope</span>
                  <select v-model="memoryDraft.memory_scope">
                    <option value="global">global</option>
                    <option value="character">character</option>
                    <option value="session">session</option>
                  </select>
                </label>
                <label>
                  <span>Type</span>
                  <select v-model="memoryDraft.memory_type">
                    <option value="stable_user_info">stable_user_info</option>
                    <option value="user_preference">user_preference</option>
                    <option value="relationship_progress">relationship_progress</option>
                    <option value="open_thread">open_thread</option>
                    <option value="recent_emotion">recent_emotion</option>
                  </select>
                </label>
              </div>
              <textarea v-model="memoryDraft.content" class="note compact" rows="3" />
              <label class="range-field">
                <span>Importance {{ Math.round(Number(memoryDraft.importance || 0) * 100) }}%</span>
                <input v-model.number="memoryDraft.importance" type="range" min="0" max="1" step="0.05" />
              </label>
              <div class="memory-actions">
                <button class="ghost" @click="saveMemoryItem(memory.id)">Save</button>
                <button class="ghost muted" @click="cancelEditMemory">Cancel</button>
              </div>
            </template>
            <template v-else>
              <div class="memory-meta">
                <button class="memory-title" @click="toggleMemoryDetails(memory.id)">
                  {{ memory.memory_scope }} / {{ memory.memory_type }}
                </button>
                <div class="memory-actions">
                  <button @click="startEditMemory(memory)">Edit</button>
                  <button @click="removeMemoryItem(memory.id)">Delete</button>
                </div>
              </div>
              <div class="score-row">
                <span>importance {{ Math.round(memory.importance * 100) }}%</span>
                <span>confidence {{ Math.round(memory.confidence * 100) }}%</span>
              </div>
              <p>{{ memory.content }}</p>
              <dl v-if="expandedMemoryId === memory.id" class="detail-grid">
                <div>
                  <dt>ID</dt>
                  <dd>{{ memory.id }}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{{ memory.source_message_id || "manual / unknown" }}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{{ memory.created_at }}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{{ memory.updated_at }}</dd>
                </div>
              </dl>
            </template>
          </div>
          <div v-if="!filteredMemories.length" class="empty">No memory in this view.</div>
        </div>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Prompt Stack</p>
            <h3>{{ includedSlots.length }} included</h3>
          </div>
        </div>

        <div class="slot-list">
          <div v-for="slot in includedSlots" :key="slot.key" class="slot-item" :class="{ expanded: expandedSlotKey === slot.key }">
            <div @click="toggleSlotDetails(slot.key)">
              <strong>{{ slot.key }}</strong>
              <span>{{ slot.priority }} / {{ slot.token_budget }}</span>
            </div>
            <p>{{ slot.content }}</p>
            <dl v-if="expandedSlotKey === slot.key" class="detail-grid">
              <div>
                <dt>Role</dt>
                <dd>{{ slot.role }}</dd>
              </div>
              <div>
                <dt>Included</dt>
                <dd>{{ slot.included ? "yes" : "no" }}</dd>
              </div>
              <div>
                <dt>Budget</dt>
                <dd>{{ slot.token_budget }}</dd>
              </div>
            </dl>
          </div>
          <div v-if="excludedSlots.length" class="excluded">{{ excludedSlots.length }} excluded by budget</div>
        </div>
      </section>
    </aside>
  </main>
</template>
