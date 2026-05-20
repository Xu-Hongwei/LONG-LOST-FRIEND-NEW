<script setup lang="ts">
import type { CharacterBond, CharacterState } from "../../types";

defineProps<{
  characterState: CharacterState | null;
  characterBond: CharacterBond | null;
  energyPercent: number;
  resonancePercent: number;
  bondPercent: number;
}>();

const stateExpanded = defineModel<boolean>("stateExpanded", { required: true });
const bondExpanded = defineModel<boolean>("bondExpanded", { required: true });
</script>

<template>
  <section class="memory-section">
    <div class="section-title">
      <div>
        <p class="eyebrow">State</p>
        <h3>{{ characterState?.mood || "No state" }}</h3>
      </div>
      <button class="ghost muted" @click="stateExpanded = !stateExpanded">
        {{ stateExpanded ? "Hide" : "Detail" }}
      </button>
    </div>

    <section v-if="characterState" class="state-strip side-strip">
      <button class="state-summary" type="button" @click="stateExpanded = !stateExpanded">
        <span>
          <small>Tone</small>
          <strong>{{ characterState.tone }}</strong>
        </span>
        <span>
          <small>Distance</small>
          <strong>{{ characterState.distance }}</strong>
        </span>
        <span class="state-focus">
          <small>Focus</small>
          <strong>{{ characterState.focus }}</strong>
        </span>
      </button>
      <div class="state-bars">
        <label>
          <span>Energy {{ energyPercent }}%</span>
          <i><b :style="{ width: `${energyPercent}%` }"></b></i>
        </label>
        <label>
          <span>Resonance {{ resonancePercent }}%</span>
          <i><b :style="{ width: `${resonancePercent}%` }"></b></i>
        </label>
      </div>
      <dl v-if="stateExpanded" class="state-detail">
        <div>
          <dt>Pace</dt>
          <dd>{{ characterState.behavior.pace }}</dd>
        </div>
        <div>
          <dt>Initiative</dt>
          <dd>{{ characterState.behavior.initiative }}</dd>
        </div>
        <div>
          <dt>Warmth</dt>
          <dd>{{ characterState.behavior.warmth }}</dd>
        </div>
        <div>
          <dt>Memory Use</dt>
          <dd>{{ characterState.behavior.memory_use }}</dd>
        </div>
        <div>
          <dt>Avoid</dt>
          <dd>{{ characterState.behavior.avoid }}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{{ characterState.last_shift || characterState.evidence }}</dd>
        </div>
      </dl>
    </section>
  </section>

  <section class="memory-section">
    <div class="section-title">
      <div>
        <p class="eyebrow">Bond</p>
        <h3>{{ characterBond?.familiarity_stage || "No bond" }}</h3>
      </div>
      <button class="ghost muted" @click="bondExpanded = !bondExpanded">
        {{ bondExpanded ? "Hide" : "Detail" }}
      </button>
    </div>

    <section v-if="characterBond" class="bond-strip side-strip">
      <button class="bond-summary" type="button" @click="bondExpanded = !bondExpanded">
        <span>
          <small>Base Resonance</small>
          <strong>{{ bondPercent }}%</strong>
        </span>
        <span class="bond-preference">
          <small>Preference</small>
          <strong>{{ characterBond.interaction_preferences }}</strong>
        </span>
      </button>
      <dl v-if="bondExpanded" class="bond-detail">
        <div>
          <dt>Trust</dt>
          <dd>{{ characterBond.trust_notes }}</dd>
        </div>
        <div>
          <dt>Boundary</dt>
          <dd>{{ characterBond.boundary_notes }}</dd>
        </div>
        <div>
          <dt>Milestones</dt>
          <dd>{{ characterBond.milestones.length ? characterBond.milestones.join(" / ") : "暂无关键节点" }}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{{ characterBond.evidence }}</dd>
        </div>
      </dl>
    </section>
  </section>
</template>
