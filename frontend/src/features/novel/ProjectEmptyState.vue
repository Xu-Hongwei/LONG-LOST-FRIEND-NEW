<script setup lang="ts">
defineProps<{
  novelProjectBusy: boolean;
  storyBusy: boolean;
  sessionId: string;
}>();

defineEmits<{
  createProject: [];
  refreshStoryTags: [];
}>();

const projectDraft = defineModel<{
  title: string;
  genre: string;
  tone: string;
  protagonist: string;
  worldview: string;
  relationship_setup: string;
  outline: string;
}>("projectDraft", { required: true });
</script>

<template>
  <div class="project-empty">
    <div class="project-empty-copy">
      <div>
        <p class="eyebrow">Project Mode</p>
        <h3>从长篇项目开始</h3>
        <p>先给作品一个方向，项目创建后再展开世界观、关系设定和章节大纲。</p>
      </div>
      <div class="project-empty-actions">
        <button type="button" :disabled="novelProjectBusy || !sessionId" @click="$emit('createProject')">新建项目</button>
        <button class="ghost muted" type="button" :disabled="storyBusy || !sessionId" @click="$emit('refreshStoryTags')">刷新剧情标签</button>
      </div>
    </div>
    <div class="project-seed-grid">
      <label>
        <span>作品标题</span>
        <input v-model="projectDraft.title" placeholder="新小说项目" />
      </label>
      <label>
        <span>类型</span>
        <input v-model="projectDraft.genre" />
      </label>
      <label>
        <span>基调</span>
        <input v-model="projectDraft.tone" />
      </label>
    </div>
  </div>
</template>
