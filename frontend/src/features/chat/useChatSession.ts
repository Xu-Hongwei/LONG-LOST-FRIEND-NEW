import { computed, nextTick, ref } from "vue";
import * as defaultApi from "./api";
import type { CharacterBond, CharacterCard, CharacterState, ChatMessage, ContextSlot, MemoryPane } from "../../types";

type ScrollPanel = { scrollToBottom: () => void | Promise<void> };
type ChatSessionOptions = {
  visitorKey: string;
  characterKey: string;
  onVisitorChanged?: (visitorId: string) => void;
  onSessionOpened?: (sessionId: string, isCurrent: () => boolean) => Promise<void>;
  onAfterUserMessage?: () => void | Promise<void>;
};

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function analysisNotice(pane: MemoryPane | null) {
  const status = String(pane?.diagnostics?.status || "");
  const notices: Record<string, string> = {
    queued: "回复已保存，记忆与关系正在后台整理。",
    running: "回复已保存，记忆与关系正在后台整理。",
    succeeded: "记忆与关系整理已完成。",
    partial: "回复已保存，部分记忆或关系整理失败，可在记忆面板查看详情。",
    failed: "回复已保存，后台整理失败，可在记忆面板查看详情。",
    skipped: "回复已保存，本轮未执行后台整理。"
  };
  return notices[status] || "";
}

export function useChatSession(options: ChatSessionOptions, api = defaultApi) {
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
  const needsReload = ref(false);
  const postprocessNotice = ref("");
  const memoryPane = ref<MemoryPane | null>(null);
  const promptSlots = ref<ContextSlot[]>([]);
  const characterState = ref<CharacterState | null>(null);
  const characterBond = ref<CharacterBond | null>(null);
  const drafts = new Map<string, string>();
  const uncertain = new Set<string>();
  const pending = new Set<string>();
  const sources = new Map<string, "remote" | "mock">();
  let draftOwner = "";
  let loadedOwner = "";
  let view = 0;
  let latestAnalysis = "";
  let characterRequest = 0;

  function characterStorageKey(id: string) { return `${options.characterKey}:${id || "anonymous"}`; }
  function conversationKey(visitor: string, character: string) { return JSON.stringify([visitor, character]); }
  const canSend = computed(() => Boolean(sessionId.value) && !needsReload.value &&
    loadedOwner === conversationKey(visitorId.value, selectedCharacterId.value));
  function currentView(token: number, visitor: string, character: string) {
    return view === token && visitorId.value === visitor && selectedCharacterId.value === character;
  }
  async function scrollChatToBottom() {
    await nextTick();
    await chatPanelRef.value?.scrollToBottom();
  }

  async function initializeChatSession() {
    const token = view;
    try {
      const resolved = await api.resolveVisitor(visitorId.value);
      if (view !== token) return;
      visitorId.value = resolved.visitor_id;
      localStorage.setItem(options.visitorKey, resolved.visitor_id);
      options.onVisitorChanged?.(resolved.visitor_id);
      const cards = await api.listCharacters(resolved.visitor_id);
      if (view !== token || visitorId.value !== resolved.visitor_id) return;
      characters.value = cards;
      const storedCharacterId = localStorage.getItem(characterStorageKey(resolved.visitor_id)) || "";
      selectedCharacterId.value = cards.some((character) => character.id === storedCharacterId) ? storedCharacterId : cards[0]?.id || "";
      if (selectedCharacterId.value) await openSession();
    } catch (err) {
      if (view === token) error.value = readableError(err);
    }
  }

  async function openSession() {
    if (draftOwner) drafts.set(draftOwner, draft.value);
    const targetVisitor = visitorId.value.trim();
    visitorId.value = targetVisitor;
    const targetCharacter = selectedCharacterId.value;
    const key = conversationKey(targetVisitor, targetCharacter);
    draftOwner = key;
    draft.value = drafts.get(key) || "";
    const token = ++view;
    const isCurrent = () => currentView(token, targetVisitor, targetCharacter);
    latestAnalysis = "";
    loadedOwner = "";
    sessionId.value = "";
    messages.value = [];
    memoryPane.value = null;
    promptSlots.value = [];
    characterState.value = null;
    characterBond.value = null;
    postprocessNotice.value = "";
    needsReload.value = uncertain.has(key);
    error.value = "";
    busy.value = false;
    if (!targetCharacter || !targetVisitor) return;
    busy.value = true;
    try {
      options.onVisitorChanged?.(targetVisitor);
      const session = await api.createSession(targetVisitor, targetCharacter);
      if (!isCurrent()) return;
      visitorId.value = session.visitor_id;
      localStorage.setItem(options.visitorKey, session.visitor_id);
      localStorage.setItem(characterStorageKey(session.visitor_id), targetCharacter);
      loadedOwner = key;
      sessionId.value = session.session_id;
      characterState.value = session.character_state;
      characterBond.value = session.character_bond;
      memoryPane.value = session.memory_pane;
      promptSlots.value = session.memory_pane.prompt_slots || [];
      messages.value = session.messages?.length
        ? session.messages.map((message) => ({ ...message, reply_source: sources.get(message.id) }))
        : [{ id: "opening", role: "assistant", content: session.character.opening_line }];
      if (!pending.has(key)) uncertain.delete(key);
      needsReload.value = pending.has(key);
      postprocessNotice.value = pending.has(key) ? "上一条消息仍在处理，请稍后重新加载会话核对。" : analysisNotice(session.memory_pane);
      try { await options.onSessionOpened?.(session.session_id, isCurrent); }
      catch { if (isCurrent()) postprocessNotice.value = "会话已打开，附加内容加载失败，可重新加载。"; }
      if (isCurrent()) await scrollChatToBottom();
    } catch (err) {
      if (isCurrent()) error.value = readableError(err);
    } finally {
      if (isCurrent()) busy.value = false;
    }
  }

  function selectCharacter(characterId: string) {
    selectedCharacterId.value = characterId;
    return openSession();
  }

  async function refreshCharacters(preferredCharacterId = selectedCharacterId.value) {
    const visitor = visitorId.value;
    const token = ++characterRequest;
    const selected = selectedCharacterId.value;
    if (!visitor) return;
    const cards = await api.listCharacters(visitor);
    if (visitorId.value !== visitor || token !== characterRequest) return;
    characters.value = cards;
    if (selectedCharacterId.value !== selected) return;
    if (preferredCharacterId && cards.some((character) => character.id === preferredCharacterId)) selectedCharacterId.value = preferredCharacterId;
    else if (!cards.some((character) => character.id === selected)) selectedCharacterId.value = cards[0]?.id || "";
    if (selectedCharacterId.value !== selected || (sessionId.value && loadedOwner !== conversationKey(visitor, selectedCharacterId.value))) await openSession();
  }

  async function submit() {
    const text = draft.value.trim();
    if (!text || !canSend.value || busy.value) return;
    const token = view;
    const targetVisitor = visitorId.value;
    const targetCharacter = selectedCharacterId.value;
    const targetSession = sessionId.value;
    const key = conversationKey(targetVisitor, targetCharacter);
    const isCurrent = () => currentView(token, targetVisitor, targetCharacter) && sessionId.value === targetSession;
    const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: text, delivery: "sending" };
    messages.value.push(optimistic);
    draft.value = "";
    drafts.set(key, "");
    pending.add(key);
    busy.value = true;
    error.value = "";
    latestAnalysis = "";
    postprocessNotice.value = "";
    try {
      const response = await api.sendMessage(targetVisitor, targetSession, text);
      const source = response.diagnostics?.reply_source;
      if (source === "remote" || source === "mock") sources.set(response.message.id, source);
      if (!isCurrent()) return;
      const postprocess = response.diagnostics?.postprocess as Record<string, unknown> | undefined;
      const userMessageId = String(postprocess?.user_message_id || "");
      messages.value = messages.value.map((item) => item.id === optimistic.id ? { ...item, id: userMessageId || item.id, delivery: "saved" } : item);
      messages.value.push({ ...response.message, reply_source: sources.get(response.message.id) });
      characterState.value = response.character_state;
      characterBond.value = response.character_bond;
      memoryPane.value = response.memory_pane;
      promptSlots.value = response.prompt_slots;
      latestAnalysis = userMessageId;
      postprocessNotice.value = userMessageId ? "回复已保存，记忆与关系正在后台整理。" : "";
      void refreshMemoryPaneAfterPostprocess(targetSession, userMessageId, isCurrent);
      void Promise.resolve().then(() => { if (isCurrent()) return options.onAfterUserMessage?.(); }).catch(() => {
        if (isCurrent()) postprocessNotice.value = "回复已保存，故事素材刷新失败，可稍后手动刷新。";
      });
      await scrollChatToBottom();
    } catch (err) {
      uncertain.add(key);
      if (!drafts.get(key)) drafts.set(key, text);
      if (!isCurrent()) return;
      messages.value = messages.value.map((item) => item.id === optimistic.id ? { ...item, delivery: "unknown" } : item);
      if (!draft.value) draft.value = text;
      needsReload.value = true;
      error.value = `${readableError(err)} 输入已保留。服务端可能已经保存，请先重新加载会话核对，再决定是否重发。`;
    } finally {
      pending.delete(key);
      if (isCurrent()) busy.value = false;
    }
  }

  async function refreshMemoryPaneAfterPostprocess(targetSessionId: string, userMessageId: string, isCurrent: () => boolean) {
    if (!userMessageId) return;
    try {
      const pane = await api.waitForMemoryPostprocess(targetSessionId, userMessageId, 60);
      if (!isCurrent() || latestAnalysis !== userMessageId) return;
      if (String(pane.diagnostics?.user_message_id || "") !== userMessageId) {
        postprocessNotice.value = "后台结果尚未确认，可稍后重新加载会话查看。";
        return;
      }
      memoryPane.value = pane;
      promptSlots.value = pane.prompt_slots || [];
      const status = String(pane.diagnostics?.status || "");
      postprocessNotice.value = ["queued", "running"].includes(status)
        ? "后台仍在处理，可继续聊天或稍后重新加载查看。" : analysisNotice(pane);
    } catch {
      if (isCurrent() && latestAnalysis === userMessageId) postprocessNotice.value = "回复已保存，暂时无法获取后台整理结果，可稍后重新加载查看。";
    }
  }

  async function exportDebugBundle() {
    if (!sessionId.value || busy.value) return;
    const targetSession = sessionId.value;
    const token = view;
    busy.value = true;
    error.value = "";
    try {
      const payload = await api.exportSession(targetSession);
      if (view !== token) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `campus-pulse-${targetSession}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (view === token) error.value = readableError(err);
    } finally {
      if (view === token) busy.value = false;
    }
  }

  return { visitorId, chatPanelRef, characters, selectedCharacterId, activeCharacter, sessionId, messages, draft,
    busy, error, needsReload, canSend, postprocessNotice, memoryPane, promptSlots, characterState, characterBond,
    initializeChatSession, openSession, selectCharacter, refreshCharacters, submit, exportDebugBundle };
}
