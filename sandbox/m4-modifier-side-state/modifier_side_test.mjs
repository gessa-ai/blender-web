// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Trusted-CDP browser contract for exact left/right GHOST modifier state.

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
  try {
    await page.waitForFunction(() => {
      const module = globalThis.ghostModule;
      return module && typeof module._ghost_harness_modifier_state_exact === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not initialize: ${diagnostics.join(" | ")}`, {cause: error});
  }

  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const client = await context.newCDPSession(page);

  const exactState = () => page.evaluate(() =>
    Number(globalThis.ghostModule._ghost_harness_modifier_state_exact()));
  const waitState = async (expected, label) => {
    try {
      await page.waitForFunction((value) =>
        Number(globalThis.ghostModule._ghost_harness_modifier_state_exact()) === value,
      expected, {timeout: 2000});
    }
    catch (error) {
      const actual = await exactState();
      throw new Error(`${label}: expected exact modifier mask ${expected}, got ${actual}`, {
        cause: error,
      });
    }
  };
  const dispatchKey = (type, key, code, virtualKeyCode, location, modifiers) =>
    client.send("Input.dispatchKeyEvent", {
      type,
      key,
      code,
      windowsVirtualKeyCode: virtualKeyCode,
      nativeVirtualKeyCode: virtualKeyCode,
      location,
      modifiers,
    });
  const dispatchMove = (modifiers) => client.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: box.x + 120,
    y: box.y + 100,
    modifiers,
  });

  const families = [
    {label: "shift", key: "Shift", left: "ShiftLeft", right: "ShiftRight",
      leftCode: 16, rightCode: 16, modifiers: 8, leftBit: 1 << 0, rightBit: 1 << 1},
    {label: "control", key: "Control", left: "ControlLeft", right: "ControlRight",
      leftCode: 17, rightCode: 17, modifiers: 2, leftBit: 1 << 4, rightBit: 1 << 5},
    {label: "alt", key: "Alt", left: "AltLeft", right: "AltRight",
      leftCode: 18, rightCode: 18, modifiers: 1, leftBit: 1 << 2, rightBit: 1 << 3},
    {label: "os", key: "Meta", left: "MetaLeft", right: "MetaRight",
      leftCode: 91, rightCode: 92, modifiers: 4, leftBit: 1 << 6, rightBit: 1 << 7},
  ];

  await waitState(0, "initial state");
  for (const family of families) {
    await dispatchKey("rawKeyDown", family.key, family.right, family.rightCode, 2,
      family.modifiers);
    await waitState(family.rightBit, `${family.label} right down`);

    await dispatchMove(family.modifiers);
    await waitState(family.rightBit, `${family.label} right survives aggregate mouse state`);

    await dispatchKey("rawKeyDown", family.key, family.left, family.leftCode, 1,
      family.modifiers);
    await waitState(family.leftBit | family.rightBit, `${family.label} both down`);

    await dispatchKey("keyUp", family.key, family.right, family.rightCode, 2, family.modifiers);
    await waitState(family.leftBit, `${family.label} right up while left held`);

    await dispatchKey("keyUp", family.key, family.left, family.leftCode, 1, 0);
    await waitState(0, `${family.label} left up`);
  }

  await dispatchKey("rawKeyDown", "Shift", "ShiftRight", 16, 2, 8);
  await waitState(1 << 1, "right shift before focus loss");
  await page.evaluate(() => document.querySelector("#clear").focus());
  await waitState(0, "focus loss clears exact right shift");
  await canvas.focus();
  await waitState(0, "refocus keeps exact state clear");

  // Mouse events expose only aggregate flags. With no exact key history, retain
  // the established left-side fallback; a later exact key event can refine it.
  await dispatchMove(8);
  await waitState(1 << 0, "aggregate-only shift fallback");
  await dispatchMove(0);
  await waitState(0, "aggregate-only shift release");

  console.log(
    "M4_MODIFIER_SIDE_LIVE PASS trusted=cdp families=shift,control,alt,os " +
    "sides=left,right,both aggregate=preserve,fallback focus=cleared");
}
finally {
  await browser.close();
}
