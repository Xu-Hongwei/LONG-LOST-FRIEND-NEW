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

function eventContractText(chapter: StoryCanvasChapter) {
  const contract = chapter.event_contract && typeof chapter.event_contract === "object"
    ? chapter.event_contract as Record<string, unknown>
    : null;
  if (!contract) return "";
  return [
    String(contract.time_anchor || "").trim(),
    String(contract.place || "").trim(),
    String(contract.external_event || "").trim()
  ].filter(Boolean).join(" · ");
}

function promiseTargetsText(chapter: StoryCanvasChapter) {
  return (chapter.promise_targets || []).slice(0, 4).join(" / ");
}

function continuityText(chapter: StoryCanvasChapter, key: "continuity_hits" | "continuity_risks") {
  const contract = chapter.event_contract && typeof chapter.event_contract === "object"
    ? chapter.event_contract as Record<string, unknown>
    : null;
  const value = contract?.[key];
  return Array.isArray(value) ? value.map(String).filter(Boolean).slice(0, 3).join(" / ") : "";
}
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
        <article v-if="eventContractText(chapter)">
          <span>事件契约</span>
          <p>{{ eventContractText(chapter) }}</p>
        </article>
        <article v-if="chapter.chapter_drive || chapter.progression_role || promiseTargetsText(chapter)">
          <span>本章推进方式</span>
          <p>{{ [chapter.progression_role, chapter.chapter_drive, promiseTargetsText(chapter)].filter(Boolean).join(" · ") }}</p>
        </article>
        <article v-if="continuityText(chapter, 'continuity_hits') || continuityText(chapter, 'continuity_risks')">
          <span>连续性账本</span>
          <p>
            {{ continuityText(chapter, 'continuity_hits') ? `命中：${continuityText(chapter, 'continuity_hits')}` : "" }}
            {{ continuityText(chapter, 'continuity_risks') ? `风险：${continuityText(chapter, 'continuity_risks')}` : "" }}
          </p>
        </article>
        <article v-for="field in canvasActionChainFields" :key="field.key">
          <span>{{ field.label }}</span>
          <p>{{ canvasFieldText(chapter[field.key]) }}</p>
        </article>
      </div>
    </article>
  </div>
</template>
