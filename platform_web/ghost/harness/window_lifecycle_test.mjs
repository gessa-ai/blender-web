// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract: disposing the active canvas window must detach every
// system lookup before deletion, and a replacement window must become the new
// callback/event target in the shipping PROXY_TO_PTHREAD topology.

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
      return module &&
        typeof module._ghost_harness_request_window_lifecycle === "function" &&
        typeof module._ghost_harness_window_lifecycle_result === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const request = async (action) => {
    const accepted = await page.evaluate((value) => Number(
      globalThis.ghostModule._ghost_harness_request_window_lifecycle(value)), action);
    if (accepted !== 1) {
      throw new Error(`window lifecycle action ${action} was not accepted: ${accepted}`);
    }
    await page.waitForFunction(() => Number(
      globalThis.ghostModule._ghost_harness_window_lifecycle_result()) !== -2);
    return page.evaluate(() => Number(
      globalThis.ghostModule._ghost_harness_window_lifecycle_result()));
  };

  const disposeResult = await request(0);
  // Bits: active-before, base-dispose-success, active-null, under-cursor-null.
  if (disposeResult !== 0b1111) {
    throw new Error(
      `active window was not detached before/after disposal: result=${disposeResult}`);
  }

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
  });
  await page.locator("#blender-canvas").focus();
  await page.keyboard.press("a");
  await page.waitForTimeout(100);
  const detachedLog = await page.locator("#log").textContent();
  if (detachedLog.includes("KeyDown") || detachedLog.includes("KeyUp")) {
    throw new Error(`disposed window callbacks still delivered input: ${detachedLog}`);
  }

  const recreateResult = await request(1);
  // Bits: replacement-created, replacement-active, under-cursor-is-replacement.
  if (recreateResult !== 0b111) {
    throw new Error(`replacement window was not published: result=${recreateResult}`);
  }

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
  });
  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  await page.keyboard.press("a");
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("KeyDown"));
  const callbackFailures = diagnostics.filter((line) =>
    line.includes("HTML5 callbacks failed to unregister"));
  if (callbackFailures.length !== 0) {
    throw new Error(`callback removal reported failure: ${callbackFailures.join(" | ")}`);
  }

  console.log(
    "WINDOW_LIFECYCLE_LIVE PASS dispose=detached callbacks=rebound replacement=input-target " +
    "worker=proxy-pthread");
}
finally {
  await browser.close();
}
