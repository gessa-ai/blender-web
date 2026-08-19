// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

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
const DEFAULT_MODULES = '/Users/paws/plushly/game-platform/node_modules';
const GOLDEN = join(REPO, 'sandbox/m5-prep/traces/m5_core.object_click_select.trace.txt');

const PY_MONITOR = String.raw`
import bpy,json,os,time
from bpy_extras.view3d_utils import location_3d_to_region_2d
_m5p={"phase":0,"started":time.perf_counter()}
def _m5p_snapshot(name):
    w=bpy.context.window
    o=bpy.data.objects.get("Cube")
    if w is None or w.screen is None or o is None: return None
    area=next((a for a in w.screen.areas if a.type == 'VIEW_3D'),None)
    if area is None: return None
    region=next((r for r in area.regions if r.type == 'WINDOW'),None)
    if region is None: return None
    co=location_3d_to_region_2d(region,region.data,o.matrix_world.translation)
    if co is None: return None
    active=bpy.context.view_layer.objects.active
    return {"name":name,"phase":_m5p["phase"],"elapsed_ms":round((time.perf_counter()-_m5p["started"])*1000,3),"active":active.name if active else None,"selected":sorted(x.name for x in bpy.context.selected_objects),"cube_selected":o.select_get(),"view3d":{"x":region.x,"y":region.y,"width":region.width,"height":region.height},"cube_window":{"x":int(co[0])+region.x,"y":int(co[1])+region.y}}
def _m5p_emit(name):
    p=_m5p_snapshot(name)
    if p is not None: os.write(2,("M5_CLICK_STATE "+json.dumps(p,sort_keys=True,separators=(",",":"))+"\n").encode())
def _m5p_poll():
    p=_m5p_snapshot("POLL")
    if p is None: return 0.02
    selected=p["selected"]
    phase=_m5p["phase"]
    if phase == 0 and selected == ["Cube"] and p["active"] == "Cube":
        _m5p_emit("READY"); _m5p["phase"]=1
    elif phase == 1 and selected == []:
        _m5p_emit("DESELECTED_1"); _m5p["phase"]=2
    elif phase == 2 and selected == ["Cube"] and p["active"] == "Cube":
        _m5p_emit("SELECTED_1"); _m5p["phase"]=3
    elif phase == 3 and selected == []:
        _m5p_emit("DESELECTED_2"); _m5p["phase"]=4
    elif phase == 4 and selected == ["Cube"] and p["active"] == "Cube":
        _m5p_emit("SELECTED_2"); _m5p["phase"]=5
    return 0.02
bpy.app.timers.register(_m5p_poll,first_interval=0.0,persistent=True)
`.trim();

function parseArgs(argv) {
  const options = { port: 8166, run: null, outRoot: join(HERE, 'evidence'), timeoutMs: 120000 };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--port') options.port = Number(argv[++i]);
    else if (arg === '--run') options.run = argv[++i];
    else if (arg === '--out-root') options.outRoot = resolve(argv[++i]);
    else if (arg === '--timeout-ms') options.timeoutMs = Number(argv[++i]);
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!options.run || !/^[a-z0-9][a-z0-9._-]*$/i.test(options.run)) {
    throw new Error('--run with a safe immutable label is required');
  }
  if (!Number.isInteger(options.port) || options.port < 1 || options.port > 65535) {
    throw new Error(`invalid port: ${options.port}`);
  }
  return options;
}

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function fileReceipt(path) {
  const stat = statSync(path);
  return { path: path.slice(REPO.length + 1), bytes: stat.size, sha256: sha256File(path) };
}

function resolvePlaywright() {
  for (const root of [process.env.BW_NODE_MODULES, process.env.NODE_PATH, DEFAULT_MODULES].filter(Boolean)) {
    try {
      const require = createRequire(join(root, 'package.json'));
      return { chromium: require('playwright').chromium, root };
    } catch (_) {}
  }
  throw new Error('cannot resolve Playwright');
}

function sanitizeTrace(lines) {
  return lines.filter((line) => /operator\s*\| Started bpy\.ops\./.test(line))
    .map((line) => line.replace(/^.*\| Started /, '').replaceAll('\0', ''));
}

function nativeCycle() {
  return readFileSync(GOLDEN, 'utf8').replaceAll('\0', '').trim().split('\n')
    .filter((line) => line.startsWith('bpy.ops.object.select_all(') ||
      line.startsWith('bpy.ops.view3d.select('));
}

function orderedSubsequence(haystack, needle) {
  let cursor = 0;
  const positions = [];
  for (const item of needle) {
    const at = haystack.indexOf(item, cursor);
    if (at < 0) return { pass: false, positions, missing: item };
    positions.push(at);
    cursor = at + 1;
  }
  return { pass: true, positions, missing: null };
}

const sleep = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing to overwrite ${outDir}`);
  const binaryDir = resolve(process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin'));
  const { binaryFiles, splitManifest } = captureRuntimeArtifactSet(binaryDir, fileReceipt);
  mkdirSync(options.outRoot, { recursive: true });
  mkdirSync(outDir);

  const startedAt = new Date().toISOString();
  const consoleLines = [];
  const states = [];
  const pageErrors = [];
  const requests = [];
  let inputEvents = [];
  let canvasReceipt = null;
  let clickPoint = null;
  let fatal = null;
  const { chromium, root: playwrightRoot } = resolvePlaywright();
  const browser = await chromium.launch({ headless: false });
  let page;

  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
    page = await context.newPage();
    page.on('console', (message) => {
      const line = message.text();
      consoleLines.push(line);
      const match = /^M5_CLICK_STATE (\{.*\})$/.exec(line);
      if (match) {
        try { states.push(JSON.parse(match[1])); }
        catch (error) { pageErrors.push(`bad state marker: ${error.message}`); }
      }
    });
    page.on('pageerror', (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on('crash', () => pageErrors.push('page crashed'));
    page.on('request', (request) => requests.push({ method: request.method(), url: request.url() }));

    await page.addInitScript(({ monitor }) => {
      window.__BW_ARGS = ['--log', 'operator', '--log-level', 'debug'];
      window.__BW_PYEXPR = monitor;
      window.__m5PickInputs = [];
      const record = (event) => window.__m5PickInputs.push({
        type: event.type, key: event.key || null, button: event.button ?? null,
        altKey: event.altKey, isTrusted: event.isTrusted,
        targetId: event.target && event.target.id || null,
        activeId: document.activeElement && document.activeElement.id || null,
        clientX: event.clientX ?? null, clientY: event.clientY ?? null,
      });
      for (const type of ['keydown', 'mousedown', 'mouseup', 'click']) {
        window.addEventListener(type, record, true);
      }
    }, { monitor: PY_MONITOR });

    await page.goto(`http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`, {
      waitUntil: 'domcontentloaded', timeout: options.timeoutMs,
    });
    await page.waitForFunction(() => document.querySelector('#state')?.textContent.includes('main loop (WM_main)'),
      null, { timeout: options.timeoutMs, polling: 100 });

    const waitState = async (name) => {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        const state = states.find((item) => item.name === name);
        if (state) return state;
        await sleep(20);
      }
      throw new Error(`timeout waiting for ${name}; saw ${states.map((item) => item.name)}`);
    };

    const ready = await waitState('READY');
    const canvas = page.locator('#canvas');
    const box = await canvas.boundingBox();
    if (!box) throw new Error('canvas has no box');
    clickPoint = {
      x: box.x + ready.cube_window.x,
      y: box.y + box.height - ready.cube_window.y,
      blenderWindow: ready.cube_window,
    };
    canvasReceipt = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas');
      const box = canvas.getBoundingClientRect();
      return {
        backing: [canvas.width, canvas.height], css: [box.width, box.height],
        dpr: devicePixelRatio, crossOriginIsolated, shellState: document.querySelector('#state')?.textContent,
      };
    });

    /* GHOST routes key events through the region under its last known cursor;
     * focus alone is not enough to establish a VIEW_3D context. */
    await page.mouse.move(clickPoint.x, clickPoint.y);
    await canvas.focus();
    await page.keyboard.press('Escape');
    await sleep(500);
    for (let cycle = 1; cycle <= 2; cycle++) {
      await page.keyboard.press('Alt+a');
      await waitState(`DESELECTED_${cycle}`);
      await page.mouse.click(clickPoint.x, clickPoint.y);
      await waitState(`SELECTED_${cycle}`);
      await sleep(100);
    }
  } catch (error) {
    fatal = error?.stack || String(error);
  } finally {
    if (page && !page.isClosed()) {
      try { inputEvents = await page.evaluate(() => window.__m5PickInputs || []); } catch (_) {}
      try { await page.screenshot({ path: join(outDir, 'selected-cube.png') }); } catch (_) {}
    }
    await browser.close();
  }

  const trace = sanitizeTrace(consoleLines);
  const cycle = nativeCycle();
  const requiredTrace = cycle.concat(cycle);
  const traceMatch = orderedSubsequence(trace, requiredTrace);
  const selectOps = trace.filter((line) => line.startsWith('bpy.ops.view3d.select('));
  const deselectOps = trace.filter((line) => line === "bpy.ops.object.select_all(action='DESELECT')");
  const clickEvents = inputEvents.filter((event) => event.type === 'click');
  const mouseEvents = inputEvents.filter((event) => ['mousedown', 'mouseup', 'click'].includes(event.type));
  const altAEvents = inputEvents.filter((event) => event.type === 'keydown' && event.key === 'a');
  const inputPass = clickEvents.length === 2 && mouseEvents.length === 6 && altAEvents.length === 2 &&
    [...mouseEvents, ...altAEvents].every((event) => event.isTrusted && event.targetId === 'canvas' &&
      event.activeId === 'canvas') && altAEvents.every((event) => event.altKey === true);
  const statePass = states.filter((state) => state.name.startsWith('SELECTED_')).length === 2 &&
    states.find((state) => state.name === 'SELECTED_2')?.active === 'Cube' &&
    JSON.stringify(states.find((state) => state.name === 'SELECTED_2')?.selected) === JSON.stringify(['Cube']);
  const externalRequests = requests.filter((request) => {
    try { return !['127.0.0.1', 'localhost'].includes(new URL(request.url).hostname); }
    catch (_) { return true; }
  });
  const screenshotPath = join(outDir, 'selected-cube.png');
  const pass = !fatal && pageErrors.length === 0 && statePass && inputPass && traceMatch.pass &&
    selectOps.length === 2 && deselectOps.length === 2 && externalRequests.length === 0 &&
    existsSync(screenshotPath) && canvasReceipt?.crossOriginIsolated === true &&
    JSON.stringify(canvasReceipt?.backing) === JSON.stringify([1280, 720]) &&
    JSON.stringify(canvasReceipt?.css) === JSON.stringify([1280, 720]);

  const artifactData = {
    'operator-trace.txt': trace.join('\n') + (trace.length ? '\n' : ''),
    'states.json': JSON.stringify(states, null, 2) + '\n',
    'trusted-inputs.json': JSON.stringify(inputEvents, null, 2) + '\n',
    'requests.json': JSON.stringify(requests, null, 2) + '\n',
    'console.log': consoleLines.join('\n') + '\n',
  };
  for (const [name, data] of Object.entries(artifactData)) writeFileSync(join(outDir, name), data);
  if (existsSync(screenshotPath)) {
    writeFileSync(`${screenshotPath}.license`,
      'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  }

  const receipt = {
    schema: 'blender-web.m5-click-pick-continuation.v1', run: options.run,
    status: pass ? 'PASS' : 'FAIL', startedAt, finishedAt: new Date().toISOString(),
    contract: {
      shell: 'shipping platform_web/shell/windowed.html', cycles: 2,
      input: 'trusted Playwright canvas mouse click after trusted Alt+A',
      observation: 'read-only bpy timer; no operator or selection-state injection',
      nativeOperatorCycle: cycle,
      runtimeArtifacts: RUNTIME_BINARY_PATHS,
    },
    result: {
      fatal, pageErrors, statePass, inputPass, tracePass: traceMatch.pass,
      tracePositions: traceMatch.positions, traceMissing: traceMatch.missing,
      selectOperatorCount: selectOps.length, deselectOperatorCount: deselectOps.length,
      externalRequestCount: externalRequests.length, clickPoint, canvas: canvasReceipt,
      finalState: states.find((state) => state.name === 'SELECTED_2') || null,
    },
    browser: { playwrightRoot, headed: true },
    provenance: {
      driver: fileReceipt(fileURLToPath(import.meta.url)), nativeGolden: fileReceipt(GOLDEN),
      runtimeContract: fileReceipt(RUNTIME_CONTRACT_SOURCE), splitManifest,
      shell: [fileReceipt(join(REPO, 'platform_web/shell/windowed.html')),
        fileReceipt(join(REPO, 'platform_web/shell/boot-windowed.js'))], binaryFiles,
    },
    artifacts: Object.fromEntries(Object.keys(artifactData).map((name) => [name, fileReceipt(join(outDir, name))])),
  };
  if (existsSync(screenshotPath)) receipt.artifacts['selected-cube.png'] = fileReceipt(screenshotPath);
  writeFileSync(join(outDir, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  writeFileSync(join(outDir, 'receipt.sha256'), `${sha256File(join(outDir, 'receipt.json'))}  receipt.json\n`);
  process.stdout.write(JSON.stringify({ status: receipt.status, outDir, result: receipt.result }, null, 2) + '\n');
  if (!pass) process.exitCode = 1;
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
