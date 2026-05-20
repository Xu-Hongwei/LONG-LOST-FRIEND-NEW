<script setup lang="ts">
type StoryCanvasView = "flow" | "chapters" | "scenes" | "threads";

defineProps<{
  canvasBuildSummary: string;
  canvasBuildActionLabel: string;
  novelProjectBusy: boolean;
  isInitialCanvasRebuildLocked: boolean;
  hasActiveCanvasScenes: boolean;
}>();

defineEmits<{
  rebuildCanvas: [];
  saveCanvas: [];
  applyToChapter: [];
}>();

const storyCanvasView = defineModel<StoryCanvasView>("storyCanvasView", { required: true });
</script>

<template>
  <div class="story-canvas-head">
    <div>
      <p class="eyebrow">Story Canvas</p>
      <h3>故事画布</h3>
      <small>{{ canvasBuildSummary }}</small>
    </div>
    <div class="story-canvas-actions">
      <button class="ghost muted" type="button" :disabled="novelProjectBusy || isInitialCanvasRebuildLocked" @click="$emit('rebuildCanvas')">{{ canvasBuildActionLabel }}</button>
      <button class="ghost muted" type="button" :disabled="novelProjectBusy" @click="$emit('saveCanvas')">保存画布</button>
      <button type="button" :disabled="novelProjectBusy || !hasActiveCanvasScenes" @click="$emit('applyToChapter')">应用到章节</button>
    </div>
  </div>
  <div class="story-canvas-tabs">
    <button type="button" :class="{ active: storyCanvasView === 'flow' }" @click="storyCanvasView = 'flow'">流程视图</button>
    <button type="button" :class="{ active: storyCanvasView === 'chapters' }" @click="storyCanvasView = 'chapters'">章节看板</button>
    <button type="button" :class="{ active: storyCanvasView === 'scenes' }" @click="storyCanvasView = 'scenes'">场景列表</button>
    <button type="button" :class="{ active: storyCanvasView === 'threads' }" @click="storyCanvasView = 'threads'">线索视图</button>
  </div>
</template>
