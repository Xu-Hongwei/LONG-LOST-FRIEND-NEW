<script setup lang="ts">
import type { CanvasActionKey } from "./constants";
import type { ChapterSceneCardDraft } from "./canvas";
import type { NovelChapter, NovelChapterStatus, StoryCanvasChapter } from "../../types";
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
}>();
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
