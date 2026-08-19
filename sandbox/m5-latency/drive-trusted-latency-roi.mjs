// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Strict current-artifact M5 latency receipt for the trusted N sidebar toggle.
// Operator start is calibrated from Blender CLOG. Visible response uses direct
// Playwright screenshots over a predeclared right-sidebar ROI derived solely
// from the READY View3D geometry. Noise and signal use the same ROI and the
// unchanged MAD > 5 detector plus 100/150/33 ms budgets.

import { createHash } from 'crypto';
import { createRequire } from 'module';
import {
  existsSync, mkdirSync, readFileSync, statSync, writeFileSync,
} from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  captureRuntimeArtifactSet, RUNTIME_BINARY_PATHS, RUNTIME_CONTRACT_SOURCE,
} from '../m5-final/runtime-artifacts.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const DEFAULT_OUT = join(HERE, 'evidence');
const DEFAULT_MODULES = '/Users/paws/plushly/game-platform/node_modules';
const N = 10;
const SPACING_MS = 600;
const ROI_WIDTH = 200;
const BUDGETS = Object.freeze({
  endToEndMedianMs: 100,
  endToEndP95Ms: 150,
  keypressToOperatorMedianMs: 33,
  changeThresholdFloor: 5,
});
const DENIED_CONSOLE = Object.freeze([
  'GPUValidationError', 'WebGPU Error', 'device lost', 'table index is out of bounds',
]);

const PY_CALIBRATOR = String.raw`
import bpy,json,os,time
_m5r={"armed":False}
def _m5r_emit(*parts):
    try: os.write(2,(" ".join(str(x) for x in parts)+"\n").encode("utf-8"))
    except Exception: pass
def _m5r_view3d():
    w=bpy.context.window
    if w is None or w.screen is None: return None
    for a in w.screen.areas:
        if a.type == 'VIEW_3D':
            for r in a.regions:
                if r.type == 'WINDOW':
                    return {"x":r.x+r.width/2.0,"y":r.y+r.height/2.0,"width":r.width,"height":r.height}
    return None
def _m5r_arm():
    v=_m5r_view3d()
    if v is None: return 0.02
    if _m5r["armed"]: return None
    _m5r["armed"]=True
    for k in range(5):
        t0=time.time()
        try: bpy.ops.ed.undo_push(message="m5-roi-lat-cal-%d"%k)
        except Exception as exc: _m5r_emit("M5_ROI_CAL_ERR",k,repr(exc))
        t1=time.time()
        _m5r_emit("M5_ROI_CAL",k,"%.6f"%t0,"%.6f"%t1)
    _m5r_emit("M5_ROI_READY",json.dumps({"view3d":v},sort_keys=True,separators=(",",":")))
    return None
bpy.app.timers.register(_m5r_arm,first_interval=0.0,persistent=False)
`.trim();

function parseArgs(argv) {
  const out = { port: 8127, run: null, outRoot: DEFAULT_OUT, timeoutMs: 120000, headed: true, selfcheck: false };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === '--port') out.port = Number(argv[++index]);
    else if (arg === '--run') out.run = argv[++index];
    else if (arg === '--out-root') out.outRoot = resolve(argv[++index]);
    else if (arg === '--timeout-ms') out.timeoutMs = Number(argv[++index]);
    else if (arg === '--headless') out.headed = false;
    else if (arg === '--selfcheck') out.selfcheck = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!Number.isInteger(out.port) || out.port < 1 || out.port > 65535) throw new Error(`invalid port: ${out.port}`);
  if (!Number.isFinite(out.timeoutMs) || out.timeoutMs < 30000) throw new Error(`invalid timeout: ${out.timeoutMs}`);
  if (out.run != null && !/^[a-z0-9][a-z0-9._-]*$/i.test(out.run)) throw new Error(`invalid run: ${out.run}`);
  return out;
}

function resolveLibraries() {
  const roots = [process.env.BW_NODE_MODULES, process.env.NODE_PATH, DEFAULT_MODULES].filter(Boolean);
  const errors = [];
  for (const root of roots) {
    try {
      const require = createRequire(join(root, 'package.json'));
      return { chromium: require('playwright').chromium, sharp: require('sharp'), root };
    }
    catch (error) { errors.push(`${root}: ${error.message}`); }
  }
  throw new Error(`cannot resolve Playwright/sharp\n${errors.join('\n')}`);
}

function sha256File(path) { return createHash('sha256').update(readFileSync(path)).digest('hex'); }
function fileReceipt(path) {
  const stat = statSync(path);
  return { path: path.slice(REPO.length + 1), bytes: stat.size, sha256: sha256File(path) };
}
function sleep(ms) { return new Promise((resolvePromise) => setTimeout(resolvePromise, ms)); }
function quantile(sorted, q) {
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * q;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return low === high ? sorted[low] : sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}
function stats(values) {
  const sorted = values.filter((value) => value != null && Number.isFinite(value)).slice().sort((a, b) => a - b);
  if (!sorted.length) return { n: 0, min: null, max: null, mean: null, median: null, p95: null };
  return {
    n: sorted.length, min: sorted[0], max: sorted.at(-1),
    mean: sorted.reduce((sum, value) => sum + value, 0) / sorted.length,
    median: quantile(sorted, 0.5), p95: quantile(sorted, 0.95),
  };
}
function round1(value) { return value == null ? null : Math.round(value * 10) / 10; }
function roundedStats(values) {
  return Object.fromEntries(Object.entries(stats(values)).map(([key, value]) => [key, round1(value)]));
}

function parseClogStarted(line) {
  const match = /^(\d+):(\d+)(?::(\d+))?\.(\d+)\s+operator\s*\|\s*Started\s+(bpy\.ops\.[A-Za-z0-9_.]+)/.exec(line);
  if (!match) return null;
  let hours = 0;
  let minutes;
  let seconds;
  if (match[3] != null) { hours = +match[1]; minutes = +match[2]; seconds = +match[3]; }
  else { minutes = +match[1]; seconds = +match[2]; }
  return {
    relativeSeconds: hours * 3600 + minutes * 60 + seconds + Number(match[4]) / 1000,
    operator: match[5], line,
  };
}

function deriveRoi(view3d, canvasHeight) {
  const right = Math.round(view3d.x + view3d.width / 2);
  const top = Math.round(canvasHeight - (view3d.y + view3d.height / 2));
  return { left: right - ROI_WIDTH, top, width: ROI_WIDTH, height: Math.round(view3d.height) };
}

async function signature(sharp, screenshot) {
  return new Uint8Array(await sharp(screenshot).greyscale()
    .resize(160, 90, { fit: 'fill' }).raw().toBuffer());
}
function meanAbsDiff(a, b) {
  let sum = 0;
  for (let index = 0; index < a.length; index++) sum += Math.abs(a[index] - b[index]);
  return sum / a.length;
}
async function capture(page, sharp, roi) {
  const request = Date.now() / 1000;
  const screenshot = await page.screenshot({
    type: 'jpeg', quality: 70,
    clip: { x: roi.left, y: roi.top, width: roi.width, height: roi.height },
  });
  const completed = Date.now() / 1000;
  return {
    responseEpochSeconds: completed,
    responseMs: (completed - request) * 1000,
    signature: await signature(sharp, screenshot),
  };
}

async function waitConsole(lines, predicate, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const line = lines.find(predicate);
    if (line) return line;
    await sleep(20);
  }
  throw new Error(`timed out waiting for ${label}`);
}

function runSelfcheck() {
  const roi = deriveRoi({ x: 526, y: 383.5, width: 1048, height: 621 }, 720);
  if (JSON.stringify(roi) !== JSON.stringify({ left: 850, top: 26, width: 200, height: 621 })) {
    throw new Error(`selfcheck: ROI drift ${JSON.stringify(roi)}`);
  }
  const parsed = parseClogStarted('00:17.220 operator | Started bpy.ops.wm.context_toggle()');
  if (parsed?.operator !== 'bpy.ops.wm.context_toggle' || parsed.relativeSeconds !== 17.22) {
    throw new Error('selfcheck: CLOG parser drift');
  }
  if (BUDGETS.endToEndMedianMs !== 100 || BUDGETS.endToEndP95Ms !== 150 ||
      BUDGETS.keypressToOperatorMedianMs !== 33 || BUDGETS.changeThresholdFloor !== 5) {
    throw new Error('selfcheck: budget drift');
  }
  process.stdout.write(JSON.stringify({ status: 'PASS', checks: 3, samples: N, roi, budgets: BUDGETS }, null, 2) + '\n');
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.selfcheck) { runSelfcheck(); return; }
  if (!options.run) throw new Error('--run is required');
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing to overwrite evidence: ${outDir}`);
  const binaryDir = resolve(process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin'));
  const { binaryFiles, splitManifest } = captureRuntimeArtifactSet(binaryDir, fileReceipt);
  mkdirSync(options.outRoot, { recursive: true });
  mkdirSync(outDir);

  const { chromium, sharp, root: playwrightRoot } = resolveLibraries();
  const startedAt = new Date().toISOString();
  const consoleLines = [];
  const pageErrors = [];
  const requests = [];
  const liveVisual = [];
  const captureResponseMs = [];
  let canvasReceipt = null;
  let ready = null;
  let roi = null;
  let trustedInputs = [];
  let noise = null;
  let fatal = null;
  const browser = await chromium.launch({ headless: !options.headed });

  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on('console', (message) => consoleLines.push(message.text()));
    page.on('pageerror', (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on('crash', () => pageErrors.push('page crashed'));
    page.on('request', (request) => requests.push({ method: request.method(), type: request.resourceType(), url: request.url() }));
    await page.addInitScript(({ calibrator }) => {
      window.__BW_ARGS = ['--log', 'operator', '--log-level', 'debug'];
      window.__BW_PYEXPR = calibrator;
      window.__m5RoiLatency = { armed: false, next: 0, inputs: [] };
      window.addEventListener('keydown', (event) => {
        const state = window.__m5RoiLatency;
        if (!state.armed || event.key !== 'n' || event.code !== 'KeyN') return;
        const index = state.next++;
        const epochSeconds = (performance.timeOrigin + event.timeStamp) / 1000;
        const record = {
          index, label: index % 2 === 0 ? 'n_show' : 'n_hide', epochSeconds,
          key: event.key, code: event.code, isTrusted: event.isTrusted,
          targetId: event.target?.id || null, activeId: document.activeElement?.id || null,
        };
        state.inputs.push(record);
        console.error(`M5_ROI_DISPATCH ${index} ${record.label} ${epochSeconds.toFixed(6)}`);
      }, true);
    }, { calibrator: PY_CALIBRATOR });

    await page.goto(`http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`, {
      waitUntil: 'domcontentloaded', timeout: options.timeoutMs,
    });
    await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
      null, { timeout: options.timeoutMs, polling: 100 });
    const readyLine = await waitConsole(consoleLines, (line) => line.startsWith('M5_ROI_READY '),
      options.timeoutMs, 'M5_ROI_READY');
    ready = JSON.parse(readyLine.slice('M5_ROI_READY '.length));
    const canvas = page.locator('#canvas');
    const box = await canvas.boundingBox();
    if (!box) throw new Error('canvas has no bounding box');
    await page.mouse.move(box.x + ready.view3d.x, box.y + box.height - ready.view3d.y);
    await canvas.focus();
    canvasReceipt = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas');
      const bounds = canvas.getBoundingClientRect();
      return {
        backing: [canvas.width, canvas.height], css: [bounds.width, bounds.height], dpr: devicePixelRatio,
        activeId: document.activeElement?.id || null, crossOriginIsolated,
        shellState: document.querySelector('#state')?.textContent || null,
      };
    });
    roi = deriveRoi(ready.view3d, canvasReceipt.backing[1]);
    if (roi.left < 0 || roi.top < 0 || roi.left + roi.width > 1280 || roi.top + roi.height > 720) {
      throw new Error(`derived ROI escapes canvas: ${JSON.stringify(roi)}`);
    }
    await page.keyboard.press('Escape');
    await sleep(500);

    const contextToggleCount = () => consoleLines.filter((line) =>
      line.includes('| Started bpy.ops.wm.context_toggle')).length;
    const waitToggle = async (minimum) => {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        if (contextToggleCount() >= minimum) return;
        await sleep(20);
      }
      throw new Error(`timed out waiting for context toggle ${minimum}`);
    };
    const before = contextToggleCount();
    await page.keyboard.press('n');
    await waitToggle(before + 1);
    await sleep(1500);
    await page.keyboard.press('n');
    await waitToggle(before + 2);
    await sleep(1500);

    const noiseShots = [];
    for (let index = 0; index < 7; index++) {
      const shot = await capture(page, sharp, roi);
      noiseShots.push(shot);
      captureResponseMs.push(shot.responseMs);
      await sleep(30);
    }
    const noiseDiffs = [];
    for (let index = 1; index < noiseShots.length; index++) {
      noiseDiffs.push(meanAbsDiff(noiseShots[index - 1].signature, noiseShots[index].signature));
    }
    noiseDiffs.sort((a, b) => a - b);
    const floor = quantile(noiseDiffs, 0.25);
    const median = quantile(noiseDiffs, 0.5);
    const p95 = quantile(noiseDiffs, 0.95);
    const threshold = Math.max(floor * 8, median * 5, BUDGETS.changeThresholdFloor);
    noise = { floor, median, p95, threshold, captures: noiseShots.length };
    await page.evaluate(() => {
      window.__m5RoiLatency.armed = true;
      window.__m5RoiLatency.next = 0;
      window.__m5RoiLatency.inputs = [];
    });
    for (let index = 0; index < N; index++) {
      const baseline = await capture(page, sharp, roi);
      captureResponseMs.push(baseline.responseMs);
      await page.keyboard.press('n');
      const input = await page.evaluate((wanted) =>
        window.__m5RoiLatency.inputs.find((item) => item.index === wanted) || null, index);
      if (!input) throw new Error(`missing N input ${index}`);
      let visibleEpochSeconds = null;
      let maxDifference = 0;
      let captureCount = 0;
      const deadline = input.epochSeconds * 1000 + 300;
      while (Date.now() <= deadline) {
        const shot = await capture(page, sharp, roi);
        captureResponseMs.push(shot.responseMs);
        captureCount++;
        const difference = meanAbsDiff(baseline.signature, shot.signature);
        maxDifference = Math.max(maxDifference, difference);
        if (difference > threshold) {
          visibleEpochSeconds = shot.responseEpochSeconds;
          break;
        }
      }
      liveVisual.push({ index, dispatchEpochSeconds: input.epochSeconds, visibleEpochSeconds, maxDifference, captureCount });
      const nextTarget = input.epochSeconds * 1000 + SPACING_MS;
      if (Date.now() < nextTarget) await sleep(nextTarget - Date.now());
    }
    await page.evaluate(() => { window.__m5RoiLatency.armed = false; });
    await sleep(1000);
    trustedInputs = await page.evaluate(() => window.__m5RoiLatency.inputs);
    await page.screenshot({ path: join(outDir, 'canvas-final.png') });
  }
  catch (error) { fatal = error?.stack || String(error); }
  finally { await browser.close(); }

  const calibrations = [];
  const dispatches = [];
  const operators = [];
  for (const line of consoleLines) {
    let match = /^M5_ROI_CAL (\d+) ([\d.]+) ([\d.]+)/.exec(line);
    if (match) {
      calibrations.push({ index: +match[1], start: +match[2], end: +match[3] });
      continue;
    }
    match = /^M5_ROI_DISPATCH (\d+) (\S+) ([\d.]+)/.exec(line);
    if (match) {
      dispatches.push({ index: +match[1], label: match[2], epochSeconds: +match[3] });
      continue;
    }
    const operator = parseClogStarted(line);
    if (operator) operators.push(operator);
  }
  const calibrationOps = operators.filter((item) =>
    item.operator === 'bpy.ops.ed.undo_push' && item.line.includes('m5-roi-lat-cal-')).slice(0, 5);
  const pairs = Math.min(calibrations.length, calibrationOps.length);
  const tickStarts = [];
  for (let index = 0; index < pairs; index++) {
    tickStarts.push((calibrations[index].start + calibrations[index].end) / 2 - calibrationOps[index].relativeSeconds);
  }
  tickStarts.sort((a, b) => a - b);
  const tickStart = tickStarts.length ? quantile(tickStarts, 0.5) : null;
  const tickSpreadMs = tickStarts.length ? (tickStarts.at(-1) - tickStarts[0]) * 1000 : null;

  const samples = [];
  let operatorIndex = 0;
  for (let index = 0; index < dispatches.length; index++) {
    const dispatch = dispatches[index];
    const end = index + 1 < dispatches.length ? dispatches[index + 1].epochSeconds :
      dispatch.epochSeconds + SPACING_MS / 1000 + 1;
    let operatorEpochSeconds = null;
    if (tickStart != null) {
      for (; operatorIndex < operators.length; operatorIndex++) {
        const item = operators[operatorIndex];
        if (item.operator !== 'bpy.ops.wm.context_toggle') continue;
        const epoch = item.relativeSeconds + tickStart;
        if (epoch < dispatch.epochSeconds - 0.02) continue;
        if (epoch >= end) break;
        operatorEpochSeconds = epoch;
        operatorIndex++;
        break;
      }
    }
    const visual = liveVisual.find((item) => item.index === dispatch.index);
    const visible = visual?.visibleEpochSeconds ?? null;
    samples.push({
      index: dispatch.index, label: dispatch.label,
      keypressToOperatorMs: operatorEpochSeconds == null ? null :
        (operatorEpochSeconds - dispatch.epochSeconds) * 1000,
      operatorToPresentMs: operatorEpochSeconds == null || visible == null ? null :
        (visible - operatorEpochSeconds) * 1000,
      endToEndMs: visible == null ? null : (visible - dispatch.epochSeconds) * 1000,
      maxDifference: visual?.maxDifference ?? 0, captureCount: visual?.captureCount ?? 0,
      hasOperator: operatorEpochSeconds != null, hasVisible: visible != null,
    });
  }
  const metrics = {
    keypressToOperatorMs: roundedStats(samples.map((sample) => sample.keypressToOperatorMs)),
    operatorToPresentMs: roundedStats(samples.map((sample) => sample.operatorToPresentMs)),
    endToEndMs: roundedStats(samples.map((sample) => sample.endToEndMs)),
    captureResponseMs: roundedStats(captureResponseMs),
  };
  const externalRequests = requests.filter((request) => {
    try { return !['127.0.0.1', 'localhost'].includes(new URL(request.url).hostname); }
    catch (_) { return true; }
  });
  const deniedDiagnostics = DENIED_CONSOLE.filter((needle) => consoleLines.some((line) => line.includes(needle)));
  const inputPass = trustedInputs.length === N && trustedInputs.every((item, index) =>
    item.index === index && item.key === 'n' && item.code === 'KeyN' && item.isTrusted &&
    item.targetId === 'canvas' && item.activeId === 'canvas');
  const measurementPass = dispatches.length === N && samples.length === N &&
    metrics.keypressToOperatorMs.n === N && metrics.endToEndMs.n === N;
  const budgetPass = measurementPass &&
    metrics.keypressToOperatorMs.median <= BUDGETS.keypressToOperatorMedianMs &&
    metrics.endToEndMs.median <= BUDGETS.endToEndMedianMs &&
    metrics.endToEndMs.p95 <= BUDGETS.endToEndP95Ms;
  const canvasPass = canvasReceipt?.backing?.join('x') === '1280x720' &&
    canvasReceipt?.css?.join('x') === '1280x720' && canvasReceipt?.dpr === 1 &&
    canvasReceipt?.activeId === 'canvas' && canvasReceipt?.crossOriginIsolated === true;
  const pass = !fatal && pageErrors.length === 0 && externalRequests.length === 0 &&
    deniedDiagnostics.length === 0 && pairs === 5 && inputPass && canvasPass && budgetPass &&
    noise?.threshold >= BUDGETS.changeThresholdFloor;

  const consolePath = join(outDir, 'console.log');
  const inputsPath = join(outDir, 'trusted-inputs.json');
  const samplesPath = join(outDir, 'samples.json');
  const screenshotPath = join(outDir, 'canvas-final.png');
  const licensePath = join(outDir, 'canvas-final.png.license');
  writeFileSync(consolePath, consoleLines.join('\n') + '\n');
  writeFileSync(inputsPath, JSON.stringify(trustedInputs, null, 2) + '\n');
  writeFileSync(samplesPath, JSON.stringify(samples, null, 2) + '\n');
  if (existsSync(screenshotPath)) {
    writeFileSync(licensePath,
      'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  }
  const receipt = {
    schema: 'blender-web.m5-trusted-roi-latency.v1', run: options.run,
    status: pass ? 'PASS' : 'FAIL', startedAt, finishedAt: new Date().toISOString(),
    contract: {
      shell: 'shipping platform_web/shell/windowed.html',
      input: '10 trusted N sidebar toggles targeted at #canvas',
      operatorProbe: 'bpy.ops.wm.context_toggle',
      roi: {
        derivation: `rightmost ${ROI_WIDTH}px of READY View3D WINDOW region`,
        sourceView3d: ready?.view3d ?? null, rectangle: roi,
      },
      dispatchClock: 'DOM keydown epoch = performance.timeOrigin + event.timeStamp',
      operatorClock: 'CLOG gettimeofday epoch calibrated by five bracketed undo_push calls',
      visibleClock: 'Date.now after Playwright page.screenshot response (upper bound)',
      detector: `ROI -> 160x90 greyscale MAD > max(p25*8, median*5, ${BUDGETS.changeThresholdFloor})`,
      budgets: BUDGETS,
      runtimeArtifacts: RUNTIME_BINARY_PATHS,
    },
    result: {
      fatal, pageErrors, externalRequestCount: externalRequests.length, deniedDiagnostics,
      inputPass, canvasPass, measurementPass, budgetPass,
      nRequested: N, nDispatch: dispatches.length,
      nWithOperator: metrics.keypressToOperatorMs.n, nWithVisible: metrics.endToEndMs.n,
      calibration: { pairs, tickStartSpreadMs: round1(tickSpreadMs) },
      frameDiff: {
        roi, noiseFloorP25: round1(noise?.floor), noiseMedian: round1(noise?.median),
        noiseP95: round1(noise?.p95), changeThreshold: round1(noise?.threshold),
        noiseCaptures: noise?.captures ?? 0,
      },
      metrics, samples, canvas: canvasReceipt, ready,
    },
    browser: { headed: options.headed, playwrightRoot, trustedInputs },
    provenance: {
      driver: fileReceipt(fileURLToPath(import.meta.url)),
      runtimeContract: fileReceipt(RUNTIME_CONTRACT_SOURCE), splitManifest,
      shell: [
        fileReceipt(join(REPO, 'platform_web/shell/windowed.html')),
        fileReceipt(join(REPO, 'platform_web/shell/boot-windowed.js')),
      ],
      binaryFiles,
    },
    artifacts: {
      console: fileReceipt(consolePath), trustedInputs: fileReceipt(inputsPath),
      samples: fileReceipt(samplesPath),
      screenshot: existsSync(screenshotPath) ? fileReceipt(screenshotPath) : null,
      screenshotLicense: existsSync(licensePath) ? fileReceipt(licensePath) : null,
    },
  };
  const receiptPath = join(outDir, 'receipt.json');
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n');
  writeFileSync(join(outDir, 'receipt.sha256'), `${sha256File(receiptPath)}  receipt.json\n`);
  process.stdout.write(JSON.stringify({ status: receipt.status, outDir, result: receipt.result }, null, 2) + '\n');
  if (!pass) process.exitCode = 1;
}

main().catch((error) => {
  process.stderr.write((error?.stack || String(error)) + '\n');
  process.exitCode = 1;
});
