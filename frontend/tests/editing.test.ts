import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { computed, effectScope, ref } from "vue";
import { useNovelProject } from "../src/features/novel/useNovelProject";
import { useNovelInstruction } from "../src/features/novel/useNovelInstruction";
import { useShortNovel } from "../src/features/novel/useShortNovel";
import { useCharacterWorkshop } from "../src/features/characters/useCharacterWorkshop";
import { useRelationshipMemory } from "../src/features/relationship/useRelationshipMemory";

const noop = () => {};
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
function deferred() {
  let resolve!: (value: Response) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Response>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
let scope: ReturnType<typeof effectScope>;
let unload: ((event: any) => void) | undefined;
beforeEach(() => {
  scope = effectScope(); unload = undefined;
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    addEventListener: (_: string, fn: any) => { unload = fn; }, removeEventListener: () => { unload = undefined; }
  } });
  globalThis.fetch = (async () => response({})) as any;
});
afterEach(() => scope.stop());
const chapter = (id: string, instruction = "") => ({ id, title: id, goal: "goal", summary: "", body: `saved ${id}`,
  status: "draft", chapter_order: id === "a" ? 1 : 2, scene_card: { generation_instruction: instruction } });
function novel() {
  const state = scope.run(() => useNovelProject(computed(() => null)))!;
  state.novelProjects.value = [{ id: "p", title: "p", story_canvas: {}, chapters: [chapter("a", "saved custom"), chapter("b")] }] as any;
  state.activeNovelProjectId.value = "p";
  const select = (id: string) => { state.activeNovelChapterId.value = id; state.syncChapterDraft(state.activeNovelChapter.value, true); };
  select("a");
  return { state, select };
}

test("chapter switches preserve body, scene and instruction drafts; closing warns until saved", () => {
  const { state, select } = novel();
  state.chapterDraft.value.body = "unsaved body";
  state.chapterDraft.value.scene_card.current_scene = "author scene";
  state.chapterInstruction.value = "unsaved instruction";
  select("b");
  let warned = false;
  unload!({ preventDefault: () => { warned = true; } });
  assert.equal(warned, true);
  select("a");
  assert.equal(state.chapterDraft.value.body, "unsaved body");
  assert.equal(state.chapterDraft.value.scene_card.current_scene, "author scene");
  assert.equal(state.chapterInstruction.value, "unsaved instruction");
  assert.match(state.editorUpdatedLabel.value, /未保存/);
  state.markChapterDraftSaved();
  warned = false; unload!({ preventDefault: () => { warned = true; } });
  assert.equal(warned, false);
});

test("saved instruction loads on a fresh page and explicit version restoration replaces the cache", () => {
  const { state } = novel();
  assert.equal(state.chapterInstruction.value, "saved custom");
  assert.equal(state.chapterDraftForApi().scene_card?.generation_instruction, "saved custom");
  state.chapterInstruction.value = "another local instruction";
  state.syncChapterDraft(chapter("a", "restored version instruction") as any);
  assert.equal(state.chapterInstruction.value, "restored version instruction");
  assert.doesNotMatch(state.editorUpdatedLabel.value, /未保存/);
});

test("selecting the same chapter preserves edits; explicit deletion removes its cached draft", () => {
  const { state, select } = novel();
  state.chapterDraft.value.body = "author edit";
  select("a");
  assert.equal(state.chapterDraft.value.body, "author edit");
  select("b");
  state.discardChapterDrafts(["a"]);
  let warned = false; unload!({ preventDefault: () => { warned = true; } });
  assert.equal(warned, false);
});

function optimizer(state: ReturnType<typeof useNovelProject>) {
  return scope.run(() => useNovelInstruction({ ...state, activeCanvasChapter: computed(() => null),
    novelStateLastHandoff: computed(() => null), novelStateSummary: computed(() => ""),
    novelStateOpenThreads: computed(() => []), activeNovelPriorStateEntries: computed(() => []) }));
}
test("late optimization cannot replace another chapter's instruction or unlock its request", async () => {
  const { state, select } = novel(); const action = optimizer(state)!;
  const a = deferred(), b = deferred(); let count = 0;
  globalThis.fetch = (async () => ++count === 1 ? a.promise : b.promise) as any;
  const first = action.applyOptimizedChapterInstruction();
  select("b");
  const second = action.applyOptimizedChapterInstruction();
  const secondDraft = state.chapterInstruction.value;
  a.resolve(response({ instruction: "old A", source: "remote" })); await first;
  assert.equal(state.chapterInstruction.value, secondDraft);
  assert.equal(state.isOptimizingInstruction.value, true);
  b.resolve(response({ instruction: "new B", source: "remote" })); await second;
  assert.equal(state.chapterInstruction.value, "new B");
});
test("optimization failure does not overwrite typing during the wait", async () => {
  const { state } = novel(); const action = optimizer(state)!;
  const pending = deferred(); globalThis.fetch = (async () => pending.promise) as any;
  const task = action.applyOptimizedChapterInstruction();
  state.chapterInstruction.value = "author edit";
  pending.reject(new Error("network")); await task;
  assert.equal(state.chapterInstruction.value, "author edit");
  assert.equal(state.isOptimizingInstruction.value, false);
  assert.match(state.instructionOptimizationNote.value, /保留/);
});

test("short story requests cannot cross sessions or release a newer request", async () => {
  const session = ref("a"), busy = ref(false), error = ref("");
  const short = scope.run(() => useShortNovel({ sessionId: session, busy, error, novelStudioMode: ref("quick"),
    beginNovelProgress: noop, clearNovelProgressTimers: noop, setNovelProgress: noop }))!;
  const a = deferred(), b = deferred(); let count = 0;
  globalThis.fetch = (async () => ++count === 1 ? a.promise : b.promise) as any;
  const first = short.generateNovelDraft(); session.value = "b";
  const second = short.generateNovelDraft();
  a.resolve(response({ title: "old A" })); await first;
  assert.equal(short.novelResult.value, null); assert.equal(busy.value, true);
  b.resolve(response({ title: "new B" })); await second;
  assert.equal(short.novelResult.value?.title, "new B"); assert.equal(busy.value, false);
  session.value = "a"; assert.equal(short.novelResult.value, null);
});
test("clearing a short story invalidates its pending result", async () => {
  const short = scope.run(() => useShortNovel({ sessionId: ref("a"), busy: ref(false), error: ref(""), novelStudioMode: ref("quick"),
    beginNovelProgress: noop, clearNovelProgressTimers: noop, setNovelProgress: noop }))!;
  const pending = deferred(); globalThis.fetch = (async () => pending.promise) as any;
  const task = short.generateNovelDraft(); short.clearNovelResult();
  pending.resolve(response({ title: "old" })); await task;
  assert.equal(short.novelResult.value, null);
});

test("late character expansion cannot overwrite a new selection or its busy state", async () => {
  const workshop = scope.run(() => useCharacterWorkshop(ref("v"), ref([])))!;
  const a = deferred(), b = deferred(); let count = 0;
  globalThis.fetch = (async () => ++count === 1 ? a.promise : b.promise) as any;
  workshop.editCharacter({ id: "a", name: "A" } as any); workshop.generationPrompt.value = "expand";
  const first = workshop.generateDraft();
  workshop.editCharacter({ id: "b", name: "B" } as any);
  const second = workshop.generateDraft();
  a.resolve(response({ character: { name: "old A" } })); await first;
  assert.equal(workshop.draft.name, "B"); assert.equal(workshop.editingCharacterId.value, "b");
  assert.equal(workshop.busy.value, true);
  b.resolve(response({ character: { name: "new B" } })); await second;
  assert.equal(workshop.draft.name, "new B"); assert.equal(workshop.busy.value, false);
});
test("changing visitor invalidates a pending character save", async () => {
  const visitor = ref("a");
  const workshop = scope.run(() => useCharacterWorkshop(visitor, ref([])))!;
  const pending = deferred(); globalThis.fetch = (async () => pending.promise) as any;
  workshop.draft.name = "A"; const task = workshop.save();
  visitor.value = "b";
  pending.resolve(response({ id: "old-a", name: "A" }));
  assert.equal(await task, null); assert.equal(workshop.editingCharacterId.value, "");
});

test("memory refresh preserves unsaved notes and accepted saves resume clean updates", async () => {
  const pane = ref<any>({ manual_note: "saved", memories: [] });
  const memory = scope.run(() => useRelationshipMemory(ref("s"), pane, ref([]), ref(false), ref(""), {
    patchMemory: async () => ({ manual_note: "typed", memories: [] })
  } as any))!;
  memory.manualNoteDraft.value = "typed";
  pane.value = { ...pane.value, diagnostics: { status: "succeeded" } };
  assert.equal(memory.manualNoteDraft.value, "typed");
  await memory.saveMemoryNote();
  pane.value = { manual_note: "new saved value", memories: [] };
  assert.equal(memory.manualNoteDraft.value, "new saved value");
});
test("an intentionally emptied note survives session switching and a later pane load", () => {
  const session = ref("a"), pane = ref<any>({ manual_note: "original A", memories: [] });
  const memory = scope.run(() => useRelationshipMemory(session, pane, ref([]), ref(false), ref("")))!;
  memory.manualNoteDraft.value = "";
  session.value = "b"; pane.value = { manual_note: "saved B", memories: [] };
  assert.equal(memory.manualNoteDraft.value, "saved B");
  session.value = "a"; pane.value = { manual_note: "original A", memories: [] };
  assert.equal(memory.manualNoteDraft.value, "");
});
