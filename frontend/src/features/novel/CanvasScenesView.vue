<script setup lang="ts">
import type { StoryCanvasScene } from "../../types";

defineProps<{
  scenes: StoryCanvasScene[];
  canvasChapterTitle: (chapterId: string) => string;
  canvasFieldText: (value: unknown) => string;
}>();
</script>

<template>
  <div class="canvas-scene-list">
    <article v-for="scene in scenes" :key="scene.id" class="canvas-card">
      <div class="canvas-card-title">
        <strong>{{ canvasChapterTitle(scene.chapter_id) }} · 场景 {{ scene.scene_order }}</strong>
        <span>{{ scene.linked_material_ids.length }} 条素材</span>
      </div>
      <div class="canvas-field-grid">
        <article>
          <span>当前场景</span>
          <p>{{ canvasFieldText(scene.current_scene) }}</p>
        </article>
        <article>
          <span>表层事件</span>
          <p>{{ canvasFieldText(scene.surface_event) }}</p>
        </article>
        <article>
          <span>人物欲望</span>
          <p>{{ canvasFieldText(scene.character_desire) }}</p>
        </article>
        <article>
          <span>阻碍 / 张力</span>
          <p>{{ canvasFieldText(scene.tension) }}</p>
        </article>
        <article>
          <span>禁止推进</span>
          <p>{{ canvasFieldText(scene.forbidden_progress) }}</p>
        </article>
        <article>
          <span>结尾落点</span>
          <p>{{ canvasFieldText(scene.ending_beat) }}</p>
        </article>
      </div>
    </article>
  </div>
</template>
