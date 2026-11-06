import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { computed, effectScope } from "vue";
import { useNovelProject } from "../src/features/novel/useNovelProject";
import { chapterDraftKey } from "../src/features/novel/chapterDraftStorage";

let values: Map<string, string>;
let scopes: ReturnType<typeof effectScope>[];
let failing: boolean;
let beforeUnload: (event: any) => void;
beforeEach(() => {
  values = new Map(); scopes = []; failing = false;
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    addEventListener(name: string, callback: any) { if (name === "beforeunload") beforeUnload = callback; }, removeEventListener() {},
    localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { if (failing) throw new Error("quota"); values.set(key, value); },
      removeItem: (key: string) => { values.delete(key); }
    }
  } });
});
afterEach(() => scopes.forEach(scope => scope.stop()));
const chapter = (id: string) => ({ id, title: id, goal: "goal", summary: "", body: `saved ${id}`,
  status: "draft", chapter_order: id === "a" ? 1 : 2, scene_card: { generation_instruction: "saved instruction" } });
function page(visitor = "v", session = "s", projectId = "p", serverBody = "saved a") {
  const scope = effectScope(); scopes.push(scope);
  const state = scope.run(() => useNovelProject(computed(() => null)))!;
  state.novelProjects.value = [{ id: projectId, visitor_id: visitor, session_id: session,
    title: "p", story_canvas: {}, chapters: [{ ...chapter("a"), body: serverBody }, chapter("b")] }] as any;
  state.activeNovelProjectId.value = projectId;
  const select = (id: string) => { state.activeNovelChapterId.value = id; state.syncChapterDraft(state.activeNovelChapter.value, true); };
  select("a");
  return { state, select, close: () => scope.stop(), key: chapterDraftKey(state.activeNovelProject.value, "a") };
}

test("closing immediately after editing restores every chapter field and instruction without saving to the server", () => {
  const first = page();
  first.state.chapterDraft.value = { title: "author title", goal: "author goal", summary: "author summary",
    body: "unsaved body", status: "revised", scene_card: { current_scene: "blue notebook" } };
  first.state.chapterInstruction.value = "author instruction";
  first.close();
  const next = page();
  assert.deepEqual(next.state.chapterDraft.value, first.state.chapterDraft.value);
  assert.equal(next.state.chapterInstruction.value, "author instruction");
  assert.equal(next.state.activeNovelChapter.value?.body, "saved a");
  assert.equal(next.state.chapterDraftDirty.value, true);
  assert.match(next.state.chapterDraftNotice.value, /已恢复/);
  assert.match(next.state.editorUpdatedLabel.value, /已暂存/);
});

test("empty body and instruction are deliberately restored", () => {
  const first = page(); first.state.chapterDraft.value.body = ""; first.state.chapterInstruction.value = "";
  const next = page();
  assert.equal(next.state.chapterDraft.value.body, ""); assert.equal(next.state.chapterInstruction.value, "");
});

test("multiple chapters survive a page restart independently", () => {
  const first = page(); first.state.chapterDraft.value.body = "draft A";
  first.select("b"); first.state.chapterDraft.value.body = "draft B"; first.close();
  const next = page(); assert.equal(next.state.chapterDraft.value.body, "draft A");
  next.select("b"); assert.equal(next.state.chapterDraft.value.body, "draft B");
});

test("visitor, session and project namespaces never recover another owner's draft", () => {
  const first = page(); first.state.chapterDraft.value.body = "private draft";
  for (const other of [page("other"), page("v", "other"), page("v", "s", "other")]) {
    assert.equal(other.state.chapterDraft.value.body, "saved a");
  }
  assert.equal(page().state.chapterDraft.value.body, "private draft");
});

test("a changed server chapter warns without overwriting it; discarding uses the server copy", () => {
  const first = page(); first.state.chapterDraft.value.body = "local text";
  const next = page("v", "s", "p", "new server text");
  assert.equal(next.state.chapterDraft.value.body, "local text");
  assert.equal(next.state.activeNovelChapter.value?.body, "new server text");
  assert.match(next.state.chapterDraftNotice.value, /已有变化/);
  next.state.chapterDraft.value.summary = "still editing";
  assert.match(page("v", "s", "p", "new server text").state.chapterDraftNotice.value, /已有变化/);
  next.state.discardActiveChapterDraft();
  assert.equal(next.state.chapterDraft.value.body, "new server text");
  assert.equal(values.has(next.key), false);
});

test("successful save clears only its chapter; failed save or no response retains recovery", () => {
  const first = page(); first.state.chapterDraft.value.body = "draft A";
  first.select("b"); first.state.chapterDraft.value.body = "draft B";
  first.select("a");
  assert.equal(page().state.chapterDraft.value.body, "draft A");
  first.state.markChapterDraftSaved();
  assert.equal(values.has(first.key), false);
  const next = page(); assert.equal(next.state.chapterDraft.value.body, "saved a");
  next.select("b"); assert.equal(next.state.chapterDraft.value.body, "draft B");
});

test("deleting chapters removes their persisted drafts, including chapters never opened this page", () => {
  const first = page(); first.state.chapterDraft.value.body = "draft A";
  first.select("b"); first.state.chapterDraft.value.body = "draft B";
  const next = page(); next.state.discardChapterDrafts(["a", "b"]);
  assert.equal(values.size, 0);
});

test("version restoration replaces the active draft and prevents its resurrection on reload", () => {
  const first = page(); first.state.chapterDraft.value.body = "old draft";
  first.state.syncChapterDraft({ ...chapter("a"), body: "restored version" } as any);
  assert.equal(first.state.chapterDraft.value.body, "restored version");
  assert.equal(values.size, 0);
  assert.equal(page("v", "s", "p", "restored version").state.chapterDraft.value.body, "restored version");
});

test("corrupt and unsupported records do not crash the editor or silently delete the original", () => {
  const key = page().key;
  for (const raw of ["{bad", JSON.stringify({ version: 99 }), JSON.stringify({ version: 1, draft: { body: 1 } })]) {
    values.set(key, raw);
    const next = page();
    assert.equal(next.state.chapterDraft.value.body, "saved a");
    assert.match(next.state.chapterDraftNotice.value, /无法读取/);
    assert.equal(values.get(key), raw);
  }
});

test("quota and disabled storage keep input editable and never claim a successful local backup", () => {
  const first = page(); failing = true; first.state.chapterDraft.value.body = "quota input";
  assert.equal(first.state.chapterDraft.value.body, "quota input");
  assert.match(first.state.chapterDraftNotice.value, /暂存失败/);
  assert.doesNotMatch(first.state.editorUpdatedLabel.value, /已暂存/);
  Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
  const next = page(); next.state.chapterDraft.value.body = "blocked input";
  assert.match(next.state.chapterDraftNotice.value, /不可用/);
  assert.equal(next.state.chapterDraft.value.body, "blocked input");
});

test("an older tab cannot overwrite or remove a newer tab's recovery record", () => {
  const older = page(), newer = page();
  newer.state.chapterDraft.value.body = "newer text";
  older.state.chapterDraft.value.body = "older text";
  assert.match(older.state.chapterDraftNotice.value, /另一页面/);
  older.state.markChapterDraftSaved();
  assert.equal(page().state.chapterDraft.value.body, "newer text");
});

test("reverting to the original fields clears an unnecessary recovery record", () => {
  const first = page(); first.state.chapterDraft.value.body = "temporary edit";
  first.state.chapterDraft.value.body = "saved a";
  assert.equal(first.state.chapterDraftDirty.value, false);
  assert.equal(values.size, 0);
});

test("switching chapters in an older tab does not rebase its draft onto another tab's newer backup", () => {
  const first = page(); first.state.chapterDraft.value.body = "old draft";
  first.select("b");
  const newer = page(); newer.state.chapterDraft.value.body = "newer draft";
  first.select("a");
  assert.equal(first.state.chapterDraft.value.body, "old draft");
  assert.match(first.state.chapterDraftNotice.value, /另一页面/);
  assert.doesNotMatch(first.state.editorUpdatedLabel.value, /已暂存/);
  first.state.chapterDraft.value.summary = "old tab continues";
  assert.equal(page().state.chapterDraft.value.body, "newer draft");
});

test("refresh is unobstructed after local backup but still warns for an unprotected chapter after switching", () => {
  const first = page(); first.state.chapterDraft.value.body = "backed up";
  let warned = false;
  beforeUnload({ preventDefault() { warned = true; } });
  assert.equal(warned, false);
  failing = true; first.state.chapterDraft.value.body = "quota failure";
  first.select("b");
  beforeUnload({ preventDefault() { warned = true; } });
  assert.equal(warned, true);
  first.select("a");
  assert.equal(first.state.chapterDraft.value.body, "quota failure");
  assert.match(first.state.chapterDraftNotice.value, /暂存失败/);
  assert.doesNotMatch(first.state.editorUpdatedLabel.value, /已暂存/);
  first.state.discardChapterDrafts(["a"]);
  warned = false; beforeUnload({ preventDefault() { warned = true; } });
  assert.equal(warned, false);
});
