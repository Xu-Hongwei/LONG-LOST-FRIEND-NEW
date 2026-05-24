import { computed, nextTick, ref } from "vue";
import {
  createSession,
  exportSession,
  listCharacters,
  resolveVisitor,
  sendMessage,
  waitForMemoryPostprocess
} from "./api";
import type {
  CharacterBond,
  CharacterCard,
  CharacterState,
  ChatMessage,
  ContextSlot,
  MemoryPane
} from "../../types";

type ScrollPanel = { scrollToBottom: () => void | Promise<void> };

type ChatSessionOptions = {
  visitorKey: string;
  characterKey: string;
  onVisitorChanged?: (visitorId: string) => void;
  onSessionOpened?: (sessionId: string) => Promise<void>;
  onAfterUserMessage?: () => void | Promise<void>;
};

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

export function useChatSession(options: ChatSessionOptions) {
  const visitorId = ref(localStorage.getItem(options.visitorKey) || "");
  const chatPanelRef = ref<ScrollPanel | null>(null);
  const characters = ref<CharacterCard[]>([]);
  const selectedCharacterId = ref("");
  const activeCharacter = computed(() => characters.value.find((item) => item.id === selectedCharacterId.value) || null);
  const sessionId = ref("");
  const messages = ref<ChatMessage[]>([]);
  const draft = ref("");
  const busy = ref(false);
  const error = ref("");
  const memoryPane = ref<MemoryPane | null>(null);
  const promptSlots = ref<ContextSlot[]>([]);
  const characterState = ref<CharacterState | null>(null);
  const characterBond = ref<CharacterBond | null>(null);

  function characterStorageKey(id: string) {
    return `${options.characterKey}:${id || "anonymous"}`;
  }

  async function scrollChatToBottom() {
    await nextTick();
    await chatPanelRef.value?.scrollToBottom();
  }

  async function initializeChatSession() {
    try {
      const resolved = await resolveVisitor(visitorId.value);
      visitorId.value = resolved.visitor_id;
      localStorage.setItem(options.visitorKey, resolved.visitor_id);
      options.onVisitorChanged?.(resolved.visitor_id);
      characters.value = await listCharacters(resolved.visitor_id);
      const storedCharacterId = localStorage.getItem(characterStorageKey(resolved.visitor_id)) || "";
      selectedCharacterId.value = characters.value.some((character) => character.id === storedCharacterId)
        ? storedCharacterId
        : characters.value[0]?.id || "";
      if (selectedCharacterId.value) {
        await openSession();
      }
    } catch (err) {
      error.value = readableError(err);
    }
  }

  async function openSession() {
    if (!selectedCharacterId.value || !visitorId.value) return;
    busy.value = true;
    error.value = "";
    try {
      options.onVisitorChanged?.(visitorId.value);
      localStorage.setItem(characterStorageKey(visitorId.value), selectedCharacterId.value);
      const session = await createSession(visitorId.value, selectedCharacterId.value);
      visitorId.value = session.visitor_id;
      localStorage.setItem(options.visitorKey, session.visitor_id);
      localStorage.setItem(characterStorageKey(session.visitor_id), selectedCharacterId.value);
      sessionId.value = session.session_id;
      characterState.value = session.character_state;
      characterBond.value = session.character_bond;
      memoryPane.value = session.memory_pane;
      promptSlots.value = session.memory_pane.prompt_slots || [];
      messages.value = session.messages?.length
        ? session.messages
        : [{ id: "opening", role: "assistant", content: session.character.opening_line }];
      await options.onSessionOpened?.(session.session_id);
      await scrollChatToBottom();
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  function selectCharacter(characterId: string) {
    selectedCharacterId.value = characterId;
    if (visitorId.value) {
      localStorage.setItem(characterStorageKey(visitorId.value), characterId);
    }
    void openSession();
  }

  async function refreshCharacters(preferredCharacterId = selectedCharacterId.value) {
    if (!visitorId.value) return;
    characters.value = await listCharacters(visitorId.value);
    if (preferredCharacterId && characters.value.some((character) => character.id === preferredCharacterId)) {
      selectedCharacterId.value = preferredCharacterId;
      return;
    }
    if (!characters.value.some((character) => character.id === selectedCharacterId.value)) {
      selectedCharacterId.value = characters.value[0]?.id || "";
    }
  }

  async function submit() {
    const text = draft.value.trim();
    if (!text || !sessionId.value || busy.value) return;
    const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: text };
    messages.value.push(optimistic);
    draft.value = "";
    busy.value = true;
    error.value = "";

    await scrollChatToBottom();

    try {
      const response = await sendMessage(visitorId.value, sessionId.value, text);
      messages.value.push(response.message);
      characterState.value = response.character_state;
      characterBond.value = response.character_bond;
      memoryPane.value = response.memory_pane;
      promptSlots.value = response.prompt_slots;
      const postprocess = response.diagnostics?.postprocess;
      const userMessageId = postprocess && typeof postprocess === "object"
        ? String((postprocess as Record<string, unknown>).user_message_id || "")
        : "";
      void refreshMemoryPaneAfterPostprocess(sessionId.value, userMessageId);
      void options.onAfterUserMessage?.();

      await scrollChatToBottom();
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  async function refreshMemoryPaneAfterPostprocess(targetSessionId: string, userMessageId: string) {
    if (!userMessageId) return;
    try {
      const pane = await waitForMemoryPostprocess(targetSessionId, userMessageId, 60);
      if (sessionId.value !== targetSessionId) return;
      memoryPane.value = pane;
      promptSlots.value = pane.prompt_slots || [];
    } catch (err) {
      console.warn("memory diagnostics wait failed", err);
    }
  }

  async function exportDebugBundle() {
    if (!sessionId.value) return;
    busy.value = true;
    error.value = "";
    try {
      const payload = await exportSession(sessionId.value);
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `campus-pulse-${sessionId.value}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      error.value = readableError(err);
    } finally {
      busy.value = false;
    }
  }

  return {
    visitorId,
    chatPanelRef,
    characters,
    selectedCharacterId,
    activeCharacter,
    sessionId,
    messages,
    draft,
    busy,
    error,
    memoryPane,
    promptSlots,
    characterState,
    characterBond,
    initializeChatSession,
    openSession,
    selectCharacter,
    refreshCharacters,
    submit,
    exportDebugBundle
  };
}
