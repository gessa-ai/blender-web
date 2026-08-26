// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Forced-software product diagnostic: trusted ordinary keys travel from the
// owned IME textarea through GHOST into Blender's stock object-name editor.
// This is text-state evidence only and binds no WebGPU receipt.

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

const port = Number(process.argv[2] || 8199);
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
const rejected = [];
try {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {origin});
  const page = await context.newPage();
  page.on("console", (message) => {
    const line = message.text();
    if (/preinit FAILED|GPU-LOST|present (queue submission|transaction) rejected/.test(line)) {
      rejected.push(line);
    }
  });
  page.on("pageerror", (error) => rejected.push(`pageerror:${error.message}`));

  await page.goto(`${origin}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() =>
    document.querySelector("#state")?.dataset.state === "running", null,
  {timeout: 180000, polling: 250});
  await page.waitForFunction(() => {
    const module = globalThis.__bwModule;
    return module && Number(module._bw_wm_tick_count?.()) >= 2 &&
      globalThis.__bwImeBridge?.schema === 1;
  }, null, {timeout: 30000, polling: 100});

  const canvas = page.locator("#canvas");
  const bounds = await canvas.boundingBox();
  if (!bounds || bounds.width < 400 || bounds.height < 300) {
    throw new Error(`invalid product canvas bounds: ${JSON.stringify(bounds)}`);
  }
  await canvas.click({position: {x: bounds.width * 0.45, y: bounds.height * 0.45}});
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);

  const beginRename = async () => {
    await page.keyboard.press("F2");
    await page.waitForFunction(() => {
      const snapshot = globalThis.__bwImeBridge?.snapshot();
      return snapshot?.enabled && snapshot.focused &&
        document.activeElement?.id === "bw-ime-input";
    }, null, {timeout: 15000, polling: 50});
  };

  await beginRename();
  const before = await page.evaluate(() => globalThis.__bwImeBridge.snapshot());
  await page.keyboard.press("Control+a");
  await page.keyboard.type("BWKEY_0123");
  await page.keyboard.press("Home");
  await page.keyboard.press("End");
  await page.keyboard.press("Backspace");
  await page.keyboard.type("X");
  await page.keyboard.press("Control+a");
  await page.keyboard.press("Control+c");
  await page.keyboard.press("Control+x");
  await page.keyboard.press("Control+v");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !globalThis.__bwImeBridge.snapshot().enabled, null,
    {timeout: 15000, polling: 50});
  const expectedName = "BWKEY_012X";

  // Exercise Escape through the same textarea without changing committed state.
  await beginRename();
  await page.keyboard.press("Control+a");
  await page.keyboard.type("MUST_NOT_COMMIT");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !globalThis.__bwImeBridge.snapshot().enabled, null,
    {timeout: 15000, polling: 50});

  // Blender itself supplies the state oracle. The Python Console reads the
  // committed object name and returns it through GHOST's clipboard bridge.
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
  }, expectedName, {timeout: 15000, polling: 100});

  const after = await page.evaluate(() => globalThis.__bwImeBridge.snapshot());
  if (after.rawKeyAdmitted <= before.rawKeyAdmitted + 40 ||
      after.rawKeySuppressed !== before.rawKeySuppressed || rejected.length !== 0) {
    throw new Error(`product ordinary-key evidence rejected: ${JSON.stringify({
      before, after, rejected,
    })}`);
  }
  console.log(
    "PRODUCT_IME_NONCOMPOSING_LIVE PASS evidence=diagnostic-nonreceipt " +
    "adapter=fallback-software keys=ascii,navigation,control,clipboard,escape,enter " +
    `state=object-rename:${expectedName} raw_admitted_delta=${after.rawKeyAdmitted - before.rawKeyAdmitted}`);
}
finally {
  await browser.close();
}
