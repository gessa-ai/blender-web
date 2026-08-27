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
const resizeLayouts = [];
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

function parseDrawPlan(token) {
  const match = token.match(
    /^(\d+)\/([01])\/(-?\d+)x(-?\d+)\/vp(-?\d+),(-?\d+),(\d+)x(\d+)\/sc([01]),(\d+),(\d+),(\d+)x(\d+)$/,
  );
  if (!match) return null;
  const values = match.slice(1).map(Number);
  return {
    sequence: values[0],
    windowTarget: values[1] === 1,
    target: values.slice(2, 4),
    viewport: values.slice(4, 8),
    scissor: {enabled: values[8] === 1, rect: values.slice(9, 13)},
  };
}

function parseResizeTrace(line) {
  const match = line.match(/episode=(\d+) sample=(\d+) present=(\d+) draws=(\d+) window_draws=(\d+) surface=(\d+)x(\d+) configured=(\d+)x(\d+) requested=(\d+)x(\d+) backbuffer=(\d+)x(\d+) any=(\S+) background=(\S+) display=(\S+)/);
  if (!match) return null;
  const values = match.slice(1, 14).map(Number);
  const plans = {
    any: parseDrawPlan(match[14]),
    background: parseDrawPlan(match[15]),
    display: parseDrawPlan(match[16]),
  };
  if (Object.values(plans).some((plan) => plan === null)) return null;
  return {
    episode: values[0], sample: values[1], present: values[2],
    draws: values[3], windowDraws: values[4],
    surface: values.slice(5, 7), configured: values.slice(7, 9),
    requested: values.slice(9, 11), backbuffer: values.slice(11, 13),
    ...plans,
  };
}

function parseResizeLayout(line) {
  const match = line.match(
    /\[bw-resize-python\] window=(\d+)x(\d+) view3d_area=(\d+)x(\d+) view3d_window=(\d+)x(\d+)/,
  );
  if (!match) return null;
  const values = match.slice(1).map(Number);
  return {
    window: values.slice(0, 2),
    view3dArea: values.slice(2, 4),
    view3dWindow: values.slice(4, 6),
  };
}

function latestResizeLayout(layouts, extent) {
  for (let index = layouts.length - 1; index >= 0; index--) {
    if (layouts[index].window[0] === extent[0] && layouts[index].window[1] === extent[1]) {
      return layouts[index];
    }
  }
  return null;
}

function validateResizeTraceEpoch(traces, episode, extent, layout, label) {
  const failures = [];
  const epoch = traces.filter((trace) => trace.episode === episode);
  if (epoch.length === 0 || epoch.length > 24) {
    failures.push(`${label} trace sample count=${epoch.length}`);
    return failures;
  }
  if (layout === null) {
    failures.push(`${label} has no matching Blender VIEW_3D layout`);
    return failures;
  }
  for (let index = 0; index < epoch.length; index++) {
    const trace = epoch[index];
    if (trace.sample !== index) failures.push(`${label} trace sample=${trace.sample}/${index}`);
    if (index > 0 && trace.present <= epoch[index - 1].present) {
      failures.push(`${label} trace presents not increasing`);
    }
    if (index > 0 &&
        (trace.draws < epoch[index - 1].draws ||
         trace.windowDraws < epoch[index - 1].windowDraws)) {
      failures.push(`${label} trace draw counts regressed`);
    }
    for (const field of ["surface", "configured", "requested", "backbuffer"]) {
      if (trace[field][0] !== extent[0] || trace[field][1] !== extent[1]) {
        failures.push(`${label} trace ${field}=${trace[field].join("x")}`);
      }
    }
    if (trace.any.sequence !== trace.draws) {
      failures.push(`${label} latest draw sequence=${trace.any.sequence}/${trace.draws}`);
    }
    if (trace.windowDraws > trace.draws) {
      failures.push(`${label} window draws exceed all draws`);
    }
    if (trace.background.sequence !== 0) {
      if (trace.background.windowTarget) {
        failures.push(`${label} overlay_background incorrectly targets the window`);
      }
      if (trace.background.target[0] !== layout.view3dWindow[0] ||
          trace.background.target[1] !== layout.view3dWindow[1]) {
        failures.push(
          `${label} overlay_background target=${trace.background.target.join("x")} ` +
          `VIEW_3D/WINDOW=${layout.view3dWindow.join("x")}`,
        );
      }
      if (trace.background.viewport[0] !== 0 || trace.background.viewport[1] !== 0 ||
          trace.background.viewport[2] !== layout.view3dWindow[0] ||
          trace.background.viewport[3] !== layout.view3dWindow[1]) {
        failures.push(`${label} overlay_background viewport does not cover VIEW_3D/WINDOW`);
      }
    }
    if (trace.display.sequence !== 0 && !trace.display.windowTarget) {
      failures.push(`${label} OCIO_Display is not a direct window draw`);
    }
    for (const planName of ["any", "background", "display"]) {
      const plan = trace[planName];
      if (plan.sequence > trace.draws) {
        failures.push(`${label} ${planName} sequence exceeds all draws`);
      }
      if (plan.sequence === 0) continue;
      const [targetWidth, targetHeight] = plan.target;
      const [viewportX, viewportY, viewportWidth, viewportHeight] = plan.viewport;
      if (targetWidth <= 0 || targetHeight <= 0 || viewportWidth <= 0 || viewportHeight <= 0) {
        failures.push(`${label} ${planName} has empty target/viewport`);
      }
      if (plan.windowTarget &&
          (targetWidth !== extent[0] || targetHeight !== extent[1])) {
        failures.push(`${label} ${planName} window target=${targetWidth}x${targetHeight}`);
      }
      if (plan.scissor.enabled) {
        const [x, y, width, height] = plan.scissor.rect;
        if (x + width > targetWidth || y + height > targetHeight) {
          failures.push(`${label} ${planName} scissor exceeds target`);
        }
      }
      if (!Number.isInteger(viewportX) || !Number.isInteger(viewportY)) {
        failures.push(`${label} ${planName} viewport origin is invalid`);
      }
    }
  }
  if (epoch.at(-1).draws <= epoch[0].draws) {
    failures.push(`${label} draw counts did not advance`);
  }
  if (epoch.at(-1).windowDraws <= epoch[0].windowDraws) {
    failures.push(`${label} window draw counts did not advance`);
  }
  for (const planName of ["background", "display"]) {
    const sequences = new Set(epoch.map((trace) => trace[planName].sequence).filter(Boolean));
    if (sequences.size < 2) failures.push(`${label} ${planName} did not advance`);
  }
  return failures;
}

const pythonTrace = String.raw`
import bpy
_bw_resize_last = None
def _bw_resize_trace():
    global _bw_resize_last
    window = bpy.context.window
    screen = bpy.context.screen
    view3d_area = next((area for area in screen.areas if area.type == 'VIEW_3D'), None) if screen else None
    view3d_window = next((region for region in view3d_area.regions if region.type == 'WINDOW'), None) if view3d_area else None
    snapshot = (window.width, window.height, view3d_area.width, view3d_area.height, view3d_window.width, view3d_window.height) if window and view3d_area and view3d_window else None
    if snapshot != _bw_resize_last:
        if snapshot:
            print(f'[bw-resize-python] window={snapshot[0]}x{snapshot[1]} view3d_area={snapshot[2]}x{snapshot[3]} view3d_window={snapshot[4]}x{snapshot[5]}', flush=True)
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
    if (line.includes("[bw-resize-python]")) {
      const layout = parseResizeLayout(line);
      if (layout) resizeLayouts.push(layout);
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

  const evidence = {initial, shrunk, restored, counters, resizeLayouts, resizeTraces, lines};
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
    const layout = latestResizeLayout(resizeLayouts, extent);
    failures.push(...validateResizeTraceEpoch(resizeTraces, episode, extent, layout, label));
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
              `trace=${resizeTraces.length} plans=advancing,current,contained,view3d-bound`);
}
finally {
  await browser.close();
}
