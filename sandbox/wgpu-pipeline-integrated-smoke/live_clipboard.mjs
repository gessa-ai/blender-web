// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Product-level GHOST text clipboard diagnostic. The forced software adapter is
// explicitly nonreceipt evidence; this validates browser/WM clipboard wiring only.

import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

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
const origin = `http://127.0.0.1:${port}`;
const headless = process.env.BW_HEADED !== "1";
const browserArgs = [
  "--enable-unsafe-webgpu",
  "--use-webgpu-adapter=swiftshader",
  "--use-gpu-in-tests",
];
if (!headless && process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({headless, args: browserArgs});
try {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {origin});
  const page = await context.newPage();
  const rejected = [];
  page.on("console", (message) => {
    const line = message.text();
    if (/present (queue submission|transaction) rejected|GPU-LOST|preinit FAILED/.test(line)) {
      rejected.push(line);
    }
  });
  page.on("pageerror", (error) => rejected.push(`pageerror:${error.message}`));

  await page.goto(`${origin}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() =>
    document.querySelector("#state")?.dataset.state === "running", null,
  {timeout: 180000, polling: 250});
  try {
    await page.waitForFunction(() => {
      const module = window.__bwModule;
      return module && Number(module._bw_wm_tick_count?.()) >= 2 &&
        Number(module._bw_present_count?.()) >= 2 &&
        window.__bwTextClipboardBridge?.schema === 1;
    }, null, {timeout: 30000, polling: 100});
  }
  catch (error) {
    const state = await page.evaluate(() => ({
      state: document.querySelector("#state")?.dataset.state ?? null,
      module: Boolean(window.__bwModule),
      ticks: Number(window.__bwModule?._bw_wm_tick_count?.() ?? -1),
      presents: Number(window.__bwModule?._bw_present_count?.() ?? -1),
      clipboardBridge: window.__bwTextClipboardBridge?.snapshot?.() ?? null,
    }));
    throw new Error(`product clipboard startup did not settle: ${JSON.stringify(state)}`, {
      cause: error,
    });
  }

  const canvas = page.locator("#canvas");
  const bounds = await canvas.boundingBox();
  if (!bounds || bounds.width < 400 || bounds.height < 300) {
    throw new Error(`invalid product canvas bounds: ${JSON.stringify(bounds)}`);
  }
  await canvas.click({position: {x: 80, y: 80}});
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);

  // Shift-F4 changes the hovered Blender area to the Python Console. The one
  // pasted expression must traverse browser paste -> GHOST getClipboard, then
  // execute WM.clipboard -> GHOST putClipboard -> browser system clipboard.
  await page.mouse.move(bounds.x + bounds.width * 0.45, bounds.y + bounds.height * 0.45);
  await page.keyboard.press("Shift+F4");
  await page.waitForTimeout(500);
  const marker = "BW_PRODUCT_CLIPBOARD_PASS_20260825";
  const expression = `bpy.context.window_manager.clipboard=${JSON.stringify(marker)}`;
  await page.evaluate((text) => navigator.clipboard.writeText(text), expression);
  const ticksBeforePaste = await page.evaluate(() =>
    Number(window.__bwModule._bw_wm_tick_count()));
  await page.keyboard.press("Control+V");
  await page.waitForFunction((before) => {
    const snapshot = window.__bwTextClipboardBridge?.snapshot();
    return snapshot?.source === "paste-event" &&
      Number(window.__bwModule?._bw_wm_tick_count?.()) >= before + 2;
  }, ticksBeforePaste, {timeout: 5000, polling: 50});
  await page.keyboard.press("Enter");

  await page.waitForFunction(async (expected) => {
    try {
      return await navigator.clipboard.readText() === expected;
    }
    catch (_) {
      return false;
    }
  }, marker, {timeout: 15000, polling: 100});
  const snapshot = await page.evaluate(() => window.__bwTextClipboardBridge.snapshot());
  if (snapshot.source !== "blender" || snapshot.writeStatus !== "fulfilled" ||
      snapshot.utf8Bytes !== marker.length || Object.hasOwn(snapshot, "text")) {
    throw new Error(`product clipboard snapshot rejected: ${JSON.stringify(snapshot)}`);
  }
  if (rejected.length !== 0) {
    throw new Error(`product diagnostics rejected: ${rejected.join(" | ")}`);
  }
  console.log(
    "PRODUCT_CLIPBOARD_LIVE PASS evidence=diagnostic-nonreceipt adapter=fallback-software " +
    `paste=ghost-get copy=ghost-put utf8_bytes=${snapshot.utf8Bytes} ` +
    "present_rejections=0 device_lost=0");
}
finally {
  await browser.close();
}
