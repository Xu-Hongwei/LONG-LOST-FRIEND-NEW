<script setup lang="ts">
import type { CharacterDraft } from "./useCharacterWorkshop";
import { settingLabel } from "./useCharacterWorkshop";

const props = defineProps<{
  busy: boolean;
  canSave: boolean;
  editing: boolean;
}>();

const draft = defineModel<CharacterDraft>("draft", { required: true });

defineEmits<{
  save: [];
  startBlank: [];
}>();
</script>

<template>
  <form class="character-form" @submit.prevent="$emit('save')">
    <header class="character-form-head">
      <div>
        <p class="eyebrow">{{ props.editing ? "Editing" : "New Character" }}</p>
        <h3>{{ draft.name || "未命名角色" }}</h3>
      </div>
      <button type="button" class="ghost muted" :disabled="props.busy" @click="$emit('startBlank')">新建</button>
    </header>

    <section class="character-preview">
      <span class="portrait large" :style="{ '--accent': draft.accent || '#9fb6d7' }"></span>
      <div>
        <p class="eyebrow">Preview</p>
        <h2>{{ draft.name || "未命名角色" }}</h2>
        <p>{{ draft.tagline || draft.archetype || "先写一句粗设定，或用 AI 扩写出完整角色卡。" }}</p>
        <div class="character-preview-tags">
          <span>{{ draft.archetype || "未设定定位" }}</span>
          <span>{{ settingLabel(draft.setting_type) }}</span>
          <span v-if="draft.gender.trim()">{{ draft.gender }}</span>
          <span v-if="draft.action_density.trim()">{{ draft.action_density }}</span>
        </div>
      </div>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">01</p>
        <h4>基础设定</h4>
      </header>
      <div class="character-form-grid">
        <label>
          <span>角色名</span>
          <input v-model="draft.name" :disabled="props.busy" />
        </label>
        <label>
          <span>定位</span>
          <input v-model="draft.archetype" :disabled="props.busy" />
        </label>
        <label class="span-2">
          <span>一句话</span>
          <input v-model="draft.tagline" :disabled="props.busy" />
        </label>
        <label>
          <span>性别</span>
          <input v-model="draft.gender" :disabled="props.busy" placeholder="由 AI 生成，可手动编辑" />
        </label>
        <label>
          <span>强调色</span>
          <input v-model="draft.accent" type="color" :disabled="props.busy" />
        </label>
        <label class="span-2">
          <span>题材补充</span>
          <input v-model="draft.setting_notes" :disabled="props.busy" placeholder="例如：低魔江湖、近未来雨城、成人职场合伙人关系" />
        </label>
      </div>
      <label>
        <span>简介</span>
        <textarea v-model="draft.bio" rows="3" :disabled="props.busy" />
      </label>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">02</p>
        <h4>人格与关系</h4>
      </header>
      <label>
        <span>性格底色</span>
        <textarea v-model="draft.personality" rows="4" :disabled="props.busy" />
      </label>
      <label>
        <span>场景语境</span>
        <textarea v-model="draft.scenario" rows="3" :disabled="props.busy" />
      </label>
      <div class="character-form-grid">
        <label>
          <span>说话风格</span>
          <textarea v-model="draft.speech_style" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>关系节奏</span>
          <textarea v-model="draft.relationship_pace" rows="3" :disabled="props.busy" />
        </label>
      </div>
      <label>
        <span>开场白</span>
        <textarea v-model="draft.opening_line" rows="2" :disabled="props.busy" />
      </label>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">03</p>
        <h4>偏好与边界</h4>
      </header>
      <div class="character-form-grid">
        <label>
          <span>喜欢</span>
          <textarea v-model="draft.likes" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>不喜欢</span>
          <textarea v-model="draft.dislikes" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>边界</span>
          <textarea v-model="draft.boundaries" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>反模式</span>
          <textarea v-model="draft.anti_patterns" rows="3" :disabled="props.busy" />
        </label>
      </div>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">04</p>
        <h4>默认故事素材包</h4>
      </header>
      <p class="story-seed-note">只作为角色默认灵感；创建小说时会按项目题材转译，不会强制写入每一本作品。</p>
      <div class="character-form-grid">
        <label>
          <span>可转译场域</span>
          <textarea v-model="draft.seed_places" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>事件模式</span>
          <textarea v-model="draft.seed_events" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>关系钩子</span>
          <textarea v-model="draft.seed_hooks" rows="3" :disabled="props.busy" />
        </label>
        <label>
          <span>角色意象</span>
          <textarea v-model="draft.seed_motifs" rows="3" :disabled="props.busy" />
        </label>
        <label class="span-2">
          <span>避免套用</span>
          <textarea v-model="draft.seed_forbidden" rows="2" :disabled="props.busy" />
        </label>
      </div>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">05</p>
        <h4>行为策略</h4>
      </header>
      <div class="character-form-grid compact">
        <label>
          <span>主动程度 {{ Math.round(draft.initiative_level * 100) }}%</span>
          <input v-model.number="draft.initiative_level" type="range" min="0" max="1" step="0.05" :disabled="props.busy" />
        </label>
        <label>
          <span>动作密度</span>
          <input v-model="draft.action_density" :disabled="props.busy" placeholder="由 AI 生成，可手动编辑" />
        </label>
      </div>
      <div class="character-form-grid">
        <label>
          <span>动作风格</span>
          <textarea v-model="draft.action_style" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>安慰方式</span>
          <textarea v-model="draft.comfort_style" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>追问方式</span>
          <textarea v-model="draft.question_style" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>记忆方式</span>
          <textarea v-model="draft.memory_style" rows="2" :disabled="props.busy" />
        </label>
      </div>
    </section>

    <section class="character-form-section">
      <header>
        <p class="eyebrow">06</p>
        <h4>声音样例</h4>
      </header>
      <div class="character-form-grid">
        <label>
          <span>句式节奏</span>
          <textarea v-model="draft.sentence_rhythm" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>标志动作</span>
          <textarea v-model="draft.signature_moves" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>避免口吻</span>
          <textarea v-model="draft.voice_avoid" rows="2" :disabled="props.busy" />
        </label>
        <label>
          <span>参考短句</span>
          <textarea v-model="draft.sample_lines" rows="2" :disabled="props.busy" />
        </label>
      </div>
      <label>
        <span>示例对话</span>
        <textarea v-model="draft.mes_example" rows="5" :disabled="props.busy" />
      </label>
      <label>
        <span>创作者备注</span>
        <textarea v-model="draft.creator_notes" rows="3" :disabled="props.busy" />
      </label>
    </section>

    <div class="character-form-actions">
      <button type="submit" class="wide" :disabled="props.busy || !props.canSave">
        {{ props.editing ? "保存修改" : "创建角色" }}
      </button>
    </div>
  </form>
</template>
