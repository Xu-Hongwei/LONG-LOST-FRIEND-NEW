import { request } from "../../lib/apiClient";
import type { MemoryPane, MemoryPatch } from "../../types";

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
