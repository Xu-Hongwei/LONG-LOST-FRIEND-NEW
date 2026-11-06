<script setup lang="ts">
import type { NovelGenerateResponse } from "../../types";

defineProps<{
  showProgress: boolean;
  novelResult: NovelGenerateResponse | null;
  novelResultSourceLabel: string;
  novelResultControlLabel: string;
  busy: boolean;
  sessionId: string;
  messageCount: number;
}>();

defineEmits<{
  downloadMarkdown: [];
  clearResult: [];
  generateQuick: [];
}>();
</script>

<template>
  <section v-if="showProgress && (busy || novelResult)" class="novel-progress-card inline-progress" role="status">
    <div class="novel-progress-meter">
      <span>{{ busy ? '正在根据当前会话生成短篇，请稍候。' : `${novelResultSourceLabel}的短篇已返回，可预览或导出。` }}</span>
    </div>
  </section>

  <section v-if="novelResult" class="novel-preview compact-preview quick-result-panel">
    <div class="novel-title-row">
      <div>
        <p class="eyebrow">Quick Draft</p>
        <h3>{{ novelResult.title }}</h3>
        <div class="novel-result-meta">
          <span>{{ novelResultSourceLabel }}</span>
          <span>{{ novelResultControlLabel }}</span>
        </div>
      </div>
      <div class="chapter-actions">
        <button class="ghost muted" type="button" @click="$emit('downloadMarkdown')">Markdown</button>
        <button class="ghost muted" type="button" @click="$emit('clearResult')">收起</button>
      </div>
    </div>
    <p class="novel-synopsis">{{ novelResult.synopsis }}</p>
    <div class="novel-body">{{ novelResult.body }}</div>
  </section>

  <section v-if="!novelResult && !busy" class="quick-empty-state">
    <p class="eyebrow">短篇工作台</p>
    <h3>左侧选择形式和语气，然后生成成稿</h3>
    <p>短篇模式不会加载长篇章节编辑器，生成结果会直接显示在这里，方便预览和导出 Markdown。</p>
    <div class="quick-empty-actions">
      <button type="button" :disabled="busy || !sessionId || messageCount < 2" @click="$emit('generateQuick')">
        生成短篇
      </button>
      <small>{{ messageCount < 2 ? "当前会话消息太少，先聊几轮再生成。" : "会使用当前会话、记忆和剧情标签作为素材。" }}</small>
    </div>
  </section>
</template>
