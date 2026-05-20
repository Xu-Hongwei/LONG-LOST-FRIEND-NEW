<script setup lang="ts">
import type { ContextSlot, MemoryItem, MemoryPane, MemoryPatch } from "../../types";

type MemoryFilter = "all" | "global" | "character" | "session" | "recall";
type MemoryCounts = Record<MemoryFilter, number>;
type PostprocessStage = { key: string; status: string; detail: string };

defineProps<{
  memoryPane: MemoryPane | null;
  memoryCounts: MemoryCounts;
  filteredMemories: MemoryItem[];
  memoryDiagnostics: Record<string, unknown>;
  postprocessStatus: string;
  postprocessStatusLabel: string;
  postprocessDetail: string;
  postprocessStages: PostprocessStage[];
  includedSlots: ContextSlot[];
  excludedSlots: ContextSlot[];
}>();

const manualNoteDraft = defineModel<string>("manualNoteDraft", { required: true });
const memoryFilter = defineModel<MemoryFilter>("memoryFilter", { required: true });
const memoryDraft = defineModel<MemoryPatch>("memoryDraft", { required: true });
const editingMemoryId = defineModel<string>("editingMemoryId", { required: true });
const expandedMemoryId = defineModel<string>("expandedMemoryId", { required: true });
const expandedSlotKey = defineModel<string>("expandedSlotKey", { required: true });

defineEmits<{
  toggleFreeze: [];
  saveMemoryNote: [];
  saveMemoryItem: [memoryId: string];
  cancelEditMemory: [];
  startEditMemory: [memory: MemoryItem];
  removeMemoryItem: [memoryId: string];
  toggleMemoryDetails: [memoryId: string];
  toggleSlotDetails: [slotKey: string];
}>();
</script>

<template>
  <section class="memory-section">
    <div class="section-title">
      <div>
        <p class="eyebrow">Memory</p>
        <h3>{{ memoryPane?.frozen ? "Frozen" : "Live" }}</h3>
      </div>
      <button class="ghost" @click="$emit('toggleFreeze')">
        {{ memoryPane?.frozen ? "Unfreeze" : "Freeze" }}
      </button>
    </div>

    <textarea v-model="manualNoteDraft" class="note" rows="4" placeholder="手动记忆" />
    <button class="wide" @click="$emit('saveMemoryNote')">Save note</button>

    <div class="postprocess-diagnostics" :class="postprocessStatus">
      <div>
        <span>Analysis</span>
        <strong>{{ postprocessStatusLabel }}</strong>
      </div>
      <p>{{ postprocessDetail }}</p>
      <ul v-if="postprocessStages.length" class="postprocess-stages">
        <li v-for="stage in postprocessStages" :key="stage.key" :class="stage.status">
          <span>{{ stage.key }}</span>
          <strong>{{ stage.status }}</strong>
          <small v-if="stage.detail">{{ stage.detail }}</small>
        </li>
      </ul>
      <small v-if="memoryDiagnostics.finished_at">{{ memoryDiagnostics.finished_at }}</small>
    </div>

    <div class="memory-tabs">
      <button :class="{ active: memoryFilter === 'all' }" @click="memoryFilter = 'all'">All {{ memoryCounts.all }}</button>
      <button :class="{ active: memoryFilter === 'global' }" @click="memoryFilter = 'global'">Global {{ memoryCounts.global }}</button>
      <button :class="{ active: memoryFilter === 'character' }" @click="memoryFilter = 'character'">Role {{ memoryCounts.character }}</button>
      <button :class="{ active: memoryFilter === 'session' }" @click="memoryFilter = 'session'">Session {{ memoryCounts.session }}</button>
      <button :class="{ active: memoryFilter === 'recall' }" @click="memoryFilter = 'recall'">Recall {{ memoryCounts.recall }}</button>
    </div>

    <div class="memory-list">
      <div v-for="memory in filteredMemories" :key="memory.id" class="memory-item">
        <template v-if="editingMemoryId === memory.id">
          <div class="memory-edit-grid">
            <label>
              <span>Scope</span>
              <select v-model="memoryDraft.memory_scope">
                <option value="global">global</option>
                <option value="character">character</option>
                <option value="session">session</option>
              </select>
            </label>
            <label>
              <span>Type</span>
              <select v-model="memoryDraft.memory_type">
                <option value="stable_user_info">stable_user_info</option>
                <option value="user_preference">user_preference</option>
                <option value="relationship_progress">relationship_progress</option>
                <option value="open_thread">open_thread</option>
                <option value="recent_emotion">recent_emotion</option>
              </select>
            </label>
          </div>
          <textarea v-model="memoryDraft.content" class="note compact" rows="3" />
          <label class="range-field">
            <span>Importance {{ Math.round(Number(memoryDraft.importance || 0) * 100) }}%</span>
            <input v-model.number="memoryDraft.importance" type="range" min="0" max="1" step="0.05" />
          </label>
          <div class="memory-actions">
            <button class="ghost" @click="$emit('saveMemoryItem', memory.id)">Save</button>
            <button class="ghost muted" @click="$emit('cancelEditMemory')">Cancel</button>
          </div>
        </template>
        <template v-else>
          <div class="memory-meta">
            <button class="memory-title" @click="$emit('toggleMemoryDetails', memory.id)">
              {{ memory.memory_scope }} / {{ memory.memory_type }}
            </button>
            <div class="memory-actions">
              <button @click="$emit('startEditMemory', memory)">Edit</button>
              <button @click="$emit('removeMemoryItem', memory.id)">Delete</button>
            </div>
          </div>
          <div class="score-row">
            <span>importance {{ Math.round(memory.importance * 100) }}%</span>
            <span>confidence {{ Math.round(memory.confidence * 100) }}%</span>
          </div>
          <p>{{ memory.content }}</p>
          <dl v-if="expandedMemoryId === memory.id" class="detail-grid">
            <div>
              <dt>ID</dt>
              <dd>{{ memory.id }}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{{ memory.source_message_id || "manual / unknown" }}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{{ memory.created_at }}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{{ memory.updated_at }}</dd>
            </div>
          </dl>
        </template>
      </div>
      <div v-if="!filteredMemories.length" class="empty">No memory in this view.</div>
    </div>
  </section>

  <section class="memory-section">
    <div class="section-title">
      <div>
        <p class="eyebrow">Prompt Stack</p>
        <h3>{{ includedSlots.length }} included</h3>
      </div>
    </div>

    <div class="slot-list">
      <div v-for="slot in includedSlots" :key="slot.key" class="slot-item" :class="{ expanded: expandedSlotKey === slot.key }">
        <div @click="$emit('toggleSlotDetails', slot.key)">
          <strong>{{ slot.key }}</strong>
          <span>{{ slot.priority }} / {{ slot.token_budget }}</span>
        </div>
        <p>{{ slot.content }}</p>
        <dl v-if="expandedSlotKey === slot.key" class="detail-grid">
          <div>
            <dt>Role</dt>
            <dd>{{ slot.role }}</dd>
          </div>
          <div>
            <dt>Included</dt>
            <dd>{{ slot.included ? "yes" : "no" }}</dd>
          </div>
          <div>
            <dt>Budget</dt>
            <dd>{{ slot.token_budget }}</dd>
          </div>
        </dl>
      </div>
      <div v-if="excludedSlots.length" class="excluded">{{ excludedSlots.length }} excluded by budget</div>
    </div>
  </section>
</template>
