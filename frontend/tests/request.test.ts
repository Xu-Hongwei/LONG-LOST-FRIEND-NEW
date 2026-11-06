import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, request } from "../src/lib/apiClient";
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("HTTP errors show a readable message instead of server JSON or HTML", async () => {
  globalThis.fetch = async () => new Response('{"detail":"private server traceback"}', { status: 500 });
  await assert.rejects(request("/test"), (err: ApiError) => err.status === 500 && err.message.includes("运行日志") && !err.message.includes("private"));
});
test("validation errors are understandable", async () => {
  globalThis.fetch = async () => new Response("{}", { status: 422 });
  await assert.rejects(request("/test"), /检查输入/);
});
test("network errors are distinct from HTTP errors", async () => {
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(request("/test"), (err: ApiError) => err.kind === "network");
});
test("timeout aborts the request and warns against a duplicate submission", async () => {
  globalThis.fetch = (_url, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
  await assert.rejects(request("/test", { method: "POST" }, { timeoutMs: 10 }), (err: ApiError) => err.kind === "timeout" && err.message.includes("避免重复提交"));
});
test("headers are merged and empty successful responses work", async () => {
  globalThis.fetch = async (_url, init) => {
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("Content-Type"), "application/json"); assert.equal(headers.get("X-Test"), "ok");
    return new Response(null, { status: 204 });
  };
  assert.equal(await request("/test", { headers: { "X-Test": "ok" } }), undefined);
});
test("invalid response JSON has a useful error message", async () => {
  globalThis.fetch = async () => new Response("<html>proxy error</html>");
  await assert.rejects(request("/test"), (err: ApiError) => err.kind === "response");
});
