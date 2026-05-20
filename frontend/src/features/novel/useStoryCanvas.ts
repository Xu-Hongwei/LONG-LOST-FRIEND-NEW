import { computed, ref, type ComputedRef } from "vue";
import { canvasActionChainFields, canvasBuildSteps, type CanvasBuildStage } from "./constants";
import { emptyStoryCanvas, normalizeStoryCanvas } from "./canvas";
import type { NovelChapter, NovelProject, StoryCanvas, StoryCanvasChapter, StoryCanvasScene } from "../../types";

export type StoryCanvasView = "flow" | "chapters" | "scenes" | "threads";

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

export function useStoryCanvas(
  activeNovelProject: ComputedRef<NovelProject | null>,
  activeNovelChapter: ComputedRef<NovelChapter | null>
) {
  const storyCanvasView = ref<StoryCanvasView>("flow");
  const storyCanvasDraft = ref<StoryCanvas>(emptyStoryCanvas());
  const canvasBuildStage = ref<CanvasBuildStage>("idle");
  const canvasBuildPercent = ref(0);
  const canvasBuildWaitingSeconds = ref(0);
  const canvasBuildRunCount = ref(0);
  const canvasBuildLastLabel = ref("");
  let canvasBuildTimers: number[] = [];
  let canvasBuildTicker: number | null = null;

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

  function syncStoryCanvasDraft(project: NovelProject | null) {
    storyCanvasDraft.value = normalizeStoryCanvas(project?.story_canvas);
  }

  function canvasChapterTitle(chapterId: string) {
    return storyCanvasDraft.value.chapters.find((chapter) => chapter.id === chapterId)?.title || chapterId || "未绑定章节";
  }

  function canvasBuildStepClass(index: number) {
    return {
      active: index === activeCanvasBuildStepIndex.value && !["done", "failed", "idle"].includes(canvasBuildStage.value),
      done: canvasBuildStage.value === "done" || index < activeCanvasBuildStepIndex.value,
      failed: canvasBuildStage.value === "failed" && index === activeCanvasBuildStepIndex.value
    };
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

  return {
    storyCanvasView,
    storyCanvasDraft,
    canvasBuildStage,
    canvasBuildPercent,
    canvasBuildWaitingSeconds,
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
  };
}
