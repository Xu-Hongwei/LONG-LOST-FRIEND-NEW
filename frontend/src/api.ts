import type {
  CharacterCard,
  ChatResponse,
  MemoryPane,
  MemoryPatch,
  NovelChapterUpdateRequest,
  NovelContinuityReport,
  NovelGenerateRequest,
  NovelGenerateResponse,
  NovelInstructionOptimizeRequest,
  NovelInstructionOptimizeResponse,
  NovelProject,
  NovelProjectCreateRequest,
  NovelProjectUpdateRequest,
  NovelVersion,
  SessionResponse,
  StoryPane
} from "./types";

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

export async function generateNovel(sessionId: string, payload: NovelGenerateRequest): Promise<NovelGenerateResponse> {
  return request(`/api/sessions/${sessionId}/novel/generate`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listNovelProjects(sessionId: string): Promise<NovelProject[]> {
  return request(`/api/sessions/${sessionId}/novel/projects`);
}

export async function getNovelProject(projectId: string): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}`);
}

export async function createNovelProject(sessionId: string, payload: NovelProjectCreateRequest): Promise<NovelProject> {
  return request(`/api/sessions/${sessionId}/novel/projects`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateNovelProject(projectId: string, payload: NovelProjectUpdateRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function buildStoryCanvas(projectId: string): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/canvas/build`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function createNovelChapter(projectId: string, payload: NovelChapterUpdateRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/chapters`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateNovelChapter(chapterId: string, payload: NovelChapterUpdateRequest): Promise<NovelProject> {
  return request(`/api/novel/chapters/${chapterId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deleteNovelChapter(chapterId: string): Promise<NovelProject> {
  return request(`/api/novel/chapters/${chapterId}`, {
    method: "DELETE"
  });
}

export async function generateProjectChapter(projectId: string, chapterId: string | null, instruction: string, targetLength: number): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/generate-chapter`, {
    method: "POST",
    body: JSON.stringify({ chapter_id: chapterId, instruction, target_length: targetLength, defer_postprocess: true })
  });
}

export async function optimizeNovelInstruction(projectId: string, payload: NovelInstructionOptimizeRequest): Promise<NovelInstructionOptimizeResponse> {
  return request(`/api/novel/projects/${projectId}/optimize-instruction`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function checkNovelContinuity(projectId: string, chapterId: string | null): Promise<NovelContinuityReport> {
  return request(`/api/novel/projects/${projectId}/check`, {
    method: "POST",
    body: JSON.stringify({ chapter_id: chapterId, instruction: "检查连续性", target_length: 1200 })
  });
}

export async function listNovelVersions(chapterId: string): Promise<NovelVersion[]> {
  return request(`/api/novel/chapters/${chapterId}/versions`);
}

export async function restoreNovelVersion(versionId: string): Promise<NovelProject> {
  return request(`/api/novel/versions/${versionId}/restore`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function deleteNovelVersion(versionId: string): Promise<NovelProject> {
  return request(`/api/novel/versions/${versionId}`, {
    method: "DELETE"
  });
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
