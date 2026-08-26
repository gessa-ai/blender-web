// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Real PROXY_TO_PTHREAD browser check: a button press owned by Blender must
// keep receiving motion plus its matching release when the pointer leaves the
// canvas, while unrelated window-level motion/releases remain outside GHOST.

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

const port = Number(process.argv[2] || 8192);
const browser = await chromium.launch({headless: process.env.BW_HEADLESS === "1"});
const diagnostics = [];
try {
  const page = await browser.newPage({viewport: {width: 960, height: 640}});
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module && typeof module._ghost_harness_input_state === "function" &&
      document.querySelector("#log")?.textContent.includes("window created");
  });

  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");

  await page.evaluate(() => { document.querySelector("#log").textContent = ""; });
  await page.mouse.move(box.x + box.width - 12, box.y + box.height / 2);
  await page.mouse.down({button: "left"});
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_input_state()) === (1 << 4));

  // Keep canvas focus but continue the drag over the neighboring panel. Both
  // motion and the terminal release remain owned by the canvas interaction.
  await page.mouse.move(box.x + box.width + 80, box.y + box.height / 2);
  await page.waitForTimeout(150);
  const dragLog = await page.locator("#log").textContent();
  const dragPositions = [...dragLog.matchAll(/CursorMove\s+x=(-?\d+) y=(-?\d+)/g)]
    .map((match) => ({x: Number(match[1]), y: Number(match[2])}));
  if (!dragPositions.some((position) => position.x > box.width)) {
    throw new Error(`owned outside motion was not delivered: ${dragLog}`);
  }

  await page.mouse.up({button: "left"});
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_input_state()) === 0);
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("ButtonUp"));

  const owned = await page.evaluate(() => ({
    activeId: document.activeElement?.id || "",
    log: document.querySelector("#log")?.textContent || "",
  }));
  if (owned.activeId !== "blender-canvas" || !owned.log.includes("ButtonUp")) {
    throw new Error(`owned outside release was not delivered: ${JSON.stringify(owned)}`);
  }

  const releasesBefore = (owned.log.match(/ButtonUp/g) || []).length;
  const movesBefore = (owned.log.match(/CursorMove/g) || []).length;
  const unrelatedPrevented = await page.evaluate(() => {
    const motion = new MouseEvent("mousemove", {
      buttons: 0,
      clientX: 920,
      clientY: 520,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(motion);
    const release = new MouseEvent("mouseup", {
      button: 0,
      buttons: 0,
      clientX: 900,
      clientY: 500,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(release);
    return motion.defaultPrevented || release.defaultPrevented;
  });
  await page.waitForTimeout(150);
  const finalLog = await page.locator("#log").textContent();
  const releasesAfter = (finalLog.match(/ButtonUp/g) || []).length;
  const movesAfter = (finalLog.match(/CursorMove/g) || []).length;
  if (unrelatedPrevented || releasesAfter !== releasesBefore || movesAfter !== movesBefore) {
    throw new Error(
      `unowned window pointer event entered GHOST: prevented=${unrelatedPrevented} ` +
      `releases=${releasesBefore}:${releasesAfter} moves=${movesBefore}:${movesAfter} ` +
      `log=${finalLog}`);
  }

  console.log(
    "MOUSE_RELEASE_OWNERSHIP_LIVE PASS motion=outside-delivered release=outside-delivered " +
    "unowned=suppressed focus=canvas worker=proxy-pthread");
}
catch (error) {
  error.message += ` | diagnostics=${diagnostics.join(" | ")}`;
  throw error;
}
finally {
  await browser.close();
}
