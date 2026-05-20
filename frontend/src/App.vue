<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from "vue";
import {
  createSession,
  deleteMemoryItem,
  exportSession,
  getMemoryPane,
  getStoryPane,
  listCharacters,
  patchMemory,
  refreshStoryPane,
  resolveVisitor,
  sendMessage,
  updateMemoryItem,
  waitForMemoryPostprocess
} from "./features/chat/api";
import {
  buildStoryCanvas,
  checkNovelContinuity,
  createNovelChapter,
  createNovelProject,
  deleteNovelChapter,
  deleteNovelVersion,
  extendStoryCanvas,
  generateNovel,
  generateProjectChapter,
  getNovelProject,
  listNovelProjects,
  listNovelVersions,
  optimizeNovelInstruction,
  restoreNovelVersion,
  saveNovelChapterDraft,
  updateNovelChapter,
  updateNovelProject
} from "./features/novel/api";
import {
  canvasActionChainFields,
  DEFAULT_CHAPTER_INSTRUCTION,
  novelChapterStatusLabels,
  novelChapterStatusOptions,
  novelFidelityLabels,
  novelFormLabels,
  novelPerspectiveLabels,
  sceneCardFields
} from "./features/novel/constants";
import type { CanvasActionKey } from "./features/novel/constants";
import {
  canvasChapterForOrder,
  canvasFieldText,
  canvasScenesForChapter,
  derivedSceneCardFromCanvasChapter,
  normalizeStoryCanvas,
  sceneCardDraftFromCanvas,
  sceneCardWithPlanningDefaults,
  storyCanvasWithChapterDraft
} from "./features/novel/canvas";
import type { ChapterSceneCardDraft } from "./features/novel/canvas";
import { useStoryCanvas } from "./features/novel/useStoryCanvas";
import type { StoryCanvasView } from "./features/novel/useStoryCanvas";
import { useNovelProgress } from "./features/novel/useNovelProgress";
import ContextBrief from "./components/ContextBrief.vue";
import ChatPanel from "./features/chat/ChatPanel.vue";
import ChatMemoryPanel from "./features/chat/ChatMemoryPanel.vue";
import CharacterInsightsPanel from "./features/chat/CharacterInsightsPanel.vue";
import CanvasChaptersView from "./features/novel/CanvasChaptersView.vue";
import CanvasFlowView from "./features/novel/CanvasFlowView.vue";
import CanvasScenesView from "./features/novel/CanvasScenesView.vue";
import CanvasThreadsView from "./features/novel/CanvasThreadsView.vue";
import NovelRail from "./features/novel/NovelRail.vue";
import ProjectChapterEditor from "./features/novel/ProjectChapterEditor.vue";
import ProjectChapterProgress from "./features/novel/ProjectChapterProgress.vue";
import ProjectEmptyState from "./features/novel/ProjectEmptyState.vue";
import ProjectSettingsDrawer from "./features/novel/ProjectSettingsDrawer.vue";
import QuickDraftPanel from "./features/novel/QuickDraftPanel.vue";
import StoryCanvasHeader from "./features/novel/StoryCanvasHeader.vue";
import StoryBiblePanel from "./features/novel/StoryBiblePanel.vue";
import LoveTestPanel from "./features/personalityTest/LoveTestPanel.vue";
import { useLoveTest } from "./features/personalityTest/useLoveTest";
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
  StoryCanvasChapter,
  StoryPane
} from "./types";

const VISITOR_KEY = "campus-pulse-lite-visitor";
const CHARACTER_KEY = "campus-pulse-lite-character";
const STORY_AUTO_REFRESH_USER_INTERVAL = 6;

type PageKey = "chat" | "love-test" | "novel";
type NovelStudioMode = "select" | "quick" | "project";
type StoryRefreshOptions = { silent?: boolean };
type NovelVersionDisplay = NovelVersion & {
  duplicateCount: number;
  restoreCount: number;
  sourceKeys: string[];
};
const currentPage = ref<PageKey>("chat");
const novelStudioMode = ref<NovelStudioMode>("select");
const {
  novelProgressStage,
  novelProgressPercent,
  novelProgressDetail,
  showActiveNovelProgress,
  novelProgressLabel,
  novelStepClass,
  clearNovelProgressTimers,
  setNovelProgress,
  applyChapterGenerationProgress,
  chapterUsedLocalFallback,
  chapterPostprocessStatus,
  chapterHasBackgroundPostprocess,
  beginNovelProgress
} = useNovelProgress(novelStudioMode);
const visitorId = ref(localStorage.getItem(VISITOR_KEY) || "");
const {
  loveAnswers,
  loveGender,
  showLoveResultModal,
  loveProgress,
  loveProgressPercent,
  loveDimensionEntries,
  loveResult,
  selectedLoveDetail,
  loveProfileImageUrl,
  hasCompleteLoveTest,
  loveBarWidth,
  answerLoveQuestion,
  resetLoveTest,
  setLoveGender,
  refreshLoveTestForVisitor,
  saveLoveResultImage
} = useLoveTest(visitorId.value);
const chatPanelRef = ref<InstanceType<typeof ChatPanel> | null>(null);
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
const storyRefreshCountsBySession = ref<Record<string, number>>({});
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
const activeNovelProject = computed(() =>
  novelProjects.value.find((project) => project.id === activeNovelProjectId.value) || null
);
const activeNovelChapter = computed(() =>
  activeNovelProject.value?.chapters.find((chapter) => chapter.id === activeNovelChapterId.value) || activeNovelProject.value?.chapters[0] || null
);
const {
  storyCanvasView,
  storyCanvasDraft,
  canvasBuildStage,
  canvasBuildPercent,
  canvasBuildActionLabel,
  canvasFlowMetrics,
  canvasSourceLabel,
  canvasBuildSummary,
  canvasBuildProgressLabel,
  isInitialCanvasRebuildLocked,
  activeCanvasChapter,
  activeCanvasScenes,
  activeCanvasActionChain,
  activeNovelPriorStateEntries,
  novelStateSummary,
  novelStateOpenThreads,
  novelStateLastHandoff,
  novelStateLastHandoffText,
  syncStoryCanvasDraft,
  canvasChapterTitle,
  canvasBuildStepClass,
  clearCanvasBuildTimers,
  beginCanvasBuildFlow,
  finishCanvasBuildFlow
} = useStoryCanvas(activeNovelProject, activeNovelChapter);
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
let novelGenerationRunId = 0;

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
const memoryDiagnostics = computed(() => memoryPane.value?.diagnostics || {});
const postprocessStatus = computed(() => String(memoryDiagnostics.value.status || "idle"));
const postprocessStatusLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: "idle",
    queued: "queued",
    running: "running",
    succeeded: "succeeded",
    failed: "failed",
    skipped: "skipped",
    partial: "partial"
  };
  return labels[postprocessStatus.value] || postprocessStatus.value;
});
const postprocessStages = computed(() => {
  const stages = memoryDiagnostics.value.stages;
  if (!stages || typeof stages !== "object") return [];
  return ["memory", "state", "bond"].map((key) => {
    const stage = ((stages as Record<string, unknown>)[key] || {}) as Record<string, unknown>;
    return {
      key,
      status: String(stage.status || "idle"),
      detail: stage.error_type
        ? String(stage.error_type)
        : stage.reason
          ? String(stage.reason)
          : key === "memory" && stage.status === "succeeded"
            ? `${Number(stage.stored_count || 0)} saved`
            : stage.updated !== undefined
              ? `updated ${stage.updated ? "yes" : "no"}`
              : stage.duration_ms !== undefined
                ? `${Number(stage.duration_ms)}ms`
                : ""
    };
  });
});
const postprocessDetail = computed(() => {
  const diagnostics = memoryDiagnostics.value;
  if (postprocessStatus.value === "failed") {
    return String(diagnostics.error_type || diagnostics.error_message || "unknown error");
  }
  if (postprocessStatus.value === "skipped") {
    return String(diagnostics.reason || "not available");
  }
  if (postprocessStatus.value === "succeeded") {
    return `${Number(diagnostics.stored_count || 0)} saved / ${Number(diagnostics.extracted_count || 0)} extracted`;
  }
  if (postprocessStatus.value === "partial") {
    return `${Number(diagnostics.stored_count || 0)} saved, some stages failed`;
  }
  if (postprocessStatus.value === "queued" || postprocessStatus.value === "running") {
    return String(diagnostics.user_message_id || "");
  }
  return "no recent analysis";
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

function setPage(page: PageKey) {
  currentPage.value = page;
}

function characterStorageKey(id: string) {
  return `${CHARACTER_KEY}:${id || "anonymous"}`;
}

async function scrollChatToBottom() {
  await nextTick();
  chatPanelRef.value?.scrollToBottom();
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

    await scrollChatToBottom();
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

function currentSceneCardForSave(): ChapterSceneCardDraft {
  return sceneCardWithPlanningDefaults(
    chapterDraft.value.scene_card,
    derivedSceneCardFromCanvasChapter(activeCanvasChapter.value)
  );
}

async function activeSceneToChapterDraft() {
  if (!activeNovelProject.value || novelProjectBusy.value) return;
  novelProjectBusy.value = true;
  error.value = "";
  try {
    const activeOrder = activeNovelChapter.value?.chapter_order || activeCanvasChapter.value?.chapter_order || 1;
    const canvasDraft = normalizeStoryCanvas(storyCanvasDraft.value);
    const canvasChapter = canvasChapterForOrder(canvasDraft, activeOrder);
    const scene = canvasScenesForChapter(canvasDraft, canvasChapter)[0];
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
      const project = await saveNovelChapterDraft(activeNovelChapter.value.id, {
        project: {
          ...projectDraft.value,
          story_canvas: storyCanvasDraft.value
        },
        chapter: {
          title: nextDraft.title,
          goal: nextDraft.goal,
          scene_card: nextDraft.scene_card
        }
      });
      replaceNovelProject(project);
      syncStoryCanvasDraft(project);
      syncChapterDraft(activeNovelChapter.value);
      await loadChapterVersions();
    } else {
      const project = await updateNovelProject(activeNovelProject.value.id, {
        ...projectDraft.value,
        story_canvas: storyCanvasDraft.value
      });
      replaceNovelProject(project);
      syncStoryCanvasDraft(project);
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    novelProjectBusy.value = false;
  }
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
    if (window.confirm("是否从删除位置前一章开始滚动重规划后续画布？已有正文会保留，后续章节仍会标记为受影响，方便你逐章确认。")) {
      beginCanvasBuildFlow();
      try {
        const replanned = await extendStoryCanvas(project.id, {
          from_chapter_order: Math.max(0, deletedOrder - 1),
          count: 4,
          instruction: `第 ${deletedOrder} 章已删除。请从第 ${deletedOrder} 章开始重新接上后续规划，保持已保留正文不被直接覆盖。`
        });
        replaceNovelProject(replanned);
        syncProjectDraft(replanned);
        const refreshedChapter = replanned.chapters.find((item) => item.chapter_order >= deletedOrder) || replanned.chapters[replanned.chapters.length - 1] || null;
        activeNovelChapterId.value = refreshedChapter?.id || "";
        syncChapterDraft(activeNovelChapter.value);
        finishCanvasBuildFlow();
      } catch (err) {
        clearCanvasBuildTimers();
        canvasBuildStage.value = "failed";
        error.value = readableError(err);
      }
    }
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
    const syncedCanvas = storyCanvasWithChapterDraft(storyCanvasDraft.value, activeNovelChapter.value, chapterDraft.value, {
      targetLength: projectChapterTargetLength.value,
      fallbackChapter: activeCanvasChapter.value
    });
    storyCanvasDraft.value = syncedCanvas;
    const project = await saveNovelChapterDraft(activeNovelChapter.value.id, {
      project: {
        ...projectDraft.value,
        story_canvas: syncedCanvas
      },
      chapter: chapterDraftForApi()
    });
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
    if (activeNovelChapter.value) {
      const syncedProject = await saveNovelChapterDraft(activeNovelChapter.value.id, {
        project: {
          ...projectDraft.value,
          story_canvas: storyCanvasDraft.value
        },
        chapter: chapterDraftForApi()
      });
      if (runId !== novelGenerationRunId) return;
      replaceNovelProject(syncedProject);
    } else {
      const savedProject = await updateNovelProject(activeNovelProject.value.id, {
        ...projectDraft.value,
        story_canvas: storyCanvasDraft.value
      });
      if (runId !== novelGenerationRunId) return;
      replaceNovelProject(savedProject);
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

  await scrollChatToBottom();

  try {
    const response = await sendMessage(visitorId.value, sessionId.value, text);
    messages.value.push(response.message);
    characterState.value = response.character_state;
    characterBond.value = response.character_bond;
    memoryPane.value = response.memory_pane;
    manualNoteDraft.value = response.memory_pane.manual_note || "";
    promptSlots.value = response.prompt_slots;
    const postprocess = response.diagnostics?.postprocess;
    const userMessageId = postprocess && typeof postprocess === "object"
      ? String((postprocess as Record<string, unknown>).user_message_id || "")
      : "";
    void refreshMemoryPaneAfterPostprocess(sessionId.value, userMessageId);
    void maybeAutoRefreshStoryTags();

    await scrollChatToBottom();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function refreshMemoryPaneAfterPostprocess(targetSessionId: string, userMessageId: string) {
  if (!userMessageId) return;
  try {
    const pane = await waitForMemoryPostprocess(targetSessionId, userMessageId, 60);
    if (sessionId.value !== targetSessionId) return;
    memoryPane.value = pane;
    manualNoteDraft.value = pane.manual_note || "";
    promptSlots.value = pane.prompt_slots || [];
  } catch (err) {
    console.warn("memory diagnostics wait failed", err);
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

function unlockNovelProgress() {
  novelGenerationRunId += 1;
  novelProjectBusy.value = false;
  clearNovelProgressTimers();
  setNovelProgress("failed", 100);
  error.value = "已解除前端生成锁定。如果后端稍后完成，刷新项目即可查看最新章节。";
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

function lastStoryRefreshCountForSession() {
  return storyRefreshCountsBySession.value[sessionId.value] || 0;
}

function rememberStoryRefreshCountForSession(count: number) {
  if (!sessionId.value) return;
  storyRefreshCountsBySession.value = {
    ...storyRefreshCountsBySession.value,
    [sessionId.value]: count
  };
}

async function maybeAutoRefreshStoryTags() {
  if (!sessionId.value || storyBusy.value) return;
  const userMessageCount = currentUserMessageCount();
  if (userMessageCount < STORY_AUTO_REFRESH_USER_INTERVAL) return;
  if (userMessageCount % STORY_AUTO_REFRESH_USER_INTERVAL !== 0) return;
  if (lastStoryRefreshCountForSession() === userMessageCount) return;
  rememberStoryRefreshCountForSession(userMessageCount);
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
    rememberStoryRefreshCountForSession(currentUserMessageCount());
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

      <ContextBrief
        :current-page="currentPage"
        :active-character="activeCharacter"
        :love-gender="loveGender"
        :love-result="loveResult"
        :love-profile-image-url="loveProfileImageUrl"
        :love-progress="loveProgress"
        :message-count="messages.length"
        :memory-pane="memoryPane"
        @set-love-gender="setLoveGender"
      />
    </aside>

    <ChatPanel
      v-if="currentPage === 'chat'"
      ref="chatPanelRef"
      v-model:draft="draft"
      :active-character="activeCharacter"
      :character-bond="characterBond"
      :bond-percent="bondPercent"
      :busy="busy"
      :messages="messages"
      :error="error"
      @submit="submit"
      @export="exportDebugBundle"
    />

    <LoveTestPanel
      v-else-if="currentPage === 'love-test'"
      v-model:show-result-modal="showLoveResultModal"
      :love-answers="loveAnswers"
      :love-progress="loveProgress"
      :love-progress-percent="loveProgressPercent"
      :has-complete-love-test="hasCompleteLoveTest"
      :love-dimension-entries="loveDimensionEntries"
      :love-result="loveResult"
      :love-gender="loveGender"
      :selected-love-detail="selectedLoveDetail"
      :love-profile-image-url="loveProfileImageUrl"
      :error="error"
      :busy="busy"
      :session-id="sessionId"
      :love-bar-width="loveBarWidth"
      @answer="answerLoveQuestion"
      @reset="resetLoveTest"
      @save-result-image="saveLoveResultImage"
      @apply-profile="applyLoveProfileToMemory"
    />

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
        <NovelRail
          v-model:novel-form="novelForm"
          v-model:novel-perspective="novelPerspective"
          v-model:novel-fidelity="novelFidelity"
          v-model:novel-atmosphere="novelAtmosphere"
          :novel-studio-mode="novelStudioMode"
          :busy="busy"
          :session-id="sessionId"
          :message-count="messages.length"
          :novel-project-busy="novelProjectBusy"
          :novel-projects="novelProjects"
          :active-novel-project="activeNovelProject"
          :active-novel-project-id="activeNovelProjectId"
          :active-novel-chapter-id="activeNovelChapterId"
          :novel-chapter-status-label="novelChapterStatusLabel"
          @generate-quick="generateNovelDraft"
          @create-project="createLongNovelProject"
          @select-project="selectNovelProject"
          @add-chapter="addNovelChapter"
          @select-chapter="selectNovelChapter"
        />

        <article class="novel-desk" :class="{ 'quick-desk': novelStudioMode === 'quick' }">
          <QuickDraftPanel
            v-if="novelStudioMode === 'quick'"
            :show-progress="showActiveNovelProgress"
            :novel-progress-label="novelProgressLabel"
            :novel-progress-percent="novelProgressPercent"
            :novel-project-busy="novelProjectBusy"
            :novel-step-class="novelStepClass"
            :novel-result="novelResult"
            :novel-result-source-label="novelResultSourceLabel"
            :novel-result-control-label="novelResultControlLabel"
            :busy="busy"
            :session-id="sessionId"
            :message-count="messages.length"
            @unlock-progress="unlockNovelProgress"
            @download-markdown="downloadNovelMarkdown"
            @clear-result="novelResult = null"
            @generate-quick="generateNovelDraft"
          />

          <ProjectEmptyState
            v-if="novelStudioMode === 'project' && !activeNovelProject"
            v-model:project-draft="projectDraft"
            :novel-project-busy="novelProjectBusy"
            :story-busy="storyBusy"
            :session-id="sessionId"
            @create-project="createLongNovelProject"
            @refresh-story-tags="refreshStoryTags()"
          />

          <ProjectSettingsDrawer
            v-if="novelStudioMode === 'project' && activeNovelProject"
            v-model:project-draft="projectDraft"
            :novel-project-busy="novelProjectBusy"
            :has-active-project="Boolean(activeNovelProject)"
            @save-project="saveNovelProject"
          />

          <section v-if="novelStudioMode === 'project' && activeNovelProject" class="story-canvas-panel">
            <StoryCanvasHeader
              v-model:story-canvas-view="storyCanvasView"
              :canvas-build-summary="canvasBuildSummary"
              :canvas-build-action-label="canvasBuildActionLabel"
              :novel-project-busy="novelProjectBusy"
              :is-initial-canvas-rebuild-locked="isInitialCanvasRebuildLocked"
              :has-active-canvas-scenes="Boolean(activeCanvasScenes.length)"
              @rebuild-canvas="rebuildStoryCanvas"
              @save-canvas="saveStoryCanvas"
              @apply-to-chapter="activeSceneToChapterDraft"
            />
            <CanvasFlowView
              v-if="storyCanvasView === 'flow'"
              :canvas-build-summary="canvasBuildSummary"
              :canvas-flow-metrics="canvasFlowMetrics"
              :canvas-source-label="canvasSourceLabel"
              :canvas-build-stage="canvasBuildStage"
              :canvas-build-progress-label="canvasBuildProgressLabel"
              :canvas-build-percent="canvasBuildPercent"
              :canvas-build-step-class="canvasBuildStepClass"
              :novel-state-summary="novelStateSummary"
              :novel-state-last-handoff-text="novelStateLastHandoffText"
              :novel-state-open-threads="novelStateOpenThreads"
            />
            <CanvasChaptersView
              v-else-if="storyCanvasView === 'chapters'"
              :chapters="storyCanvasDraft.chapters"
              :active-canvas-chapter-id="activeCanvasChapter?.id || ''"
              :canvas-action-chain-fields="canvasActionChainFields"
              :novel-chapter-status-label="novelChapterStatusLabel"
              :canvas-field-text="canvasFieldText"
              @select-chapter="selectCanvasChapter"
            />
            <CanvasScenesView
              v-else-if="storyCanvasView === 'scenes'"
              :scenes="storyCanvasDraft.scenes"
              :canvas-chapter-title="canvasChapterTitle"
              :canvas-field-text="canvasFieldText"
            />
            <CanvasThreadsView
              v-else-if="storyCanvasView === 'threads'"
              :threads="storyCanvasDraft.threads"
              :canvas-chapter-title="canvasChapterTitle"
            />
          </section>

          <ProjectChapterProgress
            v-if="showActiveNovelProgress && novelStudioMode === 'project'"
            :novel-progress-label="novelProgressLabel"
            :novel-progress-percent="novelProgressPercent"
            :novel-project-busy="novelProjectBusy"
            :novel-progress-stage="novelProgressStage"
            :novel-step-class="novelStepClass"
            @unlock-progress="unlockNovelProgress"
          />

          <ProjectChapterEditor
            v-if="novelStudioMode === 'project' && activeNovelChapter"
            v-model:chapter-draft="chapterDraft"
            v-model:chapter-instruction="chapterInstruction"
            v-model:project-chapter-target-length="projectChapterTargetLength"
            :active-novel-chapter="activeNovelChapter"
            :active-canvas-chapter="activeCanvasChapter"
            :active-canvas-action-chain="activeCanvasActionChain"
            :scene-card-fields="sceneCardFields"
            :novel-chapter-status-options="novelChapterStatusOptions"
            :novel-project-busy="novelProjectBusy"
            :is-optimizing-instruction="isOptimizingInstruction"
            :chapter-length-guide="chapterLengthGuide"
            :chapter-length-ratio="chapterLengthRatio"
            :active-chapter-word-count="activeChapterWordCount"
            :instruction-optimization-note="instructionOptimizationNote"
            :novel-editor-font="novelEditorFont"
            :active-chapter-status-label="novelChapterStatusLabel(activeNovelChapter?.status)"
            :editor-updated-label="editorUpdatedLabel"
            @check-continuity="checkActiveContinuity"
            @save-chapter="saveNovelChapter"
            @delete-chapter="deleteActiveNovelChapter"
            @generate-chapter="generateActiveChapter"
            @optimize-instruction="applyOptimizedChapterInstruction"
          />

          <p v-if="novelStudioMode === 'quick' && messages.length < 2" class="empty">当前会话消息太少，先聊几轮再生成。</p>
          <p v-if="error" class="error">{{ error }}</p>
        </article>

        <StoryBiblePanel
          v-if="novelStudioMode === 'project'"
          :story-pane="storyPane"
          :story-busy="storyBusy"
          :session-id="sessionId"
          :story-auto-refresh-user-interval="STORY_AUTO_REFRESH_USER_INTERVAL"
          :has-active-novel-project="Boolean(activeNovelProject)"
          :story-bible-entries="storyBibleEntries"
          :project-material-groups="projectMaterialGroups"
          :continuity-report="continuityReport"
          :displayed-chapter-versions="displayedChapterVersions"
          :novel-project-busy="novelProjectBusy"
          :message-count="messages.length"
          :error="error"
          @refresh-story-tags="refreshStoryTags()"
          @download-project="downloadNovelProjectMarkdown"
          @restore-version="restoreVersion"
          @delete-version="deleteVersion"
        />
      </section>
    </section>

    <aside v-if="currentPage === 'chat'" class="right-panel">
      <CharacterInsightsPanel
        v-model:state-expanded="stateExpanded"
        v-model:bond-expanded="bondExpanded"
        :character-state="characterState"
        :character-bond="characterBond"
        :energy-percent="energyPercent"
        :resonance-percent="resonancePercent"
        :bond-percent="bondPercent"
      />

      <ChatMemoryPanel
        v-model:manual-note-draft="manualNoteDraft"
        v-model:memory-filter="memoryFilter"
        v-model:memory-draft="memoryDraft"
        v-model:editing-memory-id="editingMemoryId"
        v-model:expanded-memory-id="expandedMemoryId"
        v-model:expanded-slot-key="expandedSlotKey"
        :memory-pane="memoryPane"
        :memory-counts="memoryCounts"
        :filtered-memories="filteredMemories"
        :memory-diagnostics="memoryDiagnostics"
        :postprocess-status="postprocessStatus"
        :postprocess-status-label="postprocessStatusLabel"
        :postprocess-detail="postprocessDetail"
        :postprocess-stages="postprocessStages"
        :included-slots="includedSlots"
        :excluded-slots="excludedSlots"
        @toggle-freeze="toggleFreeze"
        @save-memory-note="saveMemoryNote"
        @save-memory-item="saveMemoryItem"
        @cancel-edit-memory="cancelEditMemory"
        @start-edit-memory="startEditMemory"
        @remove-memory-item="removeMemoryItem"
        @toggle-memory-details="toggleMemoryDetails"
        @toggle-slot-details="toggleSlotDetails"
      />
    </aside>
  </main>
</template>
