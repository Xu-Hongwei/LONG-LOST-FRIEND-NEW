<script setup lang="ts">
import type { StoryCanvasChapter } from "../../types";
import type { CanvasActionKey } from "./constants";
import { formatNovelChapterTitle } from "./chapterTitle";

defineProps<{
  chapters: StoryCanvasChapter[];
  activeCanvasChapterId: string;
  canvasActionChainFields: { key: CanvasActionKey; label: string }[];
  novelChapterStatusLabel: (status?: string) => string;
  canvasFieldText: (value: unknown) => string;
}>();

defineEmits<{
  selectChapter: [chapter: StoryCanvasChapter];
}>();
</script>

<template>
  <div class="canvas-card-grid">
    <article
      v-for="chapter in chapters"
      :key="chapter.id"
      class="canvas-card"
      :class="{ active: activeCanvasChapterId === chapter.id }"
      @click="$emit('selectChapter', chapter)"
    >
      <div class="canvas-card-title">
        <strong>{{ formatNovelChapterTitle(chapter.chapter_order, chapter.title) }}</strong>
        <span>{{ novelChapterStatusLabel(chapter.status) }} · {{ chapter.target_length }} 字</span>
      </div>
      <div class="canvas-read-grid">
        <article>
          <span>剧情概述</span>
          <p>{{ canvasFieldText(chapter.goal) }}</p>
        </article>
        <article v-for="field in canvasActionChainFields" :key="field.key">
          <span>{{ field.label }}</span>
          <p>{{ canvasFieldText(chapter[field.key]) }}</p>
        </article>
      </div>
    </article>
  </div>
</template>
