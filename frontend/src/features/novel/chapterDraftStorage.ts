import type { NovelProject } from "../../types";
import type { ChapterDraft } from "./useNovelProject";

export type StoredChapterDraft = {
  version: 1;
  draft: ChapterDraft;
  instruction: string;
  serverSnapshot: string;
};

export function chapterDraftKey(project: NovelProject | null, chapterId: string): string {
  if (!project?.visitor_id || !project.session_id || !project.id || !chapterId) return "";
  return "campus.chapter-draft.v1:" + [project.visitor_id, project.session_id, project.id, chapterId]
    .map(encodeURIComponent).join(":");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validDraft(value: unknown): value is StoredChapterDraft {
  if (!isRecord(value) || value.version !== 1 || !isRecord(value.draft)) return false;
  const draft = value.draft;
  return [value.instruction, value.serverSnapshot, draft.title, draft.goal, draft.summary, draft.body]
    .every(item => typeof item === "string")
    && ["planned", "drafting", "draft", "revised", "locked", "affected"].includes(String(draft.status))
    && isRecord(draft.scene_card) && Object.values(draft.scene_card).every(item => typeof item === "string");
}

// One key per chapter avoids rewriting other visitors' drafts. Compare the last
// observed value before writing so an older tab cannot silently replace it.
export function createChapterDraftStorage(getStorage: () => Storage = () => window.localStorage) {
  const observed = new Map<string, string | null>();
  function storage() {
    try {
      const result = getStorage();
      if (!result) throw new Error();
      return result;
    } catch {
      throw new Error("浏览器暂存不可用，请保存到项目后再关闭页面。");
    }
  }
  function change(key: string, value: string | null) {
    const target = storage();
    const previous = target.getItem(key);
    if (!observed.has(key) || previous !== observed.get(key)) {
      throw new Error("另一页面更新了本机草稿，当前输入仍保留，请保存到项目或复制正文后再关闭页面。");
    }
    try {
      if (value === null) target.removeItem(key);
      else target.setItem(key, value);
    } catch {
      throw new Error("浏览器暂存失败，可能空间不足，请保存到项目后再关闭页面。");
    }
    observed.set(key, value);
  }
  return {
    load(key: string): StoredChapterDraft | null {
      const raw = storage().getItem(key);
      if (observed.has(key) && observed.get(key) !== raw) {
        throw new Error("另一页面更新了本机草稿，当前输入仍保留，请保存到项目或复制正文后再关闭页面。");
      }
      observed.set(key, raw);
      if (raw === null) return null;
      try {
        const parsed: unknown = JSON.parse(raw);
        if (validDraft(parsed)) return parsed;
      } catch { /* Invalid records never enter the editor. */ }
      throw new Error("本机草稿无法读取，已载入项目中保存的内容；原暂存记录仍保留。");
    },
    save(key: string, draft: StoredChapterDraft) { change(key, JSON.stringify(draft)); },
    remove(key: string) { change(key, null); }
  };
}
