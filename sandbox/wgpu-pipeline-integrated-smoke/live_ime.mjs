// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Product-level browser composition diagnostic. The forced software adapter is
// explicitly nonreceipt evidence; this validates DOM -> GHOST -> Blender text edit.

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
  await page.waitForFunction(() => {
    const module = window.__bwModule;
    return module && Number(module._bw_wm_tick_count?.()) >= 2 &&
      Number(module._bw_present_count?.()) >= 2 &&
      typeof module._bw_shell_ime_consumed_count === "function" &&
      window.__bwImeBridge?.schema === 1;
  }, null, {timeout: 30000, polling: 100});

  const canvas = page.locator("#canvas");
  const bounds = await canvas.boundingBox();
  if (!bounds || bounds.width < 400 || bounds.height < 300) {
    throw new Error(`invalid product canvas bounds: ${JSON.stringify(bounds)}`);
  }
  await canvas.click({position: {x: 80, y: 80}});
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  await page.mouse.move(bounds.x + bounds.width * 0.45, bounds.y + bounds.height * 0.45);

  // F2 opens Blender's stock object-name text button. Its interface handler calls
  // wm_window_IME_begin, which must focus the hidden browser input at the caret.
  await page.keyboard.press("F2");
  await page.waitForFunction(() => {
    const snapshot = window.__bwImeBridge?.snapshot();
    return snapshot?.enabled && snapshot.focused && document.activeElement?.id === "bw-ime-input";
  }, null, {timeout: 5000, polling: 50});
  const before = await page.evaluate(() => ({
    sequence: window.__bwImeBridge.snapshot().sequence,
    accepted: window.__bwImeBridge.snapshot().accepted,
    rejected: window.__bwImeBridge.snapshot().rejected,
    published: Number(window.__bwModule._bw_shell_ime_published_count()),
    consumed: Number(window.__bwModule._bw_shell_ime_consumed_count()),
    dropped: Number(window.__bwModule._bw_shell_ime_dropped_count()),
    presents: Number(window.__bwModule._bw_present_count()),
  }));

  const marker = "BW_IME_鶴_🪶";
  await page.evaluate((text) => {
    const input = document.querySelector("#bw-ime-input");
    input.dispatchEvent(new CompositionEvent("compositionstart", {data: "", bubbles: true}));
    input.dispatchEvent(new CompositionEvent("compositionupdate", {data: text, bubbles: true}));
    input.dispatchEvent(new CompositionEvent("compositionend", {data: text, bubbles: true}));
  }, marker);
  await page.waitForFunction((sample) =>
    Number(window.__bwModule._bw_shell_ime_consumed_count()) >= sample.consumed + 4,
  before, {timeout: 5000, polling: 25});
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !window.__bwImeBridge.snapshot().enabled, null,
    {timeout: 5000, polling: 50});

  // Read Blender's committed object name through its own Python console and
  // GHOST clipboard path, avoiding screenshot/OCR as a state oracle.
  await page.mouse.move(bounds.x + bounds.width * 0.45, bounds.y + bounds.height * 0.45);
  await page.keyboard.press("Shift+F4");
  await page.waitForTimeout(500);
  await page.keyboard.type("bpy.context.window_manager.clipboard=bpy.context.active_object.name");
  await page.keyboard.press("Enter");
  await page.waitForFunction(async (expected) => {
    try {
      return await navigator.clipboard.readText() === expected;
    }
    catch (_) {
      return false;
    }
  }, marker, {timeout: 15000, polling: 100});

  const after = await page.evaluate(() => ({
    snapshot: window.__bwImeBridge.snapshot(),
    published: Number(window.__bwModule._bw_shell_ime_published_count()),
    consumed: Number(window.__bwModule._bw_shell_ime_consumed_count()),
    dropped: Number(window.__bwModule._bw_shell_ime_dropped_count()),
    presents: Number(window.__bwModule._bw_present_count()),
  }));
  if (after.published !== before.published + 4 || after.consumed !== before.consumed + 4 ||
      after.dropped !== before.dropped || after.snapshot.sequence !== before.sequence + 4 ||
      after.snapshot.accepted !== before.accepted + 4 ||
      after.snapshot.rejected !== before.rejected || after.presents <= before.presents ||
      rejected.length !== 0) {
    throw new Error(`product IME evidence rejected: ${JSON.stringify({before, after, rejected})}`);
  }
  console.log(
    "PRODUCT_IME_LIVE PASS evidence=diagnostic-nonreceipt adapter=fallback-software " +
    "events=start,update,commit,end state=object-rename utf8=ghost-to-blender " +
    `present_delta=${after.presents - before.presents} present_rejections=0 device_lost=0`);
}
finally {
  await browser.close();
}
