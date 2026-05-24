<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{
  novelProjectBusy: boolean;
  projectDraftGenerating: boolean;
  projectDraftDiagnostics: Record<string, unknown>;
  storyBusy: boolean;
  sessionId: string;
}>();

defineEmits<{
  createProject: [];
  generateProjectDraft: [prompt: string];
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

const generationPrompt = ref("");

const sourceLabel = computed(() => {
  const source = props.projectDraftDiagnostics?.source;
  if (source === "remote") return "remote JSON 已填入";
  if (source === "fallback") return "fallback 草稿已填入";
  return "";
});

function isOutlineListLine(line: string) {
  return /^(\d+[\).、]|[-*•]|第[一二三四五六七八九十\d]+[章节幕阶段])\s*/.test(line.trim());
}

function normalizeDraftOutline(text: string) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length <= 1) return text.trim();
  const listLikeCount = lines.filter(isOutlineListLine).length;
  if (listLikeCount >= 2) return lines.join("\n");
  return lines.join("").replace(/\s{2,}/g, " ").trim();
}
</script>

<template>
  <div class="project-empty">
    <div class="project-empty-copy">
      <div>
        <p class="eyebrow">Project Mode</p>
        <h3>创建长篇项目</h3>
        <p>用一句话定方向，AI 会生成可编辑项目草稿；确认字段后再写入长篇项目。</p>
      </div>
      <div class="project-empty-actions">
        <button type="button" :disabled="novelProjectBusy || !sessionId" @click="$emit('createProject')">创建项目</button>
        <button class="ghost muted" type="button" :disabled="storyBusy || !sessionId" @click="$emit('refreshStoryTags')">刷新剧情标签</button>
      </div>
    </div>

    <section class="project-draft-generator">
      <label class="project-draft-input">
        <span>项目方向</span>
      <textarea
        v-model="generationPrompt"
        rows="3"
        :disabled="novelProjectBusy"
        placeholder="例：修仙武侠，少年剑修和冷淡医修被迫同行，从互相试探到并肩破局。"
      ></textarea>
      </label>
      <div class="project-draft-command">
        <button
          type="button"
          class="wide generator-button"
          :class="{ loading: projectDraftGenerating }"
          :disabled="novelProjectBusy || !sessionId || !generationPrompt.trim()"
          @click="$emit('generateProjectDraft', generationPrompt)"
        >
          <span v-if="projectDraftGenerating" class="loading-dot"></span>
          {{ projectDraftGenerating ? "生成中..." : "生成草稿" }}
        </button>
        <small v-if="projectDraftGenerating" class="generation-status compact">
          <span></span>
          正在生成结构化 JSON
        </small>
        <small v-else-if="sourceLabel" class="project-draft-source">{{ sourceLabel }}</small>
      </div>
      <p class="project-draft-hint">AI 会按这句话优先生成标题、类型、基调、世界观、关系设定和大纲。</p>
    </section>

    <div class="project-seed-grid">
      <label>
        <span>作品标题</span>
        <input v-model="projectDraft.title" :disabled="novelProjectBusy" placeholder="例如：云外听剑" />
      </label>
      <label>
        <span>类型</span>
        <input v-model="projectDraft.genre" :disabled="novelProjectBusy" placeholder="修仙武侠长篇 / 悬疑校园 / 都市奇幻" />
      </label>
      <label>
        <span>基调</span>
        <input v-model="projectDraft.tone" :disabled="novelProjectBusy" placeholder="克制、锋利、慢热、留白感强" />
      </label>
      <label>
        <span>主角</span>
        <input v-model="projectDraft.protagonist" :disabled="novelProjectBusy" placeholder="默认使用当前角色" />
      </label>
    </div>

    <div class="project-seed-detail-grid">
      <label>
        <span>世界观</span>
        <textarea v-model="projectDraft.worldview" :disabled="novelProjectBusy" rows="4" placeholder="世界规则、核心地点、力量体系、日常限制。"></textarea>
      </label>
      <label>
        <span>关系设定</span>
        <textarea v-model="projectDraft.relationship_setup" :disabled="novelProjectBusy" rows="4" placeholder="关系起点、冲突来源、推进边界和阶段性变化。"></textarea>
      </label>
      <label class="span-full project-outline-field">
        <span>章节大纲</span>
        <textarea
          v-model="projectDraft.outline"
          :disabled="novelProjectBusy"
          rows="6"
          placeholder="5 到 8 条章节阶段：开端、递进、转折、回收和下一阶段伏笔。"
          @blur="projectDraft.outline = normalizeDraftOutline(projectDraft.outline)"
        ></textarea>
      </label>
    </div>
  </div>
</template>
