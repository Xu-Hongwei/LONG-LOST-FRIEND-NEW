<script setup lang="ts">
import { novelVersionSourceLabels, storyKindLabels, storyStatusLabels } from "./constants";
import type { NovelContinuityReport, NovelMaterial, NovelVersion, StoryPane } from "../../types";

type NovelVersionDisplay = NovelVersion & {
  duplicateCount: number;
  restoreCount: number;
  sourceKeys: string[];
};

defineProps<{
  storyPane: StoryPane | null;
  storyBusy: boolean;
  sessionId: string;
  storyAutoRefreshUserInterval: number;
  hasActiveNovelProject: boolean;
  storyBibleEntries: [string, string[]][];
  projectMaterialGroups: [string, NovelMaterial[]][];
  continuityReport: NovelContinuityReport | null;
  displayedChapterVersions: NovelVersionDisplay[];
  novelProjectBusy: boolean;
  messageCount: number;
  error: string;
}>();

defineEmits<{
  refreshStoryTags: [];
  downloadProject: [];
  restoreVersion: [versionId: string];
  deleteVersion: [versionId: string];
}>();

function novelVersionSourceLabel(version: NovelVersion | NovelVersionDisplay) {
  const keys = "sourceKeys" in version && version.sourceKeys.length
    ? version.sourceKeys
    : [version.source || version.version_type || ""].filter(Boolean);
  const preferred = keys.find((key) => key !== "restore") || keys[0] || "";
  return novelVersionSourceLabels[preferred] || preferred || "历史版本";
}

function novelVersionFoldLabel(version: NovelVersionDisplay) {
  if (version.duplicateCount <= 1) return "";
  const restorePart = version.restoreCount ? `，含 ${version.restoreCount} 次恢复` : "";
  return `折叠 ${version.duplicateCount} 条${restorePart}`;
}
function storyRefreshLabel(storyPane: StoryPane | null) {
  const diagnostics = storyPane?.diagnostics;
  if (!diagnostics) return "";
  if (diagnostics.error) return `刷新失败：${String(diagnostics.error)}`;
  if (!("generated" in diagnostics) && !("stored" in diagnostics)) return "";
  const generated = Number(diagnostics.generated || 0);
  const stored = Number(diagnostics.stored || 0);
  const remoteStatus = String(diagnostics.remote_status || "");
  const source = String(diagnostics.source || "");
  const remoteDetail = diagnostics.remote_error
    ? `远程失败 ${String(diagnostics.remote_error)}`
    : remoteStatus === "empty"
      ? "远程无候选"
      : remoteStatus === "skipped"
        ? "远程未启用"
        : source === "remote"
          ? "远程生成"
          : source === "fallback"
            ? "兜底生成"
            : "";
  return `上次刷新：候选 ${generated}，写入 ${stored}${remoteDetail ? ` · ${remoteDetail}` : ""}`;
}
</script>

<template>
  <aside class="story-bible-panel">
    <section class="story-pane-card">
      <div class="story-pane-head">
        <div>
          <p class="eyebrow">Story Pane</p>
          <h3>剧情标签 {{ storyPane?.items.length || 0 }}</h3>
          <small>每 {{ storyAutoRefreshUserInterval }} 条用户消息后台更新一次</small>
          <small v-if="storyRefreshLabel(storyPane)">{{ storyRefreshLabel(storyPane) }}</small>
        </div>
        <button
          class="ghost muted"
          type="button"
          :disabled="storyBusy || !sessionId"
          @click="$emit('refreshStoryTags')"
        >
          {{ storyBusy ? "更新中" : "刷新" }}
        </button>
      </div>
      <div v-if="storyPane?.items.length" class="story-tag-list">
        <article v-for="item in storyPane.items" :key="item.id" class="story-tag">
          <div>
            <span>{{ storyKindLabels[item.kind] || item.kind }}</span>
            <small>{{ storyStatusLabels[item.status] || item.status }} · {{ item.evidence_level }}</small>
          </div>
          <strong>{{ item.label }}</strong>
          <p>{{ item.content }}</p>
        </article>
      </div>
      <p v-else class="empty">还没有剧情标签。可以先刷新一次，项目创建会把它们转成 Story Bible。</p>
    </section>

    <section class="story-pane-card">
      <div class="story-pane-head">
        <div>
          <p class="eyebrow">Story Bible</p>
          <h3>项目规则</h3>
        </div>
        <button
          class="ghost muted"
          type="button"
          :disabled="!hasActiveNovelProject"
          @click="$emit('downloadProject')"
        >
          导出
        </button>
      </div>
      <div v-if="storyBibleEntries.length" class="bible-list">
        <article v-for="[key, items] in storyBibleEntries" :key="key">
          <strong>{{ key }}</strong>
          <p v-for="item in items.slice(0, 5)" :key="item">{{ item }}</p>
        </article>
      </div>
      <p v-else class="empty">创建项目后会出现事实、伏笔、关系、边界和灵感。</p>
    </section>

    <section class="story-pane-card">
      <p class="eyebrow">Materials</p>
      <div v-if="projectMaterialGroups.length" class="material-list">
        <article v-for="[category, materials] in projectMaterialGroups" :key="category">
          <strong>{{ category }} · {{ materials.length }}</strong>
          <p v-for="material in materials.slice(0, 4)" :key="material.id">{{ material.label }}：{{ material.content }}</p>
        </article>
      </div>
      <p v-else class="empty">素材库为空。</p>
    </section>

    <section class="story-pane-card">
      <p class="eyebrow">Continuity</p>
      <div v-if="continuityReport" class="continuity-list">
        <article v-for="issue in continuityReport.issues" :key="`${issue.severity}-${issue.label}`" :class="issue.severity">
          <strong>{{ issue.label }}</strong>
          <p>{{ issue.detail }}</p>
        </article>
      </div>
      <p v-else class="empty">点击“检查”后会显示连续性、边界和内部措辞风险。</p>
    </section>

    <section class="story-pane-card">
      <p class="eyebrow">Versions</p>
      <div v-if="displayedChapterVersions.length" class="version-list">
        <article v-for="version in displayedChapterVersions.slice(0, 8)" :key="version.id">
          <strong>{{ version.title }}</strong>
          <small>
            {{ novelVersionSourceLabel(version) }} · {{ version.created_at }}
            <span v-if="novelVersionFoldLabel(version)" class="version-fold">{{ novelVersionFoldLabel(version) }}</span>
          </small>
          <div class="version-actions">
            <button
              class="ghost muted"
              type="button"
              :disabled="novelProjectBusy"
              @click="$emit('restoreVersion', version.id)"
            >
              恢复
            </button>
            <button
              class="ghost muted danger"
              type="button"
              :disabled="novelProjectBusy"
              @click="$emit('deleteVersion', version.id)"
            >
              删除
            </button>
          </div>
        </article>
      </div>
      <p v-else class="empty">保存或生成正文后会保留版本。</p>
    </section>

    <p v-if="messageCount < 2" class="empty">当前会话消息太少，先聊几轮再生成。</p>
    <p v-if="error" class="error">{{ error }}</p>
  </aside>
</template>
