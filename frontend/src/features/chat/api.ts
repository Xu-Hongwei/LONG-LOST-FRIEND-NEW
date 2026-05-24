import { request } from "../../lib/apiClient";
import type {
  CharacterCard,
  ChatResponse,
  MemoryPane,
  MemoryPatch,
  SessionResponse,
  StoryPane
} from "../../types";

export async function resolveVisitor(visitorId?: string): Promise<{ visitor_id: string; created: boolean }> {
  return request("/api/visitors/resolve", {
    method: "POST",
    body: JSON.stringify({ visitor_id: visitorId || null })
  });
}

export async function listCharacters(visitorId = ""): Promise<CharacterCard[]> {
  const query = visitorId ? `?visitor_id=${encodeURIComponent(visitorId)}` : "";
  return request(`/api/characters${query}`);
}

export async function createSession(visitorId: string, characterId: string): Promise<SessionResponse> {
  return request("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ visitor_id: visitorId, character_id: characterId })
  });
}

export async function sendMessage(visitorId: string, sessionId: string, message: string): Promise<ChatResponse> {
  return request("/api/chat/send", {
    method: "POST",
    body: JSON.stringify({ visitor_id: visitorId, session_id: sessionId, message })
  });
}

export async function patchMemory(sessionId: string, patch: { frozen?: boolean; manual_note?: string }): Promise<MemoryPane> {
  return request(`/api/sessions/${sessionId}/memory`, {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export async function getMemoryPane(sessionId: string): Promise<MemoryPane> {
  return request(`/api/sessions/${sessionId}/memory`);
}

export async function waitForMemoryPostprocess(sessionId: string, userMessageId: string, timeoutSeconds = 45): Promise<MemoryPane> {
  const params = new URLSearchParams({
    user_message_id: userMessageId,
    timeout_seconds: String(timeoutSeconds)
  });
  return request(`/api/sessions/${sessionId}/memory/wait?${params.toString()}`);
}

export async function updateMemoryItem(sessionId: string, memoryId: string, patch: MemoryPatch): Promise<MemoryPane> {
  return request(`/api/sessions/${sessionId}/memory/items/${memoryId}`, {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export async function deleteMemoryItem(sessionId: string, memoryId: string): Promise<MemoryPane> {
  return request(`/api/sessions/${sessionId}/memory/items/${memoryId}`, {
    method: "DELETE"
  });
}

export async function exportSession(sessionId: string): Promise<Record<string, unknown>> {
  return request(`/api/sessions/${sessionId}/export`);
}

export async function getStoryPane(sessionId: string): Promise<StoryPane> {
  return request(`/api/sessions/${sessionId}/story`);
}

export async function refreshStoryPane(sessionId: string): Promise<StoryPane> {
  return request(`/api/sessions/${sessionId}/story/refresh`, {
    method: "POST",
    body: JSON.stringify({})
  });
}
