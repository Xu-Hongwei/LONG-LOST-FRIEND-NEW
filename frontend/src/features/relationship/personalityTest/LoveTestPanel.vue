<script setup lang="ts">
import { loveQuestions } from "./data";
import type { LoveDimension, LoveGender, LoveProfile } from "./data";
import { loveDimensionLabels } from "./useLoveTest";

defineProps<{
  loveAnswers: Record<string, number>;
  loveProgress: number;
  loveProgressPercent: number;
  hasCompleteLoveTest: boolean;
  loveDimensionEntries: [LoveDimension, number][];
  loveResult: LoveProfile | null;
  loveGender: LoveGender;
  selectedLoveDetail: string;
  loveProfileImageUrl: string;
  error: string;
  busy: boolean;
  sessionId: string;
  loveBarWidth: (dimension: LoveDimension, value: number) => number;
}>();

defineEmits<{
  answer: [questionId: string, optionIndex: number];
  reset: [];
  saveResultImage: [];
  applyProfile: [];
}>();

const showResultModal = defineModel<boolean>("showResultModal", { default: false });
</script>

<template>
  <section class="love-test-panel">
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
              type="button"
              :class="{ selected: loveAnswers[question.id] === optionIndex }"
              @click="$emit('answer', question.id, optionIndex)"
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
        <button v-if="hasCompleteLoveTest" type="button" class="wide" @click="showResultModal = true">查看结果</button>
        <button type="button" class="ghost muted" @click="$emit('reset')">重新测试</button>
        <p v-if="error" class="error">{{ error }}</p>
      </aside>
    </section>
  </section>

  <div v-if="showResultModal && loveResult" class="modal-backdrop" @click.self="showResultModal = false">
    <section class="love-modal">
      <button type="button" class="modal-close" @click="showResultModal = false">Close</button>
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
        <button type="button" class="wide" @click="$emit('saveResultImage')">保存结果图片</button>
        <button type="button" class="wide ghost" :disabled="busy || !sessionId" @click="$emit('applyProfile')">写入当前角色记忆</button>
      </div>
    </section>
  </div>
</template>
