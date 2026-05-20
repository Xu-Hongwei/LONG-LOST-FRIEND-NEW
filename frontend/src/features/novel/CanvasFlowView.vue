<script setup lang="ts">
import type { CanvasBuildStage } from "./constants";
import { canvasBuildSteps } from "./constants";

defineProps<{
  canvasBuildSummary: string;
  canvasFlowMetrics: {
    acts: number;
    chapters: number;
    scenes: number;
    threads: number;
    materials: number;
  };
  canvasSourceLabel: string;
  canvasBuildStage: CanvasBuildStage;
  canvasBuildProgressLabel: string;
  canvasBuildPercent: number;
  canvasBuildStepClass: (index: number) => Record<string, boolean>;
  novelStateSummary: string;
  novelStateLastHandoffText: string;
  novelStateOpenThreads: string[];
}>();
</script>

<template>
  <div class="canvas-flow-view">
    <div class="canvas-flow-summary">
      <div>
        <p class="eyebrow">Canvas Run</p>
        <strong>{{ canvasBuildSummary }}</strong>
      </div>
      <div class="canvas-flow-metrics">
        <span>{{ canvasFlowMetrics.materials }} 素材</span>
        <span>{{ canvasFlowMetrics.acts }} 阶段</span>
        <span>{{ canvasFlowMetrics.chapters }} 章</span>
        <span>{{ canvasFlowMetrics.scenes }} 场景</span>
        <span>{{ canvasFlowMetrics.threads }} 线索</span>
        <span>{{ canvasSourceLabel }}</span>
      </div>
    </div>
    <div
      v-if="canvasBuildStage !== 'idle'"
      class="canvas-build-progress"
      :class="{ complete: canvasBuildStage === 'done', failed: canvasBuildStage === 'failed' }"
    >
      <div>
        <span>{{ canvasBuildProgressLabel }}</span>
        <strong>{{ Math.round(canvasBuildPercent) }}%</strong>
      </div>
      <i aria-hidden="true">
        <b :style="{ width: `${canvasBuildPercent}%` }"></b>
      </i>
    </div>
    <ol class="canvas-flow-steps">
      <li
        v-for="(step, index) in canvasBuildSteps"
        :key="step.id"
        :class="canvasBuildStepClass(index)"
      >
        <i>{{ index + 1 }}</i>
        <div>
          <strong>{{ step.label }}</strong>
          <span>{{ step.detail }}</span>
        </div>
      </li>
    </ol>
    <div class="canvas-flow-note">
      <strong>自动滚动</strong>
      <span>每章生成后会整理交接单、更新 Novel State，并重规划后续两章；“重新生成画布”只适合开局大改。</span>
    </div>
    <div class="novel-state-panel">
      <article>
        <p class="eyebrow">Novel State</p>
        <strong>截至上一章摘要</strong>
        <span>{{ novelStateSummary }}</span>
      </article>
      <article>
        <p class="eyebrow">Last Handoff</p>
        <strong>上一章交接单</strong>
        <span>{{ novelStateLastHandoffText }}</span>
      </article>
      <article>
        <p class="eyebrow">Open Threads</p>
        <strong>未解决线索</strong>
        <span v-if="!novelStateOpenThreads.length">暂无未解决线索。</span>
        <span v-else>{{ novelStateOpenThreads.join("；") }}</span>
      </article>
    </div>
  </div>
</template>
