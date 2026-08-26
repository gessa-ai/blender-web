// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract: disposing the active canvas window must detach every
// system lookup before deletion, and a replacement window must become the new
// callback/event target in the shipping PROXY_TO_PTHREAD topology. Browser
// events captured under an old listener registration must remain retired even
// when their delivery is delayed until after repeated window replacement.

import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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
const browserArgs = [];
if (process.platform === "linux" && process.env.DISPLAY) {
  browserArgs.push("--ozone-platform=x11");
}

const browser = await chromium.launch({
  headless: process.env.BW_HEADLESS === "1",
  args: browserArgs,
});
try {
  const context = await browser.newContext({ viewport: { width: 960, height: 640 } });
  const page = await context.newPage();
  await page.addInitScript(() => {
    const nativeAdd = EventTarget.prototype.addEventListener;
    const nativeRemove = EventTarget.prototype.removeEventListener;
    const keydownWrappers = new WeakMap();
    const probe = {
      armed: false,
      captured: 0,
      delivered: 0,
      held: [],
      arm() {
        if (this.armed) throw new Error("stale callback probe is already armed");
        this.armed = true;
      },
      deliverAll() {
        const pending = this.held.splice(0);
        for (const deliver of pending) deliver();
        this.delivered += pending.length;
      },
      snapshot() {
        return {
          armed: this.armed,
          captured: this.captured,
          delivered: this.delivered,
          pending: this.held.length,
        };
      },
    };

    EventTarget.prototype.addEventListener = function (type, listener, options) {
      if (this instanceof HTMLCanvasElement && this.id === "blender-canvas" &&
          type === "keydown" && typeof listener === "function") {
        const wrapped = function (event) {
          if (probe.armed) {
            probe.armed = false;
            probe.captured += 1;
            probe.held.push(() => listener.call(this, event));
            return;
          }
          return listener.call(this, event);
        };
        keydownWrappers.set(listener, wrapped);
        return nativeAdd.call(this, type, wrapped, options);
      }
      return nativeAdd.call(this, type, listener, options);
    };
    EventTarget.prototype.removeEventListener = function (type, listener, options) {
      const wrapped = type === "keydown" && typeof listener === "function" ?
        keydownWrappers.get(listener) : null;
      return nativeRemove.call(this, type, wrapped || listener, options);
    };
    Object.defineProperty(globalThis, "__bwStaleCallbackProbe", {
      value: probe,
      writable: false,
      configurable: false,
    });
  });
  const diagnostics = [];
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  try {
    await page.waitForFunction(() => {
      const module = globalThis.ghostModule;
      return module &&
        typeof module._ghost_harness_request_window_lifecycle === "function" &&
        typeof module._ghost_harness_window_lifecycle_result === "function" &&
        typeof module._ghost_harness_window_manager_state === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const request = async (action) => {
    const accepted = await page.evaluate((value) => Number(
      globalThis.ghostModule._ghost_harness_request_window_lifecycle(value)), action);
    if (accepted !== 1) {
      throw new Error(`window lifecycle action ${action} was not accepted: ${accepted}`);
    }
    await page.waitForFunction(() => Number(
      globalThis.ghostModule._ghost_harness_window_lifecycle_result()) !== -2);
    return page.evaluate(() => Number(
      globalThis.ghostModule._ghost_harness_window_lifecycle_result()));
  };

  const managerState = () => page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_window_manager_state()));

  const initialManagerState = await managerState();
  if (initialManagerState !== 1) {
    throw new Error(
      `created canvas window was not published active: state=${initialManagerState}`);
  }

  const secondWindowResult = await request(3);
  // Bits: original system/manager ownership, second create rejected, original
  // system/manager/count/hit-test ownership retained.
  if (secondWindowResult !== 0b1111111) {
    throw new Error(
      `simultaneous second window did not fail closed: result=${secondWindowResult}`);
  }
  if (await managerState() !== 1) {
    throw new Error("second-window rejection changed the active canvas window");
  }

  await page.evaluate(() => document.querySelector("#clear").focus());
  await page.waitForFunction(() => Number(
    globalThis.ghostModule._ghost_harness_window_manager_state()) === 0);
  await page.locator("#blender-canvas").focus();
  await page.waitForFunction(() => Number(
    globalThis.ghostModule._ghost_harness_window_manager_state()) === 1);

  const disposeResult = await request(0);
  // Bits: active-before, base-dispose-success, active-null, under-cursor-null.
  if (disposeResult !== 0b1111) {
    throw new Error(
      `active window was not detached before/after disposal: result=${disposeResult}`);
  }
  if (await managerState() !== 0) {
    throw new Error("disposed canvas window remained active in GHOST_WindowManager");
  }

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
  });
  await page.locator("#blender-canvas").focus();
  await page.keyboard.press("a");
  await page.waitForTimeout(100);
  const detachedLog = await page.locator("#log").textContent();
  if (detachedLog.includes("KeyDown") || detachedLog.includes("KeyUp")) {
    throw new Error(`disposed window callbacks still delivered input: ${detachedLog}`);
  }

  const recreateResult = await request(1);
  // Bits: replacement-created, replacement-active, under-cursor-is-replacement.
  if (recreateResult !== 0b111) {
    throw new Error(`replacement window was not published: result=${recreateResult}`);
  }
  if (await managerState() !== 1) {
    throw new Error("replacement canvas window was not published active");
  }

  const queueOldKey = async (key, code, expectedCaptured) => {
    const snapshot = await page.evaluate(({ eventKey, eventCode }) => {
      const probe = globalThis.__bwStaleCallbackProbe;
      probe.arm();
      document.querySelector("#blender-canvas").dispatchEvent(new KeyboardEvent("keydown", {
        key: eventKey,
        code: eventCode,
        bubbles: true,
        cancelable: true,
      }));
      return probe.snapshot();
    }, { eventKey: key, eventCode: code });
    if (snapshot.armed || snapshot.captured !== expectedCaptured ||
        snapshot.pending !== expectedCaptured) {
      throw new Error(`old-registration callback was not captured: ${JSON.stringify(snapshot)}`);
    }
  };

  // Hold one callback from each of two successive registrations, replace the
  // window after each capture, then invoke both stale listener closures only
  // after the third registration has become current.
  await page.evaluate(() => { document.querySelector("#log").textContent = ""; });
  await queueOldKey("q", "KeyQ", 1);
  if (await request(0) !== 0b1111 || await request(1) !== 0b111) {
    throw new Error("first repeated replacement failed");
  }
  await queueOldKey("w", "KeyW", 2);
  if (await request(0) !== 0b1111 || await request(1) !== 0b111) {
    throw new Error("second repeated replacement failed");
  }
  const staleSnapshot = await page.evaluate(() => {
    globalThis.__bwStaleCallbackProbe.deliverAll();
    return globalThis.__bwStaleCallbackProbe.snapshot();
  });
  await page.waitForTimeout(100);
  const staleLog = await page.locator("#log").textContent();
  if (staleSnapshot.captured !== 2 || staleSnapshot.delivered !== 2 ||
      staleSnapshot.pending !== 0 || staleLog.includes("KeyDown") ||
      staleLog.includes("KeyUp")) {
    throw new Error(
      `stale registration reached replacement: probe=${JSON.stringify(staleSnapshot)} ` +
      `log=${staleLog}`);
  }

  const hitTestResult = await request(2);
  // Bits: active/non-empty; left-top, right-bottom, and center inside;
  // one point beyond each of the left, top, right, and bottom edges outside.
  if (hitTestResult !== 0b11111111) {
    throw new Error(`window-under-cursor bounds were not enforced: result=${hitTestResult}`);
  }

  await page.evaluate(() => {
    document.querySelector("#log").textContent = "";
  });
  const canvas = page.locator("#blender-canvas");
  await canvas.focus();
  await page.keyboard.press("a");
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("KeyDown"));
  const callbackFailures = diagnostics.filter((line) =>
    line.includes("HTML5 callbacks failed to unregister"));
  if (callbackFailures.length !== 0) {
    throw new Error(`callback removal reported failure: ${callbackFailures.join(" | ")}`);
  }

  console.log(
    "WINDOW_LIFECYCLE_LIVE PASS dispose=detached callbacks=rebound replacement=input-target " +
    "queued=registration-epoch repeated-replacements=2 hit-test=bounded " +
    "manager=create-focus-blur-dispose-replace second-window=fail-closed worker=proxy-pthread");
}
finally {
  await browser.close();
}
