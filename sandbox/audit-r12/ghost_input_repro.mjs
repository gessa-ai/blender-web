// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Audit R12 repro for two GHOST-web input-ordering regressions. Serve the real
// PROXY_TO_PTHREAD harness with COOP/COEP, then pass its port as argv[2].

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

const port = Number(process.argv[2] || 8137);
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 960, height: 640}});
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module && typeof module._ghost_harness_request_ime === "function" &&
      document.querySelector("#log")?.textContent.includes("window created");
  });

  const requestIme = async (action) => {
    const accepted = await page.evaluate((value) => Number(
      globalThis.ghostModule._ghost_harness_request_ime(value, 37, 53, 18, 22, 0)), action);
    if (accepted !== 1) throw new Error(`IME action ${action} was rejected`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_ime_result()) !== -2);
    const result = await page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_ime_result()));
    if (result !== 1) throw new Error(`IME action ${action} failed: ${result}`);
  };

  await page.evaluate(() => {
    globalThis.__auditR12Keys = [];
    document.querySelector("#bw-ime-input").addEventListener("keydown", (event) => {
      globalThis.__auditR12Keys.push({
        key: event.key,
        code: event.code,
        trusted: event.isTrusted,
        composing: event.isComposing,
      });
    });
    document.querySelector("#log").textContent = "";
  });
  await requestIme(0);
  await page.keyboard.type("a");
  await page.keyboard.press("Backspace");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(100);
  const ime = await page.evaluate(() => ({
    active: document.activeElement?.id || "",
    domKeys: globalThis.__auditR12Keys,
    ghostLines: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("Key") || line.includes("Ime")),
    value: document.querySelector("#bw-ime-input").value,
  }));
  if (ime.active !== "bw-ime-input" || ime.domKeys.length !== 3 ||
      ime.domKeys.some((event) => !event.trusted || event.composing) ||
      ime.ghostLines.length !== 0 || ime.value !== "") {
    throw new Error(`ordinary IME-focused key repro changed: ${JSON.stringify(ime)}`);
  }
  await requestIme(1);

  await page.evaluate(() => {
    const log = document.querySelector("#log");
    const clear = document.querySelector("#clear");
    const canvas = document.querySelector("#blender-canvas");
    log.textContent = "";
    clear.focus();
    canvas.focus();
    canvas.dispatchEvent(new KeyboardEvent("keydown", {
      key: "x", code: "KeyX", bubbles: true, cancelable: true,
    }));
    canvas.dispatchEvent(new KeyboardEvent("keyup", {
      key: "x", code: "KeyX", bubbles: true, cancelable: true,
    }));
  });
  await page.waitForFunction(() => {
    const log = document.querySelector("#log")?.textContent || "";
    return log.includes("KeyUp") && log.includes("WindowActivate");
  });
  const focusOrder = await page.evaluate(() => document.querySelector("#log").textContent
    .split("\n")
    .filter(Boolean)
    .map((line) => line.replace(/\s+/g, " ").trim()));
  const categories = focusOrder.map((line) => {
    if (line.includes("KeyDown")) return "key-down";
    if (line.includes("KeyUp")) return "key-up";
    if (line.includes("WindowDeactivate")) return "deactivate";
    if (line.includes("WindowActivate")) return "activate";
    return "other";
  });
  const expected = ["key-down", "key-up", "deactivate", "activate"];
  if (JSON.stringify(categories) !== JSON.stringify(expected)) {
    throw new Error(`focus/input ordering repro changed: ${JSON.stringify(focusOrder)}`);
  }

  console.log(
    "AUDIT_R12_GHOST_INPUT_REPRO CONFIRMED " +
    "ime=trusted-noncomposing-dom-3,ghost-0 " +
    "focus-order=key-down,key-up,deactivate,activate");
}
finally {
  await browser.close();
}
