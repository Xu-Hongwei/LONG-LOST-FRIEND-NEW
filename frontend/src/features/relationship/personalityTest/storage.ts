import { loveQuestions } from "./data";
import type { LoveGender } from "./data";

const LOVE_TEST_KEY = "campus-pulse-lite-love-test";
const LOVE_TEST_VERSION = "love-test-v3-20q-6types-profile-images";

function loveStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:${id || "anonymous"}`;
}

function loveGenderStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:gender:${id || "anonymous"}`;
}

export function saveLoveAnswersForVisitor(visitorId: string, answers: Record<string, number>) {
  localStorage.setItem(loveStorageKey(visitorId), JSON.stringify({ version: LOVE_TEST_VERSION, answers }));
}

export function resetLoveAnswersForVisitor(visitorId: string) {
  localStorage.removeItem(loveStorageKey(visitorId));
}

export function loadLoveAnswersForVisitor(visitorId: string) {
  try {
    const raw = localStorage.getItem(loveStorageKey(visitorId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as { version?: string; answers?: Record<string, number> };
    if (parsed.version !== LOVE_TEST_VERSION || !parsed.answers) return {};
    return Object.fromEntries(
      Object.entries(parsed.answers).filter(([questionId]) => loveQuestions.some((question) => question.id === questionId))
    );
  } catch {
    return {};
  }
}

export function saveLoveGenderForVisitor(visitorId: string, gender: LoveGender) {
  localStorage.setItem(loveGenderStorageKey(visitorId), gender);
}

export function loadLoveGenderForVisitor(visitorId: string): LoveGender {
  return localStorage.getItem(loveGenderStorageKey(visitorId)) === "male" ? "male" : "female";
}
