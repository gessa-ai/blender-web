// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser diagnostic for the pre-main WM-worker presentation transaction.
// This intentionally accepts a fallback adapter and therefore binds no GPU receipt.

import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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
const browserArgs = ["--enable-unsafe-webgpu"];
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
  deviceLost: 0,
  pageErrors: 0,
};

const browser = await chromium.launch({ headless: false, args: browserArgs });
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    const line = message.text();
    if (line.includes("WM-worker WebGPU device pre-acquired")) counters.deviceReady++;
    if (line.includes("WM-worker WebGPU presentation pre-acquired")) counters.presentationReady++;
    if (line.includes("WM-worker WebGPU presentation preinit FAILED")) {
      counters.presentationFailed++;
    }
    if (line.includes("presentation preinit FAILED stage=1")) counters.stage1Failed++;
    if (line.includes("presentable preinit failed")) counters.presentableImportFailed++;
    if (line.includes("[bw][GPU-LOST]")) counters.deviceLost++;
  });
  page.on("pageerror", () => counters.pageErrors++);

  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() => {
    const state = document.querySelector("#state")?.dataset.state;
    return state === "running" || state === "aborted";
  }, null, { timeout: 180000, polling: 250 });
  await page.waitForTimeout(6000);

  const snapshot = await page.evaluate(() => {
    const module = window.__bwModule;
    return {
      state: document.querySelector("#state")?.dataset.state || "missing",
      loader: document.querySelector("#bw-pct")?.textContent || "missing",
      module: Boolean(module),
      ticks: module && typeof module._bw_wm_tick_count === "function" ?
        Number(module._bw_wm_tick_count()) : 0,
    };
  });

  const failures = [];
  if (snapshot.state !== "running") failures.push(`state=${snapshot.state}`);
  if (!snapshot.module) failures.push("module=missing");
  if (!(snapshot.ticks > 0)) failures.push(`ticks=${snapshot.ticks}`);
  if (snapshot.loader.includes("boot failed")) failures.push("loader=boot-failed");
  if (counters.deviceReady !== 1) failures.push(`deviceReady=${counters.deviceReady}`);
  if (counters.presentationReady !== 1) {
    failures.push(`presentationReady=${counters.presentationReady}`);
  }
  if (counters.presentationFailed !== 0) {
    failures.push(`presentationFailed=${counters.presentationFailed}`);
  }
  if (counters.stage1Failed !== 0) failures.push(`stage1Failed=${counters.stage1Failed}`);
  if (counters.presentableImportFailed !== 0) {
    failures.push(`presentableImportFailed=${counters.presentableImportFailed}`);
  }
  if (counters.pageErrors !== 0) failures.push(`pageErrors=${counters.pageErrors}`);
  if (failures.length) {
    throw new Error(`live WM-worker preinit diagnostic failed: ${failures.join(" ")}`);
  }

  console.log(
    `CONTRACT ghost_preinit_live PASS evidence=diagnostic-nonreceipt state=running ` +
    `device=1 presentation=1 stage1_failure=0 import_failure=0 ticks=${snapshot.ticks} ` +
    `device_lost=${counters.deviceLost} playwright_root=${playwrightRoot}`,
  );
}
finally {
  await browser.close();
}
