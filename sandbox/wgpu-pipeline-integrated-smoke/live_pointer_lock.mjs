// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Product-level Pointer Lock diagnostic. The forced software adapter makes this
// explicitly nonreceipt evidence; it validates only GHOST/WM interaction wiring.

import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
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

const port = Number(process.argv[2] || 8123);
const leaveActive = process.env.BW_POINTER_LOCK_LEAVE_ACTIVE === "1";
const headless = process.env.BW_HEADLESS === "1";
const browserArgs = [
  "--enable-unsafe-webgpu",
  "--use-webgpu-adapter=swiftshader",
  "--use-gpu-in-tests",
];
if (!headless && process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({ headless, args: browserArgs });
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const rejected = [];
  page.on("console", (message) => {
    const line = message.text();
    if (/present (queue submission|transaction) rejected|GPU-LOST|preinit FAILED/.test(line)) {
      rejected.push(line);
    }
  });
  page.on("pageerror", (error) => rejected.push(`pageerror:${error.message}`));

  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() =>
    document.querySelector("#state")?.dataset.state === "running", null,
  { timeout: 180000, polling: 250 });
  try {
    await page.waitForFunction(() => {
      const module = window.__bwModule;
      return module && Number(module._bw_wm_tick_count?.()) >= 2 &&
        Number(module._bw_present_count?.()) >= 2;
    }, null, { timeout: 30000, polling: 100 });
  }
  catch (error) {
    const startup = await page.evaluate(() => {
      const module = window.__bwModule;
      return {
        state: document.querySelector("#state")?.dataset.state ?? "missing",
        ticks: Number(module?._bw_wm_tick_count?.() ?? -1),
        presents: Number(module?._bw_present_count?.() ?? -1),
      };
    });
    throw new Error(
      `product presentation did not settle: ${JSON.stringify(startup)} ` +
      `diagnostics=${rejected.join(" | ")}`,
      { cause: error });
  }

  const canvas = page.locator("#canvas");
  const bounds = await canvas.boundingBox();
  if (!bounds || bounds.width < 400 || bounds.height < 300) {
    throw new Error(`invalid product canvas bounds: ${JSON.stringify(bounds)}`);
  }
  /* Factory startup opens Blender's splash over the viewport. Dismiss it before
   * targeting the navigation operator. */
  await canvas.click({ position: { x: 80, y: 80 } });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  const center = {
    x: bounds.x + bounds.width * 0.45,
    y: bounds.y + bounds.height * 0.45,
  };
  await page.mouse.move(center.x, center.y);
  const before = await page.evaluate(() => ({
    ticks: Number(window.__bwModule._bw_wm_tick_count()),
    presents: Number(window.__bwModule._bw_present_count()),
  }));
  await page.mouse.down({ button: "middle" });
  /* View navigation enters its modal grab after the first drag delta, not on
   * the bare button-down event. */
  await page.mouse.move(center.x + 80, center.y - 45, { steps: 4 });
  try {
    await page.waitForFunction(() => document.pointerLockElement?.id === "canvas", null,
      { timeout: 10000, polling: 50 });
  }
  catch (error) {
    throw new Error(`product pointer lock did not activate: ${rejected.join(" | ")}`, {
      cause: error,
    });
  }
  await page.mouse.move(center.x + 80, center.y - 45, { steps: 4 });
  await page.waitForFunction((sample) => {
    const module = window.__bwModule;
    return Number(module._bw_wm_tick_count()) > sample.ticks &&
      Number(module._bw_present_count()) > sample.presents;
  }, before, { timeout: 10000, polling: 50 });
  const after = await page.evaluate(() => ({
    ticks: Number(window.__bwModule._bw_wm_tick_count()),
    presents: Number(window.__bwModule._bw_present_count()),
  }));
  let recovery = { ticks: 0, presents: 0 };

  if (!leaveActive) {
    /* Simulate browser/Escape loss independently of Blender's button release.
     * The bridged pointerlockchange must retire GHOST's active state so a later
     * navigation gesture can acquire a fresh lock instead of believing the old
     * DOM lock still exists. */
    await page.evaluate(() => document.exitPointerLock());
    await page.waitForFunction(() => document.pointerLockElement === null, null,
      { timeout: 10000, polling: 50 });
    await page.waitForTimeout(100);
    await page.mouse.up({ button: "middle" });

    await canvas.focus();
    await page.mouse.move(center.x, center.y);
    const recoveryBefore = await page.evaluate(() => ({
      ticks: Number(window.__bwModule._bw_wm_tick_count()),
      presents: Number(window.__bwModule._bw_present_count()),
    }));
    await page.mouse.down({ button: "middle" });
    await page.mouse.move(center.x - 60, center.y + 35, { steps: 4 });
    await page.waitForFunction(() => document.pointerLockElement?.id === "canvas", null,
      { timeout: 10000, polling: 50 });
    await page.mouse.move(center.x - 60, center.y + 35, { steps: 4 });
    await page.waitForFunction((sample) => {
      const module = window.__bwModule;
      return Number(module._bw_wm_tick_count()) > sample.ticks &&
        Number(module._bw_present_count()) > sample.presents;
    }, recoveryBefore, { timeout: 10000, polling: 50 });
    const recoveryAfter = await page.evaluate(() => ({
      ticks: Number(window.__bwModule._bw_wm_tick_count()),
      presents: Number(window.__bwModule._bw_present_count()),
    }));
    recovery = {
      ticks: recoveryAfter.ticks - recoveryBefore.ticks,
      presents: recoveryAfter.presents - recoveryBefore.presents,
    };
    await page.mouse.up({ button: "middle" });
    await page.waitForFunction(() => document.pointerLockElement === null, null,
      { timeout: 10000, polling: 50 });
  }
  if (rejected.length !== 0) {
    throw new Error(`product diagnostics rejected: ${rejected.join(" | ")}`);
  }

  console.log(
    "PRODUCT_POINTER_LOCK_LIVE PASS evidence=diagnostic-nonreceipt adapter=fallback-software " +
    `mode=${leaveActive ? "wrap-active" : "wrap-external-loss-reacquire-disable"} ` +
    `tick_delta=${after.ticks - before.ticks} present_delta=${after.presents - before.presents} ` +
    `recovery_tick_delta=${recovery.ticks} recovery_present_delta=${recovery.presents} ` +
    "present_rejections=0 device_lost=0");
}
finally {
  await browser.close();
}
