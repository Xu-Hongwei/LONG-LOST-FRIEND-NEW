<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  getStoryPane,
  refreshStoryPane
} from "./features/chat/api";
import {
  canvasActionChainFields,
  novelChapterStatusOptions,
  sceneCardFields
} from "./features/novel/constants";
import { canvasFieldText } from "./features/novel/canvas";
import { useStoryCanvas } from "./features/novel/useStoryCanvas";
import type { StoryCanvasView } from "./features/novel/useStoryCanvas";
import { formatNovelChapterTitle } from "./features/novel/chapterTitle";
import { useNovelProgress } from "./features/novel/useNovelProgress";
import { useNovelProject } from "./features/novel/useNovelProject";
import { useNovelInstruction } from "./features/novel/useNovelInstruction";
import { useNovelProjectActions } from "./features/novel/useNovelProjectActions";
import { useShortNovel } from "./features/novel/useShortNovel";
import ContextBrief from "./components/ContextBrief.vue";
import ChatPanel from "./features/chat/ChatPanel.vue";
import { useChatSession } from "./features/chat/useChatSession";
import ChatMemoryPanel from "./features/relationship/ChatMemoryPanel.vue";
import CharacterInsightsPanel from "./features/relationship/CharacterInsightsPanel.vue";
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
import CharacterWorkshopPanel from "./features/characters/CharacterWorkshopPanel.vue";
import LoveTestPanel from "./features/relationship/personalityTest/LoveTestPanel.vue";
import { useLoveTest } from "./features/relationship/personalityTest/useLoveTest";
import { useRelationshipMemory } from "./features/relationship/useRelationshipMemory";
import { patchMemory } from "./features/relationship/api";
import type {
  MemoryPane,
  NovelProject,
  StoryPane
} from "./types";

const VISITOR_KEY = "campus-pulse-lite-visitor";
const CHARACTER_KEY = "campus-pulse-lite-character";
const STORY_AUTO_REFRESH_USER_INTERVAL = 6;

type PageKey = "chat" | "characters" | "love-test" | "novel";
type NovelStudioMode = "select" | "quick" | "project";
type StoryRefreshOptions = { silent?: boolean };
const currentPage = ref<PageKey>("chat");
const novelStudioMode = ref<NovelStudioMode>("select");
const {
  visitorId,
  chatPanelRef,
  characters,
  selectedCharacterId,
  activeCharacter,
  sessionId,
  messages,
  draft,
  busy,
  error,
  memoryPane,
  promptSlots,
  characterState,
  characterBond,
  initializeChatSession,
  openSession,
  selectCharacter,
  refreshCharacters,
  submit,
  exportDebugBundle
} = useChatSession({
  visitorKey: VISITOR_KEY,
  characterKey: CHARACTER_KEY,
  onVisitorChanged: (id) => refreshLoveTestForVisitor(id),
  onSessionOpened: loadSessionSideEffects,
  onAfterUserMessage: maybeAutoRefreshStoryTags
});
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
const {
  manualNoteDraft,
  memoryFilter,
  editingMemoryId,
  memoryDraft,
  expandedMemoryId,
  expandedSlotKey,
  stateExpanded,
  bondExpanded,
  includedSlots,
  excludedSlots,
  filteredMemories,
  memoryCounts,
  memoryDiagnostics,
  postprocessStatus,
  postprocessStatusLabel,
  postprocessStages,
  postprocessDetail,
  saveMemoryNote,
  toggleFreeze,
  startEditMemory,
  cancelEditMemory,
  saveMemoryItem,
  removeMemoryItem,
  toggleMemoryDetails,
  toggleSlotDetails
} = useRelationshipMemory(sessionId, memoryPane, promptSlots, busy, error);
const storyPane = ref<StoryPane | null>(null);
const storyBusy = ref(false);
const storyRefreshCountsBySession = ref<Record<string, number>>({});
const {
  novelProjects,
  activeNovelProjectId,
  activeNovelChapterId,
  novelProjectBusy,
  projectDraft,
  activeNovelProject,
  activeNovelChapter,
  chapterDraft,
  chapterInstruction,
  projectChapterTargetLength,
  isOptimizingInstruction,
  instructionOptimizationNote,
  continuityReport,
  chapterVersions,
  displayedChapterVersions,
  storyBibleEntries,
  projectMaterialGroups,
  novelProjectStats,
  activeChapterWordCount,
  chapterLengthRatio,
  chapterLengthGuide,
  chapterQualityDiagnosis,
  editorUpdatedLabel,
  bindStoryCanvasContext,
  syncProjectDraft,
  rememberChapterInstruction,
  clearReorderedChapterInstructionCache,
  chapterDraftForApi,
  syncChapterDraft,
  replaceNovelProject,
  novelChapterStatusLabel
} = useNovelProject(activeCharacter);
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
bindStoryCanvasContext({
  activeCanvasChapter,
  storyCanvasDraft,
  syncStoryCanvasDraft
});
const { applyOptimizedChapterInstruction } = useNovelInstruction({
  activeNovelProject,
  activeNovelChapter,
  chapterDraft,
  chapterInstruction,
  projectChapterTargetLength,
  isOptimizingInstruction,
  instructionOptimizationNote,
  activeCanvasChapter,
  activeChapterWordCount,
  chapterLengthRatio,
  novelStateLastHandoff,
  novelStateSummary,
  novelStateOpenThreads,
  activeNovelPriorStateEntries,
  chapterQualityDiagnosis,
  rememberChapterInstruction
});
const {
  novelMessageLimit,
  novelTargetLength,
  novelPerspective,
  novelForm,
  novelFidelity,
  novelAtmosphere,
  novelResult,
  novelResultSourceLabel,
  novelResultControlLabel,
  generateNovelDraft,
  clearNovelResult,
  downloadNovelMarkdown
} = useShortNovel({
  sessionId,
  busy,
  error,
  novelStudioMode,
  beginNovelProgress,
  clearNovelProgressTimers,
  setNovelProgress
});
const novelFocusMode = ref(false);
const novelEditorFont = ref<"serif" | "sans">("serif");
const {
  projectDraftGenerating,
  projectDraftDiagnostics,
  activeSceneToChapterDraft,
  selectCanvasChapter,
  loadNovelProjects,
  selectNovelProject,
  setNovelStudioMode,
  startProjectDraft,
  generateProjectDraft,
  selectNovelChapter,
  createLongNovelProject,
  saveNovelProject,
  deleteActiveNovelProject,
  rebuildStoryCanvas,
  saveStoryCanvas,
  addNovelChapter,
  deleteActiveNovelChapter,
  saveNovelChapter,
  generateActiveChapter,
  checkActiveContinuity,
  restoreVersion,
  deleteVersion,
  unlockNovelProgress
} = useNovelProjectActions({
  sessionId,
  activeCharacter,
  novelStudioMode,
  novelFocusMode,
  error,
  novelProjects,
  activeNovelProjectId,
  activeNovelChapterId,
  novelProjectBusy,
  projectDraft,
  activeNovelProject,
  activeNovelChapter,
  chapterDraft,
  chapterInstruction,
  projectChapterTargetLength,
  continuityReport,
  chapterVersions,
  storyCanvasDraft,
  activeCanvasChapter,
  isInitialCanvasRebuildLocked,
  canvasBuildStage,
  novelProgressStage,
  novelProgressPercent,
  novelProgressDetail,
  syncProjectDraft,
  syncChapterDraft,
  replaceNovelProject,
  rememberChapterInstruction,
  clearReorderedChapterInstructionCache,
  chapterDraftForApi,
  syncStoryCanvasDraft,
  beginCanvasBuildFlow,
  finishCanvasBuildFlow,
  clearCanvasBuildTimers,
  beginNovelProgress,
  clearNovelProgressTimers,
  setNovelProgress,
  applyChapterGenerationProgress,
  chapterUsedLocalFallback,
  chapterHasBackgroundPostprocess,
  chapterPostprocessStatus
});
const energyPercent = computed(() => Math.round((characterState.value?.energy || 0) * 100));
const resonancePercent = computed(() => Math.round((characterState.value?.resonance || 0) * 100));
const bondPercent = computed(() => Math.round((characterBond.value?.resonance_base || 0) * 100));

function setPage(page: PageKey) {
  currentPage.value = page;
}

async function refreshWorkshopCharacters(preferredCharacterId = "") {
  await refreshCharacters(preferredCharacterId || selectedCharacterId.value);
}

async function startChatWithCharacter(characterId: string) {
  selectedCharacterId.value = characterId;
  currentPage.value = "chat";
  await openSession();
}

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
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

onMounted(() => {
  void initializeChatSession();
});

async function loadSessionSideEffects(targetSessionId: string) {
  try {
    storyPane.value = await getStoryPane(targetSessionId);
  } catch (err) {
    storyPane.value = {
      session_id: targetSessionId,
      items: [],
      diagnostics: { error: readableError(err) },
    };
  }
  rememberStoryRefreshCountForSession(currentUserMessageCount());
  await loadNovelProjects();
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
  const newUserMessages = userMessageCount - lastStoryRefreshCountForSession();
  if (newUserMessages < STORY_AUTO_REFRESH_USER_INTERVAL) return;
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

function downloadNovelProjectMarkdown() {
  if (!activeNovelProject.value) return;
  const project = activeNovelProject.value;
  const chapters = project.chapters.map((chapter) => [
    `## ${formatNovelChapterTitle(chapter.chapter_order, chapter.title)}`,
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
  <main class="shell" :class="{ 'test-shell': currentPage === 'characters' || currentPage === 'love-test' || currentPage === 'novel', 'novel-focus-shell': currentPage === 'novel' && novelFocusMode }">
    <aside class="left-panel">
      <div class="brand">
        <span class="brand-mark"></span>
        <div>
          <h1>Campus Pulse Lite</h1>
          <p>persona memory lab</p>
        </div>
      </div>

      <nav class="page-nav">
        <button :class="{ active: currentPage === 'characters' }" @click="setPage('characters')">角色工坊</button>
        <button :class="{ active: currentPage === 'chat' }" @click="setPage('chat')">聊天</button>
        <button :class="{ active: currentPage === 'love-test' }" @click="setPage('love-test')">恋爱人格测试</button>
        <button :class="{ active: currentPage === 'novel' }" @click="setPage('novel')">小说工坊</button>
      </nav>

      <label v-if="currentPage === 'chat' || currentPage === 'characters' || currentPage === 'novel'" class="field">
        <span>Visitor ID</span>
        <input v-model="visitorId" @change="currentPage === 'characters' ? refreshWorkshopCharacters() : openSession()" spellcheck="false" />
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

    <CharacterWorkshopPanel
      v-else-if="currentPage === 'characters'"
      :visitor-id="visitorId"
      :characters="characters"
      :active-character-id="selectedCharacterId"
      @refresh="refreshWorkshopCharacters"
      @start-chat="startChatWithCharacter"
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
          @start-project-draft="startProjectDraft"
          @select-project="selectNovelProject"
          @delete-project="deleteActiveNovelProject"
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
            @clear-result="clearNovelResult"
            @generate-quick="generateNovelDraft"
          />

          <ProjectEmptyState
            v-if="novelStudioMode === 'project' && !activeNovelProject"
            v-model:project-draft="projectDraft"
            :novel-project-busy="novelProjectBusy"
            :project-draft-generating="projectDraftGenerating"
            :project-draft-diagnostics="projectDraftDiagnostics"
            :story-busy="storyBusy"
            :session-id="sessionId"
            @create-project="createLongNovelProject"
            @generate-project-draft="generateProjectDraft"
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
