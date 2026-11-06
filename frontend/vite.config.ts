import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

function port(name: string, fallback: number) {
  const value = process.env[name];
  const result = value ? Number(value) : fallback;
  if (!Number.isInteger(result) || result < 1 || result > 65535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return result;
}
const proxy = { "/api": `http://127.0.0.1:${port("CAMPUS_BACKEND_PORT", 8766)}` };

export default defineConfig({
  cacheDir: process.env.CAMPUS_RUNTIME_DIR ? `${process.env.CAMPUS_RUNTIME_DIR}/vite-cache` : "../runtime/vite-cache",
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: port("CAMPUS_FRONTEND_PORT", 5176),
    strictPort: true,
    proxy
  },
  preview: {
    host: "127.0.0.1",
    port: port("CAMPUS_PREVIEW_PORT", 4176),
    strictPort: true,
    proxy
  }
});
