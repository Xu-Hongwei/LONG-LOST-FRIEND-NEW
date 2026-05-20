<script setup lang="ts">
import type { StoryCanvasThread } from "../../types";

defineProps<{
  threads: StoryCanvasThread[];
  canvasChapterTitle: (chapterId: string) => string;
}>();
</script>

<template>
  <div class="canvas-card-grid">
    <article v-for="thread in threads" :key="thread.id" class="canvas-card">
      <div class="canvas-card-title">
        <strong>{{ thread.label || "未命名线索" }}</strong>
        <span>{{ thread.kind }} · {{ thread.status }}</span>
      </div>
      <label>
        <span>线索说明</span>
        <textarea v-model="thread.notes" rows="3" />
      </label>
      <div class="canvas-thread-route">
        <span>{{ canvasChapterTitle(thread.setup_chapter_id) }}</span>
        <span>→</span>
        <span>{{ canvasChapterTitle(thread.payoff_chapter_id) }}</span>
      </div>
    </article>
  </div>
</template>
