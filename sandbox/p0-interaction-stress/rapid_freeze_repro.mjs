// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoot = process.env.BW_NODE_MODULES || resolve(root, ".m4-node/node_modules");
const {chromium} = createRequire(resolve(moduleRoot, "package.json"))("playwright");
const port = Number(process.argv[2] || 8123);
const hardwareDiagnostic = process.env.BW_P0_RAPID_HARDWARE === "1";
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
  "microsoft basic render", "warp",
]);
if (hardwareDiagnostic && process.platform !== "darwin") {
  throw new Error(`BW_P0_RAPID_HARDWARE is Apple-only; got ${process.platform}`);
}

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const classifyAdapter = (raw) => {
  const identity = Object.values(raw.info).join(" ").trim().toLowerCase();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  let reason = "accepted-hardware";
  if (!raw.present) reason = "adapter-absent";
  else if (raw.isFallbackAdapter === true) reason = "fallback-adapter";
  else if (raw.isFallbackAdapter !== false) reason = "fallback-status-absent";
  else if (!identity || !raw.info.architecture) reason = "adapter-info-absent";
  else if (softwareMatches.length) reason = "software-adapter";
  return {
    status: reason === "accepted-hardware" ? "ACCEPTED" : "REJECTED",
    reason,
    ...raw,
    softwareMatches,
  };
};
const probeAdapter = async (page) => classifyAdapter(await page.evaluate(async () => {
  const candidate = await navigator.gpu?.requestAdapter({powerPreference: "high-performance"});
  if (!candidate) {
    return {present: false, isFallbackAdapter: null, info: {}};
  }
  const info = candidate.info || {};
  return {
    present: true,
    isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
      info.isFallbackAdapter :
      (typeof candidate.isFallbackAdapter === "boolean" ? candidate.isFallbackAdapter : null),
    info: Object.fromEntries(["vendor", "architecture", "device", "description"]
      .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
  };
}));
const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    ...(hardwareDiagnostic ? ["--use-angle=metal"] : [
      "--use-webgpu-adapter=swiftshader",
      "--use-gpu-in-tests",
    ]),
  ],
});

let failureContext = null;
try {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const consoleLines = [];
  const pageErrors = [];
  const lifecycle = [];
  failureContext = {consoleLines, pageErrors, lifecycle};
  page.on("console", (message) => consoleLines.push(message.text()));
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("close", () => lifecycle.push("page-close"));
  page.on("crash", () => lifecycle.push("page-crash"));
  context.on("close", () => lifecycle.push("context-close"));
  await page.goto(
    `http://127.0.0.1:${port}/windowed.html?args=--debug-events&ka_idle=16`,
    {waitUntil: "domcontentloaded"},
  );
  await page.waitForFunction(
    () => document.querySelector("#state")?.dataset.state === "running" &&
      Number(window.__bwModule?._bw_viewport_content_present_count?.()) > 0,
    null,
    {timeout: 180000, polling: 100},
  );
  const adapter = await probeAdapter(page);
  failureContext.adapter = adapter;
  if (hardwareDiagnostic && adapter.status !== "ACCEPTED") {
    throw new Error(`rapid input hardware adapter rejected: ${adapter.reason}`);
  }

  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(750);
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const center = {x: box.x + 500, y: box.y + 330};

  const sample = async (name) => {
    const bytes = await canvas.screenshot();
    const counters = await page.evaluate(() => {
      const module = window.__bwModule;
      const read = (name) => typeof module?.[name] === "function" ? Number(module[name]()) : null;
      return {
        ticks: read("_bw_wm_tick_count"),
        presents: read("_bw_present_count"),
        retries: read("_bw_redraw_retry_count"),
        suppressed: read("_bw_present_suppressed_count"),
        replays: read("_bw_present_replay_count"),
        pointerLock: window.__bwPointerLockBridge?.snapshot?.() || null,
        activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
      };
    });
    const result = {name, sha256: sha256(bytes), ...counters};
    failureContext.lastSample = result;
    return result;
  };
  const waitForPixelChange = async (name, baseline, counterBaseline, timeoutMs = 12000) => {
    const started = Date.now();
    while (Date.now() - started <= timeoutMs) {
      await page.waitForTimeout(250);
      const current = await sample(name);
      if (current.sha256 !== baseline &&
          current.ticks > counterBaseline.ticks &&
          current.presents > counterBaseline.presents &&
          current.retries > counterBaseline.retries) {
        return {...current, settleMs: Date.now() - started};
      }
    }
    throw new Error(
      `${name} did not change pixels plus WM/present/input-retry counters within ${timeoutMs}ms`,
    );
  };
  const steps = [];
  failureContext.steps = steps;
  steps.push(await sample("splash-dismissed"));
  const settle = async (name) => {
    await page.waitForTimeout(350);
    steps.push(await sample(name));
  };

  await page.mouse.move(center.x, center.y);
  for (const [key, name] of [
    ["Numpad1", "front"],
    ["Numpad3", "right"],
    ["Numpad7", "top"],
    ["Numpad0", "camera"],
    ["Numpad4", "camera-orbit-cancelled"],
  ]) {
    await page.keyboard.press(key);
    await settle(name);
  }
  await page.keyboard.press("a");
  await settle("select-all");
  await page.keyboard.press("Alt+a");
  await settle("deselect-all");

  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x + 34, center.y + 20, {steps: 8});
  await page.mouse.up({button: "middle"});
  await settle("orbit-before-click");

  await page.mouse.click(center.x, center.y);
  await settle("click");
  await page.mouse.move(center.x, center.y);
  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x - 34, center.y + 16, {steps: 8});
  await page.mouse.up({button: "middle"});
  await settle("orbit-after-click");
  await page.keyboard.press("g");
  await page.mouse.move(center.x + 40, center.y - 20);
  await settle("move-pending");
  await page.mouse.click(center.x + 40, center.y - 20);
  await settle("move-confirmed");

  const orbitBeforeClick = steps.find((step) => step.name === "orbit-before-click");
  let actionDrain = steps.slice(steps.indexOf(orbitBeforeClick) + 1).find((step) =>
    step.sha256 !== orbitBeforeClick.sha256 &&
    step.ticks > orbitBeforeClick.ticks &&
    step.presents > orbitBeforeClick.presents &&
    step.retries > orbitBeforeClick.retries);
  if (actionDrain) {
    actionDrain = {...actionDrain, name: "action-drain", settleMs: 0};
  }
  else {
    actionDrain = await waitForPixelChange(
      "action-drain", orbitBeforeClick.sha256, orbitBeforeClick,
    );
  }
  steps.push(actionDrain);
  await page.keyboard.press("Escape");
  await page.mouse.move(center.x, center.y);
  await page.mouse.down({button: "middle"});
  await page.mouse.move(center.x + 24, center.y - 18, {steps: 8});
  await page.mouse.up({button: "middle"});
  steps.push(await waitForPixelChange(
    "recovery-orbit", actionDrain.sha256, actionDrain,
  ));

  const retained = steps.slice(8, 13).map((step) => step.sha256);
  const evidence = {
    schema: 1,
    evidenceClass: hardwareDiagnostic ? "diagnostic-apple" : "diagnostic-software-fallback",
    adapter,
    steps,
    retainedActionFramesEqual: new Set(retained).size === 1,
    actionDrainMs: actionDrain.settleMs,
    recoveryOrbitMs: steps.at(-1).settleMs,
    pageErrors,
    lifecycle,
    pointerLockLines: consoleLines.filter((line) => /Pointer Lock|pointerlock/i.test(line)),
    eventTail: consoleLines.filter((line) => /ghost_event_proc/.test(line)).slice(-80),
  };
  if (pageErrors.length !== 0 || lifecycle.length !== 0) {
    throw new Error(`rapid input diagnostic has page/lifecycle errors: ${JSON.stringify(evidence)}`);
  }
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
}
catch (error) {
  const retained = (failureContext?.steps || []).slice(8, 13).map((step) => step.sha256);
  process.stderr.write(`${JSON.stringify({
    error: error?.stack || String(error),
    adapter: failureContext?.adapter || null,
    steps: failureContext?.steps || [],
    lastSample: failureContext?.lastSample || null,
    retainedActionFramesEqual: retained.length === 5 ? new Set(retained).size === 1 : null,
    pageErrors: failureContext?.pageErrors || [],
    lifecycle: failureContext?.lifecycle || [],
    pointerLockLines: (failureContext?.consoleLines || [])
      .filter((line) => /Pointer Lock|pointerlock/i.test(line)),
    eventTail: (failureContext?.consoleLines || [])
      .filter((line) => /ghost_event_proc/.test(line)).slice(-80),
    consoleTail: (failureContext?.consoleLines || []).slice(-120),
  }, null, 2)}\n`);
  throw error;
}
finally {
  await browser.close();
}
