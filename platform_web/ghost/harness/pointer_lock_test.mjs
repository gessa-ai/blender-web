// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract for GHOST_WindowWeb cursor grab and relative motion.

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
const leaveActive = process.env.BW_POINTER_LOCK_LEAVE_ACTIVE === "1";
const browserArgs = [];
if (process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({
  headless: process.env.BW_HEADLESS === "1",
  args: browserArgs,
});
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
      return module && typeof module._ghost_harness_request_cursor_grab === "function" &&
        typeof module._ghost_harness_cursor_grab_result === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const requestGrab = async (mode) => {
    const queued = await page.evaluate((requested) => Number(
      globalThis.ghostModule._ghost_harness_request_cursor_grab(requested)), mode);
    if (queued !== 1) throw new Error(`grab ${mode} was not queued: ${queued}`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_cursor_grab_result()) !== -2);
    return page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_cursor_grab_result()));
  };

  const canvas = page.locator("#blender-canvas");
  await canvas.click({ position: { x: 120, y: 100 } });
  if (await requestGrab(2) !== 1) {
    throw new Error("wrap grab was rejected");
  }
  if (!(await page.evaluate(() => document.pointerLockElement !== null))) {
    await canvas.click({ position: { x: 120, y: 100 } });
  }
  try {
    await page.waitForFunction(
      () => document.pointerLockElement?.id === "blender-canvas", null, { timeout: 5000 });
  }
  catch (error) {
    const state = await page.evaluate(() => ({
      active: navigator.userActivation?.isActive ?? null,
      hasBeenActive: navigator.userActivation?.hasBeenActive ?? null,
      pointerLockElement: document.pointerLockElement?.id ?? null,
      requestSupported: typeof document.querySelector("#blender-canvas")?.requestPointerLock,
    }));
    throw new Error(`pointer lock did not activate: ${JSON.stringify(state)}`, { cause: error });
  }

  const beforeMotion = await page.locator("#log").textContent();
  const cursorMatches = [...beforeMotion.matchAll(/GHOST CursorMove\s+x=(-?\d+) y=(-?\d+)/g)];
  if (cursorMatches.length === 0) {
    throw new Error(`no baseline cursor event: ${beforeMotion.slice(-1200)}`);
  }
  const baseline = cursorMatches.at(-1).slice(1).map(Number);
  const expected = [baseline[0] + 37, baseline[1] - 19];

  await page.evaluate(() => {
    const canvasElement = document.querySelector("#blender-canvas");
    const rect = canvasElement.getBoundingClientRect();
    const event = new MouseEvent("mousemove", {
      bubbles: true,
      clientX: rect.left + 120,
      clientY: rect.top + 100,
    });
    Object.defineProperties(event, {
      movementX: { value: 37 },
      movementY: { value: -19 },
    });
    canvasElement.dispatchEvent(event);
  });
  try {
    await page.waitForFunction(([expectedX, expectedY]) => {
      const lines = document.querySelector("#log")?.textContent || "";
      return lines.includes(`GHOST CursorMove       x=${expectedX} y=${expectedY}`);
    }, expected, { timeout: 5000 });
  }
  catch (error) {
    const lines = await page.locator("#log").textContent();
    throw new Error(`relative cursor event missing: ${lines.slice(-1200)}`, { cause: error });
  }

  const invalid = await page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_request_cursor_grab(99)));
  if (invalid !== 0) {
    throw new Error(`invalid grab mode was accepted: ${invalid}`);
  }

  if (!leaveActive) {
    if (await requestGrab(0) !== 1) {
      throw new Error("grab release was rejected");
    }
    await page.waitForFunction(() => document.pointerLockElement === null);
  }

  console.log(
    `POINTER_LOCK_LIVE PASS modes=wrap,${leaveActive ? "active" : "disable"} ` +
    `relative=37,-19 virtual=${expected.join(",")} invalid=rejected`);
}
finally {
  await browser.close();
}
