// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Real PROXY_TO_PTHREAD browser check: window-level keyboard listeners must not
// deliver raw keys to Blender while a non-canvas control (including the hidden
// IME textarea in the product) owns DOM focus.

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

const port = Number(process.argv[2] || 8191);
const browser = await chromium.launch({headless: process.env.BW_HEADLESS === "1"});
const diagnostics = [];
try {
  const page = await browser.newPage({viewport: {width: 960, height: 640}});
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module && document.querySelector("#log")?.textContent.includes("window created");
  });

  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  await page.keyboard.press("a");
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("KeyDown"));

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    document.querySelector("#clear").focus();
  });
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("WindowDeactivate"));
  await page.evaluate(() => { document.querySelector("#log").textContent = ""; });
  await page.keyboard.press("b");
  await page.waitForTimeout(150);

  const snapshot = await page.evaluate(() => ({
    activeId: document.activeElement?.id || "",
    log: document.querySelector("#log")?.textContent || "",
  }));
  if (snapshot.activeId !== "clear") {
    throw new Error(`non-canvas control did not retain focus: ${JSON.stringify(snapshot)}`);
  }
  if (snapshot.log.includes("KeyDown") || snapshot.log.includes("KeyUp")) {
    throw new Error(
      `blurred canvas received raw keyboard input: ${JSON.stringify(snapshot)}`);
  }

  console.log("KEYBOARD_FOCUS_LIVE PASS focused=delivered blurred=suppressed worker=proxy-pthread");
}
catch (error) {
  error.message += ` | diagnostics=${diagnostics.join(" | ")}`;
  throw error;
}
finally {
  await browser.close();
}
