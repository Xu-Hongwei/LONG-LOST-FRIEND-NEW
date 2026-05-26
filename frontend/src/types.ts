export interface CharacterCard {
  id: string;
  name: string;
  archetype: string;
  tagline: string;
  gender?: string;
  setting_type?: CharacterSettingType;
  setting_notes?: string;
  bio: string;
  speech_style: string;
  likes: string[];
  dislikes: string[];
  boundaries: string[];
  relationship_pace: string;
  opening_line: string;
  personality?: string;
  scenario?: string;
  mes_example?: string;
  creator_notes?: string;
  system_prompt?: string;
  post_history_instructions?: string;
  interaction_policy?: {
    initiative_level?: number;
    action_density?: string;
    action_style?: string;
    comfort_style?: string;
    question_style?: string;
    memory_style?: string;
  };
  anti_patterns?: string[];
  story_seed_pool?: {
    places?: string[];
    event_seeds?: string[];
    hook_seeds?: string[];
    motifs?: string[];
    forbidden_defaults?: string[];
  };
  voice?: {
    sentence_rhythm?: string;
    openings?: string[];
    signature_moves?: string[];
    avoid?: string[];
    sample_lines?: string[];
  };
  visual?: {
    accent?: string;
    portrait_hint?: string;
  };
  origin?: "builtin" | "custom";
  owner_visitor_id?: string;
}

export type CharacterSettingType =
  | "campus"
  | "modern_daily"
  | "workplace"
  | "xianxia_wuxia"
  | "urban_fantasy"
  | "mystery"
  | "sci_fi"
  | "historical"
  | "fantasy_adventure"
  | "custom";

export interface MemoryItem {
  id: string;
  memory_type: string;
  memory_scope: "global" | "character" | "session";
  content: string;
  confidence: number;
  importance: number;
  source_message_id?: string | null;
  source_created_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContextSlot {
  key: string;
  content: string;
  role: string;
  priority: number;
  token_budget: number;
  included: boolean;
}

export interface MemoryPane {
  session_id: string;
  frozen: boolean;
  manual_note: string;
  summary: string;
  memories: MemoryItem[];
  last_recall: MemoryItem[];
  prompt_slots?: ContextSlot[];
  diagnostics?: Record<string, unknown>;
}

export interface MemoryPatch {
  memory_type?: string;
  memory_scope?: "global" | "character" | "session";
  content?: string;
  confidence?: number;
  importance?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export interface CharacterBehavior {
  pace: string;
  initiative: string;
  warmth: string;
  memory_use: string;
  avoid: string;
}

export interface CharacterState {
  mood: string;
  tone: string;
  distance: string;
  focus: string;
  energy: number;
  resonance: number;
  behavior: CharacterBehavior;
  last_shift: string;
  evidence: string;
  updated_at: string;
}

export interface CharacterBond {
  familiarity_stage: string;
  stage_code: "initial" | "familiar" | "trusted" | "close";
  condition_code: "steady" | "warming" | "guarded" | "strained" | "repairing";
  condition_settle_turns: number;
  relationship_condition: string;
  resonance_base: number;
  trust_level: number;
  closeness_level: number;
  boundary_safety: number;
  trust_notes: string;
  boundary_notes: string;
  interaction_preferences: string;
  milestones: string[];
  evidence: string;
  updated_at: string;
}

export interface SessionResponse {
  session_id: string;
  visitor_id: string;
  character_id: string;
  character: CharacterCard;
  character_state: CharacterState;
  character_bond: CharacterBond;
  messages: ChatMessage[];
  memory_pane: MemoryPane;
}

export interface ChatResponse {
  session_id: string;
  visitor_id: string;
  character_id: string;
  reply: string;
  message: ChatMessage;
  character_state: CharacterState;
  character_bond: CharacterBond;
  memory_pane: MemoryPane;
  prompt_slots: ContextSlot[];
  timings: Record<string, number>;
  diagnostics?: Record<string, unknown>;
}

export type NovelPerspective = "third_person" | "user_view" | "character_view" | "dual_view";
export type NovelForm = "daily_short" | "campus_romance" | "vignette" | "chapter_one" | "side_story";
export type NovelFidelity = "faithful" | "polished" | "literary";

export interface NovelGenerateRequest {
  message_limit: number;
  perspective: NovelPerspective;
  form: NovelForm;
  fidelity: NovelFidelity;
  atmosphere: string;
  target_length: number;
}

export interface NovelGenerateResponse {
  title: string;
  synopsis: string;
  body: string;
  used_memories: string[];
  source_message_count: number;
  diagnostics: Record<string, unknown>;
}

export type NovelMaterialSource = "message" | "memory" | "story" | "manual";
export type NovelMaterialCategory = "fact" | "foreshadowing" | "open_thread" | "relationship" | "boundary" | "inspiration";
export type NovelChapterStatus = "planned" | "drafting" | "draft" | "revised" | "locked" | "affected";
export type StoryCanvasChapterStatus = NovelChapterStatus | "not_started" | "in_progress" | "complete";

export interface NovelMaterial {
  id: string;
  source_type: NovelMaterialSource;
  source_id: string;
  category: NovelMaterialCategory;
  label: string;
  content: string;
  evidence_level: StoryEvidenceLevel;
  created_at: string;
}

export interface NovelVersion {
  id: string;
  chapter_id: string;
  version_type: string;
  title: string;
  body: string;
  summary: string;
  source: string;
  state_delta?: Record<string, unknown>;
  planning_snapshot?: Record<string, unknown>;
  created_at: string;
}

export interface NovelChapter {
  id: string;
  project_id: string;
  chapter_order: number;
  title: string;
  goal: string;
  summary: string;
  body: string;
  status: NovelChapterStatus;
  scene_card: Record<string, unknown>;
  source_material_ids: string[];
  created_at: string;
  updated_at: string;
  version_count?: number;
  versions?: NovelVersion[];
}

export interface StoryCanvasAct {
  id: string;
  order: number;
  title: string;
  purpose: string;
  chapter_ids: string[];
}

export interface StoryCanvasChapter {
  id: string;
  act_id: string;
  chapter_order: number;
  event_pool_id?: string;
  title: string;
  goal: string;
  external_event: string;
  trigger_event: string;
  immediate_reaction: string;
  obstacle_escalation: string;
  counterpart_reaction: string;
  character_choice: string;
  scene_consequence: string;
  relationship_shift: string;
  ending_hook: string;
  target_length: number;
  status: StoryCanvasChapterStatus;
  emotion_curve: string;
  scene_ids: string[];
  event_pool_score?: number;
  event_pool_reasons?: string[];
  event_pool_penalties?: string[];
  completed_summary?: string;
  actual_word_count?: number;
  completed_at?: string;
}

export interface StoryCanvasScene {
  id: string;
  chapter_id: string;
  scene_order: number;
  current_scene: string;
  pov: string;
  present_characters: string;
  surface_event: string;
  character_desire: string;
  tension: string;
  required_facts: string[];
  forbidden_progress: string[];
  ending_beat: string;
  linked_material_ids: string[];
}

export interface StoryCanvasThread {
  id: string;
  kind: string;
  label: string;
  setup_chapter_id: string;
  payoff_chapter_id: string;
  status: string;
  notes: string;
}

export interface StoryCanvasEvent {
  id: string;
  place: string;
  time_anchor?: string;
  event: string;
  hook: string;
  motifs: string[];
  use_mode?: "strict" | "guide" | "flavor" | "free" | string;
  status: "fresh" | "planned" | "used" | "mutated" | "retired" | string;
  source: string;
  used_chapter_ids: string[];
  bound_chapter_orders?: string[];
  bound_chapter_titles?: string[];
  used_summary?: string;
  tags?: Record<string, unknown>;
  source_reason?: string;
  selection_score?: number;
  selection_reasons?: string[];
  selection_penalties?: string[];
}

export interface StoryCanvasEventPool {
  version: number;
  target_active: number;
  setting_type: string;
  active: StoryCanvasEvent[];
  retired: StoryCanvasEvent[];
  updated_at?: string;
}

export interface StoryCanvas {
  version: number;
  mode: string;
  event_pool?: StoryCanvasEventPool;
  acts: StoryCanvasAct[];
  chapters: StoryCanvasChapter[];
  scenes: StoryCanvasScene[];
  threads: StoryCanvasThread[];
  quality_rules?: string[];
  diagnostics?: Record<string, unknown>;
}

export interface NovelProject {
  id: string;
  session_id: string;
  visitor_id: string;
  character_id: string;
  title: string;
  genre: string;
  tone: string;
  protagonist: string;
  worldview: string;
  relationship_setup: string;
  outline: string;
  story_bible: Record<string, string[]>;
  story_canvas: StoryCanvas;
  novel_state: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
  materials: NovelMaterial[];
  chapters: NovelChapter[];
}

export interface NovelProjectCreateRequest {
  title?: string;
  genre: string;
  tone: string;
  protagonist?: string;
  worldview?: string;
  relationship_setup?: string;
  outline?: string;
  story_canvas?: StoryCanvas;
}

export interface NovelProjectDraftGenerateRequest {
  prompt: string;
  current?: NovelProjectCreateRequest;
}

export interface NovelProjectDraftGenerateResponse {
  project: NovelProjectCreateRequest;
  diagnostics: Record<string, unknown>;
}

export interface NovelProjectUpdateRequest {
  title?: string;
  genre?: string;
  tone?: string;
  protagonist?: string;
  worldview?: string;
  relationship_setup?: string;
  outline?: string;
  story_bible?: Record<string, string[]>;
  story_canvas?: StoryCanvas;
}

export interface NovelChapterUpdateRequest {
  title?: string;
  goal?: string;
  summary?: string;
  body?: string;
  status?: NovelChapterStatus;
  scene_card?: Record<string, unknown>;
  source_material_ids?: string[];
}

export interface NovelChapterDraftSaveRequest {
  project?: NovelProjectUpdateRequest;
  chapter: NovelChapterUpdateRequest;
}

export interface NovelCanvasExtendRequest {
  from_chapter_order: number;
  count?: number;
  instruction?: string;
}

export interface StoryEventPoolEventWriteRequest {
  place: string;
  time_anchor?: string;
  event: string;
  hook: string;
  motifs?: string[];
  use_mode?: "strict" | "guide" | "flavor" | "free";
  source_reason?: string;
  tags?: Record<string, unknown>;
}

export interface StoryEventPoolBindingRequest {
  event_id?: string | null;
  use_mode?: "strict" | "guide" | "flavor" | "free" | null;
}

export interface NovelInstructionOptimizeRequest {
  chapter_id?: string | null;
  base_instruction: string;
  title?: string;
  goal?: string;
  summary?: string;
  body?: string;
  status?: NovelChapterStatus;
  scene_card?: Record<string, unknown>;
  canvas_chapter?: Record<string, unknown>;
  previous_handoff?: Record<string, unknown>;
  prior_novel_state?: Record<string, unknown>;
  quality_diagnosis?: Record<string, unknown>;
  target_length: number;
}

export interface NovelInstructionOptimizeResponse {
  instruction: string;
  source: "remote" | "fallback";
  diagnostics: Record<string, unknown>;
}

export interface NovelContinuityReport {
  project_id: string;
  chapter_id?: string | null;
  issues: { severity: "ok" | "warning" | "error"; label: string; detail: string }[];
  summary: string;
  diagnostics: Record<string, unknown>;
}

export type StoryKind = "motif" | "story_beat" | "open_thread" | "relationship_texture" | "boundary";
export type StoryEvidenceLevel = "explicit" | "inferred" | "weak";
export type StoryStatus = "active" | "seed" | "developed" | "archived";

export interface StoryItem {
  id: string;
  kind: StoryKind;
  label: string;
  content: string;
  evidence: string;
  evidence_level: StoryEvidenceLevel;
  status: StoryStatus;
  source_message_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface StoryPane {
  session_id: string;
  items: StoryItem[];
  diagnostics?: Record<string, unknown>;
}
