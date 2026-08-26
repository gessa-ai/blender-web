// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Headed browser contract for GHOST_WindowWeb cursor grab and relative motion.

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
const leaveActive = process.env.BW_POINTER_LOCK_LEAVE_ACTIVE === "1";
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
  await context.addInitScript(() => {
    /* Keep Emscripten's user-sensitive request decision deterministic in
     * headless/headed Chromium. The trusted Playwright click still supplies the
     * browser's real activation when this test enables the exposed getter. */
    globalThis.__bwHarnessUserActivation = false;
    Object.defineProperty(navigator, "userActivation", {
      configurable: true,
      value: {
        get isActive() {
          return globalThis.__bwHarnessUserActivation === true;
        },
        get hasBeenActive() {
          return globalThis.__bwHarnessUserActivation === true;
        },
      },
    });

    /* Chromium's modern requestPointerLock returns a Promise, while the pinned
     * Emscripten helper discards that result. Keep the real implementation for
     * positive coverage, but make rejection deterministic for the terminal
     * fallback case below. diagnostics-bootstrap.js must consume this Promise. */
    const nativeRequestPointerLock = Element.prototype.requestPointerLock;
    if (typeof nativeRequestPointerLock === "function") {
      Object.defineProperty(Element.prototype, "requestPointerLock", {
        configurable: true,
        writable: true,
        value(...args) {
          if (globalThis.__bwHarnessRejectPointerLock === true) {
            return Promise.reject(new DOMException(
              "The root document of this element is not valid for pointer lock.",
              "WrongDocumentError"));
          }
          return nativeRequestPointerLock.apply(this, args);
        },
      });
    }
  });
  const page = await context.newPage();
  const diagnostics = [];
  const pageErrors = [];
  page.on("console", (message) => diagnostics.push(message.text()));
  page.on("pageerror", (error) => {
    pageErrors.push({name: error.name, message: error.message});
    diagnostics.push(`pageerror: ${error.message}`);
  });
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  try {
    await page.waitForFunction(() => {
      const module = globalThis.ghostModule;
      return module && typeof module._ghost_harness_request_cursor_grab === "function" &&
        typeof module._ghost_harness_cursor_grab_result === "function" &&
        typeof module._ghost_harness_cursor_grab_state === "function" &&
        typeof module._ghost_harness_request_window_lifecycle === "function" &&
        typeof module._ghost_harness_window_lifecycle_result === "function" &&
        document.querySelector("#log")?.textContent.includes("window created");
    });
  }
  catch (error) {
    throw new Error(`GHOST harness did not create a window: ${diagnostics.join(" | ")}`, {
      cause: error,
    });
  }

  const requestGrab = async (mode) => {
    const queued = await page.evaluate((requested) => Number(
      globalThis.ghostModule._ghost_harness_request_cursor_grab(requested)), mode);
    if (queued !== 1) throw new Error(`grab ${mode} was not queued: ${queued}`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_cursor_grab_result()) !== -2);
    return page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_cursor_grab_result()));
  };

  const requestLifecycle = async (action) => {
    const queued = await page.evaluate((requested) => Number(
      globalThis.ghostModule._ghost_harness_request_window_lifecycle(requested)), action);
    if (queued !== 1) throw new Error(`lifecycle ${action} was not queued: ${queued}`);
    await page.waitForFunction(() =>
      Number(globalThis.ghostModule._ghost_harness_window_lifecycle_result()) !== -2);
    return page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_window_lifecycle_result()));
  };

  const readGrabState = async () => {
    const encoded = await page.evaluate(() =>
      Number(globalThis.ghostModule._ghost_harness_cursor_grab_state()));
    return encoded < 0 ? { encoded, actual: -1, requested: -1, phase: -1 } : {
      encoded,
      actual: encoded & 0xf,
      requested: (encoded >> 4) & 0xf,
      phase: (encoded >> 8) & 0xf,
    };
  };

  const waitGrabState = async (actual, requested, phase) => {
    await page.waitForFunction(([wantActual, wantRequested, wantPhase]) => {
      const encoded = Number(globalThis.ghostModule._ghost_harness_cursor_grab_state());
      return encoded >= 0 && (encoded & 0xf) === wantActual &&
        ((encoded >> 4) & 0xf) === wantRequested &&
        ((encoded >> 8) & 0xf) === wantPhase;
    }, [actual, requested, phase]);
  };

  const canvas = page.locator("#blender-canvas");
  const activationClick = async () => {
    await page.evaluate(() => {
      globalThis.__bwHarnessUserActivation = true;
      window.scrollTo(0, 0);
    });
    try {
      await canvas.click({ position: { x: 120, y: 100 } });
    }
    finally {
      await page.evaluate(() => {
        globalThis.__bwHarnessUserActivation = false;
      });
    }
  };
  const activateGrab = async (mode = 2) => {
    if (await requestGrab(mode) !== 1) {
      throw new Error(`grab ${mode} was rejected`);
    }
    if (!(await page.evaluate(() => document.pointerLockElement !== null))) {
      await activationClick();
    }
    await page.waitForFunction(
      () => document.pointerLockElement?.id === "blender-canvas", null, { timeout: 5000 });
    await waitGrabState(mode, mode, 2);
  };

  /* Seed an absolute cursor event without granting user activation. The first
   * worker request must therefore be accepted as pending, not published as an
   * active GHOST grab, until a later trusted click runs Emscripten's deferred call. */
  await page.evaluate(() => {
    const canvasElement = document.querySelector("#blender-canvas");
    const rect = canvasElement.getBoundingClientRect();
    canvasElement.dispatchEvent(new MouseEvent("mousemove", {
      bubbles: true,
      clientX: rect.left + 120,
      clientY: rect.top + 100,
    }));
  });
  await page.waitForFunction(() =>
    document.querySelector("#log")?.textContent.includes("GHOST CursorMove"));
  if (await requestGrab(2) !== 1) {
    throw new Error("wrap grab was rejected");
  }
  const pending = await readGrabState();
  if (pending.actual !== 0 || pending.requested !== 2 || pending.phase !== 1) {
    throw new Error(`deferred grab was confused with active state: ${JSON.stringify(pending)}`);
  }
  await activationClick();
  try {
    await page.waitForFunction(
      () => document.pointerLockElement?.id === "blender-canvas", null, { timeout: 5000 });
    await waitGrabState(2, 2, 2);
  }
  catch (error) {
    const state = await page.evaluate(() => ({
      active: navigator.userActivation?.isActive ?? null,
      hasBeenActive: navigator.userActivation?.hasBeenActive ?? null,
      pointerLockElement: document.pointerLockElement?.id ?? null,
      requestSupported: typeof document.querySelector("#blender-canvas")?.requestPointerLock,
    }));
    throw new Error(`pointer lock did not activate: ${JSON.stringify(state)}`, { cause: error });
  }

  const beforeMotion = await page.locator("#log").textContent();
  const cursorMatches = [...beforeMotion.matchAll(/GHOST CursorMove\s+x=(-?\d+) y=(-?\d+)/g)];
  if (cursorMatches.length === 0) {
    throw new Error(`no baseline cursor event: ${beforeMotion.slice(-1200)}`);
  }
  const baseline = cursorMatches.at(-1).slice(1).map(Number);
  const expected = [baseline[0] + 37, baseline[1] - 19];

  await page.evaluate(() => {
    const canvasElement = document.querySelector("#blender-canvas");
    const rect = canvasElement.getBoundingClientRect();
    const event = new MouseEvent("mousemove", {
      bubbles: true,
      clientX: rect.left + 120,
      clientY: rect.top + 100,
    });
    Object.defineProperties(event, {
      movementX: { value: 37 },
      movementY: { value: -19 },
    });
    canvasElement.dispatchEvent(event);
  });
  try {
    await page.waitForFunction(([expectedX, expectedY]) => {
      const lines = document.querySelector("#log")?.textContent || "";
      return lines.includes(`GHOST CursorMove       x=${expectedX} y=${expectedY}`);
    }, expected, { timeout: 5000 });
  }
  catch (error) {
    const lines = await page.locator("#log").textContent();
    throw new Error(`relative cursor event missing: ${lines.slice(-1200)}`, { cause: error });
  }

  const invalid = await page.evaluate(() => Number(
    globalThis.ghostModule._ghost_harness_request_cursor_grab(99)));
  if (invalid !== 0) {
    throw new Error(`invalid grab mode was accepted: ${invalid}`);
  }

  if (!leaveActive) {
    /* External Escape/loss is reported only by pointerlockchange. GHOST must
     * retire Wrap before the next motion so frozen lock coordinates cannot win. */
    await page.evaluate(() => document.exitPointerLock());
    await page.waitForFunction(() => document.pointerLockElement === null);
    await waitGrabState(0, 0, 0);
    await page.evaluate(() => {
      const canvasElement = document.querySelector("#blender-canvas");
      const rect = canvasElement.getBoundingClientRect();
      const event = new MouseEvent("mousemove", {
        bubbles: true,
        clientX: rect.left + 44,
        clientY: rect.top + 55,
      });
      Object.defineProperties(event, {
        movementX: { value: 1000 },
        movementY: { value: 1000 },
      });
      canvasElement.dispatchEvent(event);
    });
    await page.waitForFunction(() =>
      document.querySelector("#log")?.textContent.includes("GHOST CursorMove       x=44 y=55"));

    /* A browser rejection must cancel both an active lock and any deferred
     * Emscripten request, then return GHOST to absolute motion. */
    await activateGrab();
    await page.evaluate(() => document.dispatchEvent(new Event("pointerlockerror")));
    await page.waitForFunction(() => document.pointerLockElement === null);
    await waitGrabState(0, 0, 0);

    /* Blur is a separate terminal path: browsers are not required to deliver
     * the operator's matching mouse-up before focus leaves the canvas. */
    await activateGrab();
    await page.evaluate(() =>
      document.querySelector("#blender-canvas").dispatchEvent(new FocusEvent("blur")));
    await page.waitForFunction(() => document.pointerLockElement === null);
    await waitGrabState(0, 0, 0);

    /* Disposal must remove an active lock before the window and callback owner
     * disappear, then a replacement must begin inactive. */
    await activateGrab();
    const disposeResult = await requestLifecycle(0);
    if (disposeResult !== 0b1111) {
      throw new Error(`active window disposal failed: ${disposeResult}`);
    }
    await page.waitForFunction(() => document.pointerLockElement === null);
    if ((await readGrabState()).encoded !== -1) {
      throw new Error("disposed window still exposes pointer-lock state");
    }
    if (await requestLifecycle(1) !== 0b111) {
      throw new Error("replacement window was not published after pointer-lock disposal");
    }
    await waitGrabState(0, 0, 0);

    /* A rejected DOM Promise is a routine unlocked-grab fallback, not a page
     * error. Exercise it twice: GHOST must retire Pending both times while the
     * shell emits only one bounded diagnostic. */
    await page.evaluate(() => {
      globalThis.__bwHarnessRejectPointerLock = true;
    });
    for (let attempt = 0; attempt < 2; attempt++) {
      if (await requestGrab(2) !== 1) {
        throw new Error(`rejected-Promise grab ${attempt} was not accepted as pending`);
      }
      await activationClick();
      try {
        await waitGrabState(0, 0, 0);
      }
      catch (error) {
        const failureState = await readGrabState();
        const failureBridge = await page.evaluate(() =>
          globalThis.__bwPointerLockBridge?.snapshot?.() ?? null);
        throw new Error(
          `rejected-Promise grab ${attempt} did not retire: ` +
          `${JSON.stringify({failureState, failureBridge, pageErrors, diagnostics})}`,
          {cause: error});
      }
    }
    await page.waitForTimeout(50);
    const rejectionBridge = await page.evaluate(() =>
      globalThis.__bwPointerLockBridge?.snapshot?.() ?? null);
    if (rejectionBridge?.rejectionCount !== 2 ||
        rejectionBridge?.lastReasonName !== "WrongDocumentError") {
      throw new Error(`pointer-lock rejection bridge drifted: ${JSON.stringify(rejectionBridge)}`);
    }
    const boundedDiagnostics = diagnostics.filter((line) =>
      line.includes("[bw] Pointer Lock request rejected; continuing without lock:"));
    if (boundedDiagnostics.length !== 1) {
      throw new Error(`pointer-lock rejection diagnostic was not bounded: ${boundedDiagnostics.length}`);
    }
    if (pageErrors.length !== 0) {
      throw new Error(`pointer-lock rejection escaped as pageerror: ${JSON.stringify(pageErrors)}`);
    }
  }

  console.log(
    `POINTER_LOCK_LIVE PASS outcomes=pending,active,${leaveActive ? "left-active" :
      "lost,error,blur,disposed,rejected-promise"} ` +
    `relative=37,-19 virtual=${expected.join(",")} post-loss=absolute invalid=rejected`);
}
finally {
  await browser.close();
}
