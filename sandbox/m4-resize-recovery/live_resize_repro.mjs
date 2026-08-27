// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoot = process.env.BW_NODE_MODULES || resolve(root, ".m4-node/node_modules");
const {chromium} = createRequire(resolve(moduleRoot, "package.json"))("playwright");
const port = Number(process.argv[2] || 8137);

const lines = [];
const resizeTraces = [];
const counters = {
  scissorRejected: 0,
  encodingRejected: 0,
  submissionRejected: 0,
  transactionRejected: 0,
  deviceLost: 0,
  resizeApplied: 0,
  resizeTrace: 0,
  wmResizeProcessed: 0,
};

function parseResizeTrace(line) {
  const match = line.match(/episode=(\d+) sample=(\d+) present=(\d+) draws=(\d+) window_draws=(\d+) surface=(\d+)x(\d+) configured=(\d+)x(\d+) requested=(\d+)x(\d+) backbuffer=(\d+)x(\d+)/);
  if (!match) return null;
  const values = match.slice(1).map(Number);
  return {
    episode: values[0], sample: values[1], present: values[2],
    draws: values[3], windowDraws: values[4],
    surface: values.slice(5, 7), configured: values.slice(7, 9),
    requested: values.slice(9, 11), backbuffer: values.slice(11, 13),
  };
}

const pythonTrace = String.raw`
import bpy
_bw_resize_last = None
def _bw_resize_trace():
    global _bw_resize_last
    window = bpy.context.window
    screen = bpy.context.screen
    snapshot = (window.width, window.height, tuple((area.type, area.x, area.y, area.width, area.height, tuple((region.type, region.x, region.y, region.width, region.height) for region in area.regions)) for area in screen.areas)) if window and screen else None
    if snapshot != _bw_resize_last:
        print('[bw-resize-python] ' + repr(snapshot), flush=True)
        _bw_resize_last = snapshot
    return 0.1
bpy.app.timers.register(_bw_resize_trace, first_interval=0.0, persistent=True)
`;

async function sample(page) {
  return page.evaluate(() => {
    const module = window.__bwModule;
    const canvas = document.querySelector("#canvas");
    return {
      inner: [window.innerWidth, window.innerHeight],
      canvas: canvas ? [canvas.width, canvas.height, canvas.clientWidth, canvas.clientHeight] : null,
      ticks: module && typeof module._bw_wm_tick_count === "function" ?
        Number(module._bw_wm_tick_count()) : null,
      presents: module && typeof module._bw_present_count === "function" ?
        Number(module._bw_present_count()) : null,
      episodes: module && typeof module._bw_redraw_episode_count === "function" ?
        Number(module._bw_redraw_episode_count()) : null,
    };
  });
}

function dimensionsMatch(sampleValue, width, height) {
  return sampleValue.inner?.[0] === width && sampleValue.inner?.[1] === height &&
    sampleValue.canvas?.[0] === width && sampleValue.canvas?.[1] === height &&
    sampleValue.canvas?.[2] === width && sampleValue.canvas?.[3] === height;
}

const browser = await chromium.launch({
  headless: false,
  args: ["--enable-unsafe-webgpu", "--use-webgpu-adapter=swiftshader", "--use-gpu-in-tests"],
});
try {
  const context = await browser.newContext({viewport: {width: 1280, height: 720}, deviceScaleFactor: 1});
  const page = await context.newPage();
  page.on("console", (message) => {
    const line = message.text();
    if (line.includes("Scissor rect") && line.includes("not contained")) counters.scissorRejected++;
    if (line.includes("draw encoding rejected")) counters.encodingRejected++;
    if (line.includes("queue submission rejected")) counters.submissionRejected++;
    if (line.includes("present transaction rejected")) counters.transactionRejected++;
    if (line.includes("[bw][GPU-LOST]")) counters.deviceLost++;
    if (line.includes("WGPUWeb-resize: backing ->")) counters.resizeApplied++;
    if (line.includes("WGPUWeb-resize-trace:")) {
      counters.resizeTrace++;
      const trace = parseResizeTrace(line);
      if (trace) resizeTraces.push(trace);
    }
    if (line.includes("ghost_event_proc: window") && line.includes("state =")) {
      counters.wmResizeProcessed++;
    }
    if (/WGPUWeb-resize:|WGPUWeb-resize-trace:|bw-resize-python|Scissor rect|draw encoding rejected|queue submission rejected|present transaction rejected|ghost_event_proc: window|GPU-LOST/.test(line)) {
      lines.push(line);
    }
  });
  const query = new URLSearchParams({
    args: "--debug-events",
    pyexpr: `exec(${JSON.stringify(pythonTrace)})`,
  });
  await page.goto(`http://127.0.0.1:${port}/windowed.html?${query}`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => document.querySelector("#state")?.dataset.state === "running", null,
                             {timeout: 180000, polling: 250});
  // Start the resize epochs after the boot recovery episode's 180-tick ceiling. This makes
  // each post-resize burst attributable to the resize publication rather than leftover boot work.
  await page.waitForFunction(() => Number(window.__bwModule?._bw_wm_tick_count?.()) >= 200, null,
                             {timeout: 30000, polling: 100});
  await page.waitForTimeout(1000);
  const initial = await sample(page);
  await page.setViewportSize({width: 1100, height: 640});
  await page.waitForTimeout(6000);
  const shrunk = await sample(page);
  await page.setViewportSize({width: 1280, height: 720});
  await page.waitForTimeout(6000);
  const restored = await sample(page);

  const evidence = {initial, shrunk, restored, counters, resizeTraces, lines};
  const failures = [];
  if (!dimensionsMatch(initial, 1280, 720)) failures.push("initial canvas extent mismatch");
  if (!dimensionsMatch(shrunk, 1100, 640)) failures.push("shrunk canvas extent mismatch");
  if (!dimensionsMatch(restored, 1280, 720)) failures.push("restored canvas extent mismatch");
  if (!(shrunk.ticks > initial.ticks && restored.ticks > shrunk.ticks)) {
    failures.push("WM ticks did not advance across both resize epochs");
  }
  if (!(shrunk.presents > initial.presents && restored.presents > shrunk.presents)) {
    failures.push("uncapped presentation count did not advance across both resize epochs");
  }
  if (!(shrunk.episodes > initial.episodes && restored.episodes > shrunk.episodes)) {
    failures.push("coherent resize commits did not start fresh redraw episodes");
  }
  const shrinkRedrawPresents = shrunk.presents - initial.presents;
  const restoreRedrawPresents = restored.presents - shrunk.presents;
  if (shrinkRedrawPresents < 8 || restoreRedrawPresents < 8) {
    failures.push(`bounded redraw episodes absent: ${shrinkRedrawPresents}/${restoreRedrawPresents}`);
  }
  if (counters.resizeApplied < 3) failures.push("shell backing resize was not observed");
  if (counters.wmResizeProcessed < 2) failures.push("WM resize processing was not observed");
  const traceEpochs = [
    {episode: shrunk.episodes, extent: [1100, 640], label: "shrink"},
    {episode: restored.episodes, extent: [1280, 720], label: "restore"},
  ];
  for (const {episode, extent, label} of traceEpochs) {
    const traces = resizeTraces.filter((trace) => trace.episode === episode);
    if (traces.length === 0 || traces.length > 24) {
      failures.push(`${label} trace sample count=${traces.length}`);
      continue;
    }
    for (const trace of traces) {
      for (const field of ["surface", "configured", "requested", "backbuffer"]) {
        if (trace[field][0] !== extent[0] || trace[field][1] !== extent[1]) {
          failures.push(`${label} trace ${field}=${trace[field].join("x")}`);
        }
      }
    }
  }
  if (counters.resizeTrace > 64 || resizeTraces.length !== counters.resizeTrace) {
    failures.push(`resize trace bound/parse mismatch=${resizeTraces.length}/${counters.resizeTrace}`);
  }
  for (const name of ["scissorRejected", "encodingRejected", "submissionRejected",
                      "transactionRejected", "deviceLost"]) {
    if (counters[name] !== 0) failures.push(`${name}=${counters[name]}`);
  }
  if (failures.length) {
    console.error(JSON.stringify(evidence, null, 2));
    throw new Error(`BW_M4_RESIZE_RECOVERY_FAIL ${failures.join("; ")}`);
  }
  console.log(`BW_M4_RESIZE_RECOVERY_PASS resize=${counters.resizeApplied} ` +
              `wm=${counters.wmResizeProcessed} ticks=${initial.ticks}/${shrunk.ticks}/${restored.ticks} ` +
              `presents=${initial.presents}/${shrunk.presents}/${restored.presents} ` +
              `episodes=${initial.episodes}/${shrunk.episodes}/${restored.episodes} ` +
              `redrawPresents=${shrinkRedrawPresents}/${restoreRedrawPresents} ` +
              `trace=${resizeTraces.length}`);
}
finally {
  await browser.close();
}
