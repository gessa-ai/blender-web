// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Browser contract for DOM composition -> WM-worker GHOST IME events.

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
const browser = await chromium.launch({headless: process.env.BW_HEADED !== "1"});
try {
  const context = await browser.newContext({viewport: {width: 960, height: 640}});
  const page = await context.newPage();
  const diagnostics = [];
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module &&
      typeof module._ghost_harness_request_ime === "function" &&
      typeof module._ghost_harness_ime_result === "function" &&
      typeof module._ghost_harness_ime_capability === "function" &&
      typeof module._ghost_harness_window_manager_state === "function" &&
      typeof module._bw_shell_ime_consumed_count === "function" &&
      typeof module._bw_shell_ime_recovered_count === "function" &&
      globalThis.__bwImeBridge?.schema === 1 &&
      document.querySelector("#log")?.textContent.includes("window created");
  });

  const capability = await page.evaluate(() =>
    Number(globalThis.ghostModule._ghost_harness_ime_capability()));
  if (capability !== 1) throw new Error(`IME capability is not advertised: ${capability}`);

  const requestIme = async (action, completed = 0) => {
    const accepted = await page.evaluate(({action, completed}) => Number(
      globalThis.ghostModule._ghost_harness_request_ime(
        action, 37, 53, 18, 22, completed)), {action, completed});
    if (accepted !== 1) throw new Error(`IME action ${action} was rejected`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_ime_result()) !== -2);
    const result = await page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_ime_result()));
    if (result !== 1) throw new Error(`IME action ${action} failed: ${result}`);
  };

  await page.evaluate(() => { document.querySelector("#log").textContent = ""; });
  await requestIme(0);
  await page.waitForTimeout(100);
  const begun = await page.evaluate(() => {
    const input = document.querySelector("#bw-ime-input");
    const canvas = document.querySelector("#blender-canvas");
    const inputBounds = input.getBoundingClientRect();
    const canvasBounds = canvas.getBoundingClientRect();
    return {
      snapshot: globalThis.__bwImeBridge.snapshot(),
      id: document.activeElement?.id,
      offsetX: Math.round(inputBounds.left - canvasBounds.left),
      offsetY: Math.round(inputBounds.top - canvasBounds.top),
      width: Math.round(inputBounds.width),
      height: Math.round(inputBounds.height),
      manager: Number(globalThis.ghostModule._ghost_harness_window_manager_state()),
      log: document.querySelector("#log").textContent,
    };
  });
  if (!begun.snapshot.enabled || !begun.snapshot.focused || begun.id !== "bw-ime-input" ||
      Math.abs(begun.offsetX - 37) > 1 || Math.abs(begun.offsetY - 53) > 1 ||
      begun.width !== 18 || begun.height !== 22 || begun.manager !== 1 ||
      begun.log.includes("WindowDeactivate") || begun.log.includes("WindowActivate")) {
    throw new Error(`IME caret/focus contract failed: ${JSON.stringify(begun)}`);
  }

  await page.evaluate(() => {
    const input = document.querySelector("#bw-ime-input");
    const dispatch = (type, data) => input.dispatchEvent(
      new CompositionEvent(type, {data, bubbles: true}));
    dispatch("compositionstart", "");
    dispatch("compositionupdate", "に");
    dispatch("compositionupdate", "日本🪶");
    dispatch("compositionend", "日本🪶");
  });
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._bw_shell_ime_consumed_count()) >= 5 &&
    document.querySelector("#log")?.textContent.includes("GHOST ImeEnd"));

  const evidence = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    consumed: Number(globalThis.ghostModule._bw_shell_ime_consumed_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
    lines: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.startsWith("GHOST Ime"))
      .map((line) => line.replace(/\s+/g, " ").trim()),
  }));
  const expected = [
    "GHOST ImeStart result='' composite='' cursor=0 target=-1:-1",
    "GHOST ImeComposition result='' composite='に' cursor=3 target=-1:-1",
    "GHOST ImeComposition result='' composite='日本🪶' cursor=10 target=-1:-1",
    "GHOST ImeComposition result='日本🪶' composite='' cursor=-1 target=-1:-1",
    "GHOST ImeEnd result='' composite='' cursor=-1 target=-1:-1",
  ];
  if (JSON.stringify(evidence.lines) !== JSON.stringify(expected) ||
      evidence.published !== 5 || evidence.consumed !== 5 || evidence.dropped !== 0 ||
      evidence.recovered !== 0 || evidence.snapshot.recovered !== 0 ||
      evidence.snapshot.accepted !== 5 || evidence.snapshot.rejected !== 0 ||
      evidence.snapshot.lastKind !== "end" || evidence.snapshot.lastUtf8Bytes !== 0 ||
      Object.hasOwn(evidence.snapshot, "text")) {
    throw new Error(`IME event contract failed: ${JSON.stringify(evidence)}`);
  }

  await requestIme(1);
  const ended = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    active: document.activeElement?.id,
    manager: Number(globalThis.ghostModule._ghost_harness_window_manager_state()),
    log: document.querySelector("#log").textContent,
  }));
  if (ended.snapshot.enabled || ended.snapshot.focused || ended.active !== "blender-canvas" ||
      ended.manager !== 1 || ended.log.includes("WindowDeactivate") ||
      ended.log.includes("WindowActivate")) {
    throw new Error(`IME end/focus contract failed: ${JSON.stringify(ended)}`);
  }

  // A page control is outside Blender's focus domain and must still deactivate
  // the GHOST window exactly once; returning to the canvas reactivates it once.
  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    document.querySelector("#clear").focus();
  });
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 0 &&
    document.querySelector("#log").textContent.includes("WindowDeactivate"));
  await page.locator("#blender-canvas").focus();
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 1 &&
    document.querySelector("#log").textContent.includes("WindowActivate"));
  const externalFocus = await page.evaluate(() => ({
    active: document.activeElement?.id,
    manager: Number(globalThis.ghostModule._ghost_harness_window_manager_state()),
    transitions: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("WindowActivate") || line.includes("WindowDeactivate"))
      .map((line) => line.trim()),
  }));
  if (externalFocus.active !== "blender-canvas" || externalFocus.manager !== 1 ||
      JSON.stringify(externalFocus.transitions) !==
        JSON.stringify(["GHOST WindowDeactivate", "GHOST WindowActivate"])) {
    throw new Error(`external focus-domain contract failed: ${JSON.stringify(externalFocus)}`);
  }

  // Window-level listeners remain required while IME owns activeElement: a tab
  // or browser-window loss has no second canvas blur to report.
  await requestIme(0);
  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    window.dispatchEvent(new FocusEvent("blur"));
  });
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 0 &&
    document.querySelector("#log").textContent.includes("WindowDeactivate"));
  await page.evaluate(() => window.dispatchEvent(new FocusEvent("focus")));
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 1 &&
    document.querySelector("#log").textContent.includes("WindowActivate"));
  const windowFocus = await page.evaluate(() => ({
    active: document.activeElement?.id,
    manager: Number(globalThis.ghostModule._ghost_harness_window_manager_state()),
    transitions: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.includes("WindowActivate") || line.includes("WindowDeactivate")),
  }));
  if (windowFocus.active !== "bw-ime-input" || windowFocus.manager !== 1 ||
      windowFocus.transitions.length !== 2 ||
      !windowFocus.transitions[0].includes("WindowDeactivate") ||
      !windowFocus.transitions[1].includes("WindowActivate")) {
    throw new Error(`window focus-domain contract failed: ${JSON.stringify(windowFocus)}`);
  }
  await requestIme(1);

  await page.evaluate(() => document.querySelector("#bw-ime-input").dispatchEvent(
    new CompositionEvent("compositionupdate", {data: "must-not-publish", bubbles: true})));
  await page.waitForTimeout(100);
  const disabled = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
  }));
  if (disabled.snapshot.sequence !== 5 || disabled.published !== 5 || disabled.dropped !== 0) {
    throw new Error(`disabled IME accepted input: ${JSON.stringify(disabled)}`);
  }

  await requestIme(0, 1);
  await requestIme(1);
  const invalid = await page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_request_ime(2, 0, 0, 0, 0, 0)));
  if (invalid !== 0 || diagnostics.length !== 0) {
    throw new Error(`IME rejection/diagnostic contract failed: ${JSON.stringify({invalid, diagnostics})}`);
  }

  await requestIme(0);
  const saturationBefore = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    consumed: Number(globalThis.ghostModule._bw_shell_ime_consumed_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
    endCount: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.startsWith("GHOST ImeEnd")).length,
  }));
  const saturationPublished = await page.evaluate((recoveredBefore) => {
    const input = document.querySelector("#bw-ime-input");
    const dispatch = (type, data) => input.dispatchEvent(
      new CompositionEvent(type, {data, bubbles: true}));
    dispatch("compositionstart", "");
    for (let index = 0; index < 2048; index += 1) {
      dispatch("compositionupdate", `saturation-${index}`);
      if (globalThis.__bwImeBridge.snapshot().recovered > recoveredBefore) {
        break;
      }
    }
    return globalThis.__bwImeBridge.snapshot();
  }, saturationBefore.snapshot.recovered);
  const acceptedDelta = saturationPublished.accepted - saturationBefore.snapshot.accepted;
  if (saturationPublished.recovered !== saturationBefore.snapshot.recovered + 1 ||
      saturationPublished.rejected <= saturationBefore.snapshot.rejected ||
      saturationPublished.composing || saturationPublished.lastKind !== "cancel" ||
      acceptedDelta < 2) {
    throw new Error(`IME saturation did not recover terminally: ${JSON.stringify({
      saturationBefore, saturationPublished, acceptedDelta,
    })}`);
  }
  await page.waitForFunction(({consumed, endCount}) =>
    Number(globalThis.ghostModule._bw_shell_ime_consumed_count()) >= consumed &&
    document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.startsWith("GHOST ImeEnd")).length > endCount,
  {
    consumed: saturationBefore.consumed + acceptedDelta,
    endCount: saturationBefore.endCount,
  });
  const saturationAfter = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    consumed: Number(globalThis.ghostModule._bw_shell_ime_consumed_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
  }));
  if (saturationAfter.published - saturationBefore.published !== acceptedDelta ||
      saturationAfter.consumed - saturationBefore.consumed !== acceptedDelta ||
      saturationAfter.dropped <= saturationBefore.dropped ||
      saturationAfter.recovered !== saturationBefore.recovered + 1) {
    throw new Error(`IME saturation counters diverged: ${JSON.stringify({
      saturationBefore, saturationAfter, acceptedDelta,
    })}`);
  }
  await requestIme(1);

  await requestIme(0);
  const cancelBefore = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    consumed: Number(globalThis.ghostModule._bw_shell_ime_consumed_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
    endCount: document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.startsWith("GHOST ImeEnd")).length,
  }));
  await page.evaluate(() => {
    const input = document.querySelector("#bw-ime-input");
    input.dispatchEvent(new CompositionEvent("compositionstart", {data: "", bubbles: true}));
    input.dispatchEvent(new CompositionEvent("compositionupdate", {data: "取消", bubbles: true}));
  });
  await requestIme(1);
  await page.waitForFunction(({consumed, recovered, endCount}) =>
    Number(globalThis.ghostModule._bw_shell_ime_consumed_count()) >= consumed + 3 &&
    Number(globalThis.ghostModule._bw_shell_ime_recovered_count()) === recovered + 1 &&
    document.querySelector("#log").textContent.split("\n")
      .filter((line) => line.startsWith("GHOST ImeEnd")).length > endCount,
  cancelBefore);
  const cancelAfter = await page.evaluate(() => ({
    snapshot: globalThis.__bwImeBridge.snapshot(),
    published: Number(globalThis.ghostModule._bw_shell_ime_published_count()),
    consumed: Number(globalThis.ghostModule._bw_shell_ime_consumed_count()),
    dropped: Number(globalThis.ghostModule._bw_shell_ime_dropped_count()),
    recovered: Number(globalThis.ghostModule._bw_shell_ime_recovered_count()),
    active: document.activeElement?.id,
  }));
  if (cancelAfter.published !== cancelBefore.published + 3 ||
      cancelAfter.consumed !== cancelBefore.consumed + 3 ||
      cancelAfter.dropped !== cancelBefore.dropped ||
      cancelAfter.recovered !== cancelBefore.recovered + 1 ||
      cancelAfter.snapshot.composing || cancelAfter.snapshot.enabled ||
      cancelAfter.snapshot.lastKind !== "cancel" || cancelAfter.active !== "blender-canvas") {
    throw new Error(`IME explicit cancel diverged: ${JSON.stringify({cancelBefore, cancelAfter})}`);
  }

  console.log(
    "GHOST_IME_BROWSER PASS events=start,update,commit,end utf8=3,10 " +
    "worker=spsc terminal=reserved,recovered " +
    "focus=domain-internal,external,window " +
    "disabled=rejected capability=on");
}
finally {
  await browser.close();
}
