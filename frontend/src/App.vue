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
  exportSession,
  generateNovel,
  generateProjectChapter,
  getStoryPane,
  listCharacters,
  listNovelProjects,
  listNovelVersions,
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
type NovelProgressStage = "idle" | "collecting" | "composing" | "generating" | "checking" | "done" | "failed";
type StoryCanvasView = "flow" | "chapters" | "scenes" | "threads";
type CanvasBuildStage = "idle" | "materials" | "structure" | "chapters" | "scenes" | "threads" | "done" | "failed";
type StoryRefreshOptions = { silent?: boolean };
type ChapterSceneCardDraft = Record<string, string>;
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
const chapterInstruction = ref("承接上一章，写出下一段自然推进，但不制造越界进展。");
const projectChapterTargetLength = ref(1800);
const continuityReport = ref<NovelContinuityReport | null>(null);
const chapterVersions = ref<NovelVersion[]>([]);
const novelFocusMode = ref(false);
const novelEditorFont = ref<"serif" | "sans">("serif");
let novelProgressTimers: number[] = [];
let canvasBuildTimers: number[] = [];
let canvasBuildTicker: number | null = null;

const novelPipelineSteps: { id: NovelProgressStage; label: string; detail: string }[] = [
  { id: "collecting", label: "取材", detail: "读取会话和记忆" },
  { id: "composing", label: "组装", detail: "整理角色与关系" },
  { id: "generating", label: "生成", detail: "写作正文" },
  { id: "checking", label: "校验", detail: "检查结构和依据" },
  { id: "done", label: "完成", detail: "可预览或导出" }
];

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
  { value: "locked", label: "已锁定" }
];

const novelChapterStatusLabels: Record<NovelChapterStatus, string> = {
  planned: "计划中",
  drafting: "生成中",
  draft: "草稿",
  revised: "已修订",
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
  { key: "surface_event", label: "表层事件", rows: 2 },
  { key: "character_desire", label: "人物欲望", rows: 2 },
  { key: "tension", label: "阻碍 / 张力", rows: 2 },
  { key: "required_facts", label: "必须保留事实", rows: 2 },
  { key: "forbidden_progress", label: "禁止推进", rows: 2 },
  { key: "ending_beat", label: "结尾落点", rows: 2 }
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
  if (novelProgressStage.value === "failed") return 2;
  return novelPipelineSteps.findIndex((step) => step.id === novelProgressStage.value);
});
const activeCanvasBuildStepIndex = computed(() => {
  if (canvasBuildStage.value === "done") return canvasBuildSteps.length;
  if (canvasBuildStage.value === "failed") return Math.max(0, canvasBuildSteps.length - 1);
  return canvasBuildSteps.findIndex((step) => step.id === canvasBuildStage.value);
});
const canvasBuildActionLabel = computed(() =>
  storyCanvasDraft.value.chapters.length ? "重新生成画布" : "生成画布"
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
  if (storyCanvasDraft.value.chapters.length) return "当前画布可继续编辑，也可以重新生成一版。";
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
  !["idle", "done", "failed"].includes(novelProgressStage.value)
);
const showActiveNovelProgress = computed(() =>
  activeNovelWorkflowMode.value === novelStudioMode.value
  && (novelProgressVisible.value || novelProgressStage.value === "failed")
);
const novelProgressLabel = computed(() => {
  if (novelProgressStage.value === "failed") return "生成失败";
  return novelPipelineSteps[activeNovelStepIndex.value]?.detail || "等待开始";
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
        status: (chapter.status || "planned") as NovelChapterStatus,
        emotion_curve: String(chapter.emotion_curve || ""),
        conflict_level: Number(chapter.conflict_level || 2),
        scene_ids: stringArray(chapter.scene_ids)
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
  storyCanvasDraft.value = normalizeStoryCanvas(project?.story_canvas);
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

function activeSceneToChapterDraft() {
  const scene = activeCanvasScenes.value[0];
  const canvasChapter = activeCanvasChapter.value;
  if (!scene || !canvasChapter) return;
  chapterDraft.value.title = canvasChapter.title || chapterDraft.value.title;
  chapterDraft.value.goal = canvasChapter.goal || chapterDraft.value.goal;
  chapterDraft.value.scene_card = normalizeSceneCardDraft(scene as unknown as Record<string, unknown>);
  projectChapterTargetLength.value = canvasChapter.target_length || projectChapterTargetLength.value;
}

function updateSceneArray(scene: StoryCanvasScene, key: "required_facts" | "forbidden_progress" | "linked_material_ids", event: Event) {
  scene[key] = stringArray((event.target as HTMLTextAreaElement).value);
}

function canvasChapterTitle(chapterId: string) {
  return storyCanvasDraft.value.chapters.find((chapter) => chapter.id === chapterId)?.title || chapterId || "未绑定章节";
}

function selectCanvasChapter(chapter: StoryCanvasChapter) {
  const matched = activeNovelProject.value?.chapters.find((item) => item.chapter_order === chapter.chapter_order);
  if (matched) {
    activeNovelChapterId.value = matched.id;
    syncChapterDraft(matched);
  }
}

function syncChapterDraft(chapter: NovelChapter | null) {
  chapterDraft.value = {
    title: chapter?.title || "",
    goal: chapter?.goal || "",
    summary: chapter?.summary || "",
    body: chapter?.body || "",
    status: chapter?.status || "planned",
    scene_card: normalizeSceneCardDraft(chapter?.scene_card)
  };
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

function optimizedChapterInstruction() {
  const goal = compactInstructionText(chapterDraft.value.goal) || "承接前文，推进一个可验证的小目标";
  const current = activeChapterWordCount.value;
  const target = projectChapterTargetLength.value;
  if (!current) {
    return `围绕“${goal}”写出完整章节，目标约 ${target} 字。直接进入小说场景，用动作、环境、对白和心理推进，不写创作说明，不制造越界进展。`;
  }
  if (chapterLengthRatio.value < 85) {
    return `在保留现有正文事实和语气的基础上扩写到约 ${target} 字。围绕“${goal}”补足场景细节、人物动作、自然对白和内心转折，不新增重大关系进展。`;
  }
  if (chapterLengthRatio.value > 130) {
    return `在保留核心事实的基础上精修到约 ${target} 字。围绕“${goal}”压缩重复描写，保留最有画面感的动作、对白和情绪落点。`;
  }
  return `承接现有正文继续润色，目标约 ${target} 字。围绕“${goal}”保持节奏自然，补强场景连贯性和章节收束，不制造越界进展。`;
}

function applyOptimizedChapterInstruction() {
  chapterInstruction.value = optimizedChapterInstruction();
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
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function rebuildStoryCanvas() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  beginCanvasBuildFlow();
  try {
    const savedProject = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
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
      goal: "承接前文，推进一个可验证的小目标。",
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

async function saveNovelChapter() {
  if (!activeNovelChapter.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const project = await updateNovelChapter(activeNovelChapter.value.id, chapterDraft.value);
    replaceNovelProject(project);
    await loadChapterVersions();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
}

async function generateActiveChapter() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelStudioMode.value = "project";
  novelProjectBusy.value = true;
  error.value = "";
  beginNovelProgress("project");
  try {
    const savedProject = await updateNovelProject(activeNovelProject.value.id, {
      ...projectDraft.value,
      story_canvas: storyCanvasDraft.value
    });
    replaceNovelProject(savedProject);
    if (activeNovelChapter.value) {
      const syncedProject = await updateNovelChapter(activeNovelChapter.value.id, chapterDraft.value);
      replaceNovelProject(syncedProject);
    }
    const project = await generateProjectChapter(
      activeNovelProject.value.id,
      activeNovelChapter.value?.id || null,
      chapterInstruction.value,
      projectChapterTargetLength.value
    );
    replaceNovelProject(project);
    if (!activeNovelChapterId.value) {
      activeNovelChapterId.value = project.chapters[project.chapters.length - 1]?.id || "";
    }
    syncChapterDraft(activeNovelChapter.value);
    await loadChapterVersions();
    clearNovelProgressTimers();
    setNovelProgress("done", 100);
  } catch (err) {
    error.value = readableError(err);
    clearNovelProgressTimers();
    setNovelProgress("failed", 100);
  } finally {
    novelProjectBusy.value = false;
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
}

function setNovelProgress(stage: NovelProgressStage, percent: number) {
  novelProgressStage.value = stage;
  novelProgressPercent.value = percent;
}

function beginNovelProgress(mode: NovelWorkflowMode) {
  clearNovelProgressTimers();
  activeNovelWorkflowMode.value = mode;
  novelProgressVisible.value = true;
  setNovelProgress("collecting", 12);
  novelProgressTimers.push(window.setTimeout(() => setNovelProgress("composing", 32), 180));
  novelProgressTimers.push(window.setTimeout(() => setNovelProgress("generating", 58), 520));
  novelProgressTimers.push(window.setTimeout(() => setNovelProgress("checking", 78), 1200));
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
          <section v-if="showActiveNovelProgress" class="novel-progress-card inline-progress">
            <div class="novel-progress-meter">
              <span>{{ novelProgressLabel }}</span>
              <strong>{{ novelProgressPercent }}%</strong>
              <i><b :style="{ width: `${novelProgressPercent}%` }"></b></i>
            </div>
            <div class="novel-step-list">
              <span
                v-for="(step, index) in novelPipelineSteps"
                :key="step.id"
                :class="{
                  active: index === activeNovelStepIndex,
                  done: novelProgressStage === 'done' || index < activeNovelStepIndex,
                  failed: novelProgressStage === 'failed' && index === activeNovelStepIndex
                }"
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
                <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="rebuildStoryCanvas">{{ canvasBuildActionLabel }}</button>
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
                <strong>可反复生成</strong>
                <span>每次生成会基于当前项目设定和素材重新写入画布；如果你手动调整过画布，先保存或确认可以被新版本覆盖。</span>
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
                <label>
                  <span>章节目标</span>
                  <textarea v-model="chapter.goal" rows="2" />
                </label>
                <label>
                  <span>外部事件</span>
                  <textarea v-model="chapter.external_event" rows="2" />
                </label>
                <label>
                  <span>触发事件</span>
                  <textarea v-model="chapter.trigger_event" rows="2" />
                </label>
                <label>
                  <span>即时反应</span>
                  <textarea v-model="chapter.immediate_reaction" rows="2" />
                </label>
                <label>
                  <span>阻碍升级</span>
                  <textarea v-model="chapter.obstacle_escalation" rows="2" />
                </label>
                <label>
                  <span>对方反应</span>
                  <textarea v-model="chapter.counterpart_reaction" rows="2" />
                </label>
                <label>
                  <span>人物选择</span>
                  <textarea v-model="chapter.character_choice" rows="2" />
                </label>
                <label>
                  <span>场景后果</span>
                  <textarea v-model="chapter.scene_consequence" rows="2" />
                </label>
                <label>
                  <span>关系变化</span>
                  <textarea v-model="chapter.relationship_shift" rows="2" />
                </label>
                <label>
                  <span>结尾钩子</span>
                  <textarea v-model="chapter.ending_hook" rows="2" />
                </label>
              </article>
            </div>
            <div v-else-if="storyCanvasView === 'scenes'" class="canvas-scene-list">
              <article v-for="scene in storyCanvasDraft.scenes" :key="scene.id" class="canvas-card">
                <div class="canvas-card-title">
                  <strong>{{ canvasChapterTitle(scene.chapter_id) }} · 场景 {{ scene.scene_order }}</strong>
                  <span>{{ scene.linked_material_ids.length }} 条素材</span>
                </div>
                <div class="canvas-field-grid">
                  <label>
                    <span>当前场景</span>
                    <textarea v-model="scene.current_scene" rows="2" />
                  </label>
                  <label>
                    <span>表层事件</span>
                    <textarea v-model="scene.surface_event" rows="2" />
                  </label>
                  <label>
                    <span>人物欲望</span>
                    <textarea v-model="scene.character_desire" rows="2" />
                  </label>
                  <label>
                    <span>阻碍 / 张力</span>
                    <textarea v-model="scene.tension" rows="2" />
                  </label>
                  <label>
                    <span>禁止推进</span>
                    <textarea :value="scene.forbidden_progress.join('；')" rows="2" @input="updateSceneArray(scene, 'forbidden_progress', $event)" />
                  </label>
                  <label>
                    <span>结尾落点</span>
                    <textarea v-model="scene.ending_beat" rows="2" />
                  </label>
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

          <section v-if="novelStudioMode === 'project' && activeNovelChapter" class="chapter-editor">
            <div class="chapter-editor-head">
              <div>
                <p class="eyebrow">Chapter {{ activeNovelChapter.chapter_order }}</p>
                <h3>{{ chapterDraft.title || "未命名章节" }}</h3>
              </div>
              <div class="chapter-actions">
                <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="checkActiveContinuity">检查</button>
                <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="saveNovelChapter">保存</button>
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
              <span>本章目标</span>
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
              <div class="scene-card-grid">
                <label v-for="field in sceneCardFields" :key="field.key">
                  <span>{{ field.label }}</span>
                  <textarea v-model="chapterDraft.scene_card[field.key]" :rows="field.rows" />
                </label>
              </div>
            </section>
            <label>
              <span>生成指令</span>
              <textarea v-model="chapterInstruction" rows="2" />
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
              <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="applyOptimizedChapterInstruction">
                优化生成指令
              </button>
            </div>
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
                <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="restoreVersion(version.id)">恢复</button>
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
