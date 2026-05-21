import { computed, ref, type Ref } from "vue";
import { generateNovel } from "./api";
import {
  novelFidelityLabels,
  novelFormLabels,
  novelPerspectiveLabels,
  type NovelProgressStage
} from "./constants";
import type {
  NovelFidelity,
  NovelForm,
  NovelGenerateResponse,
  NovelPerspective
} from "../../types";

type NovelStudioMode = "select" | "quick" | "project";
type NovelProgressMode = "quick" | "project";

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

export function useShortNovel(options: {
  sessionId: Ref<string>;
  busy: Ref<boolean>;
  error: Ref<string>;
  novelStudioMode: Ref<NovelStudioMode>;
  beginNovelProgress: (mode: NovelProgressMode) => void;
  clearNovelProgressTimers: () => void;
  setNovelProgress: (stage: NovelProgressStage, percent: number, detail?: string) => void;
}) {
  const novelMessageLimit = ref(40);
  const novelTargetLength = ref(1200);
  const novelPerspective = ref<NovelPerspective>("third_person");
  const novelForm = ref<NovelForm>("daily_short");
  const novelFidelity = ref<NovelFidelity>("polished");
  const novelAtmosphere = ref("温柔、克制、日常");
  const novelResult = ref<NovelGenerateResponse | null>(null);

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
      fidelity ? novelFidelityLabels[fidelity] : novelFidelityLabels[novelFidelity.value]
    ].filter(Boolean).join(" · ");
  });

  async function generateNovelDraft() {
    if (!options.sessionId.value) return;
    options.novelStudioMode.value = "quick";
    options.busy.value = true;
    options.error.value = "";
    novelResult.value = null;
    options.beginNovelProgress("quick");
    try {
      novelResult.value = await generateNovel(options.sessionId.value, {
        message_limit: novelMessageLimit.value,
        perspective: novelPerspective.value,
        form: novelForm.value,
        fidelity: novelFidelity.value,
        atmosphere: novelAtmosphere.value,
        target_length: novelTargetLength.value
      });
      options.clearNovelProgressTimers();
      options.setNovelProgress("done", 100);
    } catch (err) {
      options.error.value = readableError(err);
      options.clearNovelProgressTimers();
      options.setNovelProgress("failed", 100);
    } finally {
      options.busy.value = false;
    }
  }

  function clearNovelResult() {
    novelResult.value = null;
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

  return {
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
  };
}
