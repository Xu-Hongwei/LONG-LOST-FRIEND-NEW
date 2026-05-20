<script setup lang="ts">
defineProps<{
  novelProjectBusy: boolean;
  hasActiveProject: boolean;
}>();

defineEmits<{
  saveProject: [];
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
  <details class="project-settings-drawer">
    <summary>
      <span>项目设定</span>
      <small>{{ projectDraft.genre }} · {{ projectDraft.tone }}</small>
    </summary>
    <section class="project-fields">
      <div class="project-title-row">
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
        <button type="button" :disabled="novelProjectBusy || !hasActiveProject" @click="$emit('saveProject')">保存设定</button>
      </div>
      <label>
        <span>世界观</span>
        <textarea v-model="projectDraft.worldview" rows="3" placeholder="项目创建后会自动从素材生成" />
      </label>
      <label>
        <span>关系设定</span>
        <textarea v-model="projectDraft.relationship_setup" rows="3" />
      </label>
      <label>
        <span>章节大纲</span>
        <textarea v-model="projectDraft.outline" rows="4" />
      </label>
    </section>
  </details>
</template>
