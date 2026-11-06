const API_BASE = "";

export class ApiError extends Error {
  constructor(message: string, public kind: "http" | "network" | "timeout" | "aborted" | "response", public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function httpMessage(status: number) {
  if (status === 400 || status === 422) return "提交内容未通过检查，请检查输入后再试。";
  if (status === 401 || status === 403) return "当前操作没有访问权限，请检查服务配置。";
  if (status === 404) return "内容不存在或已被删除，请重新加载后核对。";
  if (status === 409) return "内容状态已变化，请重新加载后核对。";
  if (status === 429) return "请求过于频繁，请稍后再试。";
  return `服务暂时无法完成请求（HTTP ${status}），请查看运行日志。`;
}

export async function request<T>(path: string, init: RequestInit = {}, options: { timeoutMs?: number } = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? (init.method && init.method !== "GET" ? 120_000 : 30_000);
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (init.signal?.aborted) abort();
  else init.signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const headers = new Headers(init.headers);
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal });
    if (!response.ok) throw new ApiError(httpMessage(response.status), "http", response.status);
    if (response.status === 204) return undefined as T;
    try {
      return await response.json() as T;
    } catch (err) {
      if (controller.signal.aborted) throw err;
      throw new ApiError("服务返回的内容无法读取，请重新加载后核对。", "response");
    }
  } catch (err) {
    if (timedOut) throw new ApiError("等待超时，服务端可能仍在处理。请先查看已有记录，避免重复提交。", "timeout");
    if (controller.signal.aborted) throw new ApiError("请求已取消，服务端可能仍在处理。", "aborted");
    if (err instanceof ApiError) throw err;
    throw new ApiError("无法连接服务，请确认本地服务已启动并检查连接。", "network");
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", abort);
  }
}
