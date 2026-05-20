import { computed, ref, type Ref } from "vue";
import { novelPipelineSteps, type NovelPipelineStep, type NovelProgressStage } from "./constants";
import type { NovelChapter } from "../../types";

type NovelWorkflowMode = "quick" | "project";

export function useNovelProgress(currentMode: Readonly<Ref<string>>) {
  const activeNovelWorkflowMode = ref<NovelWorkflowMode | null>(null);
  const novelProgressStage = ref<NovelProgressStage>("idle");
  const novelProgressPercent = ref(0);
  const novelProgressVisible = ref(false);
  const novelProgressWaitingSeconds = ref(0);
  const novelProgressDetail = ref("");
  let novelProgressTimers: number[] = [];
  let novelProgressTicker: number | null = null;

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
  const isNovelGenerating = computed(() =>
    !["idle", "done", "failed", "fallback"].includes(novelProgressStage.value)
  );
  const showActiveNovelProgress = computed(() =>
    activeNovelWorkflowMode.value === currentMode.value
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

  function novelStepClass(step: NovelPipelineStep) {
    const index = novelPipelineSteps.findIndex((item) => item.id === step.id);
    const activeIndex = activeNovelStepIndex.value;
    return {
      active: step.id === novelProgressStage.value || (novelProgressStage.value === "fallback" && step.id === "drafting"),
      done: novelProgressStage.value === "done" || (index >= 0 && index < activeIndex),
      failed: novelProgressStage.value === "failed" && index === activeIndex
    };
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
    if (!progress || typeof progress !== "object") return;
    const raw = progress as Record<string, unknown>;
    const stage = asNovelProgressStage(raw.stage);
    if (!stage) return;
    const percent = Number(raw.percent);
    const detail = String(raw.detail || "");
    setNovelProgress(stage, Number.isFinite(percent) ? Math.max(0, Math.min(100, Math.round(percent))) : novelProgressPercent.value, detail);
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

  return {
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
  };
}
