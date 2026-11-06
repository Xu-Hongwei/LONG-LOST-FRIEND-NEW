<script setup lang="ts">
import { ref } from "vue";
import type { CharacterBond, CharacterCard, ChatMessage } from "../../types";

defineProps<{
  activeCharacter: CharacterCard | null;
  characterBond: CharacterBond | null;
  bondPercent: number;
  busy: boolean;
  messages: ChatMessage[];
  error: string;
  canSend: boolean;
  postprocessNotice: string;
}>();

defineEmits<{
  submit: [];
  export: [];
  reload: [];
}>();

const draft = defineModel<string>("draft", { default: "" });
const messageListRef = ref<HTMLElement | null>(null);

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
  }
}

defineExpose({ scrollToBottom });
</script>

<template>
  <section class="chat-panel">
    <header class="chat-header" v-if="activeCharacter">
      <div>
        <p class="eyebrow">{{ activeCharacter.archetype }}</p>
        <h2>{{ activeCharacter.name }}</h2>
        <span>{{ activeCharacter.tagline }}</span>
        <div v-if="characterBond" class="header-growth">
          <small>{{ characterBond.familiarity_stage }}</small>
          <small>Resonance {{ bondPercent }}%</small>
        </div>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost muted" :disabled="busy" @click="$emit('reload')">重新加载</button>
        <button type="button" class="ghost muted" :disabled="busy" @click="$emit('export')">导出</button>
        <div class="status" :class="{ busy }">{{ busy ? "处理中" : "就绪" }}</div>
      </div>
    </header>

    <div class="message-list" ref="messageListRef">
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <span>{{ message.role === "user" ? "你" : activeCharacter?.name || "角色" }}</span>
        <p>{{ message.content }}</p>
        <small v-if="message.reply_source === 'mock'" class="message-feedback warning">本地备用回复 · 本轮模型未正常返回</small>
        <small v-else-if="message.reply_source === 'remote'" class="message-feedback">模型回复</small>
        <small v-if="message.delivery === 'sending'" class="message-feedback">正在发送…</small>
        <small v-else-if="message.delivery === 'unknown'" class="message-feedback warning">未确认是否送达，请重新加载会话核对</small>
      </article>
    </div>

    <form class="composer" @submit.prevent="$emit('submit')">
      <textarea
        v-model="draft"
        :disabled="busy"
        rows="3"
        placeholder="输入这一轮想说的话"
        @keydown.enter.exact.prevent="$emit('submit')"
      />
      <button :disabled="busy || !canSend || !draft.trim()">发送</button>
    </form>

    <p v-if="postprocessNotice" class="chat-notice" role="status">{{ postprocessNotice }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.message-feedback { display: block; margin-top: 0.5rem; color: #b6beae; font-size: 0.8rem; line-height: 1.5; }
.message-feedback.warning { color: #e6c16a; }
.chat-notice { margin: 0.5rem 1rem; font-size: 0.8rem; line-height: 1.5; color: #b6beae; }
</style>
