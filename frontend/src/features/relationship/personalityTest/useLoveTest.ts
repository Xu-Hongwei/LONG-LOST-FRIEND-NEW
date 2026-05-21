import { computed, ref } from "vue";
import { saveLoveResultImageToPng } from "./resultImage";
import {
  loadLoveAnswersForVisitor,
  loadLoveGenderForVisitor,
  resetLoveAnswersForVisitor,
  saveLoveAnswersForVisitor,
  saveLoveGenderForVisitor
} from "./storage";
import { loveProfiles, loveQuestions } from "./data";
import type { LoveDimension, LoveGender } from "./data";

export const loveDimensionLabels: Record<LoveDimension, string> = {
  warmth: "情绪温度",
  space: "边界留白",
  initiative: "主动推进",
  security: "安全确认",
  depth: "深度连接",
  playfulness: "轻盈火花"
};

export function useLoveTest(initialVisitorId = "") {
  const activeVisitorId = ref(initialVisitorId);
  const loveAnswers = ref<Record<string, number>>(loadLoveAnswersForVisitor(initialVisitorId));
  const loveGender = ref<LoveGender>(loadLoveGenderForVisitor(initialVisitorId));
  const showLoveResultModal = ref(false);

  const loveProgress = computed(() => Object.keys(loveAnswers.value).length);
  const loveProgressPercent = computed(() => Math.round((loveProgress.value / loveQuestions.length) * 100));
  const loveScores = computed<Record<LoveDimension, number>>(() => {
    const scores: Record<LoveDimension, number> = {
      warmth: 0,
      space: 0,
      initiative: 0,
      security: 0,
      depth: 0,
      playfulness: 0
    };
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
    const maxScores: Record<LoveDimension, number> = {
      warmth: 0,
      space: 0,
      initiative: 0,
      security: 0,
      depth: 0,
      playfulness: 0
    };
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

  function loveBarWidth(dimension: LoveDimension, value: number) {
    const max = loveDimensionMax.value[dimension] || 1;
    return Math.min(100, Math.round((value / max) * 100));
  }

  function answerLoveQuestion(questionId: string, optionIndex: number) {
    const wasComplete = hasCompleteLoveTest.value;
    loveAnswers.value = { ...loveAnswers.value, [questionId]: optionIndex };
    saveLoveAnswersForVisitor(activeVisitorId.value, loveAnswers.value);
    if (!wasComplete && Object.keys(loveAnswers.value).length === loveQuestions.length) {
      showLoveResultModal.value = true;
    }
  }

  function resetLoveTest() {
    loveAnswers.value = {};
    showLoveResultModal.value = false;
    resetLoveAnswersForVisitor(activeVisitorId.value);
  }

  function setLoveGender(gender: LoveGender) {
    loveGender.value = gender;
    saveLoveGenderForVisitor(activeVisitorId.value, gender);
  }

  function refreshLoveTestForVisitor(visitorId: string) {
    activeVisitorId.value = visitorId;
    loveAnswers.value = loadLoveAnswersForVisitor(visitorId);
    loveGender.value = loadLoveGenderForVisitor(visitorId);
    showLoveResultModal.value = false;
  }

  async function saveLoveResultImage() {
    if (!loveResult.value) return;
    try {
      await saveLoveResultImageToPng(loveResult.value, loveGender.value);
    } catch (err) {
      console.error("生成图片失败: ", err);
    }
  }

  return {
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
  };
}
