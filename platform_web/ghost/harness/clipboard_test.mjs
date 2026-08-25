// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Browser contract for the GHOST-web synchronous text clipboard facade.

import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

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
const origin = `http://127.0.0.1:${port}`;
const browserArgs = [];
if (process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({
  headless: process.env.BW_HEADED !== "1",
  args: browserArgs,
});
try {
  const context = await browser.newContext({viewport: {width: 960, height: 640}});
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {origin});
  const page = await context.newPage();
  const diagnostics = [];
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`${origin}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module &&
      typeof module._ghost_harness_request_clipboard_operation === "function" &&
      typeof module._ghost_harness_clipboard_result === "function" &&
      globalThis.__bwTextClipboardBridge?.schema === 1 &&
      document.querySelector("#log")?.textContent.includes("window created");
  });

  const runOperation = async (operation) => {
    const queued = await page.evaluate((value) => Number(
      globalThis.ghostModule._ghost_harness_request_clipboard_operation(value)), operation);
    if (queued !== 1) throw new Error(`clipboard operation ${operation} was not queued`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_clipboard_result()) !== -2);
    const result = await page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_clipboard_result()));
    if (result !== 1) throw new Error(`clipboard operation ${operation} failed: ${result}`);
  };

  // No ordinary text has been observed or written yet; primary remains unsupported.
  await runOperation(0);

  const external = "from-browser-paste-\ud83e\udeb6";
  await page.evaluate((text) => navigator.clipboard.writeText(text), external);
  const canvas = page.locator("#blender-canvas");
  await canvas.click({position: {x: 80, y: 70}});
  await page.keyboard.press("Control+V");
  await page.waitForFunction(() => {
    const snapshot = globalThis.__bwTextClipboardBridge?.snapshot();
    return snapshot?.source === "paste-event" && snapshot.utf8Bytes === 23;
  });
  await runOperation(1);

  // Blender's worker publishes borrowed UTF-8, including non-ASCII and a newline.
  await runOperation(2);
  await page.waitForFunction(() => {
    const snapshot = globalThis.__bwTextClipboardBridge?.snapshot();
    return snapshot?.source === "blender" && snapshot.writeStatus === "fulfilled";
  });
  const outbound = "from-ghost-worker-\u2713-\ud83e\udeb6\nline-2";
  const systemText = await page.evaluate(() => navigator.clipboard.readText());
  if (systemText !== outbound) {
    throw new Error(`worker clipboard write mismatch: ${JSON.stringify(systemText)}`);
  }
  await runOperation(3);

  // X11-style primary selection is not advertised and cannot poison ordinary text.
  await runOperation(4);
  await runOperation(5);

  // An empty clipboard is a valid owned string, distinct from initial unavailability.
  await runOperation(6);
  await page.waitForFunction(() =>
    globalThis.__bwTextClipboardBridge?.snapshot().writeStatus === "fulfilled");
  await runOperation(7);
  if (await page.evaluate(() => navigator.clipboard.readText()) !== "") {
    throw new Error("empty clipboard write was not preserved");
  }

  const snapshot = await page.evaluate(() => globalThis.__bwTextClipboardBridge.snapshot());
  if (Object.hasOwn(snapshot, "text") || snapshot.utf8Bytes !== 0 || diagnostics.length !== 0) {
    throw new Error(`clipboard diagnostics contract failed: ${JSON.stringify({snapshot, diagnostics})}`);
  }
  const invalid = await page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_request_clipboard_operation(99)));
  if (invalid !== 0) throw new Error(`invalid clipboard operation was accepted: ${invalid}`);

  console.log(
    "GHOST_CLIPBOARD_BROWSER PASS paste=external put=system utf8=owned empty=distinct primary=off");
}
finally {
  await browser.close();
}
