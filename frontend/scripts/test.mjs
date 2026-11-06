import { build } from "esbuild";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const directory = await mkdtemp(join(tmpdir(), "campus-frontend-tests-"));
try {
  const names = (await readdir(new URL("../tests/", import.meta.url))).filter(name => name.endsWith(".test.ts"));
  const outputs = [];
  for (const name of names) {
    const output = join(directory, name.replace(/\.ts$/, ".mjs"));
    await build({ entryPoints: [fileURLToPath(new URL(`../tests/${name}`, import.meta.url))],
      outfile: output, bundle: true, platform: "node", format: "esm", logLevel: "silent" });
    outputs.push(output);
  }
  if (!outputs.length) throw new Error("No frontend tests found");
  const result = spawnSync(process.execPath, ["--test", ...outputs], { stdio: "inherit" });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  if (dirname(resolve(directory)) !== resolve(tmpdir())) throw new Error("Unexpected temporary test directory");
  await rm(directory, { recursive: true, force: true });
}
