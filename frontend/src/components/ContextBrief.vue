<script setup lang="ts">
import type { CharacterCard, MemoryPane } from "../types";
import type { LoveGender, LoveProfile } from "../features/relationship/personalityTest/data";
import { loveQuestions } from "../features/relationship/personalityTest/data";

type PageKey = "chat" | "love-test" | "novel";

defineProps<{
  currentPage: PageKey;
  activeCharacter: CharacterCard | null;
  loveGender: LoveGender;
  loveResult: LoveProfile | null;
  loveProfileImageUrl: string;
  loveProgress: number;
  messageCount: number;
  memoryPane: MemoryPane | null;
}>();

defineEmits<{
  setLoveGender: [gender: LoveGender];
}>();
</script>

<template>
  <section v-if="currentPage === 'chat' && activeCharacter" class="character-brief">
    <p class="eyebrow">Character Card</p>
    <h3>{{ activeCharacter.name }}</h3>
    <p>{{ activeCharacter.personality || activeCharacter.bio }}</p>
    <dl>
      <div>
        <dt>Scenario</dt>
        <dd>{{ activeCharacter.scenario || "校园轻陪伴聊天" }}</dd>
      </div>
      <div>
        <dt>Rhythm</dt>
        <dd>{{ activeCharacter.voice?.sentence_rhythm || activeCharacter.speech_style }}</dd>
      </div>
      <div>
        <dt>Dynamic Action</dt>
        <dd>{{ activeCharacter.interaction_policy?.action_style || "按当前语境动态生成，低密度，不抢话" }}</dd>
      </div>
    </dl>
  </section>

  <section v-else-if="currentPage === 'love-test'" class="character-brief">
    <p class="eyebrow">Love Type</p>
    <h3>相处风格校准</h3>
    <p>这不是严肃诊断，也不会替角色推进剧情。它只把你的偏好转成可解释的互动建议。</p>
    <div class="gender-toggle">
      <button type="button" :class="{ active: loveGender === 'female' }" @click="$emit('setLoveGender', 'female')">女性画像</button>
      <button type="button" :class="{ active: loveGender === 'male' }" @click="$emit('setLoveGender', 'male')">男性画像</button>
    </div>
    <div v-if="loveResult" class="love-type-art" :style="{ backgroundImage: `url('${loveProfileImageUrl}')` }">
      <span>{{ loveResult.name }}</span>
    </div>
    <div v-else class="love-type-art pending">
      <span>答完后生成画像</span>
    </div>
    <dl>
      <div>
        <dt>Progress</dt>
        <dd>{{ loveProgress }} / {{ loveQuestions.length }}</dd>
      </div>
      <div>
        <dt>Apply</dt>
        <dd>完成后可写入手动记忆，让当前角色知道怎样靠近你更舒服。</dd>
      </div>
    </dl>
  </section>

  <section v-else-if="currentPage === 'novel' && activeCharacter" class="character-brief">
    <p class="eyebrow">Novel Studio</p>
    <h3>{{ activeCharacter.name }} · 会话改编</h3>
    <p>把当前角色会话改编成短篇、番外或章节开头。生成会参考角色卡、会话记录、记忆和关系档案。</p>
    <dl>
      <div>
        <dt>Source</dt>
        <dd>{{ messageCount }} 条消息 · {{ memoryPane?.memories.length || 0 }} 条记忆</dd>
      </div>
      <div>
        <dt>Boundary</dt>
        <dd>允许文学化氛围，不制造原会话没有发生的重大关系进展。</dd>
      </div>
    </dl>
  </section>
</template>
