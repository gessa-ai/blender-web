// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Real-worker repro: a blur and refocus queued in one browser task must retire
// held GHOST input and order that boundary before later key or pointer input.

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

const port = Number(process.argv[2] || 8124);
const browser = await chromium.launch({headless: process.env.BW_HEADLESS === "1"});
try {
  const context = await browser.newContext({viewport: {width: 960, height: 640}});
  const page = await context.newPage();
  const diagnostics = [];
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => {
    const module = globalThis.ghostModule;
    return module && typeof module._ghost_harness_input_state === "function" &&
      document.querySelector("#log")?.textContent.includes("window created");
  });

  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  await page.keyboard.down("Control");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  await page.mouse.move(box.x + 120, box.y + 100);
  await page.mouse.down({button: "left"});

  const held = (1 << 0) | (1 << 4);
  await page.waitForFunction((expected) =>
    Number(globalThis.ghostModule._ghost_harness_input_state()) === expected, held);
  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    document.querySelector("#clear").focus();
    document.querySelector("#blender-canvas").focus();
  });

  await page.waitForFunction(() => {
    const log = document.querySelector("#log")?.textContent || "";
    return Number(globalThis.ghostModule._ghost_harness_input_state()) === 0 &&
      log.includes("WindowDeactivate") && log.includes("WindowActivate");
  }, null, {timeout: 2000});
  const result = await page.evaluate(() => ({
    state: Number(globalThis.ghostModule._ghost_harness_input_state()),
    log: document.querySelector("#log")?.textContent || "",
    transitions: (document.querySelector("#log")?.textContent || "").split("\n")
      .filter((line) => line.includes("WindowDeactivate") || line.includes("WindowActivate"))
      .map((line) => line.trim()),
    focused: document.activeElement?.id || "",
    bridge: globalThis.__bwFocusBridge?.snapshot(),
    publisher: typeof globalThis.ghostModule?._bw_shell_focus_lost,
    publishedLoss: Number(globalThis.ghostModule?._bw_shell_focus_loss_generation?.()),
  }));
  if (result.state !== 0 || !result.log.includes("ButtonUp") ||
      !result.log.includes("WindowDeactivate") || !result.log.includes("WindowActivate") ||
      result.focused !== "blender-canvas" || result.bridge?.handoffDepth !== 0 ||
      result.publisher !== "function" ||
      JSON.stringify(result.transitions) !==
        JSON.stringify(["GHOST WindowDeactivate", "GHOST WindowActivate"]) ||
      result.publishedLoss !== result.bridge?.lossGeneration) {
    throw new Error(
      `rapid blur/refocus lost the domain boundary: ${JSON.stringify(result)}; ` +
      `diagnostics=${diagnostics.join(" | ")}`);
  }

  // Retire Playwright's physical input state after proving GHOST synthesized
  // its own releases; the ordinary focus sequence below must start quiescent.
  await page.mouse.up({button: "left"});
  await page.keyboard.up("Control");
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 1);

  const ordinaryBefore = await page.evaluate(() => ({
    bridge: globalThis.__bwFocusBridge?.snapshot(),
    publishedLoss: Number(globalThis.ghostModule?._bw_shell_focus_loss_generation?.()),
  }));
  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
    document.querySelector("#clear").focus();
  });
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 0 &&
    document.querySelector("#log")?.textContent.includes("WindowDeactivate"));
  await canvas.focus();
  await page.waitForFunction(() =>
    Number(globalThis.ghostModule._ghost_harness_window_manager_state()) === 1 &&
    document.querySelector("#log")?.textContent.includes("WindowActivate"));
  const ordinary = await page.evaluate(() => ({
    bridge: globalThis.__bwFocusBridge?.snapshot(),
    publishedLoss: Number(globalThis.ghostModule?._bw_shell_focus_loss_generation?.()),
    transitions: (document.querySelector("#log")?.textContent || "").split("\n")
      .filter((line) => line.includes("WindowDeactivate") || line.includes("WindowActivate"))
      .map((line) => line.trim()),
  }));
  if (JSON.stringify(ordinary.transitions) !==
      JSON.stringify(["GHOST WindowDeactivate", "GHOST WindowActivate"]) ||
      ordinary.publishedLoss !== ordinaryBefore.publishedLoss + 1 ||
      ordinary.bridge?.lossGeneration !== ordinaryBefore.bridge?.lossGeneration + 1) {
    throw new Error(
      `ordinary blur/refocus was duplicated: ${JSON.stringify({ordinaryBefore, ordinary})}`);
  }

  const assertSameTaskInputOrder = async (kind) => {
    await page.evaluate((inputKind) => {
      const log = document.querySelector("#log");
      const clear = document.querySelector("#clear");
      const canvas = document.querySelector("#blender-canvas");
      log.textContent = "";
      clear.focus();
      canvas.focus();
      if (inputKind === "key") {
        canvas.dispatchEvent(new KeyboardEvent("keydown", {
          key: "x", code: "KeyX", bubbles: true, cancelable: true,
        }));
        canvas.dispatchEvent(new KeyboardEvent("keyup", {
          key: "x", code: "KeyX", bubbles: true, cancelable: true,
        }));
      }
      else {
        canvas.dispatchEvent(new MouseEvent("mousedown", {
          button: 0, buttons: 1, clientX: 120, clientY: 100,
          bubbles: true, cancelable: true,
        }));
        window.dispatchEvent(new MouseEvent("mouseup", {
          button: 0, buttons: 0, clientX: 120, clientY: 100,
          bubbles: true, cancelable: true,
        }));
      }
    }, kind);
    const terminal = kind === "key" ? "KeyUp" : "ButtonUp";
    await page.waitForFunction((terminalEvent) => {
      const log = document.querySelector("#log")?.textContent || "";
      return log.includes("WindowDeactivate") && log.includes("WindowActivate") &&
        log.includes(terminalEvent);
    }, terminal, {timeout: 2000});
    const categories = await page.evaluate(() =>
      (document.querySelector("#log")?.textContent || "").split("\n")
        .filter(Boolean)
        .map((line) => {
          if (line.includes("WindowDeactivate")) return "deactivate";
          if (line.includes("WindowActivate")) return "activate";
          if (line.includes("KeyDown")) return "key-down";
          if (line.includes("KeyUp")) return "key-up";
          if (line.includes("ButtonDown")) return "button-down";
          if (line.includes("ButtonUp")) return "button-up";
          return null;
        })
        .filter(Boolean));
    const expected = kind === "key" ?
      ["deactivate", "activate", "key-down", "key-up"] :
      ["deactivate", "activate", "button-down", "button-up"];
    if (JSON.stringify(categories) !== JSON.stringify(expected)) {
      throw new Error(
        `same-task ${kind} crossed the focus barrier: ` +
        `${JSON.stringify({categories, expected})}`);
    }
  };
  await assertSameTaskInputOrder("key");
  await assertSameTaskInputOrder("mouse");
  console.log(
    "M4_FOCUS_TRANSITION_ORDER_LIVE PASS rapid=blur,refocus held=ctrl+left retired=1 " +
    "ordinary=single-pair same-task=key+mouse-ordered");
}
finally {
  await browser.close();
}
