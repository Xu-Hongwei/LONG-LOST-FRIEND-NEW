<script setup lang="ts">
import type { CharacterCard } from "../../types";
import CharacterForm from "./CharacterForm.vue";
import { settingLabel, useCharacterWorkshop } from "./useCharacterWorkshop";

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

function generationSourceLabel(source: unknown) {
  if (source === "remote") return "远程返回";
  if (source === "partial") return "部分远程";
  if (source === "fallback") return "本地兜底";
  if (source === "local") return "本地生成";
  return String(source || "");
}

function generationSourceTone(source: unknown) {
  if (source === "partial") return "partial";
  return source === "remote" ? "remote" : "fallback";
}

function generationReason(diagnostics: Record<string, unknown>) {
  return String(diagnostics.reason || diagnostics.error || diagnostics.fallback_reason || "").trim();
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
          placeholder="先选题材，再写一句话。例：冷淡但可靠的医修，讲话短，关系推进慢。"
        />
        <label class="generator-setting">
          <span>题材类型</span>
          <select v-model="workshop.draft.setting_type" :disabled="workshop.busy.value">
            <option v-for="option in workshop.settingOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <div class="generator-mode" role="group" aria-label="角色卡生成模式">
          <button
            type="button"
            :class="{ active: workshop.draftMode.value === 'complete' }"
            :disabled="workshop.busy.value"
            @click="workshop.draftMode.value = 'complete'"
          >
            补全润色
          </button>
          <button
            type="button"
            :class="{ active: workshop.draftMode.value === 'rewrite' }"
            :disabled="workshop.busy.value"
            @click="workshop.draftMode.value = 'rewrite'"
          >
            整卡重写
          </button>
        </div>
        <small>
          {{
            workshop.draftMode.value === "rewrite"
              ? "只保留名字、题材和一句话核心，整张角色卡重新生成。"
              : "保留已写好的内容，补齐空字段并润色薄弱字段。"
          }}
        </small>
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
          <p>正在请求远程结构化 JSON，并填入角色卡草稿。</p>
        </div>
        <div
          v-else-if="workshop.generationDiagnostics.value.source"
          class="generation-source"
          :class="generationSourceTone(workshop.generationDiagnostics.value.source)"
        >
          <strong>{{ generationSourceLabel(workshop.generationDiagnostics.value.source) }}</strong>
          <span v-if="workshop.generationDiagnostics.value.source === 'remote'">结构化 JSON 已填入</span>
          <span v-else-if="workshop.generationDiagnostics.value.source === 'partial'">
            部分远程成功，其余字段使用本地兜底
          </span>
          <span v-else>使用本地草稿填入</span>
          <em v-if="generationReason(workshop.generationDiagnostics.value)">
            {{ generationReason(workshop.generationDiagnostics.value) }}
          </em>
        </div>
      </section>

      <section class="workshop-panel">
        <div class="workshop-panel-head">
          <p class="eyebrow">Library</p>
          <strong>{{ props.characters.length }}</strong>
        </div>
        <div class="workshop-list">
          <template v-for="group in workshop.groupedCharacters.value" :key="group.settingType">
            <p class="workshop-group-label">{{ group.label }}</p>
            <article
              v-for="character in group.characters"
              :key="character.id"
              class="workshop-character"
              :class="{ compact: character.origin !== 'custom' }"
            >
              <span class="portrait" :style="{ '--accent': character.visual?.accent || '#8da2c8' }"></span>
              <div>
                <strong>{{ character.name }}</strong>
                <small>{{ character.archetype }}</small>
                <small class="workshop-card-meta">{{ character.origin === "custom" ? "自建" : "模板" }}</small>
              </div>
              <div v-if="character.origin === 'custom'" class="workshop-actions">
                <button type="button" class="ghost muted" @click="workshop.editCharacter(character)">编辑</button>
                <button type="button" class="ghost muted" @click="startChat(character.id)">
                  {{ character.id === props.activeCharacterId ? "当前" : "开聊" }}
                </button>
                <button type="button" class="ghost danger" @click="removeCharacter(character)">删除</button>
              </div>
              <button v-else type="button" class="ghost muted" @click="workshop.useTemplate(character)">复制</button>
            </article>
          </template>
          <p v-if="!props.characters.length" class="workshop-empty">还没有角色，可以先用 AI 扩写一版。</p>
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
