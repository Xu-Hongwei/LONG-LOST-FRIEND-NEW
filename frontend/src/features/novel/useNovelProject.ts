import { computed, ref, type ComputedRef, type Ref } from "vue";
import { DEFAULT_CHAPTER_INSTRUCTION, novelChapterStatusLabels } from "./constants";
import {
  derivedSceneCardFromCanvasChapter,
  sceneCardDraftFromCanvas,
  sceneCardWithPlanningDefaults,
  type ChapterSceneCardDraft
} from "./canvas";
import { stripNovelChapterPrefix } from "./chapterTitle";
import type {
  CharacterCard,
  NovelChapter,
  NovelChapterStatus,
  NovelContinuityReport,
  NovelProject,
  NovelVersion,
  StoryCanvas,
  StoryCanvasChapter
} from "../../types";

export type ProjectDraft = {
  title: string;
  genre: string;
  tone: string;
  protagonist: string;
  worldview: string;
  relationship_setup: string;
  outline: string;
};

export type ChapterDraft = {
  title: string;
  goal: string;
  summary: string;
  body: string;
  status: NovelChapterStatus;
  scene_card: ChapterSceneCardDraft;
};

type NovelVersionDisplay = NovelVersion & {
  duplicateCount: number;
  restoreCount: number;
  sourceKeys: string[];
};

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

export function useNovelProject(activeCharacter: ComputedRef<CharacterCard | null>) {
  const novelProjects = ref<NovelProject[]>([]);
  const activeNovelProjectId = ref("");
  const activeNovelChapterId = ref("");
  const novelProjectBusy = ref(false);
  const projectDraft = ref<ProjectDraft>({
    title: "",
    genre: "校园日常长篇",
    tone: "温柔、克制、日常",
    protagonist: "",
    worldview: "",
    relationship_setup: "",
    outline: ""
  });
  const chapterDraft = ref<ChapterDraft>({
    title: "",
    goal: "",
    summary: "",
    body: "",
    status: "planned",
    scene_card: {}
  });
  const chapterInstruction = ref(DEFAULT_CHAPTER_INSTRUCTION);
  const chapterInstructionsById = ref<Record<string, string>>({});
  const activeInstructionChapterId = ref("");
  const projectChapterTargetLength = ref(1800);
  const isOptimizingInstruction = ref(false);
  const instructionOptimizationNote = ref("");
  const continuityReport = ref<NovelContinuityReport | null>(null);
  const chapterVersions = ref<NovelVersion[]>([]);

  let activeCanvasChapterRef: ComputedRef<StoryCanvasChapter | null> | null = null;
  let storyCanvasDraftRef: Ref<StoryCanvas> | null = null;
  let syncStoryCanvasDraftFn: (project: NovelProject | null) => void = () => {};

  const activeNovelProject = computed(() =>
    novelProjects.value.find((project) => project.id === activeNovelProjectId.value) || null
  );
  const activeNovelChapter = computed(() =>
    activeNovelProject.value?.chapters.find((chapter) => chapter.id === activeNovelChapterId.value) || activeNovelProject.value?.chapters[0] || null
  );
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

  function bindStoryCanvasContext(context: {
    activeCanvasChapter: ComputedRef<StoryCanvasChapter | null>;
    storyCanvasDraft: Ref<StoryCanvas>;
    syncStoryCanvasDraft: (project: NovelProject | null) => void;
  }) {
    activeCanvasChapterRef = context.activeCanvasChapter;
    storyCanvasDraftRef = context.storyCanvasDraft;
    syncStoryCanvasDraftFn = context.syncStoryCanvasDraft;
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
    syncStoryCanvasDraftFn(project);
  }

  function currentSceneCardForSave(): ChapterSceneCardDraft {
    return sceneCardWithPlanningDefaults(
      chapterDraft.value.scene_card,
      derivedSceneCardFromCanvasChapter(activeCanvasChapterRef?.value || null)
    );
  }

  function chapterPlotGoal(chapter: NovelChapter | null) {
    const rawGoal = chapter?.goal || "";
    if (rawGoal && !isInstructionLikeGoal(rawGoal)) return rawGoal;
    const canvasGoal = storyCanvasDraftRef?.value.chapters.find((item) => item.chapter_order === chapter?.chapter_order)?.goal || "";
    return canvasGoal || "";
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
      title: stripNovelChapterPrefix(chapterDraft.value.title),
      scene_card: sceneCard
    };
  }

  function syncChapterDraft(chapter: NovelChapter | null) {
    rememberChapterInstruction();
    chapterDraft.value = {
      title: stripNovelChapterPrefix(chapter?.title || ""),
      goal: chapterPlotGoal(chapter),
      summary: chapter?.summary || "",
      body: chapter?.body || "",
      status: chapter?.status || "planned",
      scene_card: sceneCardDraftFromCanvas(chapter?.scene_card, activeCanvasChapterRef?.value || null)
    };
    syncChapterInstruction(chapter);
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

  function novelChapterStatusLabel(status?: NovelChapterStatus | string) {
    return status ? novelChapterStatusLabels[status as NovelChapterStatus] || status : "计划中";
  }

  return {
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
    currentSceneCardForSave,
    rememberChapterInstruction,
    clearReorderedChapterInstructionCache,
    chapterDraftForApi,
    syncChapterDraft,
    replaceNovelProject,
    novelChapterStatusLabel
  };
}
