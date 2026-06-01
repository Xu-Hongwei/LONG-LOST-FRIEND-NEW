<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { StoryCanvasChapter, StoryCanvasEvent, StoryCanvasEventPool, StoryEventPoolEventWriteRequest } from "../../types";
import type { CanvasBuildStage } from "./constants";
import { canvasBuildSteps } from "./constants";

type EventUseMode = "strict" | "guide" | "flavor" | "free";

type EventDraft = {
  place: string;
  time_anchor: string;
  event: string;
  hook: string;
  motifs: string;
  use_mode: EventUseMode;
  source_reason: string;
};

function eventBindingLabel(item: StoryCanvasEvent) {
  const orders = item.bound_chapter_orders || [];
  if (!orders.length) return "";
  return `绑定第 ${orders.join("、")} 章`;
}

function eventScoreLabel(item: StoryCanvasEvent) {
  const score = item.selection_score || 0;
  return score > 0 ? `score ${score}` : "";
}

function eventReasonLabel(item: StoryCanvasEvent) {
  return (item.selection_reasons || [])[0] || item.source_reason || "";
}

function eventSourceLabel(item: StoryCanvasEvent) {
  const source = item.source || "setting_profile";
  const labels: Record<string, string> = {
    project: "项目",
    remote: "滚动新增",
    llm: "滚动新增",
    character: "角色素材",
    character_seed: "角色素材",
    character_seed_translated: "角色转译",
    setting_profile: "题材兜底",
    manual: "手动"
  };
  return labels[source] || source;
}

function draftFromEvent(item?: StoryCanvasEvent): EventDraft {
  return {
    place: item?.place || "",
    time_anchor: item?.time_anchor || "",
    event: item?.event || "",
    hook: item?.hook || "",
    motifs: (item?.motifs || []).join("\n"),
    use_mode: (["strict", "guide", "flavor", "free"].includes(String(item?.use_mode || ""))
      ? item?.use_mode
      : "guide") as EventUseMode,
    source_reason: item?.source_reason || ""
  };
}

function payloadFromDraft(draft: EventDraft): StoryEventPoolEventWriteRequest {
  return {
    place: draft.place.trim(),
    time_anchor: draft.time_anchor.trim(),
    event: draft.event.trim(),
    hook: draft.hook.trim(),
    motifs: draft.motifs
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean),
    use_mode: draft.use_mode,
    source_reason: draft.source_reason.trim(),
    tags: {}
  };
}

const editingEvent = ref<StoryCanvasEvent | null>(null);
const eventDraftMode = ref<"create" | "edit" | "">("");
const eventDraft = ref<EventDraft>(draftFromEvent());
const bindingEvent = ref<StoryCanvasEvent | null>(null);
const bindingUseMode = ref<EventUseMode>("guide");
const bindingSubmitted = ref(false);
const bindingStage = ref<"idle" | "contract" | "sync" | "refresh" | "done">("idle");
const bindingTimers: number[] = [];

const props = defineProps<{
  canvasBuildSummary: string;
  canvasFlowMetrics: {
    acts: number;
    chapters: number;
    scenes: number;
    threads: number;
    materials: number;
  };
  canvasSourceLabel: string;
  canvasBuildStage: CanvasBuildStage;
  canvasBuildProgressLabel: string;
  canvasBuildPercent: number;
  canvasBuildStepClass: (index: number) => Record<string, boolean>;
  eventPool?: StoryCanvasEventPool;
  activeCanvasChapter?: StoryCanvasChapter | null;
  novelStateSummary: string;
  novelStateLastHandoffText: string;
  novelStateOpenThreads: string[];
  novelProjectBusy: boolean;
}>();

const eventPoolSourceSummary = computed(() => {
  const active = props.eventPool?.active || [];
  if (!active.length) return "";
  const counts = active.reduce<Record<string, number>>((acc, item) => {
    const label = eventSourceLabel(item);
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const order = ["滚动新增", "项目", "手动", "角色素材", "角色转译", "题材兜底"];
  return order
    .filter((label) => counts[label])
    .map((label) => `${label} ${counts[label]}`)
    .join(" / ");
});

const emit = defineEmits<{
  addEvent: [payload: StoryEventPoolEventWriteRequest];
  editEvent: [event: StoryCanvasEvent, payload: StoryEventPoolEventWriteRequest];
  retireEvent: [event: StoryCanvasEvent];
  deleteEvent: [event: StoryCanvasEvent];
  bindEvent: [event: StoryCanvasEvent, useMode: EventUseMode];
}>();

const eventUseModeOptions: { value: EventUseMode; label: string; detail: string }[] = [
  { value: "strict", label: "strict", detail: "必须采用地点、时间、外部事件和钩子" },
  { value: "guide", label: "guide", detail: "作为主要方向，首次同步画布和场景卡" },
  { value: "flavor", label: "flavor", detail: "只借地点、意象、气氛或钩子" },
  { value: "free", label: "free", detail: "只作为灵感，不自动同步" }
];

function normalizeUseMode(value: unknown): EventUseMode {
  return (["strict", "guide", "flavor", "free"].includes(String(value || ""))
    ? String(value)
    : "guide") as EventUseMode;
}

function openEventCreator() {
  editingEvent.value = null;
  eventDraftMode.value = "create";
  eventDraft.value = draftFromEvent();
}

function openEventEditor(item: StoryCanvasEvent) {
  editingEvent.value = item;
  eventDraftMode.value = "edit";
  eventDraft.value = draftFromEvent(item);
}

function closeEventEditor() {
  editingEvent.value = null;
  eventDraftMode.value = "";
  eventDraft.value = draftFromEvent();
}

function openBindingPanel(item: StoryCanvasEvent) {
  bindingEvent.value = item;
  bindingUseMode.value = normalizeUseMode(item.use_mode);
}

function closeBindingPanel() {
  bindingTimers.splice(0).forEach((timer) => window.clearTimeout(timer));
  bindingEvent.value = null;
  bindingUseMode.value = "guide";
  bindingSubmitted.value = false;
  bindingStage.value = "idle";
}

function submitBinding() {
  if (!bindingEvent.value) return;
  bindingSubmitted.value = true;
  bindingStage.value = "contract";
  bindingTimers.splice(0).forEach((timer) => window.clearTimeout(timer));
  bindingTimers.push(window.setTimeout(() => {
    if (bindingSubmitted.value && bindingStage.value !== "done") bindingStage.value = "sync";
  }, 320));
  bindingTimers.push(window.setTimeout(() => {
    if (bindingSubmitted.value && bindingStage.value !== "done") bindingStage.value = "refresh";
  }, 760));
  emit("bindEvent", bindingEvent.value, bindingUseMode.value);
}

function bindingStepClass(step: "contract" | "sync" | "refresh" | "done") {
  const order = ["contract", "sync", "refresh", "done"];
  const current = order.indexOf(bindingStage.value);
  const target = order.indexOf(step);
  return {
    active: bindingStage.value === step,
    done: current > target || bindingStage.value === "done"
  };
}

watch(
  () => props.novelProjectBusy,
  (busy) => {
    if (!bindingSubmitted.value || busy) return;
    bindingStage.value = "done";
  }
);

function submitEventDraft() {
  const payload = payloadFromDraft(eventDraft.value);
  if (!payload.place && !payload.event && !payload.hook) return;
  if (eventDraftMode.value === "edit" && editingEvent.value) {
    emit("editEvent", editingEvent.value, payload);
  } else {
    emit("addEvent", payload);
  }
  closeEventEditor();
}
</script>

<template>
  <div class="canvas-flow-view">
    <div class="canvas-flow-summary">
      <div>
        <p class="eyebrow">Canvas Run</p>
        <strong>{{ canvasBuildSummary }}</strong>
      </div>
      <div class="canvas-flow-metrics">
        <span>{{ canvasFlowMetrics.materials }} 素材</span>
        <span>{{ canvasFlowMetrics.acts }} 阶段</span>
        <span>{{ canvasFlowMetrics.chapters }} 章</span>
        <span>{{ canvasFlowMetrics.scenes }} 场景</span>
        <span>{{ canvasFlowMetrics.threads }} 线索</span>
        <span>{{ canvasSourceLabel }}</span>
      </div>
    </div>
    <div
      v-if="canvasBuildStage !== 'idle'"
      class="canvas-build-progress"
      :class="{ complete: canvasBuildStage === 'done', failed: canvasBuildStage === 'failed' }"
    >
      <div>
        <span>{{ canvasBuildProgressLabel }}</span>
        <strong>{{ Math.round(canvasBuildPercent) }}%</strong>
      </div>
      <i aria-hidden="true">
        <b :style="{ width: `${canvasBuildPercent}%` }"></b>
      </i>
    </div>
    <ol class="canvas-flow-steps">
      <li
        v-for="(step, index) in canvasBuildSteps"
        :key="step.id"
        :class="canvasBuildStepClass(index)"
      >
        <i>{{ index + 1 }}</i>
        <div>
          <strong>{{ step.label }}</strong>
          <span>{{ step.detail }}</span>
        </div>
      </li>
    </ol>
    <div class="canvas-flow-note">
      <strong>自动滚动</strong>
      <span>每章生成后会整理交接单、更新 Novel State，并重规划后续两章；“重新生成画布”只适合开局大改。</span>
    </div>
    <section class="story-event-pool">
      <header>
        <div>
          <p class="eyebrow">Event Pool</p>
          <strong>项目事件池</strong>
        </div>
        <div class="story-event-pool-actions">
          <small v-if="eventPoolSourceSummary">{{ eventPoolSourceSummary }}</small>
          <span>{{ eventPool?.active.length || 0 }} / {{ eventPool?.target_active || 10 }} active</span>
          <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="openEventCreator">新增事件</button>
        </div>
      </header>
      <form v-if="eventDraftMode" class="story-event-editor" @submit.prevent="submitEventDraft">
        <div class="story-event-editor-head">
          <div>
            <p class="eyebrow">{{ eventDraftMode === "edit" ? "Edit Event" : "New Event" }}</p>
            <strong>{{ eventDraftMode === "edit" ? "编辑项目事件" : "新增项目事件" }}</strong>
          </div>
        </div>
        <div class="story-event-editor-grid">
          <label>
            <span>地点</span>
            <input v-model="eventDraft.place" placeholder="例如：湖边小路" />
          </label>
          <label>
            <span>时间锚点</span>
            <input v-model="eventDraft.time_anchor" placeholder="例如：周六 19:15，路灯刚熄灭不久" />
          </label>
          <label>
            <span>外部事件</span>
            <textarea v-model="eventDraft.event" rows="3" placeholder="这一章可采用的外部事件" />
          </label>
          <label>
            <span>钩子</span>
            <textarea v-model="eventDraft.hook" rows="3" placeholder="留下什么选择、余波或下一步理由" />
          </label>
          <label>
            <span>意象，每行一个</span>
            <textarea v-model="eventDraft.motifs" rows="3" placeholder="雨后路灯&#10;水面倒影" />
          </label>
          <label>
            <span>使用模式</span>
            <select v-model="eventDraft.use_mode">
              <option value="strict">strict · 必须采用核心</option>
              <option value="guide">guide · 作为主要方向</option>
              <option value="flavor">flavor · 只借气味和钩子</option>
              <option value="free">free · 自由发挥</option>
            </select>
          </label>
          <label class="story-event-source-field">
            <span>来源说明</span>
            <input v-model="eventDraft.source_reason" placeholder="例如：根据当前章节节奏手动添加" />
          </label>
        </div>
        <div class="story-event-editor-actions">
          <button type="button" class="ghost muted" @click="closeEventEditor">取消</button>
          <button type="submit" :disabled="novelProjectBusy || (!eventDraft.place && !eventDraft.event && !eventDraft.hook)">
            {{ eventDraftMode === "edit" ? "保存事件" : "新增事件" }}
          </button>
        </div>
      </form>
      <form v-if="bindingEvent" class="story-event-bind-panel" @submit.prevent="submitBinding">
        <div class="story-event-bind-head">
          <div>
            <p class="eyebrow">Bind Event</p>
            <strong>选择本章采用强度</strong>
          </div>
          <button type="button" class="ghost muted" :disabled="bindingSubmitted && bindingStage !== 'done'" @click="closeBindingPanel">关闭</button>
        </div>
        <div class="story-event-bind-summary">
          <span>{{ bindingEvent.time_anchor || "未设定时间" }}</span>
          <strong>{{ bindingEvent.place || "未设定地点" }}</strong>
          <p>{{ bindingEvent.event || "暂无事件描述" }}</p>
          <em>{{ bindingEvent.hook || "暂无钩子" }}</em>
        </div>
        <div class="story-event-mode-grid">
          <label
            v-for="option in eventUseModeOptions"
            :key="option.value"
            :class="{ active: bindingUseMode === option.value }"
          >
            <input v-model="bindingUseMode" type="radio" name="story-event-bind-mode" :value="option.value" :disabled="bindingSubmitted" />
            <strong>{{ option.label }}</strong>
            <span>{{ option.detail }}</span>
          </label>
        </div>
        <ol v-if="bindingSubmitted" class="story-event-bind-progress">
          <li :class="bindingStepClass('contract')">
            <i>1</i>
            <span>写入本章事件契约</span>
          </li>
          <li :class="bindingStepClass('sync')">
            <i>2</i>
            <span>按模式同步画布与场景卡</span>
          </li>
          <li :class="bindingStepClass('refresh')">
            <i>3</i>
            <span>刷新项目事件池和章节状态</span>
          </li>
          <li :class="bindingStepClass('done')">
            <i>4</i>
            <span>完成，返回结果见当前章节采用事件</span>
          </li>
        </ol>
        <div class="story-event-editor-actions">
          <button type="button" class="ghost muted" :disabled="bindingSubmitted && bindingStage !== 'done'" @click="closeBindingPanel">取消</button>
          <button type="submit" :disabled="novelProjectBusy || bindingSubmitted || !activeCanvasChapter">绑定本章</button>
        </div>
      </form>
      <div v-if="eventPool?.active.length" class="story-event-pool-grid">
        <article
          v-for="item in eventPool.active"
          :key="item.id"
          :class="['story-event-item', item.status]"
        >
          <div class="story-event-meta">
            <small>{{ eventSourceLabel(item) }}</small>
            <b>{{ eventBindingLabel(item) || eventScoreLabel(item) || item.status || "fresh" }} · {{ item.use_mode || "guide" }}</b>
          </div>
          <div class="story-event-content">
            <p v-if="eventReasonLabel(item)" class="story-event-reason">{{ eventReasonLabel(item) }}</p>
            <p v-if="item.time_anchor" class="story-event-time">{{ item.time_anchor }}</p>
            <div class="story-event-body">
              <span>地点</span>
              <strong>{{ item.place || "未设定地点" }}</strong>
            </div>
            <div class="story-event-body">
              <span>事件</span>
              <p>{{ item.event || "暂无事件描述" }}</p>
            </div>
            <div class="story-event-body">
              <span>钩子</span>
              <em>{{ item.hook || "暂无钩子" }}</em>
            </div>
          </div>
          <div class="story-event-controls">
            <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="openEventEditor(item)">编辑</button>
            <button type="button" class="ghost muted" :disabled="novelProjectBusy || !activeCanvasChapter" @click="openBindingPanel(item)">绑定本章</button>
            <button type="button" class="ghost muted" :disabled="novelProjectBusy" @click="$emit('retireEvent', item)">退休</button>
            <button type="button" class="ghost muted danger" :disabled="novelProjectBusy" @click="$emit('deleteEvent', item)">删除</button>
          </div>
        </article>
      </div>
      <p v-else class="story-event-empty">当前画布还没有事件池。新建或重建画布后会自动生成 10 条活动事件。</p>
    </section>
    <div class="novel-state-panel">
      <article>
        <p class="eyebrow">Novel State</p>
        <strong>截至上一章摘要</strong>
        <span>{{ novelStateSummary }}</span>
      </article>
      <article>
        <p class="eyebrow">Last Handoff</p>
        <strong>上一章交接单</strong>
        <span>{{ novelStateLastHandoffText }}</span>
      </article>
      <article>
        <p class="eyebrow">Open Threads</p>
        <strong>未解决线索</strong>
        <span v-if="!novelStateOpenThreads.length">暂无未解决线索。</span>
        <span v-else>{{ novelStateOpenThreads.join("；") }}</span>
      </article>
    </div>
  </div>
</template>
