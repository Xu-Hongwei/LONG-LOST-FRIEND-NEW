<script setup lang="ts">
import type { NovelChapterStatus, NovelFidelity, NovelForm, NovelPerspective, NovelProject } from "../../types";
import { formatNovelChapterTitle } from "./chapterTitle";

type NovelStudioMode = "quick" | "project";

defineProps<{
  novelStudioMode: NovelStudioMode;
  busy: boolean;
  sessionId: string;
  messageCount: number;
  novelProjectBusy: boolean;
  novelProjects: NovelProject[];
  activeNovelProject: NovelProject | null;
  activeNovelProjectId: string;
  activeNovelChapterId: string;
  novelChapterStatusLabel: (status?: NovelChapterStatus | string) => string;
}>();

defineEmits<{
  generateQuick: [];
  startProjectDraft: [];
  selectProject: [projectId: string];
  deleteProject: [projectId: string];
  addChapter: [];
  selectChapter: [chapterId: string];
}>();

const novelForm = defineModel<NovelForm>("novelForm", { required: true });
const novelPerspective = defineModel<NovelPerspective>("novelPerspective", { required: true });
const novelFidelity = defineModel<NovelFidelity>("novelFidelity", { required: true });
const novelAtmosphere = defineModel<string>("novelAtmosphere", { required: true });
</script>

<template>
  <aside class="novel-rail">
    <section v-if="novelStudioMode === 'quick'" class="quick-novel-block">
      <div class="story-pane-head">
        <div>
          <p class="eyebrow">Quick Draft</p>
          <h3>短篇生成</h3>
        </div>
        <button class="ghost muted" type="button" :disabled="busy || !sessionId || messageCount < 2" @click="$emit('generateQuick')">生成</button>
      </div>
      <label>
        <span>形式</span>
        <select v-model="novelForm">
          <option value="daily_short">日常短篇</option>
          <option value="campus_romance">校园恋爱短篇</option>
          <option value="vignette">片段随笔</option>
          <option value="chapter_one">第一章</option>
          <option value="side_story">番外</option>
        </select>
      </label>
      <label>
        <span>视角</span>
        <select v-model="novelPerspective">
          <option value="third_person">第三人称</option>
          <option value="user_view">用户视角</option>
          <option value="character_view">角色视角</option>
          <option value="dual_view">双视角</option>
        </select>
      </label>
      <label>
        <span>改编强度</span>
        <select v-model="novelFidelity">
          <option value="faithful">忠实记录</option>
          <option value="polished">轻度润色</option>
          <option value="literary">文学化扩写</option>
        </select>
      </label>
      <label>
        <span>氛围</span>
        <input v-model="novelAtmosphere" maxlength="80" />
      </label>
    </section>

    <section v-if="novelStudioMode === 'project'" class="project-list-block">
      <div class="story-pane-head">
        <div>
          <p class="eyebrow">Projects</p>
          <h3>长篇项目</h3>
        </div>
        <button class="ghost muted" type="button" :disabled="novelProjectBusy || !sessionId" @click="$emit('startProjectDraft')">新建</button>
      </div>
      <div class="project-list">
        <article
          v-for="project in novelProjects"
          :key="project.id"
          class="project-list-item"
          :class="{ active: project.id === activeNovelProjectId }"
        >
          <button type="button" class="project-select" @click="$emit('selectProject', project.id)">
            <strong>{{ project.title }}</strong>
            <span>{{ project.genre }} · {{ project.chapters.length }} 章</span>
          </button>
          <button
            type="button"
            class="project-delete ghost danger"
            :disabled="novelProjectBusy"
            title="删除长篇项目"
            @click="$emit('deleteProject', project.id)"
          >
            删除
          </button>
        </article>
        <p v-if="!novelProjects.length" class="empty">还没有长篇项目。会从当前会话、记忆和剧情标签生成初始 Story Bible。</p>
      </div>
    </section>

    <section v-if="novelStudioMode === 'project'" class="project-list-block">
      <div class="story-pane-head">
        <div>
          <p class="eyebrow">Chapters</p>
          <h3>章节</h3>
        </div>
        <button class="ghost muted" type="button" :disabled="novelProjectBusy || !activeNovelProject" @click="$emit('addChapter')">新增</button>
      </div>
      <div class="chapter-list">
        <button
          v-for="chapter in activeNovelProject?.chapters || []"
          :key="chapter.id"
          type="button"
          :class="{ active: chapter.id === activeNovelChapterId }"
          @click="$emit('selectChapter', chapter.id)"
        >
          <b>{{ chapter.chapter_order }}</b>
          <span>{{ formatNovelChapterTitle(chapter.chapter_order, chapter.title) }}</span>
          <small>{{ novelChapterStatusLabel(chapter.status) }}</small>
        </button>
      </div>
    </section>
  </aside>
</template>
