<script setup lang="ts">
import type { CharacterCard } from "../../types";
import CharacterForm from "./CharacterForm.vue";
import { useCharacterWorkshop } from "./useCharacterWorkshop";

const props = defineProps<{
  visitorId: string;
  characters: CharacterCard[];
  activeCharacterId: string;
}>();

const emit = defineEmits<{
  refresh: [preferredCharacterId?: string];
  startChat: [characterId: string];
}>();

const workshop = useCharacterWorkshop(
  { get value() { return props.visitorId; } },
  { get value() { return props.characters; } }
);

async function saveCharacter() {
  const saved = await workshop.save();
  if (!saved) return;
  emit("refresh", saved.id);
}

async function removeCharacter(character: CharacterCard) {
  const deleted = await workshop.remove(character);
  if (!deleted) return;
  emit("refresh");
}

function startChat(characterId: string) {
  emit("refresh", characterId);
  emit("startChat", characterId);
}
</script>

<template>
  <section class="character-workshop">
    <header class="character-workshop-header">
      <div>
        <p class="eyebrow">Character Workshop</p>
        <h2>角色工坊</h2>
        <span>自建角色会进入聊天、关系记忆和小说工坊。</span>
      </div>
      <button type="button" class="ghost muted" @click="workshop.startBlank">空白角色</button>
    </header>

    <aside class="character-template-rail">
      <section class="character-generator">
        <div>
          <p class="eyebrow">AI Draft</p>
          <h3>一句话扩写角色卡</h3>
        </div>
        <textarea
          v-model="workshop.generationPrompt.value"
          rows="5"
          :disabled="workshop.busy.value"
          placeholder="例：一个嘴硬但很会照顾人的社团学姐，讲话短促，关系推进慢。"
        />
        <button
          type="button"
          class="wide generator-button"
          :class="{ loading: workshop.generating.value }"
          :disabled="workshop.busy.value || !workshop.generationPrompt.value.trim()"
          @click="workshop.generateDraft"
        >
          <span v-if="workshop.generating.value" class="loading-dot"></span>
          {{ workshop.generating.value ? "生成中..." : "AI 扩写并填入" }}
        </button>
        <div v-if="workshop.generating.value" class="generation-status">
          <span></span>
          <p>正在生成结构化 JSON，并填入角色卡草稿。</p>
        </div>
        <small v-else-if="workshop.generationDiagnostics.value.source">
          {{ workshop.generationDiagnostics.value.source === "remote" ? "remote JSON" : "fallback draft" }}
        </small>
      </section>

      <section class="workshop-panel">
        <div class="workshop-panel-head">
          <p class="eyebrow">Custom</p>
          <strong>{{ workshop.customCharacters.value.length }}</strong>
        </div>
        <div class="workshop-list">
          <article v-for="character in workshop.customCharacters.value" :key="character.id" class="workshop-character">
            <span class="portrait" :style="{ '--accent': character.visual?.accent || '#8da2c8' }"></span>
            <div>
              <strong>{{ character.name }}</strong>
              <small>{{ character.archetype }}</small>
            </div>
            <div class="workshop-actions">
              <button type="button" class="ghost muted" @click="workshop.editCharacter(character)">编辑</button>
              <button type="button" class="ghost muted" @click="startChat(character.id)">
                {{ character.id === props.activeCharacterId ? "当前" : "开聊" }}
              </button>
              <button type="button" class="ghost danger" @click="removeCharacter(character)">删除</button>
            </div>
          </article>
          <p v-if="!workshop.customCharacters.value.length" class="workshop-empty">还没有自建角色，可以先用 AI 扩写一版。</p>
        </div>
      </section>

      <section class="workshop-panel">
        <div class="workshop-panel-head">
          <p class="eyebrow">Templates</p>
          <strong>{{ workshop.builtinCharacters.value.length }}</strong>
        </div>
        <div class="workshop-list">
          <article v-for="character in workshop.builtinCharacters.value" :key="character.id" class="workshop-character compact">
            <span class="portrait" :style="{ '--accent': character.visual?.accent || '#8da2c8' }"></span>
            <div>
              <strong>{{ character.name }}</strong>
              <small>{{ character.archetype }}</small>
            </div>
            <button type="button" class="ghost muted" @click="workshop.useTemplate(character)">复制</button>
          </article>
        </div>
      </section>
    </aside>

    <CharacterForm
      v-model:draft="workshop.draft"
      :busy="workshop.busy.value"
      :can-save="workshop.canSave.value"
      :editing="Boolean(workshop.editingCharacterId.value)"
      @save="saveCharacter"
      @start-blank="workshop.startBlank"
    />

    <p v-if="workshop.error.value" class="error character-workshop-error">{{ workshop.error.value }}</p>
  </section>
</template>
