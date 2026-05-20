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
}>();

defineEmits<{
  submit: [];
  export: [];
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
        <button type="button" class="ghost muted" @click="$emit('export')">Export</button>
        <div class="status" :class="{ busy }">{{ busy ? "thinking" : "ready" }}</div>
      </div>
    </header>

    <div class="message-list" ref="messageListRef">
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <span>{{ message.role === "user" ? "你" : activeCharacter?.name || "角色" }}</span>
        <p>{{ message.content }}</p>
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
      <button :disabled="busy || !draft.trim()">Send</button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
