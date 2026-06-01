import { ref, type ComputedRef, type Ref } from "vue";
import {
  buildStoryCanvas,
  checkNovelContinuity,
  bindStoryEventPoolEvent,
  createNovelChapter,
  createNovelProject,
  createStoryEventPoolEvent,
  deleteNovelChapter,
  deleteNovelProject,
  deleteStoryEventPoolEvent,
  deleteNovelVersion,
  extendStoryCanvas,
  generateNovelProjectDraft,
  generateProjectChapter,
  getNovelProject,
  listNovelProjects,
  listNovelVersions,
  retireStoryEventPoolEvent,
  restoreNovelVersion,
  saveNovelChapterDraft,
  updateStoryEventPoolEvent,
  updateNovelProject
} from "./api";
import {
  canvasChapterForOrder,
  canvasScenesForChapter,
  normalizeStoryCanvas,
  sceneCardDraftFromCanvas,
  storyCanvasWithChapterDraft
} from "./canvas";
import { formatNovelChapterTitle, stripNovelChapterPrefix } from "./chapterTitle";
import type { CanvasBuildStage, NovelProgressStage } from "./constants";
import type { ChapterDraft, ProjectDraft } from "./useNovelProject";
import type {
  CharacterCard,
  NovelChapter,
  NovelChapterUpdateRequest,
  NovelContinuityReport,
  NovelProject,
  NovelVersion,
  StoryCanvas,
  StoryCanvasChapter,
  StoryCanvasEvent,
  StoryEventPoolEventWriteRequest
} from "../../types";

type NovelStudioMode = "select" | "quick" | "project";

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function isOutlineListLine(line: string) {
  return /^(\d+[\).、]|[-*•]|第[一二三四五六七八九十\d]+[章节幕阶段])\s*/.test(line.trim());
}

function normalizeDraftOutline(text: string) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length <= 1) return text.trim();
  const listLikeCount = lines.filter(isOutlineListLine).length;
  if (listLikeCount >= 2) return lines.join("\n");
  return lines.join("").replace(/\s{2,}/g, " ").trim();
}

export function useNovelProjectActions(options: {
  sessionId: Ref<string>;
  activeCharacter: ComputedRef<CharacterCard | null>;
  novelStudioMode: Ref<NovelStudioMode>;
  novelFocusMode: Ref<boolean>;
  error: Ref<string>;
  novelProjects: Ref<NovelProject[]>;
  activeNovelProjectId: Ref<string>;
  activeNovelChapterId: Ref<string>;
  novelProjectBusy: Ref<boolean>;
  projectDraft: Ref<ProjectDraft>;
  activeNovelProject: ComputedRef<NovelProject | null>;
  activeNovelChapter: ComputedRef<NovelChapter | null>;
  chapterDraft: Ref<ChapterDraft>;
  chapterInstruction: Ref<string>;
  projectChapterTargetLength: Ref<number>;
  continuityReport: Ref<NovelContinuityReport | null>;
  chapterVersions: Ref<NovelVersion[]>;
  storyCanvasDraft: Ref<StoryCanvas>;
  activeCanvasChapter: ComputedRef<StoryCanvasChapter | null>;
  isInitialCanvasRebuildLocked: ComputedRef<boolean>;
  canvasBuildStage: Ref<CanvasBuildStage>;
  novelProgressStage: Ref<NovelProgressStage>;
  novelProgressPercent: Ref<number>;
  novelProgressDetail: Ref<string>;
  syncProjectDraft: (project: NovelProject | null) => void;
  syncChapterDraft: (chapter: NovelChapter | null) => void;
  replaceNovelProject: (project: NovelProject) => void;
  rememberChapterInstruction: () => void;
  clearReorderedChapterInstructionCache: (project: NovelProject, deletedChapterId: string, deletedOrder: number) => void;
  chapterDraftForApi: () => NovelChapterUpdateRequest;
  syncStoryCanvasDraft: (project: NovelProject | null) => void;
  beginCanvasBuildFlow: () => void;
  finishCanvasBuildFlow: () => void;
  clearCanvasBuildTimers: () => void;
  beginNovelProgress: (mode: "quick" | "project") => void;
  clearNovelProgressTimers: () => void;
  setNovelProgress: (stage: NovelProgressStage, percent: number, detail?: string) => void;
  applyChapterGenerationProgress: (chapter: NovelChapter | null | undefined) => void;
  chapterUsedLocalFallback: (chapter: NovelChapter | null | undefined) => boolean;
  chapterHasBackgroundPostprocess: (chapter: NovelChapter | null | undefined) => boolean;
  chapterPostprocessStatus: (chapter: NovelChapter | null | undefined) => string;
}) {
  const projectDraftGenerating = ref(false);
  const projectDraftDiagnostics = ref<Record<string, unknown>>({});
  let novelGenerationRunId = 0;

  async function activeSceneToChapterDraft() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const activeOrder = options.activeNovelChapter.value?.chapter_order || options.activeCanvasChapter.value?.chapter_order || 1;
      const canvasDraft = normalizeStoryCanvas(options.storyCanvasDraft.value);
      const canvasChapter = canvasChapterForOrder(canvasDraft, activeOrder);
      const scene = canvasScenesForChapter(canvasDraft, canvasChapter)[0];
      if (!scene || !canvasChapter) return;
      const nextDraft = {
        ...options.chapterDraft.value,
        title: stripNovelChapterPrefix(canvasChapter.title || options.chapterDraft.value.title),
        goal: canvasChapter.goal || options.chapterDraft.value.goal,
        scene_card: sceneCardDraftFromCanvas(scene as unknown as Record<string, unknown>, canvasChapter)
      };
      options.chapterDraft.value = nextDraft;
      options.projectChapterTargetLength.value = canvasChapter.target_length || options.projectChapterTargetLength.value;
      if (options.activeNovelChapter.value) {
        const project = await saveNovelChapterDraft(options.activeNovelChapter.value.id, {
          project: {
            ...options.projectDraft.value,
            story_canvas: options.storyCanvasDraft.value
          },
          chapter: {
            title: nextDraft.title,
            goal: nextDraft.goal,
            scene_card: nextDraft.scene_card
          }
        });
        options.replaceNovelProject(project);
        options.syncStoryCanvasDraft(project);
        options.syncChapterDraft(options.activeNovelChapter.value);
        await loadChapterVersions();
      } else {
        const project = await updateNovelProject(options.activeNovelProject.value.id, {
          ...options.projectDraft.value,
          story_canvas: options.storyCanvasDraft.value
        });
        options.replaceNovelProject(project);
        options.syncStoryCanvasDraft(project);
      }
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  function selectCanvasChapter(chapter: StoryCanvasChapter) {
    options.rememberChapterInstruction();
    const matched = options.activeNovelProject.value?.chapters.find((item) => item.chapter_order === chapter.chapter_order);
    if (matched) {
      options.activeNovelChapterId.value = matched.id;
      options.syncChapterDraft(matched);
    }
  }

  async function loadNovelProjects() {
    if (!options.sessionId.value) return;
    try {
      options.novelProjects.value = await listNovelProjects(options.sessionId.value);
      if (!options.activeNovelProjectId.value || !options.novelProjects.value.some((project) => project.id === options.activeNovelProjectId.value)) {
        options.activeNovelProjectId.value = options.novelProjects.value[0]?.id || "";
      }
      if (!options.activeNovelChapterId.value || !options.activeNovelProject.value?.chapters.some((chapter) => chapter.id === options.activeNovelChapterId.value)) {
        options.activeNovelChapterId.value = options.activeNovelProject.value?.chapters[0]?.id || "";
      }
      options.syncProjectDraft(options.activeNovelProject.value);
      options.syncChapterDraft(options.activeNovelChapter.value);
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    }
  }

  function selectNovelProject(projectId: string) {
    options.novelStudioMode.value = "project";
    options.activeNovelProjectId.value = projectId;
    options.activeNovelChapterId.value = options.activeNovelProject.value?.chapters[0]?.id || "";
    options.continuityReport.value = null;
    options.syncProjectDraft(options.activeNovelProject.value);
    options.syncChapterDraft(options.activeNovelChapter.value);
    void loadChapterVersions();
  }

  function setNovelStudioMode(mode: NovelStudioMode) {
    options.novelStudioMode.value = mode;
    if (mode !== "project") {
      options.novelFocusMode.value = false;
      return;
    }
    if (!options.activeNovelProjectId.value && options.novelProjects.value[0]) {
      selectNovelProject(options.novelProjects.value[0].id);
    }
  }

  function startProjectDraft() {
    options.novelStudioMode.value = "project";
    options.novelFocusMode.value = false;
    options.activeNovelProjectId.value = "";
    options.activeNovelChapterId.value = "";
    options.continuityReport.value = null;
    options.chapterVersions.value = [];
    projectDraftDiagnostics.value = {};
    options.syncProjectDraft(null);
    options.syncChapterDraft(null);
  }

  function selectNovelChapter(chapterId: string) {
    options.activeNovelChapterId.value = chapterId;
    options.continuityReport.value = null;
    options.syncChapterDraft(options.activeNovelChapter.value);
    void loadChapterVersions();
  }

  async function createLongNovelProject() {
    if (!options.sessionId.value || options.novelProjectBusy.value) return;
    options.novelStudioMode.value = "project";
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await createNovelProject(options.sessionId.value, {
        title: options.projectDraft.value.title || undefined,
        genre: options.projectDraft.value.genre,
        tone: options.projectDraft.value.tone,
        protagonist: options.projectDraft.value.protagonist || options.activeCharacter.value?.name || "",
        worldview: options.projectDraft.value.worldview,
        relationship_setup: options.projectDraft.value.relationship_setup,
        outline: normalizeDraftOutline(options.projectDraft.value.outline),
        story_canvas: options.storyCanvasDraft.value
      });
      options.novelProjects.value = [project, ...options.novelProjects.value.filter((item) => item.id !== project.id)];
      selectNovelProject(project.id);
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function generateProjectDraft(prompt: string) {
    const trimmed = prompt.trim();
    if (!options.sessionId.value || !trimmed || options.novelProjectBusy.value || projectDraftGenerating.value) return;
    projectDraftGenerating.value = true;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    projectDraftDiagnostics.value = {};
    try {
      const result = await generateNovelProjectDraft(options.sessionId.value, {
        prompt: trimmed
      });
      options.projectDraft.value = {
        ...options.projectDraft.value,
        title: result.project.title || options.projectDraft.value.title,
        genre: result.project.genre || options.projectDraft.value.genre,
        tone: result.project.tone || options.projectDraft.value.tone,
        protagonist: result.project.protagonist || options.projectDraft.value.protagonist,
        worldview: result.project.worldview || options.projectDraft.value.worldview,
        relationship_setup: result.project.relationship_setup || options.projectDraft.value.relationship_setup,
        outline: result.project.outline
          ? normalizeDraftOutline(result.project.outline)
          : options.projectDraft.value.outline
      };
      projectDraftDiagnostics.value = result.diagnostics || {};
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      projectDraftGenerating.value = false;
      options.novelProjectBusy.value = false;
    }
  }

  async function saveNovelProject() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await updateNovelProject(options.activeNovelProject.value.id, {
        ...options.projectDraft.value,
        outline: normalizeDraftOutline(options.projectDraft.value.outline),
        story_canvas: options.storyCanvasDraft.value
      });
      options.replaceNovelProject(project);
      options.syncStoryCanvasDraft(project);
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function deleteActiveNovelProject(projectId: string) {
    if (!projectId || options.novelProjectBusy.value) return;
    const project = options.novelProjects.value.find((item) => item.id === projectId);
    const title = project?.title || "当前长篇项目";
    if (!window.confirm(`删除长篇项目「${title}」？章节、画布和版本会从列表中移除。`)) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      await deleteNovelProject(projectId);
      options.novelProjects.value = options.novelProjects.value.filter((item) => item.id !== projectId);
      if (options.activeNovelProjectId.value === projectId) {
        const next = options.novelProjects.value[0];
        if (next) {
          selectNovelProject(next.id);
        } else {
          startProjectDraft();
        }
      }
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function rebuildStoryCanvas() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    if (options.isInitialCanvasRebuildLocked.value) {
      options.error.value = "已有正文后不能重建初版画布。请通过生成/续写当前章来滚动更新后续两章画布。";
      return;
    }
    options.novelProjectBusy.value = true;
    options.error.value = "";
    options.beginCanvasBuildFlow();
    try {
      const savedProject = await updateNovelProject(options.activeNovelProject.value.id, {
        ...options.projectDraft.value
      });
      options.replaceNovelProject(savedProject);
      const project = await buildStoryCanvas(savedProject.id);
      options.replaceNovelProject(project);
      options.syncProjectDraft(project);
      options.syncChapterDraft(options.activeNovelChapter.value);
      options.finishCanvasBuildFlow();
    } catch (err) {
      options.clearCanvasBuildTimers();
      options.canvasBuildStage.value = "failed";
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function saveStoryCanvas() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await updateNovelProject(options.activeNovelProject.value.id, {
        ...options.projectDraft.value,
        story_canvas: options.storyCanvasDraft.value
      });
      options.replaceNovelProject(project);
      options.syncStoryCanvasDraft(project);
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function addNovelChapter() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    options.novelStudioMode.value = "project";
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await createNovelChapter(options.activeNovelProject.value.id, {
        title: "新章节",
        goal: "承接前文，完成一个具体事件中的关系推进。",
        status: "planned"
      });
      options.replaceNovelProject(project);
      options.activeNovelChapterId.value = project.chapters[project.chapters.length - 1]?.id || "";
      options.syncChapterDraft(options.activeNovelChapter.value);
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function deleteActiveNovelChapter() {
    if (!options.activeNovelProject.value || !options.activeNovelChapter.value || options.novelProjectBusy.value) return;
    const chapter = options.activeNovelChapter.value;
    if (!window.confirm(`删除「${formatNovelChapterTitle(chapter.chapter_order, chapter.title)}」？章节正文和版本记录都会删除，后续章节会重新编号并标记受影响。`)) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const deletedOrder = chapter.chapter_order;
      const project = await deleteNovelChapter(chapter.id);
      options.replaceNovelProject(project);
      options.syncStoryCanvasDraft(project);
      options.clearReorderedChapterInstructionCache(project, chapter.id, deletedOrder);
      const nextChapter = project.chapters.find((item) => item.chapter_order >= deletedOrder) || project.chapters[project.chapters.length - 1] || null;
      options.activeNovelChapterId.value = nextChapter?.id || "";
      options.syncChapterDraft(options.activeNovelChapter.value);
      if (window.confirm("是否从删除位置前一章开始滚动重规划后续画布？已有正文会保留，后续章节仍会标记为受影响，方便你逐章确认。")) {
        options.beginCanvasBuildFlow();
        try {
          const replanned = await extendStoryCanvas(project.id, {
            from_chapter_order: Math.max(0, deletedOrder - 1),
            count: 4,
            instruction: `第 ${deletedOrder} 章已删除。请从第 ${deletedOrder} 章开始重新接上后续规划，保持已保留正文不被直接覆盖。`
          });
          options.replaceNovelProject(replanned);
          options.syncProjectDraft(replanned);
          const refreshedChapter = replanned.chapters.find((item) => item.chapter_order >= deletedOrder) || replanned.chapters[replanned.chapters.length - 1] || null;
          options.activeNovelChapterId.value = refreshedChapter?.id || "";
          options.syncChapterDraft(options.activeNovelChapter.value);
          options.finishCanvasBuildFlow();
        } catch (err) {
          options.clearCanvasBuildTimers();
          options.canvasBuildStage.value = "failed";
          options.error.value = readableError(err);
        }
      }
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function saveNovelChapter() {
    if (!options.activeNovelProject.value || !options.activeNovelChapter.value || options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const syncedCanvas = storyCanvasWithChapterDraft(options.storyCanvasDraft.value, options.activeNovelChapter.value, options.chapterDraft.value, {
        targetLength: options.projectChapterTargetLength.value,
        fallbackChapter: options.activeCanvasChapter.value
      });
      options.storyCanvasDraft.value = syncedCanvas;
      const project = await saveNovelChapterDraft(options.activeNovelChapter.value.id, {
        project: {
          ...options.projectDraft.value,
          story_canvas: syncedCanvas
        },
        chapter: options.chapterDraftForApi()
      });
      options.replaceNovelProject(project);
      options.syncStoryCanvasDraft(project);
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function generateActiveChapter() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    const runId = ++novelGenerationRunId;
    options.novelStudioMode.value = "project";
    options.novelProjectBusy.value = true;
    options.error.value = "";
    options.beginNovelProgress("project");
    try {
      const generatingChapterId = options.activeNovelChapter.value?.id || "";
      if (options.activeNovelChapter.value) {
        const syncedProject = await saveNovelChapterDraft(options.activeNovelChapter.value.id, {
          project: {
            ...options.projectDraft.value,
            story_canvas: options.storyCanvasDraft.value
          },
          chapter: options.chapterDraftForApi()
        });
        if (runId !== novelGenerationRunId) return;
        options.replaceNovelProject(syncedProject);
      } else {
        const savedProject = await updateNovelProject(options.activeNovelProject.value.id, {
          ...options.projectDraft.value,
          story_canvas: options.storyCanvasDraft.value
        });
        if (runId !== novelGenerationRunId) return;
        options.replaceNovelProject(savedProject);
      }
      const liveChapterId = options.activeNovelChapter.value?.id || generatingChapterId;
      if (liveChapterId) {
        void pollLiveNovelProgress(runId, options.activeNovelProject.value.id, liveChapterId);
      }
      const project = await generateProjectChapter(
        options.activeNovelProject.value.id,
        options.activeNovelChapter.value?.id || null,
        options.chapterInstruction.value,
        options.projectChapterTargetLength.value
      );
      if (runId !== novelGenerationRunId) return;
      options.replaceNovelProject(project);
      options.syncProjectDraft(project);
      if (!options.activeNovelChapterId.value) {
        options.activeNovelChapterId.value = project.chapters[project.chapters.length - 1]?.id || "";
      }
      options.syncChapterDraft(options.activeNovelChapter.value);
      await loadChapterVersions();
      const generatedChapter = project.chapters.find((item) => item.id === (generatingChapterId || options.activeNovelChapterId.value)) || options.activeNovelChapter.value;
      options.applyChapterGenerationProgress(generatedChapter);
      if (options.chapterUsedLocalFallback(generatedChapter)) {
        options.clearNovelProgressTimers();
        options.setNovelProgress("fallback", 100);
      } else if (options.chapterHasBackgroundPostprocess(generatedChapter)) {
        options.setNovelProgress("handoff", 96);
        pollChapterPostprocess(project.id, generatedChapter?.id || options.activeNovelChapterId.value);
      } else {
        options.clearNovelProgressTimers();
        options.setNovelProgress("done", 100);
      }
    } catch (err) {
      if (runId !== novelGenerationRunId) return;
      options.error.value = readableError(err);
      options.clearNovelProgressTimers();
      options.setNovelProgress("failed", 100);
    } finally {
      if (runId === novelGenerationRunId) {
        options.novelProjectBusy.value = false;
      }
    }
  }

  async function checkActiveContinuity() {
    if (!options.activeNovelProject.value || options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      options.continuityReport.value = await checkNovelContinuity(options.activeNovelProject.value.id, options.activeNovelChapter.value?.id || null);
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function loadChapterVersions() {
    if (!options.activeNovelChapter.value) {
      options.chapterVersions.value = [];
      return;
    }
    try {
      options.chapterVersions.value = await listNovelVersions(options.activeNovelChapter.value.id);
    } catch {
      options.chapterVersions.value = [];
    }
  }

  async function applyEventPoolProjectUpdate(action: () => Promise<NovelProject>) {
    if (options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await action();
      options.replaceNovelProject(project);
      options.syncStoryCanvasDraft(project);
      options.syncChapterDraft(options.activeNovelChapter.value);
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function createEventPoolEvent(payload: StoryEventPoolEventWriteRequest) {
    const project = options.activeNovelProject.value;
    if (!project) return;
    await applyEventPoolProjectUpdate(() => createStoryEventPoolEvent(project.id, payload));
  }

  async function editEventPoolEvent(event: StoryCanvasEvent, payload: StoryEventPoolEventWriteRequest) {
    const project = options.activeNovelProject.value;
    if (!project || !event.id) return;
    await applyEventPoolProjectUpdate(() => updateStoryEventPoolEvent(project.id, event.id, payload));
  }

  async function retireEventPoolEventAction(event: StoryCanvasEvent) {
    const project = options.activeNovelProject.value;
    if (!project || !event.id) return;
    if (!window.confirm("退休这条事件？")) return;
    await applyEventPoolProjectUpdate(() => retireStoryEventPoolEvent(project.id, event.id));
  }

  async function deleteEventPoolEventAction(event: StoryCanvasEvent) {
    const project = options.activeNovelProject.value;
    if (!project || !event.id) return;
    if (!window.confirm("删除这条未绑定事件？")) return;
    await applyEventPoolProjectUpdate(() => deleteStoryEventPoolEvent(project.id, event.id));
  }

  async function bindEventToActiveChapter(event: StoryCanvasEvent, useMode?: "strict" | "guide" | "flavor" | "free") {
    const project = options.activeNovelProject.value;
    const chapter = options.activeNovelChapter.value;
    if (!project || !chapter || !event.id) return;
    const mode = useMode || (["strict", "guide", "flavor", "free"].includes(String(event.use_mode || ""))
      ? event.use_mode as "strict" | "guide" | "flavor" | "free"
      : "guide");
    await applyEventPoolProjectUpdate(() => bindStoryEventPoolEvent(project.id, chapter.id, {
      event_id: event.id,
      use_mode: mode
    }));
  }

  async function clearActiveChapterEventBinding() {
    const project = options.activeNovelProject.value;
    const chapter = options.activeNovelChapter.value;
    if (!project || !chapter) return;
    await applyEventPoolProjectUpdate(() => bindStoryEventPoolEvent(project.id, chapter.id, { event_id: null }));
  }

  async function rebindActiveChapterEventFromPrompt() {
    const project = options.activeNovelProject.value;
    const chapter = options.activeNovelChapter.value;
    if (!project || !chapter) return;
    const eventId = window.prompt("输入要绑定的事件 ID，留空则取消绑定", options.activeCanvasChapter.value?.event_pool_id || "");
    if (eventId === null) return;
    await applyEventPoolProjectUpdate(() => bindStoryEventPoolEvent(project.id, chapter.id, { event_id: eventId.trim() || null }));
  }

  async function pollChapterPostprocess(projectId: string, chapterId: string) {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 5000));
      if (!options.activeNovelProject.value || options.activeNovelProject.value.id !== projectId) return;
      try {
        const project = await getNovelProject(projectId);
        options.replaceNovelProject(project);
        options.syncProjectDraft(project);
        const chapter = project.chapters.find((item) => item.id === chapterId);
        options.applyChapterGenerationProgress(chapter);
        const status = options.chapterPostprocessStatus(chapter);
        if (status === "handoff_done") {
          options.setNovelProgress("replan", Math.max(options.novelProgressPercent.value, 96), options.novelProgressDetail.value || "后台滚动重规划后续两章画布和场景卡");
        }
        if (status === "done") {
          options.clearNovelProgressTimers();
          options.setNovelProgress("done", 100, "正文、状态和后续画布已更新");
          options.syncChapterDraft(options.activeNovelChapter.value);
          await loadChapterVersions();
          return;
        }
        if (status === "failed") {
          options.clearNovelProgressTimers();
          options.setNovelProgress("failed", 100, options.novelProgressDetail.value);
          options.error.value = "正文已返回，但后台交接或滚动画布失败。可以稍后重新生成或刷新项目。";
          return;
        }
      } catch (err) {
        options.error.value = `正文已返回；后台状态刷新失败：${readableError(err)}`;
        return;
      }
    }
    options.error.value = "正文已返回；后台交接仍在运行，可以继续编辑或稍后刷新查看 Novel State。";
  }

  async function restoreVersion(versionId: string) {
    if (options.novelProjectBusy.value) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await restoreNovelVersion(versionId);
      options.replaceNovelProject(project);
      options.syncChapterDraft(options.activeNovelChapter.value);
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function deleteVersion(versionId: string) {
    if (options.novelProjectBusy.value) return;
    if (!window.confirm("删除这个版本记录？当前章节正文不会被删除。")) return;
    options.novelProjectBusy.value = true;
    options.error.value = "";
    try {
      const project = await deleteNovelVersion(versionId);
      options.replaceNovelProject(project);
      await loadChapterVersions();
    } catch (err) {
      options.error.value = readableError(err);
    } finally {
      options.novelProjectBusy.value = false;
    }
  }

  async function pollLiveNovelProgress(runId: number, projectId: string, chapterId: string) {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
      if (runId !== novelGenerationRunId) return;
      if (["done", "fallback", "failed"].includes(options.novelProgressStage.value)) return;
      try {
        const project = await getNovelProject(projectId);
        if (runId !== novelGenerationRunId) return;
        options.replaceNovelProject(project);
        const chapter = project.chapters.find((item) => item.id === chapterId);
        options.applyChapterGenerationProgress(chapter);
      } catch {
        return;
      }
    }
  }

  function unlockNovelProgress() {
    novelGenerationRunId += 1;
    options.novelProjectBusy.value = false;
    options.clearNovelProgressTimers();
    options.setNovelProgress("failed", 100);
    options.error.value = "已解除前端生成锁定。如果后端稍后完成，刷新项目即可查看最新章节。";
  }

  return {
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
    loadChapterVersions,
    createEventPoolEvent,
    editEventPoolEvent,
    retireEventPoolEventAction,
    deleteEventPoolEventAction,
    bindEventToActiveChapter,
    clearActiveChapterEventBinding,
    rebindActiveChapterEventFromPrompt,
    restoreVersion,
    deleteVersion,
    unlockNovelProgress
  };
}
