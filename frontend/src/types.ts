export interface CharacterCard {
  id: string;
  name: string;
  archetype: string;
  tagline: string;
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
}

export interface MemoryItem {
  id: string;
  memory_type: string;
  memory_scope: "global" | "character" | "session";
  content: string;
  confidence: number;
  importance: number;
  source_message_id?: string | null;
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
  resonance_base: number;
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
}
