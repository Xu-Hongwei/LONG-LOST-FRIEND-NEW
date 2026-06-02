import type { NovelChapter, NovelChapterStatus, ProgressionProtocol, StoryCanvas, StoryCanvasChapter, StoryCanvasEvent, StoryCanvasEventPool, StoryCanvasScene, StoryPromise } from "../../types";
import { sceneCardFields } from "./constants";

export type ChapterSceneCardDraft = Record<string, string>;

export function emptyStoryCanvas(): StoryCanvas {
  return {
    version: 1,
    mode: "story_canvas",
    story_promise: emptyStoryPromise(),
    progression_protocol: emptyProgressionProtocol(),
    acts: [],
    chapters: [],
    scenes: [],
    threads: [],
    event_pool: {
      version: 1,
      target_active: 10,
      setting_type: "modern_daily",
      active: [],
      retired: []
    },
    quality_rules: []
  };
}

export function emptyStoryPromise(): StoryPromise {
  return {
    core_experience: "",
    genre_contract: "",
    relationship_engine: "",
    tone_commitment: ""
  };
}

export function emptyProgressionProtocol(): ProgressionProtocol {
  return {
    driver: "",
    chapter_rules: [],
    progression_tools: [],
    relationship_rule: "",
    drift_guards: [],
    style_directives: [],
    source: "local",
    manual_edited: false
  };
}

export function stringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  const text = String(value || "").trim();
  return text ? text.split(/[；;]\s*/).map((item) => item.trim()).filter(Boolean) : [];
}

function normalizeStoryEvent(value: unknown, index: number): StoryCanvasEvent {
  const raw = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  return {
    id: String(raw.id || `evt_${index + 1}`),
    place: String(raw.place || ""),
    time_anchor: String(raw.time_anchor || ""),
    event: String(raw.event || ""),
    hook: String(raw.hook || ""),
    motifs: stringArray(raw.motifs),
    use_mode: String(raw.use_mode || "guide"),
    status: String(raw.status || "fresh"),
    source: String(raw.source || "setting_profile"),
    used_chapter_ids: stringArray(raw.used_chapter_ids),
    bound_chapter_orders: stringArray(raw.bound_chapter_orders),
    bound_chapter_titles: stringArray(raw.bound_chapter_titles),
    used_summary: String(raw.used_summary || ""),
    tags: raw.tags && typeof raw.tags === "object" ? raw.tags as Record<string, unknown> : {},
    source_reason: String(raw.source_reason || ""),
    selection_score: Number(raw.selection_score || 0),
    selection_reasons: stringArray(raw.selection_reasons),
    selection_penalties: stringArray(raw.selection_penalties)
  };
}

function normalizeStoryEventPool(value: unknown): StoryCanvasEventPool {
  const raw = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  const active = Array.isArray(raw.active) ? raw.active : [];
  const retired = Array.isArray(raw.retired) ? raw.retired : [];
  return {
    version: Number(raw.version || 1),
    target_active: Number(raw.target_active || 10),
    setting_type: String(raw.setting_type || "modern_daily"),
    active: active.map(normalizeStoryEvent),
    retired: retired.map(normalizeStoryEvent),
    updated_at: String(raw.updated_at || "")
  };
}

function normalizeStoryPromise(value: unknown): StoryPromise {
  const raw = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  return {
    core_experience: String(raw.core_experience || ""),
    genre_contract: String(raw.genre_contract || ""),
    relationship_engine: String(raw.relationship_engine || ""),
    tone_commitment: String(raw.tone_commitment || "")
  };
}

function normalizeProgressionProtocol(value: unknown): ProgressionProtocol {
  const raw = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  return {
    driver: String(raw.driver || ""),
    chapter_rules: stringArray(raw.chapter_rules),
    progression_tools: stringArray(raw.progression_tools),
    relationship_rule: String(raw.relationship_rule || ""),
    drift_guards: stringArray(raw.drift_guards),
    style_directives: stringArray(raw.style_directives),
    source: String(raw.source || ""),
    manual_edited: Boolean(raw.manual_edited)
  };
}

export function normalizeStoryCanvas(canvas: unknown): StoryCanvas {
  const raw = (canvas && typeof canvas === "object" ? canvas : {}) as Record<string, unknown>;
  const acts = Array.isArray(raw.acts) ? raw.acts : [];
  const chapters = Array.isArray(raw.chapters) ? raw.chapters : [];
  const scenes = Array.isArray(raw.scenes) ? raw.scenes : [];
  const threads = Array.isArray(raw.threads) ? raw.threads : [];

  return {
    version: Number(raw.version || 1),
    mode: String(raw.mode || "story_canvas"),
    story_promise: normalizeStoryPromise(raw.story_promise),
    progression_protocol: normalizeProgressionProtocol(raw.progression_protocol),
    event_pool: normalizeStoryEventPool(raw.event_pool),
    acts: acts.map((item, index) => {
      const act = item as Record<string, unknown>;
      return {
        id: String(act.id || `act_${index + 1}`),
        order: Number(act.order || index + 1),
        title: String(act.title || `阶段 ${index + 1}`),
        purpose: String(act.purpose || ""),
        chapter_ids: stringArray(act.chapter_ids)
      };
    }),
    chapters: chapters.map((item, index) => {
      const chapter = item as Record<string, unknown>;
      return {
        id: String(chapter.id || `canvas_ch_${index + 1}`),
        act_id: String(chapter.act_id || "act_1"),
        chapter_order: Number(chapter.chapter_order || index + 1),
        event_pool_id: String(chapter.event_pool_id || ""),
        title: String(chapter.title || `第 ${index + 1} 章`),
        goal: String(chapter.goal || ""),
        external_event: String(chapter.external_event || ""),
        trigger_event: String(chapter.trigger_event || chapter.external_event || ""),
        immediate_reaction: String(chapter.immediate_reaction || ""),
        obstacle_escalation: String(chapter.obstacle_escalation || ""),
        counterpart_reaction: String(chapter.counterpart_reaction || ""),
        character_choice: String(chapter.character_choice || chapter.relationship_shift || ""),
        scene_consequence: String(chapter.scene_consequence || chapter.relationship_shift || ""),
        relationship_shift: String(chapter.relationship_shift || ""),
        ending_hook: String(chapter.ending_hook || ""),
        target_length: Number(chapter.target_length || 1800),
        status: String(chapter.status || "planned") as StoryCanvasChapter["status"],
        emotion_curve: String(chapter.emotion_curve || ""),
        scene_ids: stringArray(chapter.scene_ids),
        event_pool_score: Number(chapter.event_pool_score || 0),
        event_pool_reasons: stringArray(chapter.event_pool_reasons),
        event_pool_penalties: stringArray(chapter.event_pool_penalties),
        event_contract: chapter.event_contract && typeof chapter.event_contract === "object"
          ? chapter.event_contract as Record<string, unknown>
          : undefined,
        event_sync: chapter.event_sync && typeof chapter.event_sync === "object"
          ? chapter.event_sync as Record<string, unknown>
          : undefined,
        chapter_drive: String(chapter.chapter_drive || ""),
        progression_role: String(chapter.progression_role || ""),
        promise_targets: stringArray(chapter.promise_targets),
        completed_summary: String(chapter.completed_summary || ""),
        actual_word_count: Number(chapter.actual_word_count || 0),
        completed_at: String(chapter.completed_at || "")
      };
    }),
    scenes: scenes.map((item, index) => {
      const scene = item as Record<string, unknown>;
      return {
        id: String(scene.id || `scene_${index + 1}`),
        chapter_id: String(scene.chapter_id || ""),
        scene_order: Number(scene.scene_order || index + 1),
        current_scene: String(scene.current_scene || ""),
        pov: String(scene.pov || ""),
        present_characters: String(scene.present_characters || ""),
        surface_event: String(scene.surface_event || ""),
        character_desire: String(scene.character_desire || ""),
        tension: String(scene.tension || ""),
        required_facts: stringArray(scene.required_facts),
        forbidden_progress: stringArray(scene.forbidden_progress),
        ending_beat: String(scene.ending_beat || ""),
        linked_material_ids: stringArray(scene.linked_material_ids)
      };
    }),
    threads: threads.map((item, index) => {
      const thread = item as Record<string, unknown>;
      return {
        id: String(thread.id || `thread_${index + 1}`),
        kind: String(thread.kind || "foreshadowing"),
        label: String(thread.label || ""),
        setup_chapter_id: String(thread.setup_chapter_id || ""),
        payoff_chapter_id: String(thread.payoff_chapter_id || ""),
        status: String(thread.status || "seed"),
        notes: String(thread.notes || "")
      };
    }),
    quality_rules: stringArray(raw.quality_rules),
    diagnostics: (raw.diagnostics && typeof raw.diagnostics === "object" ? raw.diagnostics : {}) as Record<string, unknown>
  };
}

export function normalizeSceneCardDraft(sceneCard: Record<string, unknown> | null | undefined): ChapterSceneCardDraft {
  const draft: ChapterSceneCardDraft = {};
  for (const field of sceneCardFields) {
    const value = sceneCard?.[field.key];
    draft[field.key] = Array.isArray(value)
      ? value.map((item) => String(item).trim()).filter(Boolean).join("；")
      : String(value || "").trim();
  }
  return draft;
}

export function derivedSceneCardFromCanvasChapter(chapter: StoryCanvasChapter | null | undefined): ChapterSceneCardDraft {
  if (!chapter) return {};
  const contract = chapter.event_contract && typeof chapter.event_contract === "object"
    ? chapter.event_contract as Record<string, unknown>
    : null;
  const contractPlace = String(contract?.place || "").trim();
  const contractTime = String(contract?.time_anchor || "").trim();
  const contractEvent = String(contract?.external_event || "").trim();
  const contractHook = String(contract?.hook || "").trim();
  return {
    current_scene: [contractTime, contractPlace].filter(Boolean).join("，"),
    surface_event: contractEvent || chapter.trigger_event || chapter.external_event || chapter.goal || "",
    tension: chapter.obstacle_escalation || "",
    ending_beat: contractHook || chapter.ending_hook || ""
  };
}

export function sceneCardWithPlanningDefaults(base: ChapterSceneCardDraft, defaults: ChapterSceneCardDraft): ChapterSceneCardDraft {
  const next = { ...base };
  for (const [key, value] of Object.entries(defaults)) {
    if (String(value || "").trim() && !String(next[key] || "").trim()) {
      next[key] = value;
    }
  }
  return next;
}

export function sceneCardDraftFromCanvas(
  scene: Record<string, unknown> | null | undefined,
  chapter: StoryCanvasChapter | null | undefined
): ChapterSceneCardDraft {
  return sceneCardWithPlanningDefaults(normalizeSceneCardDraft(scene), derivedSceneCardFromCanvasChapter(chapter));
}

export function canvasChapterForOrder(canvas: StoryCanvas, order: number): StoryCanvasChapter | null {
  return canvas.chapters.find((chapter) => chapter.chapter_order === order) || canvas.chapters[0] || null;
}

export function canvasScenesForChapter(canvas: StoryCanvas, chapter: StoryCanvasChapter | null): StoryCanvasScene[] {
  const chapterId = chapter?.id || "";
  return canvas.scenes.filter((scene) => scene.chapter_id === chapterId);
}

export function canvasFieldText(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean).join("；") || "未设定";
  return String(value || "").trim() || "未设定";
}

function splitSceneDraftList(value: string): string[] {
  return value
    .split(/[；;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function storyCanvasWithChapterDraft(
  canvas: StoryCanvas,
  chapter: NovelChapter | null,
  draft: {
    title: string;
    goal: string;
    status: NovelChapterStatus;
    scene_card: ChapterSceneCardDraft;
  },
  options: { targetLength: number; fallbackChapter?: StoryCanvasChapter | null }
): StoryCanvas {
  const nextCanvas = normalizeStoryCanvas(JSON.parse(JSON.stringify(canvas)) as StoryCanvas);
  const order = chapter?.chapter_order || options.fallbackChapter?.chapter_order || 1;
  let canvasChapter = canvasChapterForOrder(nextCanvas, order);

  if (!canvasChapter) {
    canvasChapter = {
      id: `canvas_ch_${order}`,
      act_id: nextCanvas.acts[0]?.id || "act_1",
      chapter_order: order,
      title: draft.title || `第${order}章`,
      goal: draft.goal,
      external_event: "",
      trigger_event: "",
      immediate_reaction: "",
      obstacle_escalation: "",
      counterpart_reaction: "",
      character_choice: "",
      scene_consequence: "",
      relationship_shift: "",
      ending_hook: "",
      target_length: options.targetLength,
      status: draft.status,
      emotion_curve: "",
      scene_ids: [],
      event_contract: undefined,
      event_sync: undefined,
      chapter_drive: "",
      progression_role: "",
      promise_targets: []
    };
    nextCanvas.chapters.push(canvasChapter);
  }

  canvasChapter.title = draft.title || canvasChapter.title;
  canvasChapter.goal = draft.goal || canvasChapter.goal;
  canvasChapter.target_length = options.targetLength || canvasChapter.target_length;
  canvasChapter.status = draft.status;

  let scene = canvasScenesForChapter(nextCanvas, canvasChapter)[0];
  if (!scene) {
    scene = {
      id: `scene_${order}`,
      chapter_id: canvasChapter.id,
      scene_order: 1,
      current_scene: "",
      pov: "",
      present_characters: "",
      surface_event: "",
      character_desire: "",
      tension: "",
      required_facts: [],
      forbidden_progress: [],
      ending_beat: "",
      linked_material_ids: []
    };
    nextCanvas.scenes.push(scene);
    canvasChapter.scene_ids = [...new Set([...canvasChapter.scene_ids, scene.id])];
  }

  scene.current_scene = draft.scene_card.current_scene || scene.current_scene;
  scene.pov = draft.scene_card.pov || scene.pov;
  scene.present_characters = draft.scene_card.present_characters || scene.present_characters;
  scene.surface_event = draft.scene_card.surface_event || canvasChapter.trigger_event || canvasChapter.external_event || draft.goal || scene.surface_event;
  scene.character_desire = draft.scene_card.character_desire || scene.character_desire;
  scene.tension = draft.scene_card.tension || canvasChapter.obstacle_escalation || scene.tension;

  const requiredFacts = splitSceneDraftList(draft.scene_card.required_facts || "");
  const forbiddenProgress = splitSceneDraftList(draft.scene_card.forbidden_progress || "");
  scene.required_facts = requiredFacts.length ? requiredFacts : scene.required_facts;
  scene.forbidden_progress = forbiddenProgress.length ? forbiddenProgress : scene.forbidden_progress;
  scene.ending_beat = draft.scene_card.ending_beat || canvasChapter.ending_hook || scene.ending_beat;

  return nextCanvas;
}
