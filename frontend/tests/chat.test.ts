import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { ref } from "vue";
import { useChatSession } from "../src/features/chat/useChatSession";
import { useRelationshipMemory } from "../src/features/relationship/useRelationshipMemory";
import * as chatApi from "../src/features/chat/api";

function deferred<T = any>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const pane = (id = "", status = "succeeded") => ({ memories: [], manual_note: "", prompt_slots: [], diagnostics: { user_message_id: id, status } });
const session = (id: string) => ({ session_id: id, visitor_id: "v", character_id: id,
  character: { id, name: id, opening_line: "hello" }, character_state: {}, character_bond: {}, memory_pane: pane(),
  messages: [{ id: `opening-${id}`, role: "assistant", content: `hello-${id}` }] });
const reply = (id = "m1", source = "remote") => ({ message: { id: `reply-${id}`, role: "assistant", content: id },
  character_state: {}, character_bond: {}, memory_pane: pane(id, "queued"), prompt_slots: [],
  diagnostics: { reply_source: source, postprocess: { user_message_id: id } } });
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
beforeEach(() => {
  const data = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
    getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => data.set(key, value)
  } });
});
function setup(overrides = {}, options = {}) {
  const api = { ...chatApi, createSession: async (_v: string, character: string) => session(character),
    sendMessage: async () => reply(), waitForMemoryPostprocess: async (_s: string, id: string) => pane(id), ...overrides };
  const chat = useChatSession({ visitorKey: "visitor", characterKey: "character", ...options }, api as any);
  chat.visitorId.value = "v";
  return chat;
}

test("late session responses cannot overwrite a newer selection or release its busy state", async () => {
  const a = deferred(), b = deferred();
  const chat = setup({ createSession: (_v: string, c: string) => c === "a" ? a.promise : b.promise });
  const first = chat.selectCharacter("a");
  const second = chat.selectCharacter("b");
  a.resolve(session("a")); await first;
  assert.equal(chat.sessionId.value, ""); assert.equal(chat.busy.value, true);
  b.resolve(session("b")); await second;
  assert.equal(chat.sessionId.value, "b"); assert.equal(chat.messages.value[0].content, "hello-b");
});

test("opening a different session unsuccessfully cannot send to the previous session", async () => {
  let calls = 0;
  const chat = setup({ createSession: async (_v: string, c: string) => { if (c === "bad") throw new Error("failed"); return session(c); },
    sendMessage: async () => { calls++; return reply(); } });
  await chat.selectCharacter("a"); await chat.selectCharacter("bad");
  chat.draft.value = "text"; await chat.submit();
  assert.equal(chat.sessionId.value, ""); assert.equal(calls, 0);
});

test("changing visitor identity cannot send into the previously loaded session", async () => {
  let calls = 0;
  const chat = setup({ sendMessage: async () => { calls++; return reply(); } });
  await chat.selectCharacter("a"); chat.visitorId.value = "another-visitor";
  chat.draft.value = "private draft"; await chat.submit();
  assert.equal(chat.canSend.value, false); assert.equal(calls, 0);
});

test("refreshing characters after deletion loads the replacement session", async () => {
  const chat = setup({ listCharacters: async () => [session("b").character] });
  await chat.selectCharacter("a"); await chat.refreshCharacters();
  assert.equal(chat.sessionId.value, "b"); assert.equal(chat.selectedCharacterId.value, "b");
});

test("failed send retains input, marks uncertain delivery and blocks repeat until reload", async () => {
  let calls = 0;
  const chat = setup({ sendMessage: async () => { calls++; throw new Error("connection lost"); } });
  await chat.selectCharacter("a"); chat.draft.value = "keep me";
  await chat.submit(); await chat.submit();
  assert.equal(calls, 1); assert.equal(chat.draft.value, "keep me");
  assert.equal(chat.messages.value.at(-1)?.delivery, "unknown"); assert.equal(chat.needsReload.value, true);
  await chat.openSession(); assert.equal(chat.needsReload.value, false); assert.equal(chat.draft.value, "keep me");
});

test("late reply cannot appear under another character", async () => {
  const send = deferred();
  const chat = setup({ sendMessage: () => send.promise });
  await chat.selectCharacter("a"); chat.draft.value = "a text"; const sent = chat.submit();
  await chat.selectCharacter("b"); chat.draft.value = "b draft";
  send.resolve(reply()); await sent;
  assert.equal(chat.messages.value.length, 1); assert.equal(chat.draft.value, "b draft"); assert.equal(chat.busy.value, false);
});

test("late send failure preserves the original character draft", async () => {
  const send = deferred(); const chat = setup({ sendMessage: () => send.promise });
  await chat.selectCharacter("a"); chat.draft.value = "recover a"; const sent = chat.submit();
  await chat.selectCharacter("b"); chat.draft.value = "keep b";
  send.reject(new Error("lost")); await sent;
  assert.equal(chat.error.value, ""); await chat.selectCharacter("a"); assert.equal(chat.draft.value, "recover a");
  await chat.selectCharacter("b"); assert.equal(chat.draft.value, "keep b");
});

test("returning while a send is pending cannot resend until a later reload", async () => {
  const send = deferred(); const chat = setup({ sendMessage: () => send.promise });
  await chat.selectCharacter("a"); chat.draft.value = "pending"; const sent = chat.submit();
  await chat.selectCharacter("b"); await chat.selectCharacter("a");
  assert.equal(chat.needsReload.value, true);
  send.resolve(reply()); await sent;
  assert.equal(chat.needsReload.value, true);
  await chat.openSession(); assert.equal(chat.needsReload.value, false);
});

test("mock source remains visible after reloading in the same browser session", async () => {
  let sent = false;
  const chat = setup({ createSession: async () => ({ ...session("a"), messages: sent ? [reply("m1", "mock").message] : session("a").messages }),
    sendMessage: async () => { sent = true; return reply("m1", "mock"); } });
  await chat.selectCharacter("a"); chat.draft.value = "hi"; await chat.submit();
  assert.equal(chat.messages.value.at(-1)?.reply_source, "mock");
  await chat.openSession(); assert.equal(chat.messages.value[0].reply_source, "mock");
});

test("an older background result cannot overwrite the newest turn", async () => {
  const old = deferred(); let count = 0;
  const chat = setup({ sendMessage: async () => reply(`m${++count}`), waitForMemoryPostprocess: (_s: string, id: string) => id === "m1" ? old.promise : Promise.resolve(pane("m2", "partial")) });
  await chat.selectCharacter("a"); chat.draft.value = "one"; await chat.submit();
  chat.draft.value = "two"; await chat.submit(); await tick();
  old.resolve(pane("m1")); await tick();
  assert.equal(chat.memoryPane.value?.diagnostics?.user_message_id, "m2");
  assert.match(chat.postprocessNotice.value, /部分/);
});

test("background fetch failure does not mark a saved reply as an unsuccessful send", async () => {
  const chat = setup({ waitForMemoryPostprocess: async () => { throw new Error("timeout"); } });
  await chat.selectCharacter("a"); chat.draft.value = "hello"; await chat.submit(); await tick();
  assert.equal(chat.error.value, ""); assert.equal(chat.needsReload.value, false);
  assert.match(chat.postprocessNotice.value, /回复已保存/);
});

test("stale memory edits cannot replace another session's pane or busy state", async () => {
  const pending = deferred(); const id = ref("a"), memory = ref<any>(pane()), slots = ref<any[]>([]), busy = ref(false), error = ref("");
  const relationship = useRelationshipMemory(id, memory, slots, busy, error, { patchMemory: () => pending.promise } as any);
  relationship.manualNoteDraft.value = "old note"; const action = relationship.saveMemoryNote();
  id.value = "b"; memory.value = { ...pane(), manual_note: "new note" }; busy.value = true;
  pending.resolve({ ...pane(), manual_note: "old note" }); await action;
  assert.equal(memory.value.manual_note, "new note"); assert.equal(busy.value, true);
});
