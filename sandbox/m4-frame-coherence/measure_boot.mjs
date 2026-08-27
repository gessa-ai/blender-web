// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Diagnostic-only fallback-adapter timeline for release boot coherence.
// A software adapter binds no pixel, profile, or milestone receipt.

import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const outDir = resolve(root, "sandbox/m4-frame-coherence/artifacts");
mkdirSync(outDir, { recursive: true });

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

const port = Number(process.argv[2] || 8123);
const tag = String(process.argv[3] || "boot").replace(/[^a-zA-Z0-9_.-]/g, "_");
const maxMs = Number(process.env.BW_COHERENCE_TIMEOUT_MS || 180000);
const settleMs = Number(process.env.BW_COHERENCE_SETTLE_MS || 30000);
const started = Date.now();
const consoleLines = [];
const pageErrors = [];
const transitions = [];

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--use-webgpu-adapter=swiftshader",
    "--use-gpu-in-tests",
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});

let page = null;
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });
  page = await context.newPage();
  page.on("console", (message) => {
    consoleLines.push({ elapsedMs: Date.now() - started, text: message.text() });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({
      elapsedMs: Date.now() - started,
      name: String(error?.name || "Error"),
      message: String(error?.message || error),
    });
  });

  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded",
    timeout: maxMs,
  });

  let previous = null;
  let lastSample = null;
  let runningAtMs = null;
  let deadline = started + maxMs;
  while (Date.now() < deadline) {
    const sample = await page.evaluate(() => {
      const loader = document.querySelector("#loader");
      const state = document.querySelector("#state");
      const mod = window.__bwModule;
      return {
        state: state?.dataset.state || null,
        stateText: state?.textContent || null,
        loaderHidden: Boolean(loader?.classList.contains("bw-hidden")),
        loaderGone: Boolean(loader?.classList.contains("bw-gone")),
        presents: typeof mod?._bw_present_count === "function" ?
          Number(mod._bw_present_count()) : null,
        viewportContentPresents:
          typeof mod?._bw_viewport_content_present_count === "function" ?
            Number(mod._bw_viewport_content_present_count()) : null,
        ticks: typeof mod?._bw_wm_tick_count === "function" ?
          Number(mod._bw_wm_tick_count()) : null,
      };
    });
    lastSample = sample;
    const key = JSON.stringify([
      sample.state,
      sample.stateText,
      sample.loaderHidden,
      sample.loaderGone,
      sample.presents,
      sample.viewportContentPresents,
    ]);
    if (key !== previous) {
      transitions.push({ elapsedMs: Date.now() - started, ...sample });
      previous = key;
    }
    if (sample.state === "error" || sample.state === "aborted") {
      throw new Error(`boot entered ${sample.state}: ${sample.stateText}`);
    }
    if (sample.state === "running" && runningAtMs === null) {
      runningAtMs = Date.now() - started;
      deadline = Date.now() + settleMs;
    }
    await page.waitForTimeout(25);
  }

  const firstPresented = transitions.find((entry) => Number(entry.presents) > 0) || null;
  const firstViewportContent = transitions.find(
    (entry) => Number(entry.viewportContentPresents) > 0) || null;
  const loaderHidden = transitions.find((entry) => entry.loaderHidden) || null;
  const final = lastSample ? { elapsedMs: Date.now() - started, ...lastSample } : null;
  const failures = [];
  const loaderHiddenBeforeViewportContent = Boolean(
    loaderHidden && !(Number(loaderHidden.viewportContentPresents) > 0));
  if (!firstViewportContent) failures.push("no validated VIEW_3D content presentation");
  if (!loaderHidden) failures.push("loader did not dismiss after validated VIEW_3D content");
  if (loaderHiddenBeforeViewportContent) {
    failures.push("loader hid before a validated VIEW_3D content presentation");
  }
  if (pageErrors.length !== 0) failures.push(`page errors: ${pageErrors.length}`);
  const result = {
    contract: "fallback-boot-frame-coherence-diagnostic-v2",
    verdict: failures.length === 0 ? "PASS" : "FAIL",
    failures,
    tag,
    diagnosticNonreceipt: true,
    runningAtMs,
    firstPresented,
    firstViewportContent,
    loaderHidden,
    loaderHiddenAtPresent: loaderHidden?.presents ?? null,
    loaderHiddenAtViewportContent: loaderHidden?.viewportContentPresents ?? null,
    loaderHiddenBeforeViewportContent,
    presentsAfterLoaderHidden:
      final && loaderHidden && Number.isFinite(final.presents) &&
      Number.isFinite(loaderHidden.presents) ? final.presents - loaderHidden.presents : null,
    final,
    transitions,
    consoleLines,
    pageErrors,
  };
  writeFileSync(resolve(outDir, `${tag}.json`), `${JSON.stringify(result, null, 2)}\n`);
  if (failures.length !== 0) {
    throw new Error(failures.join("; "));
  }
  console.log(`BW_FRAME_COHERENCE_DIAGNOSTIC verdict=PASS tag=${tag} running_ms=${runningAtMs} ` +
    `first_present_ms=${firstPresented?.elapsedMs ?? -1} ` +
    `first_viewport_content_ms=${firstViewportContent?.elapsedMs ?? -1} ` +
    `loader_hidden_ms=${loaderHidden?.elapsedMs ?? -1} ` +
    `loader_present=${result.loaderHiddenAtPresent} ` +
    `loader_viewport_content=${result.loaderHiddenAtViewportContent} ` +
    `post_loader_presents=${result.presentsAfterLoaderHidden} ` +
    `final_presents=${final?.presents} page_errors=${pageErrors.length}`);
}
finally {
  await browser.close();
}
