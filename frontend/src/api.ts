import type { CharacterCard, ChatResponse, MemoryPane, MemoryPatch, SessionResponse } from "./types";

const API_BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function resolveVisitor(visitorId?: string): Promise<{ visitor_id: string; created: boolean }> {
  return request("/api/visitors/resolve", {
    method: "POST",
    body: JSON.stringify({ visitor_id: visitorId || null })
  });
}

export async function listCharacters(): Promise<CharacterCard[]> {
  return request("/api/characters");
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
