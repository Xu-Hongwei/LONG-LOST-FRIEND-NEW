import { request } from "../../lib/apiClient";
import type { CharacterCard } from "../../types";

export type CharacterWritePayload = Omit<CharacterCard, "id" | "origin" | "owner_visitor_id"> & {
  visitor_id: string;
};

export async function createCharacter(payload: CharacterWritePayload): Promise<CharacterCard> {
  return request("/api/characters", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateCharacter(characterId: string, payload: CharacterWritePayload): Promise<CharacterCard> {
  return request(`/api/characters/${characterId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteCharacter(characterId: string, visitorId: string): Promise<{ deleted: boolean }> {
  return request(`/api/characters/${characterId}?visitor_id=${encodeURIComponent(visitorId)}`, {
    method: "DELETE"
  });
}

export async function generateCharacterDraft(
  visitorId: string,
  prompt: string,
  template?: Partial<CharacterCard>
): Promise<{ character: Partial<CharacterCard>; diagnostics: Record<string, unknown> }> {
  return request("/api/characters/draft", {
    method: "POST",
    body: JSON.stringify({
      visitor_id: visitorId,
      prompt,
      template: template || null
    })
  });
}
