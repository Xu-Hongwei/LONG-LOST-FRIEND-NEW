<script setup lang="ts">
import type { CanvasActionKey } from "./constants";
import type { ChapterSceneCardDraft } from "./canvas";
import type { NovelChapter, NovelChapterStatus, StoryCanvasChapter, StoryCanvasEvent } from "../../types";
import { formatNovelChapterTitle } from "./chapterTitle";

type ChapterDraft = {
  title: string;
  goal: string;
  summary: string;
  body: string;
  status: NovelChapterStatus;
  scene_card: ChapterSceneCardDraft;
};

type ChapterLengthGuide = {
  tone: string;
  label: string;
  detail: string;
};

defineProps<{
  activeNovelChapter: NovelChapter;
  activeCanvasChapter: StoryCanvasChapter | null;
  activeCanvasEvent: StoryCanvasEvent | null;
  activeCanvasActionChain: { key: CanvasActionKey; label: string; text: string }[];
  sceneCardFields: { key: string; label: string; rows: number }[];
  novelChapterStatusOptions: { value: NovelChapterStatus; label: string }[];
  novelProjectBusy: boolean;
  isOptimizingInstruction: boolean;
  chapterLengthGuide: ChapterLengthGuide;
  chapterLengthRatio: number;
  activeChapterWordCount: number;
  instructionOptimizationNote: string;
  novelEditorFont: "serif" | "sans";
  activeChapterStatusLabel: string;
  editorUpdatedLabel: string;
}>();

const chapterDraft = defineModel<ChapterDraft>("chapterDraft", { required: true });
const chapterInstruction = defineModel<string>("chapterInstruction", { required: true });
const projectChapterTargetLength = defineModel<number>("projectChapterTargetLength", { required: true });

defineEmits<{
  checkContinuity: [];
  saveChapter: [];
  deleteChapter: [];
  generateChapter: [];
  optimizeInstruction: [];
  clearEventBinding: [];
  rebindEvent: [];
}>();

function eventSyncLabel(chapter: StoryCanvasChapter | null) {
  const sync = chapter?.event_sync;
  if (!sync || typeof sync !== "object") return "未同步";
  const data = sync as Record<string, unknown>;
  const fields = data.fields;
  const sceneFields = data.scene_fields;
  const fieldCount = fields && typeof fields === "object" ? Object.keys(fields).length : 0;
  const sceneCount = sceneFields && typeof sceneFields === "object" ? Object.keys(sceneFields).length : 0;
  return `${String(data.mode || "guide")} · 画布 ${fieldCount} 项 · 场景卡 ${sceneCount} 项`;
}

const canvasSyncLabels: Record<string, string> = {
  external_event: "外部事件",
  trigger_event: "触发事件",
  ending_hook: "结尾钩子",
  goal: "章节目标",
  obstacle_escalation: "阻碍升级",
  scene_consequence: "场景后果"
};

const sceneSyncLabels: Record<string, string> = {
  current_scene: "当前场景",
  surface_event: "表层事件",
  ending_beat: "结尾落点"
};

function syncFieldEntries(chapter: StoryCanvasChapter | null, key: "fields" | "scene_fields") {
  const sync = chapter?.event_sync;
  if (!sync || typeof sync !== "object") return [];
  const data = sync as Record<string, unknown>;
  const fields = data[key];
  if (!fields || typeof fields !== "object") return [];
  const labels = key === "fields" ? canvasSyncLabels : sceneSyncLabels;
  return Object.entries(fields as Record<string, unknown>)
    .map(([field, value]) => ({
      field,
      label: labels[field] || field,
      value: String(value || "").trim()
    }))
    .filter((item) => item.value);
}

function eventContractReturnRows(chapter: StoryCanvasChapter | null) {
  const contract = chapter?.event_contract;
  if (!contract || typeof contract !== "object") return [];
  const data = contract as Record<string, unknown>;
  return [
    ["event_id", data.event_id],
    ["source", data.source],
    ["status", data.status],
    ["updated_at", data.updated_at]
  ]
    .map(([label, value]) => ({ label: String(label), value: String(value || "").trim() }))
    .filter((item) => item.value);
}

function eventSyncReturnRows(chapter: StoryCanvasChapter | null) {
  const sync = chapter?.event_sync;
  if (!sync || typeof sync !== "object") return [];
  const data = sync as Record<string, unknown>;
  return [
    ["sync_source", data.source],
    ["remote_status", data.remote_status],
    ["remote_reason", data.remote_reason],
    ["source_note", data.source_note]
  ]
    .map(([label, value]) => ({ label: String(label), value: String(value || "").trim() }))
    .filter((item) => item.value);
}

function chapterProgressionText(chapter: StoryCanvasChapter | null) {
  if (!chapter) return "";
  const contract = chapter.event_contract && typeof chapter.event_contract === "object"
    ? chapter.event_contract as Record<string, unknown>
    : {};
  const promiseTargets = Array.isArray(contract.promise_markers)
    ? contract.promise_markers.map(String).filter(Boolean)
    : (chapter.promise_targets || []);
  return [
    String(contract.progression_role || chapter.progression_role || "").trim(),
    String(contract.chapter_drive || chapter.chapter_drive || "").trim(),
    promiseTargets.slice(0, 4).join(" / ")
  ].filter(Boolean).join(" · ");
}

function contractList(chapter: StoryCanvasChapter | null, key: "continuity_hits" | "continuity_risks") {
  const contract = chapter?.event_contract;
  if (!contract || typeof contract !== "object") return [];
  const value = (contract as Record<string, unknown>)[key];
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}
</script>

<template>
  <section class="chapter-editor">
    <div class="chapter-editor-head">
      <div>
        <p class="eyebrow">Chapter {{ activeNovelChapter.chapter_order }}</p>
        <h3>{{ formatNovelChapterTitle(activeNovelChapter.chapter_order, chapterDraft.title) }}</h3>
      </div>
      <div class="chapter-actions">
        <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="$emit('checkContinuity')">检查</button>
        <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="$emit('saveChapter')">保存</button>
        <button type="button" class="ghost muted danger" :disabled="novelProjectBusy" @click="$emit('deleteChapter')">删除</button>
        <button type="button" :disabled="novelProjectBusy" @click="$emit('generateChapter')">生成/续写</button>
      </div>
    </div>
    <div class="chapter-grid">
      <label>
        <span>章节名</span>
        <input v-model="chapterDraft.title" />
      </label>
      <label>
        <span>状态</span>
        <select v-model="chapterDraft.status">
          <option v-for="option in novelChapterStatusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>
    <label>
      <span>本章剧情概述</span>
      <textarea v-model="chapterDraft.goal" rows="3" />
    </label>
    <section class="chapter-event-binding">
      <div>
        <p class="eyebrow">Event Binding</p>
        <h4>当前章节采用事件</h4>
      </div>
      <div v-if="activeCanvasEvent" class="chapter-event-binding-grid">
        <span>地点</span>
        <strong>{{ activeCanvasEvent.place || "未设定地点" }}</strong>
        <span>时间</span>
        <strong>{{ activeCanvasEvent.time_anchor || "未设定时间锚点" }}</strong>
        <span>事件</span>
        <p>{{ activeCanvasEvent.event || "暂无事件描述" }}</p>
        <span>钩子</span>
        <p>{{ activeCanvasEvent.hook || "暂无钩子" }}</p>
        <span>模式</span>
        <strong>{{ activeCanvasEvent.use_mode || "guide" }}</strong>
        <span>本章推进</span>
        <p>{{ chapterProgressionText(activeCanvasChapter) || "暂未写入推进方式" }}</p>
        <span>Score</span>
        <strong>{{ activeCanvasEvent.selection_score || activeCanvasChapter?.event_pool_score || 0 }}</strong>
        <span>Reasons</span>
        <p>{{ (activeCanvasEvent.selection_reasons || activeCanvasChapter?.event_pool_reasons || []).join("；") || "暂无原因" }}</p>
        <span>连续性命中</span>
        <p>{{ contractList(activeCanvasChapter, "continuity_hits").join("；") || "暂无命中" }}</p>
        <span>连续性风险</span>
        <p>{{ contractList(activeCanvasChapter, "continuity_risks").join("；") || "暂无风险" }}</p>
        <span>同步</span>
        <p>{{ eventSyncLabel(activeCanvasChapter) }}</p>
      </div>
      <div v-if="activeCanvasEvent && activeCanvasChapter?.event_sync" class="chapter-event-sync-detail">
        <div>
          <p class="eyebrow">Returned Sync</p>
          <strong>后端返回结果</strong>
        </div>
        <div class="chapter-event-sync-meta">
          <span v-for="row in eventContractReturnRows(activeCanvasChapter)" :key="row.label">
            {{ row.label }}: {{ row.value }}
          </span>
          <span v-for="row in eventSyncReturnRows(activeCanvasChapter)" :key="row.label">
            {{ row.label }}: {{ row.value }}
          </span>
        </div>
        <article>
          <span>画布生成/同步</span>
          <p v-if="syncFieldEntries(activeCanvasChapter, 'fields').length">
            <b v-for="item in syncFieldEntries(activeCanvasChapter, 'fields')" :key="item.field">
              {{ item.label }}：{{ item.value }}
            </b>
          </p>
          <em v-else>本次没有写入画布字段，可能是 free/flavor 模式，或已有手写字段被保护。</em>
        </article>
        <article>
          <span>场景卡生成/同步</span>
          <p v-if="syncFieldEntries(activeCanvasChapter, 'scene_fields').length">
            <b v-for="item in syncFieldEntries(activeCanvasChapter, 'scene_fields')" :key="item.field">
              {{ item.label }}：{{ item.value }}
            </b>
          </p>
          <em v-else>本次没有写入场景卡字段，可能是 free 模式，或场景卡字段已被用户改写。</em>
        </article>
      </div>
      <p v-if="!activeCanvasEvent" class="chapter-event-empty">未绑定项目事件</p>
      <div class="chapter-event-actions">
        <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="$emit('rebindEvent')">重新绑定</button>
        <button type="button" class="ghost muted danger" :disabled="novelProjectBusy || !activeCanvasEvent" @click="$emit('clearEventBinding')">取消绑定</button>
      </div>
    </section>
    <section class="scene-card-editor">
      <div class="scene-card-head">
        <div>
          <p class="eyebrow">Scene Card</p>
          <h4>场景卡</h4>
        </div>
        <small>生成前先约束场景、人物欲望、张力和结尾落点。</small>
      </div>
      <div v-if="activeCanvasChapter" class="canvas-link-editor">
        <div>
          <p class="eyebrow">Canvas Link</p>
          <strong>对应画布动作链</strong>
          <small>剧情推进以这里为准，保存后会反向写回故事画布。</small>
        </div>
        <div class="canvas-action-grid">
          <label v-for="item in activeCanvasActionChain" :key="item.label">
            <span>{{ item.label }}</span>
            <textarea v-model="activeCanvasChapter[item.key]" rows="3" />
          </label>
        </div>
      </div>
      <div class="scene-card-grid">
        <label v-for="field in sceneCardFields" :key="field.key">
          <span>{{ field.label }}</span>
          <textarea v-model="chapterDraft.scene_card[field.key]" :rows="field.rows" />
        </label>
      </div>
    </section>
    <label>
      <span>生成指令</span>
      <textarea v-model="chapterInstruction" rows="10" />
    </label>
    <label class="range-field">
      <span>项目章节目标长度 {{ projectChapterTargetLength }} 字</span>
      <input v-model.number="projectChapterTargetLength" type="range" min="400" max="6000" step="200" />
    </label>
    <div class="chapter-length-panel" :class="`tone-${chapterLengthGuide.tone}`">
      <div>
        <strong>{{ activeChapterWordCount }} / {{ projectChapterTargetLength }} 字</strong>
        <span>{{ chapterLengthGuide.label }} · {{ chapterLengthRatio }}%</span>
      </div>
      <p>{{ chapterLengthGuide.detail }}</p>
      <button
        class="ghost muted"
        type="button"
        :disabled="novelProjectBusy || isOptimizingInstruction"
        @click="$emit('optimizeInstruction')"
      >
        {{ isOptimizingInstruction ? "远程优化中" : "优化生成指令" }}
      </button>
    </div>
    <p v-if="instructionOptimizationNote" class="instruction-optimization-note">{{ instructionOptimizationNote }}</p>
    <div class="writing-surface" :class="`font-${novelEditorFont}`">
      <label>
        <span>章节摘要</span>
        <textarea v-model="chapterDraft.summary" rows="3" />
      </label>
      <label class="chapter-body-label">
        <span>正文</span>
        <textarea
          v-model="chapterDraft.body"
          class="chapter-body-input"
          rows="18"
          placeholder="从这里开始写正文。AI 生成、续写和手动编辑都会落在这张写作纸面上。"
        />
      </label>
      <div class="editor-status-bar">
        <span>{{ activeChapterWordCount }} 字</span>
        <span>{{ activeChapterStatusLabel }}</span>
        <span>{{ editorUpdatedLabel }}</span>
      </div>
    </div>
  </section>
</template>
