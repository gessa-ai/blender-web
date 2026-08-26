// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract: losing canvas focus must retire GHOST's tracked
// modifier/button state even when the browser cannot deliver matching key-up or
// mouse-up events.

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
      return module && typeof module._ghost_harness_input_state === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const inputState = () => page.evaluate(() =>
    Number(globalThis.ghostModule._ghost_harness_input_state()));
  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  await page.keyboard.down("Control");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  await page.mouse.move(box.x + 120, box.y + 100);
  await page.mouse.down({ button: "left" });

  const held = (1 << 0) | (1 << 4);
  await page.waitForFunction((expected) =>
    Number(globalThis.ghostModule._ghost_harness_input_state()) === expected, held);

  // Move focus without releasing either input. A real tab switch/window blur has
  // the same defining behavior: no matching release is guaranteed to reach GHOST.
  await page.evaluate(() => document.querySelector("#clear").focus());
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("WindowDeactivate"));
  const afterBlur = await inputState();
  if (afterBlur !== 0) {
    throw new Error(
      `focus loss retained stale GHOST input state: held=${held} afterBlur=${afterBlur}`);
  }
  const afterBlurLog = await page.locator("#log").textContent();
  if (!afterBlurLog.includes("ButtonUp")) {
    throw new Error(`focus loss did not synthesize the held button release: ${afterBlurLog}`);
  }

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
  });
  await canvas.focus();
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("WindowActivate"));
  const afterRefocus = await inputState();
  if (afterRefocus !== 0) {
    throw new Error(`refocus resurrected stale GHOST input state: ${afterRefocus}`);
  }

  console.log(
    "FOCUS_STATE_LIVE PASS held=ctrl+left blur=cleared refocus=clear worker=proxy-pthread");
}
finally {
  await browser.close();
}
