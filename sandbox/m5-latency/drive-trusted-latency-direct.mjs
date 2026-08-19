// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Strict current-artifact M5 latency receipt. Trusted Playwright keys target the
// shipping canvas. Visible response is polled with direct CDP
// Page.captureScreenshot calls because Page.screencastFrame is stale for the
// worker-owned OffscreenCanvas. The timestamp immediately after each screenshot
// response is an honest upper bound on capture/present. The pixel detector and
// 100/150/33 ms budgets are unchanged from notes/m5-latency-budget.md.

import { createHash } from 'crypto';
import { createRequire } from 'module';
import {
  existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync,
} from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const DEFAULT_OUT = join(HERE, 'evidence');
const DEFAULT_MODULES = '/Users/paws/plushly/game-platform/node_modules';
const THUMBNAIL = Object.freeze({ width: 160, height: 90 });
const BUDGETS = Object.freeze({
  endToEndMedianMs: 100,
  endToEndP95Ms: 150,
  keypressToOperatorMedianMs: 33,
  changeThresholdFloor: 5,
});
const PROBES = Object.freeze({
  n: Object.freeze({
    press: 'n', key: 'n', code: 'KeyN', operator: 'bpy.ops.wm.context_toggle',
    labels: Object.freeze(['n_show', 'n_hide']), prewarmMs: 1500,
  }),
  tab: Object.freeze({
    press: 'Tab', key: 'Tab', code: 'Tab', operator: 'bpy.ops.object.editmode_toggle',
    labels: Object.freeze(['tab_in', 'tab_out']), prewarmMs: 15000,
  }),
});
const DENIED_CONSOLE = Object.freeze([
  'GPUValidationError', 'WebGPU Error', 'device lost', 'table index is out of bounds',
]);

const PY_CALIBRATOR = String.raw`
import bpy,json,os,time
_m5tl={"armed":False}
def _m5tl_emit(*parts):
    try: os.write(2,(" ".join(str(x) for x in parts)+"\n").encode("utf-8"))
    except Exception: pass
def _m5tl_view3d():
    w=bpy.context.window
    if w is None or w.screen is None: return None
    for a in w.screen.areas:
        if a.type == 'VIEW_3D':
            for r in a.regions:
                if r.type == 'WINDOW':
                    return {"x":r.x+r.width/2.0,"y":r.y+r.height/2.0,"width":r.width,"height":r.height}
    return None
def _m5tl_arm():
    v=_m5tl_view3d()
    if v is None: return 0.02
    if _m5tl["armed"]: return None
    _m5tl["armed"]=True
    for k in range(5):
        t0=time.time()
        try: bpy.ops.ed.undo_push(message="m5-trusted-direct-cal-%d"%k)
        except Exception as exc: _m5tl_emit("M5_TRUSTED_DIRECT_CAL_ERR",k,repr(exc))
        t1=time.time()
        _m5tl_emit("M5_TRUSTED_DIRECT_CAL",k,"%.6f"%t0,"%.6f"%t1)
    _m5tl_emit("M5_TRUSTED_DIRECT_READY",json.dumps({"view3d":v},sort_keys=True,separators=(",",":")))
    return None
bpy.app.timers.register(_m5tl_arm,first_interval=0.0,persistent=False)
`.trim();

function parseArgs(argv) {
  const options = {
    port: 8127, run: null, outRoot: DEFAULT_OUT, n: 10, spacingMs: 600,
    timeoutMs: 120000, headed: true, probe: 'n', selfcheck: false,
  };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === '--port') options.port = Number(argv[++index]);
    else if (arg === '--run') options.run = argv[++index];
    else if (arg === '--out-root') options.outRoot = resolve(argv[++index]);
    else if (arg === '--n') options.n = Number(argv[++index]);
    else if (arg === '--spacing-ms') options.spacingMs = Number(argv[++index]);
    else if (arg === '--timeout-ms') options.timeoutMs = Number(argv[++index]);
    else if (arg === '--probe') options.probe = argv[++index];
    else if (arg === '--headless') options.headed = false;
    else if (arg === '--selfcheck') options.selfcheck = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!Number.isInteger(options.port) || options.port < 1 || options.port > 65535) {
    throw new Error(`invalid --port: ${options.port}`);
  }
  if (!Number.isInteger(options.n) || options.n < 10) throw new Error(`invalid --n: ${options.n}`);
  if (!Number.isFinite(options.spacingMs) || options.spacingMs < 300) {
    throw new Error(`invalid --spacing-ms: ${options.spacingMs}`);
  }
  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs < 30000) {
    throw new Error(`invalid --timeout-ms: ${options.timeoutMs}`);
  }
  if (!(options.probe in PROBES)) throw new Error(`invalid --probe: ${options.probe}`);
  if (options.run != null && !/^[a-z0-9][a-z0-9._-]*$/i.test(options.run)) {
    throw new Error(`invalid --run label: ${options.run}`);
  }
  return options;
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
  throw new Error(`cannot resolve Playwright/sharp; set BW_NODE_MODULES\n${errors.join('\n')}`);
}

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

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
  if (low === high) return sorted[low];
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

function stats(values) {
  const sorted = values.filter((value) => value != null && Number.isFinite(value))
    .slice().sort((a, b) => a - b);
  if (!sorted.length) return { n: 0, min: null, max: null, mean: null, median: null, p95: null };
  return {
    n: sorted.length,
    min: sorted[0], max: sorted[sorted.length - 1],
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
  if (match[3] != null) {
    hours = Number(match[1]); minutes = Number(match[2]); seconds = Number(match[3]);
  }
  else { minutes = Number(match[1]); seconds = Number(match[2]); }
  return {
    relativeSeconds: hours * 3600 + minutes * 60 + seconds + Number(match[4]) / 1000,
    operator: match[5], line,
  };
}

async function imageSignature(sharp, buffer) {
  const bytes = await sharp(buffer).greyscale()
    .resize(THUMBNAIL.width, THUMBNAIL.height, { fit: 'fill' }).raw().toBuffer();
  return new Uint8Array(bytes);
}

function meanAbsDiff(a, b) {
  if (!a || !b || a.length !== b.length) return null;
  let sum = 0;
  for (let index = 0; index < a.length; index++) sum += Math.abs(a[index] - b[index]);
  return sum / a.length;
}

async function captureDirect(client, sharp) {
  const requestEpochSeconds = Date.now() / 1000;
  const response = await client.send('Page.captureScreenshot', {
    format: 'jpeg', quality: 70, fromSurface: true, captureBeyondViewport: false,
  });
  const responseEpochSeconds = Date.now() / 1000;
  const buffer = Buffer.from(response.data, 'base64');
  return {
    requestEpochSeconds,
    responseEpochSeconds,
    responseMs: (responseEpochSeconds - requestEpochSeconds) * 1000,
    signature: await imageSignature(sharp, buffer),
  };
}

function runSelfcheck() {
  const parsed = parseClogStarted('00:17.220  operator | Started bpy.ops.wm.context_toggle()');
  if (parsed?.operator !== PROBES.n.operator || parsed.relativeSeconds !== 17.22) {
    throw new Error('selfcheck: CLOG parser drift');
  }
  if (quantile([1, 2, 3, 4], 0.5) !== 2.5) throw new Error('selfcheck: quantile drift');
  if (BUDGETS.endToEndMedianMs !== 100 || BUDGETS.endToEndP95Ms !== 150 ||
      BUDGETS.keypressToOperatorMedianMs !== 33 || BUDGETS.changeThresholdFloor !== 5) {
    throw new Error('selfcheck: published threshold drift');
  }
  process.stdout.write(JSON.stringify({
    status: 'PASS', checks: 3, budgets: BUDGETS, probes: Object.keys(PROBES),
  }, null, 2) + '\n');
}

async function waitForConsole(consoleLines, predicate, timeoutMs, description) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const match = consoleLines.find(predicate);
    if (match) return match;
    await sleep(20);
  }
  throw new Error(`timed out waiting for ${description}`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.selfcheck) { runSelfcheck(); return; }
  if (!options.run) throw new Error('--run is required');
  const probe = PROBES[options.probe];
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing to overwrite evidence: ${outDir}`);
  mkdirSync(options.outRoot, { recursive: true });
  mkdirSync(outDir);

  const { chromium, sharp, root: playwrightRoot } = resolveLibraries();
  const startedAt = new Date().toISOString();
  const consoleLines = [];
  const pageErrors = [];
  const requests = [];
  const visualSamples = [];
  const captureResponseMs = [];
  let canvasReceipt = null;
  let ready = null;
  let trustedInputs = [];
  let noise = null;
  let fatal = null;
  const browser = await chromium.launch({ headless: !options.headed });
  let page = null;

  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
    page = await context.newPage();
    page.on('console', (message) => consoleLines.push(message.text()));
    page.on('pageerror', (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on('crash', () => pageErrors.push('page crashed'));
    page.on('request', (request) => requests.push({
      method: request.method(), type: request.resourceType(), url: request.url(),
    }));
    await page.addInitScript(({ calibrator, expected }) => {
      window.__BW_ARGS = ['--log', 'operator', '--log-level', 'debug'];
      window.__BW_PYEXPR = calibrator;
      window.__m5TrustedDirect = { armed: false, next: 0, inputs: [] };
      window.addEventListener('keydown', (event) => {
        const state = window.__m5TrustedDirect;
        if (!state?.armed || event.key !== expected.key || event.code !== expected.code) return;
        const index = state.next++;
        const epochSeconds = (performance.timeOrigin + event.timeStamp) / 1000;
        const record = {
          index, label: expected.labels[index % expected.labels.length], epochSeconds,
          key: event.key, code: event.code, isTrusted: event.isTrusted,
          targetId: event.target?.id || null,
          activeId: document.activeElement?.id || null,
        };
        state.inputs.push(record);
        console.error(`M5_TRUSTED_DIRECT_DISPATCH ${index} ${record.label} ${epochSeconds.toFixed(6)}`);
      }, true);
    }, { calibrator: PY_CALIBRATOR, expected: probe });

    await page.goto(`http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`, {
      waitUntil: 'domcontentloaded', timeout: options.timeoutMs,
    });
    await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
      null, { timeout: options.timeoutMs, polling: 100 });
    const readyLine = await waitForConsole(consoleLines,
      (line) => line.startsWith('M5_TRUSTED_DIRECT_READY '),
      options.timeoutMs, 'M5_TRUSTED_DIRECT_READY');
    ready = JSON.parse(readyLine.slice('M5_TRUSTED_DIRECT_READY '.length));

    const canvas = page.locator('#canvas');
    const box = await canvas.boundingBox();
    if (!box) throw new Error('canvas has no bounding box');
    await page.mouse.move(box.x + ready.view3d.x, box.y + box.height - ready.view3d.y);
    await canvas.focus();
    canvasReceipt = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas');
      const bounds = canvas.getBoundingClientRect();
      return {
        backing: [canvas.width, canvas.height], css: [bounds.width, bounds.height],
        dpr: devicePixelRatio, activeId: document.activeElement?.id || null,
        crossOriginIsolated, shellState: document.querySelector('#state')?.textContent || null,
      };
    });

    await page.keyboard.press('Escape');
    await sleep(500);
    const probeOpCount = () => consoleLines.filter((line) =>
      line.includes(`| Started ${probe.operator}`)).length;
    const waitProbeOp = async (minimum) => {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        if (probeOpCount() >= minimum) return;
        await sleep(20);
      }
      throw new Error(`timed out waiting for prewarm ${probe.operator}`);
    };
    const beforePrewarm = probeOpCount();
    await page.keyboard.press(probe.press);
    await waitProbeOp(beforePrewarm + 1);
    await sleep(probe.prewarmMs);
    await page.keyboard.press(probe.press);
    await waitProbeOp(beforePrewarm + 2);
    await sleep(1500);

    const client = await context.newCDPSession(page);
    const noiseCaptures = [];
    for (let index = 0; index < 7; index++) {
      const shot = await captureDirect(client, sharp);
      noiseCaptures.push(shot);
      captureResponseMs.push(shot.responseMs);
      await sleep(30);
    }
    const noiseDiffs = [];
    for (let index = 1; index < noiseCaptures.length; index++) {
      noiseDiffs.push(meanAbsDiff(noiseCaptures[index - 1].signature, noiseCaptures[index].signature));
    }
    noiseDiffs.sort((a, b) => a - b);
    const floor = quantile(noiseDiffs, 0.25);
    const median = quantile(noiseDiffs, 0.5);
    const p95 = quantile(noiseDiffs, 0.95);
    const threshold = Math.max(floor * 8, median * 5, BUDGETS.changeThresholdFloor);
    noise = { floor, median, p95, threshold, captures: noiseCaptures.length };

    await page.evaluate(() => {
      window.__m5TrustedDirect.armed = true;
      window.__m5TrustedDirect.next = 0;
      window.__m5TrustedDirect.inputs = [];
    });
    for (let index = 0; index < options.n; index++) {
      const baseline = await captureDirect(client, sharp);
      captureResponseMs.push(baseline.responseMs);
      await page.keyboard.press(probe.press);
      const input = await page.evaluate((expectedIndex) =>
        window.__m5TrustedDirect.inputs.find((item) => item.index === expectedIndex) || null, index);
      if (!input) throw new Error(`missing trusted input ${index}`);
      let visibleEpochSeconds = null;
      let maxDifference = 0;
      let captureCount = 0;
      const visualDeadline = input.epochSeconds * 1000 + 300;
      while (Date.now() <= visualDeadline) {
        const shot = await captureDirect(client, sharp);
        captureResponseMs.push(shot.responseMs);
        captureCount++;
        const difference = meanAbsDiff(baseline.signature, shot.signature);
        maxDifference = Math.max(maxDifference, difference);
        if (difference > threshold) {
          // Response completion is at/after the screenshot capture, therefore an
          // upper bound on visible response rather than a favorable back-date.
          visibleEpochSeconds = shot.responseEpochSeconds;
          break;
        }
      }
      visualSamples.push({
        index, label: input.label, dispatchEpochSeconds: input.epochSeconds,
        visibleEpochSeconds, maxDifference, captureCount,
      });
      const nextDispatchTarget = input.epochSeconds * 1000 + options.spacingMs;
      if (Date.now() < nextDispatchTarget) await sleep(nextDispatchTarget - Date.now());
    }
    await page.evaluate(() => { window.__m5TrustedDirect.armed = false; });
    await sleep(1000);
    trustedInputs = await page.evaluate(() => window.__m5TrustedDirect.inputs);
    await page.screenshot({ path: join(outDir, 'canvas-final.png') });
  }
  catch (error) { fatal = error?.stack || String(error); }
  finally { await browser.close(); }

  const calibrations = [];
  const dispatches = [];
  const operators = [];
  for (const line of consoleLines) {
    let match = /^M5_TRUSTED_DIRECT_CAL (\d+) ([\d.]+) ([\d.]+)/.exec(line);
    if (match) {
      calibrations.push({ index: Number(match[1]), start: Number(match[2]), end: Number(match[3]) });
      continue;
    }
    match = /^M5_TRUSTED_DIRECT_DISPATCH (\d+) (\S+) ([\d.]+)/.exec(line);
    if (match) {
      dispatches.push({ index: Number(match[1]), label: match[2], epochSeconds: Number(match[3]) });
      continue;
    }
    const operator = parseClogStarted(line);
    if (operator) operators.push(operator);
  }
  const calibrationOps = operators.filter((item) =>
    item.operator === 'bpy.ops.ed.undo_push' && item.line.includes('m5-trusted-direct-cal-')).slice(0, 5);
  const pairs = Math.min(calibrations.length, calibrationOps.length);
  const tickStarts = [];
  for (let index = 0; index < pairs; index++) {
    const midpoint = (calibrations[index].start + calibrations[index].end) / 2;
    tickStarts.push(midpoint - calibrationOps[index].relativeSeconds);
  }
  tickStarts.sort((a, b) => a - b);
  const tickStart = tickStarts.length ? quantile(tickStarts, 0.5) : null;
  const tickSpreadMs = tickStarts.length ?
    (tickStarts[tickStarts.length - 1] - tickStarts[0]) * 1000 : null;

  const samples = [];
  let operatorIndex = 0;
  for (let index = 0; index < dispatches.length; index++) {
    const dispatch = dispatches[index];
    const windowEnd = index + 1 < dispatches.length ?
      dispatches[index + 1].epochSeconds : dispatch.epochSeconds + options.spacingMs / 1000 + 1;
    let operatorEpochSeconds = null;
    if (tickStart != null) {
      for (; operatorIndex < operators.length; operatorIndex++) {
        const item = operators[operatorIndex];
        if (item.operator !== probe.operator) continue;
        const epoch = item.relativeSeconds + tickStart;
        if (epoch < dispatch.epochSeconds - 0.02) continue;
        if (epoch >= windowEnd) break;
        operatorEpochSeconds = epoch;
        operatorIndex++;
        break;
      }
    }
    const visual = visualSamples.find((item) => item.index === dispatch.index);
    const visible = visual?.visibleEpochSeconds ?? null;
    samples.push({
      index: dispatch.index, label: dispatch.label,
      keypressToOperatorMs: operatorEpochSeconds == null ? null :
        (operatorEpochSeconds - dispatch.epochSeconds) * 1000,
      operatorToPresentMs: operatorEpochSeconds == null || visible == null ? null :
        (visible - operatorEpochSeconds) * 1000,
      endToEndMs: visible == null ? null : (visible - dispatch.epochSeconds) * 1000,
      maxDifference: round1(visual?.maxDifference ?? 0),
      captureCount: visual?.captureCount ?? 0,
      hasOperator: operatorEpochSeconds != null,
      hasVisible: visible != null,
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
  const deniedDiagnostics = DENIED_CONSOLE.filter((needle) =>
    consoleLines.some((line) => line.includes(needle)));
  const inputPass = trustedInputs.length === options.n && trustedInputs.every((input, index) =>
    input.index === index && input.key === probe.key && input.code === probe.code &&
    input.isTrusted === true && input.targetId === 'canvas' && input.activeId === 'canvas');
  const measurementPass = dispatches.length === options.n && samples.length === options.n &&
    metrics.keypressToOperatorMs.n === options.n && metrics.endToEndMs.n === options.n;
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
  const binaryDir = process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin');
  const binaryFiles = readdirSync(binaryDir).filter((name) => name.startsWith('blender_browser.'))
    .sort().map((name) => fileReceipt(join(binaryDir, name)));
  const receipt = {
    schema: 'blender-web.m5-trusted-input-direct-latency.v1',
    run: options.run,
    status: pass ? 'PASS' : 'FAIL',
    startedAt,
    finishedAt: new Date().toISOString(),
    contract: {
      shell: 'shipping platform_web/shell/windowed.html', probe: options.probe,
      input: `Playwright trusted ${probe.press} keys targeted at #canvas`,
      dispatchClock: 'DOM keydown epoch = performance.timeOrigin + event.timeStamp',
      operatorClock: 'CLOG gettimeofday epoch calibrated by five bracketed undo_push calls',
      visibleClock: 'Date.now immediately after direct CDP Page.captureScreenshot response (upper bound)',
      detector: `160x90 greyscale mean-absolute-difference > max(p25*8, median*5, ${BUDGETS.changeThresholdFloor})`,
      steadyState: `trusted ${probe.press} show/hide prewarm completed before measurement`,
      budgets: BUDGETS,
    },
    result: {
      fatal, pageErrors, externalRequestCount: externalRequests.length, deniedDiagnostics,
      inputPass, canvasPass, measurementPass, budgetPass,
      nRequested: options.n, nDispatch: dispatches.length,
      nWithOperator: metrics.keypressToOperatorMs.n, nWithVisible: metrics.endToEndMs.n,
      calibration: { pairs, tickStartSpreadMs: round1(tickSpreadMs) },
      frameDiff: {
        noiseFloorP25: round1(noise?.floor), noiseMedian: round1(noise?.median),
        noiseP95: round1(noise?.p95), changeThreshold: round1(noise?.threshold),
        noiseCaptures: noise?.captures ?? 0,
      },
      metrics, samples, canvas: canvasReceipt, ready,
    },
    browser: { headed: options.headed, playwrightRoot, trustedInputs },
    provenance: {
      driver: fileReceipt(fileURLToPath(import.meta.url)),
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
