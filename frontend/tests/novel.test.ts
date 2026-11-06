import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { computed, effectScope, ref } from "vue";
import { useNovelProjectActions } from "../src/features/novel/useNovelProjectActions";

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
function deferred() {
  let resolve!: (value: any) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<any>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const project = (id: string, body = id, status = "") => ({ id, title: id, story_canvas: {}, chapters: [{
  id: `${id}-1`, chapter_order: 1, title: id, goal: "", summary: "", body, status: "draft",
  source_material_ids: [], scene_card: status ? {
    postprocess: { status }, generation_progress: { run_id: `${id}-run`, stage: "handoff", percent: 88 }
  } : {}
}] });
let timers: { fn: () => void; ms: number }[];
let scopes: ReturnType<typeof effectScope>[];
let fetcher: (path: string, init: RequestInit) => Promise<Response>;
beforeEach(() => {
  timers = []; scopes = [];
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    setTimeout: (fn: () => void, ms: number) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: () => {}, confirm: () => true
  } });
  fetcher = async path => path.endsWith("/versions") ? response([]) : response(project("a"));
  globalThis.fetch = ((path: string, init: RequestInit) => fetcher(path, init)) as any;
});
afterEach(() => { scopes.forEach(scope => scope.stop()); });
const tick = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
async function fire(ms: number) {
  const index = timers.findIndex(item => item.ms === ms);
  assert.ok(index >= 0, `missing timer ${ms}`);
  timers.splice(index, 1)[0].fn();
  await tick();
}
function setup() {
  const options: any = {
    sessionId: ref("s"), activeCharacter: computed(() => ({ name: "test" })),
    novelStudioMode: ref("project"), novelFocusMode: ref(false), error: ref(""),
    novelProjects: ref([project("a"), project("b")]), activeNovelProjectId: ref("a"), activeNovelChapterId: ref("a-1"),
    novelProjectBusy: ref(false), projectDraft: ref({ title: "a", outline: "" }),
    chapterDraft: ref(clone(project("a").chapters[0])), chapterInstruction: ref("write"), projectChapterTargetLength: ref(1000),
    continuityReport: ref(null), chapterVersions: ref([]), storyCanvasDraft: ref({}), activeCanvasChapter: computed(() => null),
    isInitialCanvasRebuildLocked: computed(() => false), canvasBuildStage: ref("idle"),
    novelProgressStage: ref("idle"), novelProgressPercent: ref(0), novelProgressDetail: ref(""),
    rememberChapterInstruction: () => {}, clearReorderedChapterInstructionCache: () => {},
    beginCanvasBuildFlow: () => {}, finishCanvasBuildFlow: () => {}, clearCanvasBuildTimers: () => {},
    clearNovelProgressTimers: () => {}, chapterUsedLocalFallback: () => false,
    chapterPostprocessStatus: (chapter: any) => chapter?.scene_card?.postprocess?.status || "",
    chapterHasBackgroundPostprocess: (chapter: any) => chapter?.scene_card?.postprocess?.status === "pending"
  };
  options.activeNovelProject = computed(() => options.novelProjects.value.find((p: any) => p.id === options.activeNovelProjectId.value) || null);
  options.activeNovelChapter = computed(() => options.activeNovelProject.value?.chapters.find((c: any) => c.id === options.activeNovelChapterId.value) || null);
  options.syncChapterDraft = (c: any) => { options.chapterDraft.value = clone(c || {}); };
  options.syncProjectDraft = (p: any) => { options.projectDraft.value = { title: p?.title || "", outline: "" }; options.syncStoryCanvasDraft(p); };
  options.syncStoryCanvasDraft = (p: any) => { options.storyCanvasDraft.value = clone(p?.story_canvas || {}); };
  options.chapterDraftForApi = () => clone(options.chapterDraft.value);
  options.replaceNovelProject = (p: any) => {
    const index = options.novelProjects.value.findIndex((item: any) => item.id === p.id);
    if (index >= 0) options.novelProjects.value.splice(index, 1, p);
  };
  options.setNovelProgress = (stage: string, percent: number, detail = "") => {
    options.novelProgressStage.value = stage; options.novelProgressPercent.value = percent; options.novelProgressDetail.value = detail;
  };
  options.beginNovelProgress = () => options.setNovelProgress("drafting", 10);
  options.applyChapterGenerationProgress = (c: any) => {
    const progress = c?.scene_card?.generation_progress;
    if (progress) options.setNovelProgress(progress.stage, progress.percent);
  };
  const scope = effectScope(); scopes.push(scope);
  const actions = scope.run(() => useNovelProjectActions(options))!;
  return { options, actions, scope };
}

test("late save cannot change a different project or release its new operation", async () => {
  const a = deferred(), b = deferred();
  fetcher = async path => path.endsWith("/versions") ? response([]) : path.includes("a-1") ? a.promise : b.promise;
  const { options, actions } = setup();
  const first = actions.saveNovelChapter();
  actions.selectNovelProject("b");
  const second = actions.saveNovelChapter();
  a.resolve(response(project("a", "late a"))); await first;
  assert.equal(options.activeNovelProjectId.value, "b");
  assert.equal(options.chapterDraft.value.body, "b");
  assert.equal(options.novelProjectBusy.value, true);
  b.resolve(response(project("b"))); await second;
  assert.equal(options.novelProjectBusy.value, false);
});

test("leaving and returning to a chapter still invalidates the old restore", async () => {
  const pending = deferred();
  fetcher = async path => path.endsWith("/versions") ? response([]) : pending.promise;
  const { options, actions } = setup();
  const restore = actions.restoreVersion("version-old");
  actions.selectNovelProject("b"); actions.selectNovelProject("a");
  pending.resolve(response(project("a", "stale restore"))); await restore;
  assert.equal(options.chapterDraft.value.body, "a");
  assert.equal(options.activeNovelProject.value.chapters[0].body, "a");
});

test("save response preserves typing made while request was pending", async () => {
  const pending = deferred(); fetcher = async () => pending.promise;
  const { options, actions } = setup();
  const save = actions.saveNovelChapter();
  options.chapterDraft.value.body = "unsaved typing";
  pending.resolve(response(project("a", "saved earlier"))); await save;
  assert.equal(options.chapterDraft.value.body, "unsaved typing");
  assert.match(options.error.value, /保留当前输入/);
  assert.equal(options.novelProjectBusy.value, false);
});

test("switching during generation's initial save prevents follow-on generation", async () => {
  const pending = deferred(); let generateCalls = 0;
  fetcher = async path => {
    if (path.includes("generate-chapter")) generateCalls++;
    return path.endsWith("/versions") ? response([]) : pending.promise;
  };
  const { options, actions } = setup();
  const generate = actions.generateActiveChapter();
  actions.selectNovelProject("b");
  pending.resolve(response(project("a"))); await generate;
  assert.equal(generateCalls, 0);
  assert.equal(options.chapterDraft.value.body, "b");
});

test("generation response cannot overwrite typing during the model wait", async () => {
  const pending = deferred();
  fetcher = async path => path.includes("generate-chapter") ? pending.promise : response(project("a"));
  const { options, actions } = setup();
  const generate = actions.generateActiveChapter(); await tick();
  options.chapterDraft.value.body = "new input";
  pending.resolve(response(project("a", "model output", "pending"))); await generate;
  assert.equal(options.chapterDraft.value.body, "new input");
  assert.match(options.error.value, /保留当前输入/);
});

async function startBackground() {
  fetcher = async path => path.endsWith("/versions") ? response([])
    : path.includes("generate-chapter") ? response(project("a", "generated", "pending")) : response(project("a"));
  const context = setup(); await context.actions.generateActiveChapter();
  return context;
}

test("background response arriving after project switch has no UI effects", async () => {
  const { options, actions } = await startBackground();
  const pending = deferred(); fetcher = async path => path.endsWith("/versions") ? response([]) : pending.promise;
  await fire(5000); actions.selectNovelProject("b");
  pending.resolve(response(project("a", "late background", "done"))); await tick();
  assert.equal(options.chapterDraft.value.body, "b");
  assert.equal(options.projectDraft.value.title, "b");
  assert.equal(options.error.value, "");
});

test("background polling preserves unsaved chapter and project changes", async () => {
  const { options } = await startBackground();
  const pending = deferred(); fetcher = async () => pending.promise;
  await fire(5000);
  options.chapterDraft.value.body = "my edit"; options.projectDraft.value.title = "my title";
  pending.resolve(response(project("a", "background output", "done"))); await tick();
  assert.equal(options.chapterDraft.value.body, "my edit");
  assert.equal(options.projectDraft.value.title, "my title");
  assert.equal(options.novelProgressStage.value, "superseded");
});

test("restoring a version invalidates an already pending background refresh", async () => {
  const { options, actions } = await startBackground();
  const pending = deferred();
  fetcher = async path => path.endsWith("/versions") ? response([])
    : path.endsWith("/restore") ? response(project("a", "restored")) : pending.promise;
  await fire(5000); await actions.restoreVersion("old");
  pending.resolve(response(project("a", "stale generated", "done"))); await tick();
  assert.equal(options.chapterDraft.value.body, "restored");
  assert.equal(options.activeNovelProject.value.chapters[0].body, "restored");
});

test("an unchanged draft accepts background completion", async () => {
  const { options } = await startBackground();
  fetcher = async path => path.endsWith("/versions") ? response([]) : response(project("a", "completed", "done"));
  await fire(5000); await tick();
  assert.equal(options.chapterDraft.value.body, "completed");
  assert.equal(options.novelProgressStage.value, "done");
});

test("late failures after session change do not display errors in the new view", async () => {
  const pending = deferred(); fetcher = async () => pending.promise;
  const { options, actions } = setup();
  const restore = actions.restoreVersion("old"); options.sessionId.value = "other-session";
  pending.reject(new Error("old request failed")); await restore;
  assert.equal(options.error.value, ""); assert.equal(options.novelProjectBusy.value, false);
});

test("late live progress cannot regress a completed generation", async () => {
  const generated = deferred(), progress = deferred();
  fetcher = async path => path.endsWith("/versions") ? response([])
    : path.includes("generate-chapter") ? generated.promise
    : path.endsWith("/draft") ? response(project("a")) : progress.promise;
  const { options, actions } = setup();
  const generate = actions.generateActiveChapter(); await tick(); await fire(1200);
  generated.resolve(response(project("a", "completed", "done"))); await generate;
  progress.resolve(response(project("a", "old progress", "pending"))); await tick();
  assert.equal(options.novelProgressStage.value, "done");
  assert.equal(options.activeNovelProject.value.chapters[0].body, "completed");
});

test("background refresh cannot adopt another server run", async () => {
  const { options } = await startBackground();
  const newer: any = project("a", "another run", "done");
  newer.chapters[0].scene_card.generation_progress.run_id = "new-run";
  fetcher = async () => response(newer);
  await fire(5000);
  assert.equal(options.chapterDraft.value.body, "generated");
  assert.equal(options.novelProgressStage.value, "superseded");
});

test("unmounting invalidates an in-flight background response", async () => {
  const { options, scope } = await startBackground();
  const pending = deferred(); fetcher = async () => pending.promise;
  await fire(5000); scope.stop();
  pending.resolve(response(project("a", "late completion", "done"))); await tick();
  assert.equal(options.chapterDraft.value.body, "generated");
  assert.equal(options.novelProgressStage.value, "idle");
});

test("restoration refreshes the canvas draft without discarding project title edits", async () => {
  const restored = { ...project("a", "restored"), story_canvas: { marker: "restored canvas" } };
  fetcher = async path => path.endsWith("/versions") ? response([]) : response(restored);
  const { options, actions } = setup(); options.projectDraft.value.title = "unsaved project title";
  await actions.restoreVersion("old");
  assert.equal(options.storyCanvasDraft.value.marker, "restored canvas");
  assert.equal(options.projectDraft.value.title, "unsaved project title");
});
