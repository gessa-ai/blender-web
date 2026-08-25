// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Browser contract for WM-worker RGBA/XBM custom cursor publication.

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
  const context = await browser.newContext({viewport: {width: 960, height: 640}});
  const page = await context.newPage();
  const diagnostics = [];
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  try {
    await page.waitForFunction(() => {
      const module = globalThis.ghostModule;
      const bridge = globalThis.__bwCursorBridge;
      return module && bridge?.schema === 2 &&
        typeof module._ghost_harness_request_custom_cursor === "function" &&
        typeof module._ghost_harness_custom_cursor_result === "function" &&
        typeof module._ghost_harness_custom_cursor_capabilities === "function" &&
        bridge.snapshot() && document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`custom cursor harness did not initialize: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const capabilities = await page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_custom_cursor_capabilities()));
  if (capabilities !== 1) {
    throw new Error(`cursor capabilities differ: ${capabilities}`);
  }

  const request = async (operation) => {
    const queued = await page.evaluate((value) => Number(
      globalThis.ghostModule._ghost_harness_request_custom_cursor(value)), operation);
    if (queued !== 1) throw new Error(`custom cursor operation ${operation} was not queued`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_custom_cursor_result()) !== -2);
    return page.evaluate(() => Number(
      globalThis.ghostModule._ghost_harness_custom_cursor_result()));
  };

  const snapshot = () => page.evaluate(() => globalThis.__bwCursorBridge.snapshot());
  const requestAndWaitForGeneration = async (operation) => {
    const before = await snapshot();
    const result = await request(operation);
    if (result !== 1) throw new Error(`custom cursor operation ${operation} failed: ${result}`);
    await page.waitForFunction((generation) =>
      globalThis.__bwCursorBridge.snapshot()?.generation !== generation, before.generation);
    return snapshot();
  };
  const decodeCustomCursor = () => page.evaluate(async () => {
    const current = globalThis.__bwCursorBridge.snapshot();
    const match = /^url\("([^"]+)"\) (\d+) (\d+), default$/.exec(current.css);
    if (!match) throw new Error(`custom cursor CSS differs: ${current.css}`);
    const image = new Image();
    const loaded = new Promise((resolveLoaded, rejectLoaded) => {
      image.onload = resolveLoaded;
      image.onerror = rejectLoaded;
    });
    image.src = match[1];
    await loaded;
    const raster = document.createElement("canvas");
    raster.width = image.width;
    raster.height = image.height;
    const context2d = raster.getContext("2d");
    context2d.drawImage(image, 0, 0);
    return {
      snapshot: current,
      hotSpot: [Number(match[2]), Number(match[3])],
      size: [image.width, image.height],
      pixels: Array.from(context2d.getImageData(0, 0, image.width, image.height).data),
    };
  });

  await requestAndWaitForGeneration(0);
  const rgba = await decodeCustomCursor();
  const expectedRgba = [
    255, 0, 0, 255, 0, 255, 0, 128,
    0, 0, 255, 64, 0, 0, 0, 0,
  ];
  if (rgba.snapshot.shape !== 46 || rgba.size.join() !== "2,2" ||
      rgba.hotSpot.join() !== "1,0" || rgba.pixels.join() !== expectedRgba.join()) {
    throw new Error(`RGBA cursor differs: ${JSON.stringify(rgba)}`);
  }

  await requestAndWaitForGeneration(1);
  const xbm = await decodeCustomCursor();
  const expectedXbm = [
    255, 255, 255, 255, 0, 0, 0, 255,
    0, 0, 0, 0, 255, 255, 255, 255,
  ];
  if (xbm.snapshot.shape !== 46 || xbm.hotSpot.join() !== "0,1" ||
      xbm.pixels.join() !== expectedXbm.join()) {
    throw new Error(`XBM cursor differs: ${JSON.stringify(xbm)}`);
  }

  const beforeInvalid = await snapshot();
  if (await request(2) !== 0) throw new Error("invalid custom cursor was accepted");
  const afterInvalid = await snapshot();
  if (JSON.stringify(afterInvalid) !== JSON.stringify(beforeInvalid)) {
    throw new Error("invalid custom cursor replaced published state");
  }

  const hidden = await requestAndWaitForGeneration(4);
  if (hidden.css !== "none" || hidden.visible !== false) {
    throw new Error(`hidden custom cursor differs: ${JSON.stringify(hidden)}`);
  }
  const shown = await requestAndWaitForGeneration(5);
  if (shown.css !== xbm.snapshot.css || shown.visible !== true) {
    throw new Error(`restored custom cursor differs: ${JSON.stringify(shown)}`);
  }
  const standard = await requestAndWaitForGeneration(3);
  if (standard.shape !== 7 || standard.css !== "text") {
    throw new Error(`standard cursor regression: ${JSON.stringify(standard)}`);
  }

  console.log(
    "CUSTOM_CURSOR_LIVE PASS capabilities=rgba,!generator rgba=2x2@1,0 " +
    "xbm=2x2@0,1 invalid=closed visibility=retained standard=text");
}
finally {
  await browser.close();
}
