// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Browser-only behavior probe for the GHOST-web text clipboard bridge.

import {createServer} from "node:http";
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

const html = String.raw`<!doctype html>
<meta charset="utf-8">
<canvas id="canvas" width="320" height="200" tabindex="0"></canvas>
<script>
  const events = [];
  let cachedPaste = null;
  const canvas = document.querySelector("#canvas");
  const record = (type, value = null) => events.push({type, value});
  document.addEventListener("paste", (event) => {
    cachedPaste = event.clipboardData.getData("text/plain");
    record("paste", cachedPaste);
  }, true);
  document.addEventListener("copy", () => record("copy"), true);
  window.addEventListener("keydown", (event) => {
    record("keydown", event.code);
    if ((event.ctrlKey || event.metaKey) && event.code === "KeyV") {
      setTimeout(() => record("worker-consume", cachedPaste), 0);
    }
    if ((event.ctrlKey || event.metaKey) && event.code === "KeyC") {
      setTimeout(async () => {
        await navigator.clipboard.writeText("from-worker-copy-\u2713");
        record("worker-write");
      }, 0);
    }
  });
  globalThis.probe = {events, focus: () => canvas.focus()};
</script>`;

const server = createServer((request, response) => {
  response.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
  });
  response.end(html);
});
await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
const address = server.address();
const origin = `http://127.0.0.1:${address.port}`;

const browser = await chromium.launch({headless: process.env.BW_HEADED !== "1"});
try {
  const context = await browser.newContext();
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {origin});
  const page = await context.newPage();
  await page.goto(origin);
  await page.evaluate(async () => {
    await navigator.clipboard.writeText("from-system-paste-\ud83e\udeb6");
    globalThis.probe.focus();
  });
  await page.keyboard.press("Control+V");
  await page.waitForFunction(() => globalThis.probe.events.some((event) =>
    event.type === "worker-consume"));

  const pasteEvents = await page.evaluate(() => globalThis.probe.events.map((event) => ({...event})));
  const pasteIndex = pasteEvents.findIndex((event) => event.type === "paste");
  const consumeIndex = pasteEvents.findIndex((event) => event.type === "worker-consume");
  if (pasteIndex < 0 || consumeIndex <= pasteIndex ||
      pasteEvents[consumeIndex].value !== "from-system-paste-\ud83e\udeb6") {
    throw new Error(`paste event did not precede worker consumption: ${JSON.stringify(pasteEvents)}`);
  }

  await page.keyboard.press("Control+C");
  await page.waitForFunction(() => globalThis.probe.events.some((event) =>
    event.type === "worker-write"));
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  if (copied !== "from-worker-copy-\u2713") {
    throw new Error(`late worker clipboard write was not published: ${JSON.stringify(copied)}`);
  }

  console.log("GHOST_CLIPBOARD_BROWSER_PROBE PASS paste-before-worker=1 late-write=1 utf8=1");
}
finally {
  await browser.close();
  await new Promise((resolveClose) => server.close(resolveClose));
}
