import { computed, reactive, ref } from "vue";
import type { CharacterCard, CharacterSettingType } from "../../types";
import { createCharacter, deleteCharacter, generateCharacterDraft, updateCharacter, type CharacterWritePayload } from "./api";

export const CHARACTER_SETTING_OPTIONS: { value: CharacterSettingType; label: string }[] = [
  { value: "campus", label: "校园轻伴" },
  { value: "modern_daily", label: "现代日常" },
  { value: "workplace", label: "职场现实" },
  { value: "xianxia_wuxia", label: "武侠修仙" },
  { value: "urban_fantasy", label: "都市奇幻" },
  { value: "mystery", label: "悬疑推理" },
  { value: "sci_fi", label: "科幻赛博" },
  { value: "historical", label: "历史古风" },
  { value: "fantasy_adventure", label: "奇幻冒险" },
  { value: "custom", label: "自定义" }
];

export function settingLabel(value?: string) {
  return CHARACTER_SETTING_OPTIONS.find((item) => item.value === value)?.label || "现代日常";
}

function groupCharactersBySetting(cards: CharacterCard[]) {
  const groups: { settingType: string; label: string; characters: CharacterCard[] }[] = [];
  for (const character of cards) {
    const settingType = character.setting_type || "modern_daily";
    let group = groups.find((item) => item.settingType === settingType);
    if (!group) {
      group = { settingType, label: settingLabel(settingType), characters: [] };
      groups.push(group);
    }
    group.characters.push(character);
  }
  return groups;
}

export type CharacterDraft = {
  name: string;
  archetype: string;
  tagline: string;
  gender: string;
  setting_type: CharacterSettingType;
  setting_notes: string;
  bio: string;
  personality: string;
  scenario: string;
  speech_style: string;
  relationship_pace: string;
  opening_line: string;
  likes: string;
  dislikes: string;
  boundaries: string;
  mes_example: string;
  creator_notes: string;
  system_prompt: string;
  post_history_instructions: string;
  initiative_level: number;
  action_density: string;
  action_style: string;
  comfort_style: string;
  question_style: string;
  memory_style: string;
  anti_patterns: string;
  seed_places: string;
  seed_events: string;
  seed_hooks: string;
  seed_motifs: string;
  seed_forbidden: string;
  sentence_rhythm: string;
  signature_moves: string;
  voice_avoid: string;
  sample_lines: string;
  accent: string;
};

export type CharacterDraftMode = "complete" | "rewrite";

const emptyDraft: CharacterDraft = {
  name: "",
  archetype: "",
  tagline: "",
  gender: "",
  setting_type: "modern_daily",
  setting_notes: "",
  bio: "",
  personality: "",
  scenario: "",
  speech_style: "",
  relationship_pace: "",
  opening_line: "",
  likes: "",
  dislikes: "",
  boundaries: "",
  mes_example: "",
  creator_notes: "",
  system_prompt: "",
  post_history_instructions: "",
  initiative_level: 0.45,
  action_density: "",
  action_style: "",
  comfort_style: "",
  question_style: "",
  memory_style: "",
  anti_patterns: "",
  seed_places: "",
  seed_events: "",
  seed_hooks: "",
  seed_motifs: "",
  seed_forbidden: "",
  sentence_rhythm: "",
  signature_moves: "",
  voice_avoid: "",
  sample_lines: "",
  accent: "#9fb6d7"
};

function lines(value: string) {
  return value
    .split(/\r?\n|[,，、]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinList(value?: string[]) {
  return (value || []).join("\n");
}

function displayGender(value?: string) {
  const text = (value || "").trim();
  const normalized = text.toLowerCase();
  const map: Record<string, string> = {
    female: "女",
    woman: "女",
    girl: "女",
    male: "男",
    man: "男",
    boy: "男",
    nonbinary: "非二元",
    "non-binary": "非二元",
    unknown: "未设定",
    unspecified: "未设定"
  };
  return map[normalized] || text;
}

function displayActionDensity(value?: string) {
  const text = (value || "").trim();
  const normalized = text.toLowerCase();
  const map: Record<string, string> = {
    very_low: "极少动作，只在情绪转折或关系边界需要时出现一个轻动作。",
    low: "少量轻动作，每 2 到 3 轮出现一次，优先用眼神、停顿和小幅动作。",
    medium_low: "偏少但稳定，重要回应时可出现一个轻动作，避免连续重复。",
    medium: "动作适中，每轮可有一个服务对话的小动作，避免连续重复同一姿态。",
    high: "动作较多，可以自然穿插走动、递物、靠近或观察环境，但每轮最多一个重点动作。"
  };
  return map[normalized] || text;
}

function applyCardToDraft(draft: CharacterDraft, card?: CharacterCard | null) {
  const source = card || null;
  Object.assign(draft, emptyDraft, {
    name: source?.name || "",
    archetype: source?.archetype || "",
    tagline: source?.tagline || "",
    gender: displayGender(source?.gender),
    setting_type: source?.setting_type || "modern_daily",
    setting_notes: source?.setting_notes || "",
    bio: source?.bio || "",
    personality: source?.personality || "",
    scenario: source?.scenario || "",
    speech_style: source?.speech_style || "",
    relationship_pace: source?.relationship_pace || "",
    opening_line: source?.opening_line || "",
    likes: joinList(source?.likes),
    dislikes: joinList(source?.dislikes),
    boundaries: joinList(source?.boundaries),
    mes_example: source?.mes_example || "",
    creator_notes: source?.creator_notes || "",
    system_prompt: source?.system_prompt || "",
    post_history_instructions: source?.post_history_instructions || "",
    initiative_level: Number(source?.interaction_policy?.initiative_level ?? 0.45),
    action_density: displayActionDensity(source?.interaction_policy?.action_density),
    action_style: source?.interaction_policy?.action_style || "",
    comfort_style: source?.interaction_policy?.comfort_style || "",
    question_style: source?.interaction_policy?.question_style || "",
    memory_style: source?.interaction_policy?.memory_style || "",
    anti_patterns: joinList(source?.anti_patterns),
    seed_places: joinList(source?.story_seed_pool?.places),
    seed_events: joinList(source?.story_seed_pool?.event_seeds),
    seed_hooks: joinList(source?.story_seed_pool?.hook_seeds),
    seed_motifs: joinList(source?.story_seed_pool?.motifs),
    seed_forbidden: joinList(source?.story_seed_pool?.forbidden_defaults),
    sentence_rhythm: source?.voice?.sentence_rhythm || "",
    signature_moves: joinList(source?.voice?.signature_moves),
    voice_avoid: joinList(source?.voice?.avoid),
    sample_lines: joinList(source?.voice?.sample_lines),
    accent: source?.visual?.accent || "#9fb6d7"
  });
}

function currentDraftTemplate(draft: CharacterDraft): Partial<CharacterCard> | undefined {
  const template: Partial<CharacterCard> = {};
  const assignText = (key: keyof CharacterCard, value: string, blocked: string[] = []) => {
    const text = value.trim();
    if (!text || blocked.includes(text.toLowerCase())) return;
    (template as Record<string, unknown>)[key] = text;
  };

  assignText("name", draft.name);
  assignText("archetype", draft.archetype);
  assignText("tagline", draft.tagline);
  assignText("gender", draft.gender, ["unknown", "未设定"]);
  assignText("setting_notes", draft.setting_notes);
  assignText("bio", draft.bio);
  assignText("personality", draft.personality);
  assignText("scenario", draft.scenario);
  assignText("speech_style", draft.speech_style);
  assignText("relationship_pace", draft.relationship_pace);
  assignText("opening_line", draft.opening_line);
  assignText("mes_example", draft.mes_example);
  assignText("creator_notes", draft.creator_notes);
  assignText("system_prompt", draft.system_prompt);
  assignText("post_history_instructions", draft.post_history_instructions);

  template.setting_type = draft.setting_type;
  const likes = lines(draft.likes);
  const dislikes = lines(draft.dislikes);
  const boundaries = lines(draft.boundaries);
  const antiPatterns = lines(draft.anti_patterns);
  if (likes.length) template.likes = likes;
  if (dislikes.length) template.dislikes = dislikes;
  if (boundaries.length) template.boundaries = boundaries;
  if (antiPatterns.length) template.anti_patterns = antiPatterns;
  const storySeedPool = {
    places: lines(draft.seed_places),
    event_seeds: lines(draft.seed_events),
    hook_seeds: lines(draft.seed_hooks),
    motifs: lines(draft.seed_motifs),
    forbidden_defaults: lines(draft.seed_forbidden)
  };
  if (Object.values(storySeedPool).some((items) => items.length)) template.story_seed_pool = storySeedPool;

  const interactionPolicy: NonNullable<CharacterCard["interaction_policy"]> = {};
  if (draft.initiative_level !== emptyDraft.initiative_level) interactionPolicy.initiative_level = draft.initiative_level;
  if (draft.action_density.trim() && draft.action_density.trim().toLowerCase() !== "low") {
    interactionPolicy.action_density = draft.action_density.trim();
  }
  if (draft.action_style.trim()) interactionPolicy.action_style = draft.action_style.trim();
  if (draft.comfort_style.trim()) interactionPolicy.comfort_style = draft.comfort_style.trim();
  if (draft.question_style.trim()) interactionPolicy.question_style = draft.question_style.trim();
  if (draft.memory_style.trim()) interactionPolicy.memory_style = draft.memory_style.trim();
  if (Object.keys(interactionPolicy).length) template.interaction_policy = interactionPolicy;

  const voice: NonNullable<CharacterCard["voice"]> = {};
  if (draft.sentence_rhythm.trim()) voice.sentence_rhythm = draft.sentence_rhythm.trim();
  const signatureMoves = lines(draft.signature_moves);
  const avoid = lines(draft.voice_avoid);
  const sampleLines = lines(draft.sample_lines);
  if (signatureMoves.length) voice.signature_moves = signatureMoves;
  if (avoid.length) voice.avoid = avoid;
  if (sampleLines.length) voice.sample_lines = sampleLines;
  if (Object.keys(voice).length) template.voice = voice;

  if (draft.accent.trim() && draft.accent.trim().toLowerCase() !== emptyDraft.accent.toLowerCase()) {
    template.visual = { accent: draft.accent.trim() };
  }

  return Object.keys(template).some((key) => key !== "setting_type") ? template : undefined;
}

function rewriteDraftTemplate(draft: CharacterDraft): Partial<CharacterCard> | undefined {
  const template: Partial<CharacterCard> = { setting_type: draft.setting_type };
  if (draft.name.trim()) template.name = draft.name.trim();
  if (draft.setting_notes.trim()) template.setting_notes = draft.setting_notes.trim();
  return template;
}

function fallbackSettingNotes(settingType: CharacterSettingType, prompt: string, existing = "") {
  const current = existing.trim();
  if (current) return current;
  const base: Record<CharacterSettingType, string> = {
    campus: "校园日常、社团与课后场景、慢热同伴关系",
    modern_daily: "现代都市日常、生活化场景、自然推进关系",
    workplace: "成人职场、合作与边界、现实压力下的关系推进",
    xianxia_wuxia: "低魔江湖或修仙门派、医修/剑修等身份、克制慢热关系",
    urban_fantasy: "现代城市异常、隐秘组织或规则、日常与超自然交错",
    mystery: "悬疑调查、线索与误会、克制协作关系",
    sci_fi: "近未来城市、数据/义体/调查线索、冷静克制关系",
    historical: "古风时代、家族/官署/江湖约束、礼法边界",
    fantasy_adventure: "奇幻旅途、遗迹与同行选择、冒险中的信任建立",
    custom: "自定义世界观、角色可转译故事素材、按用户设定约束展开"
  };
  const seed = prompt.trim().slice(0, 40);
  return seed ? `${base[settingType]}；核心设定：${seed}` : base[settingType];
}

export function useCharacterWorkshop(visitorId: { value: string }, characters: { value: CharacterCard[] }) {
  const draft = reactive<CharacterDraft>({ ...emptyDraft });
  const editingCharacterId = ref("");
  const generationPrompt = ref("");
  const draftMode = ref<CharacterDraftMode>("complete");
  const generationDiagnostics = ref<Record<string, unknown>>({});
  const generating = ref(false);
  const busy = ref(false);
  const error = ref("");
  const savedCharacterId = ref("");

  const customCharacters = computed(() => characters.value.filter((character) => character.origin === "custom"));
  const builtinCharacters = computed(() => characters.value.filter((character) => character.origin !== "custom"));
  const groupedCharacters = computed(() => groupCharactersBySetting(characters.value));
  const canSave = computed(() => Boolean(visitorId.value && draft.name.trim()));

  function startBlank() {
    editingCharacterId.value = "";
    savedCharacterId.value = "";
    error.value = "";
    applyCardToDraft(draft, null);
  }

  function useTemplate(card: CharacterCard) {
    editingCharacterId.value = "";
    savedCharacterId.value = "";
    error.value = "";
    applyCardToDraft(draft, card);
  }

  function editCharacter(card: CharacterCard) {
    editingCharacterId.value = card.id;
    savedCharacterId.value = "";
    error.value = "";
    applyCardToDraft(draft, card);
  }

  function payload(): CharacterWritePayload {
    return {
      visitor_id: visitorId.value,
      name: draft.name.trim(),
      archetype: draft.archetype.trim(),
      tagline: draft.tagline.trim(),
      gender: draft.gender,
      setting_type: draft.setting_type,
      setting_notes: draft.setting_notes.trim(),
      bio: draft.bio.trim(),
      personality: draft.personality.trim(),
      scenario: draft.scenario.trim(),
      speech_style: draft.speech_style.trim(),
      relationship_pace: draft.relationship_pace.trim(),
      opening_line: draft.opening_line.trim(),
      likes: lines(draft.likes),
      dislikes: lines(draft.dislikes),
      boundaries: lines(draft.boundaries),
      mes_example: draft.mes_example.trim(),
      creator_notes: draft.creator_notes.trim(),
      system_prompt: draft.system_prompt.trim(),
      post_history_instructions: draft.post_history_instructions.trim(),
      interaction_policy: {
        initiative_level: draft.initiative_level,
        action_density: draft.action_density,
        action_style: draft.action_style.trim(),
        comfort_style: draft.comfort_style.trim(),
        question_style: draft.question_style.trim(),
        memory_style: draft.memory_style.trim()
      },
      anti_patterns: lines(draft.anti_patterns),
      story_seed_pool: {
        places: lines(draft.seed_places),
        event_seeds: lines(draft.seed_events),
        hook_seeds: lines(draft.seed_hooks),
        motifs: lines(draft.seed_motifs),
        forbidden_defaults: lines(draft.seed_forbidden)
      },
      voice: {
        sentence_rhythm: draft.sentence_rhythm.trim(),
        signature_moves: lines(draft.signature_moves),
        avoid: lines(draft.voice_avoid),
        sample_lines: lines(draft.sample_lines)
      },
      visual: {
        accent: draft.accent.trim() || "#9fb6d7"
      }
    };
  }

  async function save() {
    if (!canSave.value) return null;
    busy.value = true;
    error.value = "";
    try {
      const result = editingCharacterId.value
        ? await updateCharacter(editingCharacterId.value, payload())
        : await createCharacter(payload());
      editingCharacterId.value = result.id;
      savedCharacterId.value = result.id;
      return result;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function generateDraft() {
    const prompt = generationPrompt.value.trim();
    if (!visitorId.value || !prompt || busy.value || generating.value) return null;
    const currentEditingCharacterId = editingCharacterId.value;
    const currentSavedCharacterId = savedCharacterId.value;
    generating.value = true;
    busy.value = true;
    error.value = "";
    generationDiagnostics.value = {};
    try {
      const template = draftMode.value === "rewrite" ? rewriteDraftTemplate(draft) : currentDraftTemplate(draft);
      const result = await generateCharacterDraft(
        visitorId.value,
        prompt,
        draft.setting_type,
        draft.setting_notes,
        draftMode.value,
        template
      );
      generationDiagnostics.value = result.diagnostics || {};
      result.character.setting_type = (result.character.setting_type || draft.setting_type) as CharacterSettingType;
      result.character.setting_notes = fallbackSettingNotes(
        result.character.setting_type as CharacterSettingType,
        prompt,
        result.character.setting_notes || draft.setting_notes
      );
      applyCardToDraft(draft, result.character as CharacterCard);
      editingCharacterId.value = currentEditingCharacterId;
      savedCharacterId.value = currentEditingCharacterId ? currentSavedCharacterId : "";
      return result.character;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return null;
    } finally {
      generating.value = false;
      busy.value = false;
    }
  }

  async function remove(character: CharacterCard) {
    if (!visitorId.value || character.origin !== "custom") return false;
    busy.value = true;
    error.value = "";
    try {
      await deleteCharacter(character.id, visitorId.value);
      if (editingCharacterId.value === character.id) startBlank();
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return false;
    } finally {
      busy.value = false;
    }
  }

  startBlank();

  return {
    draft,
    editingCharacterId,
    generationPrompt,
    draftMode,
    generationDiagnostics,
    generating,
    busy,
    error,
    savedCharacterId,
    customCharacters,
    builtinCharacters,
    groupedCharacters,
    settingOptions: CHARACTER_SETTING_OPTIONS,
    canSave,
    startBlank,
    useTemplate,
    editCharacter,
    generateDraft,
    save,
    remove
  };
}
