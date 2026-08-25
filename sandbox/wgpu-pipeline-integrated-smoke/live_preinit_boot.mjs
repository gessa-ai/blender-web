// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser diagnostic for the pre-main WM-worker presentation transaction.
// This intentionally accepts a fallback adapter and therefore binds no GPU receipt.

import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  LIVE_INPUT_ROUND_TRIP_MAX_MS,
  LIVE_STARTUP_SETTLE_MAX_MS,
  classifyLivePreinitDiagnostic,
} from "./live_preinit_contract.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoots = [process.env.BW_NODE_MODULES, resolve(root, ".m4-node/node_modules")]
  .filter(Boolean);
let chromium = null;
let playwrightRoot = null;
for (const candidate of moduleRoots) {
  try {
    chromium = createRequire(resolve(candidate, "package.json"))("playwright").chromium;
    playwrightRoot = candidate;
    break;
  }
  catch (_) {}
}
if (!chromium) {
  throw new Error(`playwright is unavailable; checked ${moduleRoots.join(", ")}`);
}

const port = Number(process.argv[2] || 8123);
const entryPath = process.argv[3] || "/windowed.html";
const shellTitle = "Source-derived WebAssembly editor preview";
if (entryPath !== "/" && entryPath !== "/windowed.html") {
  throw new Error(`entry path must be / or /windowed.html, got: ${entryPath}`);
}
// This is deliberately Chromium's software WebGPU test posture, not a hardware
// receipt profile. `--use-gpu-in-tests` initializes the GPU service before Dawn;
// without it, current Linux Chromium destroys the forced SwiftShader device as
// soon as an OffscreenCanvas is configured, producing a false one-tick product
// diagnosis. The classifier below requires the resulting fallback status.
const browserArgs = [
  "--enable-unsafe-webgpu",
  "--use-webgpu-adapter=swiftshader",
  "--use-gpu-in-tests",
];
if (process.platform === "darwin") {
  browserArgs.push("--use-angle=metal");
}
else if (process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const counters = {
  deviceReady: 0,
  presentationReady: 0,
  presentationFailed: 0,
  stage1Failed: 0,
  presentableImportFailed: 0,
  presentSubmissionRejected: 0,
  presentTransactionRejected: 0,
  deviceLost: 0,
  pageErrors: 0,
  adapterFallback: "unseen",
  presentationValidation: "unseen",
};

const diagnosticConsole = [];

async function readSample(page) {
  const sampledAtMs = performance.now();
  return page.evaluate((at) => {
    const module = window.__bwModule;
    return {
      state: document.querySelector("#state")?.dataset.state || "missing",
      loader: document.querySelector("#bw-pct")?.textContent || "missing",
      module: Boolean(module),
      ticks: module && typeof module._bw_wm_tick_count === "function" ?
        Number(module._bw_wm_tick_count()) : null,
      presents: module && typeof module._bw_present_count === "function" ?
        Number(module._bw_present_count()) : null,
      sampledAtMs: at,
    };
  }, sampledAtMs);
}

async function waitForInputRoundTrip(page, before) {
  const deadline = performance.now() + LIVE_INPUT_ROUND_TRIP_MAX_MS;
  let sample = await readSample(page);
  while (performance.now() <= deadline) {
    if (sample.ticks > before.ticks && sample.presents > before.presents) return sample;
    await page.waitForTimeout(100);
    sample = await readSample(page);
  }
  return sample;
}

const browser = await chromium.launch({ headless: false, args: browserArgs });
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    const line = message.text();
    if (line.includes("[bw][GPU-") || line.includes("[WebGPU]") ||
        line.includes("WGPUWeb:") ||
        line.includes("WM-worker WebGPU device pre-acquired") ||
        line.includes("WM-worker WebGPU presentation pre-acquired") ||
        /error|abort|assert|exception|keepalive|main loop/i.test(line)) {
      diagnosticConsole.push(line);
    }
    if (line.includes("WM-worker WebGPU device pre-acquired")) counters.deviceReady++;
    if (line.includes("WM-worker WebGPU device pre-acquired")) {
      counters.adapterFallback = /\bfallback=([^ ]+)/.exec(line)?.[1] || "unseen";
    }
    if (line.includes("WM-worker WebGPU presentation pre-acquired")) {
      counters.presentationReady++;
      counters.presentationValidation = /\bvalidation=([^ ]+)/.exec(line)?.[1] || "unseen";
    }
    if (line.includes("WM-worker WebGPU presentation preinit FAILED")) {
      counters.presentationFailed++;
    }
    if (line.includes("presentation preinit FAILED stage=1")) counters.stage1Failed++;
    if (line.includes("presentable preinit failed")) counters.presentableImportFailed++;
    if (line.includes("present queue submission rejected")) {
      counters.presentSubmissionRejected++;
    }
    if (line.includes("present transaction rejected")) counters.presentTransactionRejected++;
    if (line.includes("[bw][GPU-LOST]")) counters.deviceLost++;
  });
  page.on("pageerror", () => counters.pageErrors++);

  await page.goto(`http://127.0.0.1:${port}${entryPath}`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() => {
    const state = document.querySelector("#state")?.dataset.state;
    return state === "running" || state === "aborted";
  }, null, { timeout: 180000, polling: 250 });
  await page.waitForFunction((initialTitle) => {
    return document.title.length > 0 && document.title !== initialTitle;
  }, shellTitle, { timeout: 10000, polling: 100 });

  await page.waitForFunction(() => {
    const module = window.__bwModule;
    return module && typeof module._bw_wm_tick_count === "function" &&
      typeof module._bw_present_count === "function";
  }, null, { timeout: 10000, polling: 100 });
  await page.waitForFunction(() => {
    const bridge = window.__bwCursorBridge;
    const snapshot = bridge && bridge.snapshot();
    return bridge?.schema === 2 && bridge.standardShapeCount === 46 &&
      bridge.customShape === 46 && bridge.customMaxDimension === 128 && snapshot &&
      Number.isInteger(snapshot.generation) && Number.isInteger(snapshot.shape) &&
      snapshot.shape >= 0 && snapshot.shape < bridge.standardShapeCount &&
      snapshot.visible === true && snapshot.css === document.querySelector("#canvas")?.style.cursor;
  }, null, { timeout: 10000, polling: 100 });
  // `state=running` is published when WM_main is entered, before the first
  // software-rendered iteration has necessarily completed. Bound that startup
  // phase by requiring a second real processEvents entry; the samples below
  // then prove continued progress rather than counting the entry tick twice.
  const settleStartedAtMs = performance.now();
  let secondTickSettled = true;
  try {
    await page.waitForFunction(() => {
      const module = window.__bwModule;
      return module && Number(module._bw_wm_tick_count?.()) >= 2;
    }, null, { timeout: LIVE_STARTUP_SETTLE_MAX_MS, polling: 250 });
  }
  catch (_) {
    secondTickSettled = false;
  }
  const startupSettleMs = performance.now() - settleStartedAtMs;
  const first = await readSample(page);
  await page.waitForTimeout(1250);
  const second = await readSample(page);

  const canvas = page.locator("#canvas");
  const bounds = await canvas.boundingBox();
  let trustedInputIssued = false;
  const inputStartedAtMs = performance.now();
  if (bounds && bounds.width >= 80 && bounds.height >= 80) {
    const x = bounds.x + bounds.width * 0.5;
    const y = bounds.y + bounds.height * 0.5;
    await page.mouse.move(x - 20, y - 20);
    await page.mouse.move(x, y);
    await page.mouse.click(x, y);
    trustedInputIssued = true;
  }
  const afterInput = await waitForInputRoundTrip(page, second);
  const snapshot = await readSample(page);
  const cursorSnapshot = await page.evaluate(() => window.__bwCursorBridge.snapshot());
  const documentTitle = await page.title();
  const result = classifyLivePreinitDiagnostic({
    state: snapshot.state,
    module: snapshot.module,
    loader: snapshot.loader,
    secondTickSettled,
    startupSettleMs,
    first,
    second,
    inputStartedAtMs,
    trustedInputIssued,
    afterInput,
    counters,
  });
  if (!result.accepted) {
    const context = [
      ...diagnosticConsole.filter((line) => line.includes("[bw][GPU-")),
      ...diagnosticConsole.slice(0, 12),
      ...diagnosticConsole.slice(-8),
    ].join(" | ");
    throw new Error(
      `live WM-worker preinit diagnostic failed: ${result.failures.join(" ")}` +
      (context ? ` console=${context}` : ""),
    );
  }

  console.log(
    `CONTRACT ghost_preinit_live PASS evidence=diagnostic-nonreceipt state=running ` +
    `adapter=${result.adapterMode} validation=${counters.presentationValidation} ` +
    `device=1 presentation=1 stage1_failure=0 import_failure=0 ` +
    `startup_settle_ms=${Math.round(result.startupSettleMs ?? startupSettleMs)} ` +
    `idle_sample_ms=${Math.round(result.idleElapsedMs)} idle_tick_delta=${result.idleTickDelta} ` +
    `input_round_trip_ms=${Math.round(result.inputElapsedMs)} ` +
    `input_tick_delta=${result.inputTickDelta} input_present_delta=${result.inputPresentDelta} ` +
    `cursor_shape=${cursorSnapshot.shape} cursor_css=${cursorSnapshot.css} ` +
    `title_updated=1 document_title=${encodeURIComponent(documentTitle)} ` +
    `present_submission_rejected=0 present_transaction_rejected=0 device_lost=0 ` +
    `playwright_root=${playwrightRoot}`,
  );
}
finally {
  await browser.close();
}
