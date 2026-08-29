// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Diagnostic-only fallback-adapter proof for a first-boot WGSL cache seed.
// Software WebGPU binds no pixel, profile, performance, or milestone receipt.

import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoots = [
  process.env.BW_NODE_MODULES,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean);
let chromium = null;
for (const candidate of moduleRoots) {
  try {
    chromium = createRequire(resolve(candidate, "package.json"))("playwright").chromium;
    break;
  }
  catch (_) {}
}
if (!chromium) {
  throw new Error(`playwright is unavailable; checked ${moduleRoots.join(", ")}`);
}

const mode = process.argv[2] || "extract";
if (!new Set([
  "extract", "extract-selection", "seeded", "seeded-selection", "bundled", "disabled",
  "extract-bundled-selection",
]).has(mode)) {
  throw new Error(
    "usage: probe_seed.mjs extract|extract-selection|extract-bundled-selection|" +
    "seeded|seeded-selection|bundled|disabled " +
    "[port] [seed-dir] [tag]",
  );
}
const port = Number(process.argv[3] || 8123);
const seedDir = resolve(process.argv[4] ||
  resolve(root, "sandbox/m8-shader-cache-seed/artifacts/seed"));
const tag = String(process.argv[5] || mode).replace(/[^a-zA-Z0-9_.-]/g, "_");
const artifactDir = resolve(root, "sandbox/m8-shader-cache-seed/artifacts");
const entryPattern = /^[0-9a-f]{32}\.wgslc$/;
const started = Date.now();
const consoleLines = [];
const pageErrors = [];

mkdirSync(artifactDir, {recursive: true});
if (mode.startsWith("extract")) {
  mkdirSync(seedDir, {recursive: true});
}

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--use-webgpu-adapter=swiftshader",
    "--use-gpu-in-tests",
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});

let context = null;
try {
  context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    consoleLines.push({elapsedMs: Date.now() - started, text: message.text()});
  });
  page.on("pageerror", (error) => {
    pageErrors.push({
      elapsedMs: Date.now() - started,
      name: String(error?.name || "Error"),
      message: String(error?.message || error),
    });
  });

  if (mode === "disabled" || mode === "extract-selection") {
    await page.route("**/boot-windowed.js", async (route) => {
      const response = await route.fetch();
      const source = await response.text();
      const anchor = "const ENV_VARS = {\n";
      if (source.split(anchor).length !== 2) {
        throw new Error("ENV_VARS diagnostic anchor drifted");
      }
      await route.fulfill({
        response,
        body: source.replace(anchor, anchor + '  BW_SHADER_CACHE_SEED: "0",\n'),
      });
    });
  }

  if (mode === "seeded" || mode === "seeded-selection") {
    const entries = readdirSync(seedDir, {withFileTypes: true})
      .filter((entry) => entry.isFile() && entryPattern.test(entry.name))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((entry) => ({
        name: entry.name,
        bytes: readFileSync(resolve(seedDir, entry.name)).toString("base64"),
      }));
    if (entries.length === 0) {
      throw new Error(`seed directory has no cache entries: ${seedDir}`);
    }
    await page.goto(`http://127.0.0.1:${port}/__bw_shader_seed__`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    const seeded = await page.evaluate(async (payload) => {
      const rootHandle = await navigator.storage.getDirectory();
      const cache = await rootHandle.getDirectoryHandle(".shadercache", {create: true});
      let total = 0;
      for (const entry of payload) {
        const raw = atob(entry.bytes);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) {
          bytes[i] = raw.charCodeAt(i);
        }
        const handle = await cache.getFileHandle(entry.name, {create: true});
        const writable = await handle.createWritable();
        await writable.write(bytes);
        await writable.close();
        total += bytes.length;
      }
      return {count: payload.length, total};
    }, entries);
    consoleLines.push({elapsedMs: Date.now() - started,
      text: `BW_SHADER_SEED_INJECTED count=${seeded.count} bytes=${seeded.total}`});
  }

  const navigationAt = Date.now();
  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  await page.waitForFunction(() => {
    const state = document.querySelector("#state")?.dataset.state;
    if (state === "error" || state === "aborted") {
      throw new Error(`boot entered ${state}`);
    }
    const mod = window.__bwModule;
    return state === "running" && typeof mod?._bw_present_count === "function" &&
      Number(mod._bw_present_count()) > 0;
  }, null, {timeout: 180000, polling: 25});
  const firstPresentMs = Date.now() - navigationAt;
  await page.waitForTimeout(2000);

  let selectionReadyMs = null;
  if (mode.endsWith("-selection")) {
    const canvas = page.locator("#canvas");
    await canvas.focus();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(750);
    const box = await canvas.boundingBox();
    if (!box) {
      throw new Error("selection seed canvas has no bounding box");
    }
    const selectionAt = Date.now();
    await page.mouse.click(box.x + box.width * 0.47, box.y + box.height * 0.54);
    await page.waitForFunction(() => {
      const mod = window.__bwModule;
      return Number(mod?._bw_exact_buffer_readback_ready_count?.()) > 0 &&
        Number(mod?._bw_gpu_select_async_phase?.()) === 0;
    }, null, {timeout: 120000, polling: 50});
    selectionReadyMs = Date.now() - selectionAt;
    await page.waitForTimeout(2000);
  }

  if (mode.startsWith("extract")) {
    const extracted = await page.evaluate(async () => {
      const rootHandle = await navigator.storage.getDirectory();
      const cache = await rootHandle.getDirectoryHandle(".shadercache");
      const result = [];
      for await (const [name, handle] of cache.entries()) {
        if (handle.kind !== "file") {
          continue;
        }
        const file = await handle.getFile();
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        const block = 0x8000;
        for (let i = 0; i < bytes.length; i += block) {
          binary += String.fromCharCode(...bytes.subarray(i, i + block));
        }
        result.push({name, bytes: btoa(binary)});
      }
      return result;
    });
    for (const entry of extracted) {
      if (!entryPattern.test(entry.name)) {
        throw new Error(`unexpected cache entry name: ${entry.name}`);
      }
      writeFileSync(resolve(seedDir, entry.name), Buffer.from(entry.bytes, "base64"));
    }
  }

  const files = (!new Set(["bundled", "disabled"]).has(mode) && existsSync(seedDir) ?
    readdirSync(seedDir, {withFileTypes: true}) : [])
    .filter((entry) => entry.isFile() && entryPattern.test(entry.name))
    .map((entry) => entry.name)
    .sort();
  const hash = createHash("sha256");
  let seedBytes = 0;
  for (const name of files) {
    const bytes = readFileSync(resolve(seedDir, name));
    hash.update(name);
    hash.update("\0");
    hash.update(bytes);
    seedBytes += bytes.length;
  }
  const hits = consoleLines.filter((entry) =>
    entry.text.includes("BW_SHADER_CACHE_RESULT HIT ")).length;
  const misses = consoleLines.filter((entry) =>
    entry.text.includes("BW_SHADER_CACHE_RESULT MISS ")).length;
  const result = {
    contract: "fallback-shader-cache-seed-diagnostic-v1",
    diagnosticNonreceipt: true,
    mode,
    firstPresentMs,
    selectionReadyMs,
    seed: {count: files.length, bytes: seedBytes, sha256: hash.digest("hex")},
    cacheResults: {hits, misses},
    pageErrors,
    consoleLines,
  };
  writeFileSync(resolve(artifactDir, `${tag}.json`), `${JSON.stringify(result, null, 2)}\n`);
  console.log(`BW_SHADER_CACHE_SEED_DIAGNOSTIC mode=${mode} ` +
    `first_present_ms=${firstPresentMs} selection_ready_ms=${selectionReadyMs ?? "none"} ` +
    `entries=${files.length} bytes=${seedBytes} ` +
    `hits=${hits} misses=${misses} page_errors=${pageErrors.length} ` +
    `sha256=${result.seed.sha256}`);
}
finally {
  await context?.close();
  await browser.close();
}
