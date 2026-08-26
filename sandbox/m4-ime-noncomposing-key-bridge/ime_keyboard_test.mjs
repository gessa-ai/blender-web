// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

// Real PROXY_TO_PTHREAD browser contract for the Blender-owned IME textarea:
// trusted non-composing keys must reach GHOST, active composition must not also
// emit raw keys, and an unrelated page control must remain outside the domain.

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

const port = Number(process.argv[2] || 8198);
const browser = await chromium.launch({headless: process.env.BW_HEADED !== "1"});
const diagnostics = [];
try {
  const page = await browser.newPage({viewport: {width: 960, height: 640}});
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.push(`console:${message.text()}`);
  });
  page.on("pageerror", (error) => diagnostics.push(`pageerror:${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module && typeof module._ghost_harness_request_ime === "function" &&
      typeof module._bw_shell_ime_consumed_count === "function" &&
      globalThis.__bwImeBridge?.schema === 1 &&
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
    globalThis.__bwTrustedImeKeys = [];
    const input = document.querySelector("#bw-ime-input");
    for (const type of ["keydown", "keyup"]) {
      input.addEventListener(type, (event) => {
        globalThis.__bwTrustedImeKeys.push({
          type,
          key: event.key,
          code: event.code,
          trusted: event.isTrusted,
          composing: event.isComposing,
        });
      });
    }
    document.querySelector("#log").textContent = "";
  });
  await requestIme(0);
  await page.keyboard.type("a");
  for (const key of ["ArrowLeft", "Backspace", "Enter", "Escape"]) {
    await page.keyboard.press(key);
  }
  for (const shortcut of ["Control+c", "Control+x", "Control+v"]) {
    await page.keyboard.press(shortcut);
  }
  await page.waitForFunction(() => document.querySelector("#log").textContent
    .split("\n").filter((line) => line.includes("GHOST Key")).length === 22);

  const ordinary = await page.evaluate(() => ({
    active: document.activeElement?.id || "",
    domKeys: globalThis.__bwTrustedImeKeys,
    ghostKeys: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("GHOST Key"))
      .map((line) => line.replace(/\s+/g, " ").trim()),
    value: document.querySelector("#bw-ime-input").value,
  }));
  const domDown = ordinary.domKeys.filter((event) => event.type === "keydown")
    .map((event) => event.key);
  const expectedDown = [
    "a", "ArrowLeft", "Backspace", "Enter", "Escape",
    "Control", "c", "Control", "x", "Control", "v",
  ];
  if (ordinary.active !== "bw-ime-input" || ordinary.value !== "" ||
      ordinary.domKeys.length !== 22 ||
      ordinary.domKeys.some((event) => !event.trusted || event.composing) ||
      JSON.stringify(domDown) !== JSON.stringify(expectedDown) ||
      ordinary.ghostKeys.length !== 22 ||
      !ordinary.ghostKeys.some((line) => line.includes("KeyDown") && line.includes("utf8='a'"))) {
    throw new Error(`ordinary IME keyboard contract failed: ${JSON.stringify(ordinary)}`);
  }

  const consumedBefore = await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    return Number(globalThis.ghostModule._bw_shell_ime_consumed_count());
  });
  await page.evaluate(() => {
    const input = document.querySelector("#bw-ime-input");
    input.dispatchEvent(new CompositionEvent("compositionstart", {data: "", bubbles: true}));
    input.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Process", code: "KeyA", bubbles: true, cancelable: true,
    }));
    input.dispatchEvent(new KeyboardEvent("keyup", {
      key: "Process", code: "KeyA", bubbles: true, cancelable: true,
    }));
    input.dispatchEvent(new CompositionEvent("compositionupdate", {data: "に", bubbles: true}));
    input.dispatchEvent(new CompositionEvent("compositionend", {data: "に", bubbles: true}));
  });
  await page.waitForFunction((before) =>
    Number(globalThis.ghostModule._bw_shell_ime_consumed_count()) >= before + 4,
  consumedBefore);
  const composition = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    lines: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("GHOST Key") || line.includes("GHOST Ime"))
      .map((line) => line.replace(/\s+/g, " ").trim()),
  }));
  if (composition.lines.some((line) => line.includes("GHOST Key")) ||
      composition.lines.filter((line) => line.includes("GHOST Ime")).length !== 4 ||
      composition.snapshot.composing || composition.snapshot.lastKind !== "end") {
    throw new Error(`composition duplicated raw keys: ${JSON.stringify(composition)}`);
  }

  await requestIme(1);
  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    document.querySelector("#clear").focus();
  });
  await page.keyboard.press("b");
  await page.waitForTimeout(150);
  const external = await page.evaluate(() => ({
    active: document.activeElement?.id || "",
    keys: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("GHOST Key")),
  }));
  if (external.active !== "clear" || external.keys.length !== 0 || diagnostics.length !== 0) {
    throw new Error(`external keyboard ownership failed: ${JSON.stringify({external, diagnostics})}`);
  }

  console.log(
    "IME_NONCOMPOSING_KEYS_LIVE PASS trusted=ascii,navigation,control,clipboard " +
    "composition=raw-suppressed external=control-suppressed worker=proxy-pthread");
}
catch (error) {
  error.message += ` | diagnostics=${diagnostics.join(" | ")}`;
  throw error;
}
finally {
  await browser.close();
}
