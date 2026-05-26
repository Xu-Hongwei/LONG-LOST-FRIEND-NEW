import { request } from "../../lib/apiClient";
import type {
  NovelCanvasExtendRequest,
  NovelChapterDraftSaveRequest,
  NovelChapterUpdateRequest,
  NovelContinuityReport,
  NovelGenerateRequest,
  NovelGenerateResponse,
  NovelInstructionOptimizeRequest,
  NovelInstructionOptimizeResponse,
  NovelProject,
  NovelProjectCreateRequest,
  NovelProjectDraftGenerateRequest,
  NovelProjectDraftGenerateResponse,
  NovelProjectUpdateRequest,
  NovelVersion,
  StoryEventPoolBindingRequest,
  StoryEventPoolEventWriteRequest
} from "../../types";

export async function generateNovel(sessionId: string, payload: NovelGenerateRequest): Promise<NovelGenerateResponse> {
  return request(`/api/sessions/${sessionId}/novel/generate`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listNovelProjects(sessionId: string): Promise<NovelProject[]> {
  return request(`/api/sessions/${sessionId}/novel/projects`);
}

export async function generateNovelProjectDraft(
  sessionId: string,
  payload: NovelProjectDraftGenerateRequest
): Promise<NovelProjectDraftGenerateResponse> {
  return request(`/api/sessions/${sessionId}/novel/project-draft`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
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

export async function deleteNovelProject(projectId: string): Promise<{ deleted: boolean }> {
  return request(`/api/novel/projects/${projectId}`, {
    method: "DELETE"
  });
}

export async function buildStoryCanvas(projectId: string): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/canvas/build`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function extendStoryCanvas(projectId: string, payload: NovelCanvasExtendRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/canvas/extend`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createStoryEventPoolEvent(projectId: string, payload: StoryEventPoolEventWriteRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/event-pool/events`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateStoryEventPoolEvent(projectId: string, eventId: string, payload: StoryEventPoolEventWriteRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/event-pool/events/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function retireStoryEventPoolEvent(projectId: string, eventId: string): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/event-pool/events/${eventId}/retire`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function deleteStoryEventPoolEvent(projectId: string, eventId: string): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/event-pool/events/${eventId}`, {
    method: "DELETE"
  });
}

export async function bindStoryEventPoolEvent(projectId: string, chapterId: string, payload: StoryEventPoolBindingRequest): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/chapters/${chapterId}/event-pool-binding`, {
    method: "POST",
    body: JSON.stringify(payload)
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

export async function saveNovelChapterDraft(chapterId: string, payload: NovelChapterDraftSaveRequest): Promise<NovelProject> {
  return request(`/api/novel/chapters/${chapterId}/draft`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deleteNovelChapter(chapterId: string): Promise<NovelProject> {
  return request(`/api/novel/chapters/${chapterId}`, {
    method: "DELETE"
  });
}

export async function generateProjectChapter(
  projectId: string,
  chapterId: string | null,
  instruction: string,
  targetLength: number
): Promise<NovelProject> {
  return request(`/api/novel/projects/${projectId}/generate-chapter`, {
    method: "POST",
    body: JSON.stringify({ chapter_id: chapterId, instruction, target_length: targetLength, defer_postprocess: true })
  });
}

export async function optimizeNovelInstruction(
  projectId: string,
  payload: NovelInstructionOptimizeRequest
): Promise<NovelInstructionOptimizeResponse> {
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
