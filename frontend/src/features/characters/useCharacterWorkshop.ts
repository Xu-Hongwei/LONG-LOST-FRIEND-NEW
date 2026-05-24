import { computed, reactive, ref } from "vue";
import type { CharacterCard } from "../../types";
import { createCharacter, deleteCharacter, generateCharacterDraft, updateCharacter, type CharacterWritePayload } from "./api";

export type CharacterDraft = {
  name: string;
  archetype: string;
  tagline: string;
  gender: string;
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
  sentence_rhythm: string;
  signature_moves: string;
  voice_avoid: string;
  sample_lines: string;
  accent: string;
};

const emptyDraft: CharacterDraft = {
  name: "",
  archetype: "",
  tagline: "",
  gender: "unknown",
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
  action_density: "low",
  action_style: "",
  comfort_style: "",
  question_style: "",
  memory_style: "",
  anti_patterns: "",
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

function applyCardToDraft(draft: CharacterDraft, card?: CharacterCard | null) {
  const source = card || null;
  Object.assign(draft, emptyDraft, {
    name: source?.origin === "custom" ? source.name : source ? `${source.name} 副本` : "",
    archetype: source?.archetype || "",
    tagline: source?.tagline || "",
    gender: source?.gender || "unknown",
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
    action_density: source?.interaction_policy?.action_density || "low",
    action_style: source?.interaction_policy?.action_style || "",
    comfort_style: source?.interaction_policy?.comfort_style || "",
    question_style: source?.interaction_policy?.question_style || "",
    memory_style: source?.interaction_policy?.memory_style || "",
    anti_patterns: joinList(source?.anti_patterns),
    sentence_rhythm: source?.voice?.sentence_rhythm || "",
    signature_moves: joinList(source?.voice?.signature_moves),
    voice_avoid: joinList(source?.voice?.avoid),
    sample_lines: joinList(source?.voice?.sample_lines),
    accent: source?.visual?.accent || "#9fb6d7"
  });
}

export function useCharacterWorkshop(visitorId: { value: string }, characters: { value: CharacterCard[] }) {
  const draft = reactive<CharacterDraft>({ ...emptyDraft });
  const editingCharacterId = ref("");
  const generationPrompt = ref("");
  const generationDiagnostics = ref<Record<string, unknown>>({});
  const generating = ref(false);
  const busy = ref(false);
  const error = ref("");
  const savedCharacterId = ref("");

  const customCharacters = computed(() => characters.value.filter((character) => character.origin === "custom"));
  const builtinCharacters = computed(() => characters.value.filter((character) => character.origin !== "custom"));
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
    generating.value = true;
    busy.value = true;
    error.value = "";
    generationDiagnostics.value = {};
    try {
      const template = editingCharacterId.value
        ? characters.value.find((character) => character.id === editingCharacterId.value)
        : undefined;
      const result = await generateCharacterDraft(visitorId.value, prompt, template);
      generationDiagnostics.value = result.diagnostics || {};
      applyCardToDraft(draft, result.character as CharacterCard);
      editingCharacterId.value = "";
      savedCharacterId.value = "";
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
    generationDiagnostics,
    generating,
    busy,
    error,
    savedCharacterId,
    customCharacters,
    builtinCharacters,
    canSave,
    startBlank,
    useTemplate,
    editCharacter,
    generateDraft,
    save,
    remove
  };
}
