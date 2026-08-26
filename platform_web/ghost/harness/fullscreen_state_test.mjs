// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract for GHOST_WindowWeb's HTML5 fullscreen state bridge.

import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const moduleRoots = [process.env.BW_NODE_MODULES, resolve(root, ".m4-node/node_modules")]
  .filter(Boolean);
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

const port = Number(process.argv[2] || 8124);
const browserArgs = [];
if (process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({ headless: false, args: browserArgs });
try {
  const context = await browser.newContext({ viewport: { width: 960, height: 640 } });
  const page = await context.newPage();
  const diagnostics = [];
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  try {
    await page.waitForFunction(() => {
      const module = globalThis.ghostModule;
      return module && typeof module._ghost_harness_request_window_state === "function" &&
        typeof module._ghost_harness_window_state_result === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const initial = await page.evaluate(() => ({
    enabled: document.fullscreenEnabled,
    fullscreen: document.fullscreenElement !== null,
  }));
  if (!initial.enabled || initial.fullscreen) {
    throw new Error(`invalid initial state: ${JSON.stringify(initial)}`);
  }

  const requestState = async (state) => {
    const queued = await page.evaluate((requested) => Number(
      globalThis.ghostModule._ghost_harness_request_window_state(requested)), state);
    if (queued !== 1) throw new Error(`state ${state} was not queued: ${queued}`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_window_state_result()) !== -2);
    return page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_window_state_result()));
  };

  // This request runs on a WM-worker main-loop turn, outside the DOM callback.
  // A browser may retain automation activation and enter immediately; otherwise
  // Emscripten must defer it until the next genuine GHOST canvas event.
  const deferredStatus = await requestState(3);
  if (deferredStatus !== 1) {
    throw new Error(`deferred fullscreen request returned ${deferredStatus}`);
  }
  let entryMode = "immediate";
  if (!(await page.evaluate(() => document.fullscreenElement !== null))) {
    entryMode = "deferred";
    await page.locator("#blender-canvas").click({ position: { x: 40, y: 40 } });
  }
  await page.waitForFunction(() => document.fullscreenElement?.id === "blender-canvas");
  const minimizedStatus = await requestState(2);
  if (minimizedStatus !== 0 ||
      !(await page.evaluate(() => document.fullscreenElement?.id === "blender-canvas"))) {
    throw new Error(`minimized request was not rejected in-place: ${minimizedStatus}`);
  }

  const normalStatus = await requestState(0);
  if (normalStatus !== 1) {
    throw new Error(`fullscreen exit returned ${normalStatus}`);
  }
  await page.waitForFunction(() => document.fullscreenElement === null);

  const maximizedStatus = await requestState(1);
  const finalFullscreen = await page.evaluate(() => document.fullscreenElement !== null);
  if (maximizedStatus !== 1 || finalFullscreen) {
    throw new Error(`page-fill maximized mapping failed: ${maximizedStatus}/${finalFullscreen}`);
  }

  console.log(
    "FULLSCREEN_STATE_LIVE PASS states=normal,maximized,minimized,fullscreen " +
    `entry=${entryMode} exit=browser-api`);
}
finally {
  await browser.close();
}
