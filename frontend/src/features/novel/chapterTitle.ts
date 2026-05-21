const CHAPTER_PREFIX_PATTERN = /^\s*(?:\u7b2c\s*[\d\u4e00-\u9fff]+\s*\u7ae0|chapter\s*[\divxlcdm]+)\s*[:\uff1a\u3001.\-]?\s*/iu;

export function stripNovelChapterPrefix(title: string) {
  return String(title || "").trim().replace(CHAPTER_PREFIX_PATTERN, "").trim();
}

export function formatNovelChapterTitle(order: number, title: string) {
  const chapterOrder = Number.isFinite(order) && order > 0 ? Math.trunc(order) : 1;
  const cleanTitle = stripNovelChapterPrefix(title);
  return cleanTitle ? `第${chapterOrder}章 ${cleanTitle}` : `第${chapterOrder}章`;
}
