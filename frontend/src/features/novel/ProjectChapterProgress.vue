<script setup lang="ts">
import { novelDraftSteps, novelReviewSteps } from "./constants";
import type { NovelPipelineStep, NovelProgressStage } from "./constants";

defineProps<{
  novelProgressLabel: string;
  novelProgressPercent: number;
  novelProjectBusy: boolean;
  novelProgressStage: NovelProgressStage;
  novelStepClass: (step: NovelPipelineStep) => Record<string, boolean>;
}>();

defineEmits<{
  unlockProgress: [];
}>();
</script>

<template>
  <section class="novel-progress-card inline-progress chapter-progress-card">
    <div class="novel-progress-meter">
      <span>{{ novelProgressLabel }}</span>
      <strong>{{ novelProgressPercent }}%</strong>
      <i><b :style="{ width: `${novelProgressPercent}%` }"></b></i>
      <button
        v-if="novelProjectBusy"
        type="button"
        class="ghost muted progress-unlock"
        @click="$emit('unlockProgress')"
      >
        解除卡住
      </button>
    </div>
    <div class="novel-step-groups">
      <div class="novel-step-group">
        <div class="novel-step-group-title">
          <span>正文生成</span>
          <small>决定这一章从远程正文还是本地草稿返回</small>
        </div>
        <div class="novel-step-list detailed">
          <span
            v-for="(step, index) in novelDraftSteps"
            :key="step.id"
            :class="novelStepClass(step)"
          >
            <b>{{ index + 1 }}</b>
            <em>{{ step.label }}</em>
            <small>{{ step.detail }}</small>
          </span>
        </div>
      </div>
      <div class="novel-step-group">
        <div class="novel-step-group-title">
          <span>质检与续写状态</span>
          <small>正文返回后再审稿、必要时重写，并更新交接和滚动画布</small>
        </div>
        <div class="novel-step-list detailed review">
          <span
            v-for="(step, index) in novelReviewSteps"
            :key="step.id"
            :class="novelStepClass(step)"
          >
            <b>{{ novelDraftSteps.length + index + 1 }}</b>
            <em>{{ step.label }}</em>
            <small>{{ step.detail }}</small>
          </span>
        </div>
      </div>
    </div>
    <p v-if="novelProgressStage === 'fallback'" class="progress-note warning">
      远程正文没有成功返回，本次只保留本地正文草稿；不会写入全局摘要、交接单或滚动画布。
    </p>
  </section>
</template>
