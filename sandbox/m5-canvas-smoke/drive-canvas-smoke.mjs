// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M5 browser-level canvas smoke.
//
// This is deliberately separate from the event-simulate replay rig. Playwright
// sends trusted keyboard events to the shipping windowed shell's real canvas;
// a read-only bpy timer reports the resulting Blender state from the WM worker.
// The driver never calls an operator through JS/Python and never mutates an
// oracle, golden, threshold, or pass flag.

import { createHash } from 'crypto';
import { createRequire } from 'module';
import {
  existsSync, mkdirSync, readFileSync, statSync, writeFileSync,
} from 'fs';
import { basename, dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  captureRuntimeArtifactSet, RUNTIME_BINARY_PATHS, RUNTIME_CONTRACT_SOURCE,
} from '../m5-final/runtime-artifacts.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const DEFAULT_OUT = join(HERE, 'evidence');
const DEFAULT_MODULES = '/Users/paws/plushly/game-platform/node_modules';
const GOLDEN_EDIT = join(REPO, 'sandbox/m5-prep/traces/m5_core.edit_mode_toggle.trace.txt');
const GOLDEN_SELECT = join(REPO, 'sandbox/m5-prep/traces/m5_core.object_select_all.trace.txt');
const WASM_EDIT = join(REPO, 'sandbox/m5-prep/wasm-out/m5_core.edit_mode_toggle.trace.txt');
const WASM_SELECT = join(REPO, 'sandbox/m5-prep/wasm-out/m5_core.object_select_all.trace.txt');

const ACTIONS = Object.freeze([
  { id: 'tab_into_edit', press: 'Tab', expect: 'EDIT_MODE' },
  { id: 'tab_back_object', press: 'Tab', expect: 'OBJECT_AFTER_EDIT' },
  { id: 'deselect_all', press: 'Alt+a', expect: 'DESELECTED' },
  { id: 'select_all', press: 'a', expect: 'SELECT_ALL' },
]);
const EXPECTED_NON_MODIFIER_KEYS = Object.freeze(['Escape', 'Tab', 'Tab', 'a', 'a']);
const INTER_ACTION_SETTLE_MS = 500;

const PY_MONITOR = String.raw`
import bpy,json,os,time
_m5={"phase":0,"started":time.perf_counter()}
def _m5_view3d():
    w=bpy.context.window
    if w is None or w.screen is None: return None
    for a in w.screen.areas:
        if a.type == 'VIEW_3D':
            for r in a.regions:
                if r.type == 'WINDOW':
                    return {"x":r.x+r.width/2.0,"y":r.y+r.height/2.0,"width":r.width,"height":r.height}
    return None
def _m5_emit(name):
    o=bpy.data.objects.get("Cube")
    p={"name":name,"phase":_m5["phase"],"elapsed_ms":round((time.perf_counter()-_m5["started"])*1000,3),"context_mode":bpy.context.mode,"cube_mode":(o.mode if o else None),"active":(bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None),"selected":sorted(x.name for x in bpy.context.selected_objects),"view3d":_m5_view3d()}
    os.write(2,("M5_CANVAS_STATE "+json.dumps(p,sort_keys=True,separators=(",",":"))+"\n").encode())
def _m5_poll():
    o=bpy.data.objects.get("Cube")
    if o is None or _m5_view3d() is None: return 0.02
    mode=o.mode
    sel=sorted(x.name for x in bpy.context.selected_objects)
    p=_m5["phase"]
    if p == 0 and mode == 'OBJECT' and sel == ['Cube']:
        _m5_emit('READY'); _m5["phase"]=1
    elif p == 1 and mode == 'EDIT':
        _m5_emit('EDIT_MODE'); _m5["phase"]=2
    elif p == 2 and mode == 'OBJECT':
        _m5_emit('OBJECT_AFTER_EDIT'); _m5["phase"]=3
    elif p == 3 and sel == []:
        _m5_emit('DESELECTED'); _m5["phase"]=4
    elif p == 4 and sel == ['Camera','Cube','Light']:
        _m5_emit('SELECT_ALL'); _m5["phase"]=5
    return 0.02
bpy.app.timers.register(_m5_poll,first_interval=0.0,persistent=True)
`.trim();

function parseArgs(argv) {
  const out = {
    port: 8127,
    run: null,
    outRoot: DEFAULT_OUT,
    timeoutMs: 120000,
    selfcheck: false,
    headed: true,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--selfcheck') out.selfcheck = true;
    else if (arg === '--headless') out.headed = false;
    else if (arg === '--port') out.port = Number(argv[++i]);
    else if (arg === '--run') out.run = argv[++i];
    else if (arg === '--out-root') out.outRoot = resolve(argv[++i]);
    else if (arg === '--timeout-ms') out.timeoutMs = Number(argv[++i]);
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!Number.isInteger(out.port) || out.port < 1 || out.port > 65535) {
    throw new Error(`invalid --port: ${out.port}`);
  }
  if (!Number.isFinite(out.timeoutMs) || out.timeoutMs < 1000) {
    throw new Error(`invalid --timeout-ms: ${out.timeoutMs}`);
  }
  if (out.run != null && !/^[a-z0-9][a-z0-9._-]*$/i.test(out.run)) {
    throw new Error(`invalid --run label: ${out.run}`);
  }
  return out;
}

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}

function fileReceipt(path) {
  const st = statSync(path);
  return { path: path.slice(REPO.length + 1), bytes: st.size, sha256: sha256File(path) };
}

function normalizedLines(path) {
  return readFileSync(path, 'utf8').replaceAll('\0', '').trim().split('\n').filter(Boolean);
}

function requiredNativeActions() {
  const edit = normalizedLines(GOLDEN_EDIT);
  const select = normalizedLines(GOLDEN_SELECT);
  const trimBookends = (lines) => lines.filter((line) =>
    !line.startsWith('bpy.ops.wm.tool_set_by_id(') && line !== 'bpy.ops.wm.quit_blender()');
  const editActions = trimBookends(edit);
  const selectActions = trimBookends(select);
  if (editActions.length !== 4 || selectActions.length !== 2) {
    throw new Error(`unexpected native action shape: edit=${editActions.length}, select=${selectActions.length}`);
  }
  return editActions.concat(selectActions);
}

function orderedSubsequence(haystack, needle) {
  let at = 0;
  const positions = [];
  for (const line of needle) {
    const found = haystack.indexOf(line, at);
    if (found < 0) return { pass: false, positions, missing: line };
    positions.push(found);
    at = found + 1;
  }
  return { pass: true, positions, missing: null };
}

function sanitizeTrace(lines) {
  const out = [];
  for (const line of lines) {
    if (/operator\s*\| Started bpy\.ops\./.test(line)) {
      out.push(line.replace(/^.*\| Started /, '').replaceAll('\0', ''));
    }
  }
  return out;
}

function assertSelfcheck(condition, message) {
  if (!condition) throw new Error(`selfcheck: ${message}`);
}

function runSelfcheck() {
  const required = requiredNativeActions();
  assertSelfcheck(ACTIONS.map((x) => x.expect).join(',') ===
    'EDIT_MODE,OBJECT_AFTER_EDIT,DESELECTED,SELECT_ALL', 'action/state sequence drift');
  assertSelfcheck(PY_MONITOR.includes("_m5_emit('EDIT_MODE')"), 'monitor lacks edit marker');
  assertSelfcheck(PY_MONITOR.includes("sel == ['Camera','Cube','Light']"), 'monitor lacks select oracle');
  assertSelfcheck(required.length === 6, 'native action count is not six');
  assertSelfcheck(orderedSubsequence(['x', ...required, 'y'], required).pass,
    'ordered-subsequence positive case');
  assertSelfcheck(!orderedSubsequence(required.slice(1), required).pass,
    'ordered-subsequence negative case');
  assertSelfcheck(normalizedLines(GOLDEN_EDIT).join('\n') === normalizedLines(WASM_EDIT).join('\n'),
    'edit native/wasm trace evidence differs');
  assertSelfcheck(normalizedLines(GOLDEN_SELECT).join('\n') === normalizedLines(WASM_SELECT).join('\n'),
    'select native/wasm trace evidence differs');
  assertSelfcheck(EXPECTED_NON_MODIFIER_KEYS[0] === 'Escape', 'shipping splash dismissal drift');
  process.stdout.write(JSON.stringify({
    status: 'PASS', checks: 9, actions: ACTIONS, requiredNativeActions: required,
  }, null, 2) + '\n');
}

function resolvePlaywright() {
  const roots = [process.env.BW_NODE_MODULES, process.env.NODE_PATH, DEFAULT_MODULES].filter(Boolean);
  const errors = [];
  for (const root of roots) {
    try {
      const req = createRequire(join(root, 'package.json'));
      return { chromium: req('playwright').chromium, root };
    } catch (error) {
      errors.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve playwright; set BW_NODE_MODULES\n${errors.join('\n')}`);
}

function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.selfcheck) {
    runSelfcheck();
    return;
  }
  if (!options.run) throw new Error('--run is required (e.g. m5-canvas-smoke-r1)');

  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) {
    throw new Error(`refusing to overwrite existing evidence directory: ${outDir}`);
  }
  const binaryDir = resolve(process.env.BLENDER_WEB_BIN || join(REPO, 'build-wasm-windowed-opt/bin'));
  const { binaryFiles, splitManifest } = captureRuntimeArtifactSet(binaryDir, fileReceipt);
  mkdirSync(options.outRoot, { recursive: true });
  mkdirSync(outDir, { recursive: false });

  const startedAt = new Date().toISOString();
  const consoleLines = [];
  const states = [];
  const requests = [];
  const pageErrors = [];
  const actionReceipts = [];
  let trustedKeys = [];
  let canvasReceipt = null;
  const required = requiredNativeActions();
  const { chromium, root: playwrightRoot } = resolvePlaywright();
  const browser = await chromium.launch({ headless: !options.headed });
  let page;
  let fatal = null;

  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1,
    });
    page = await context.newPage();
    page.on('console', (message) => {
      const line = message.text();
      consoleLines.push(line);
      const marker = /^M5_CANVAS_STATE (\{.*\})$/.exec(line);
      if (marker) {
        try { states.push(JSON.parse(marker[1])); }
        catch (error) { pageErrors.push(`invalid state marker: ${error.message}`); }
      }
    });
    page.on('pageerror', (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on('crash', () => pageErrors.push('page crashed'));
    page.on('request', (request) => requests.push({
      method: request.method(), type: request.resourceType(), url: request.url(),
    }));

    await page.addInitScript(({ monitor }) => {
      window.__BW_ARGS = ['--log', 'operator', '--log-level', 'debug'];
      window.__BW_PYEXPR = monitor;
      window.__m5TrustedKeys = [];
      window.addEventListener('keydown', (event) => {
        window.__m5TrustedKeys.push({
          at: performance.now(), key: event.key, code: event.code,
          altKey: event.altKey, ctrlKey: event.ctrlKey, metaKey: event.metaKey,
          shiftKey: event.shiftKey, repeat: event.repeat, isTrusted: event.isTrusted,
          targetId: event.target && event.target.id || null,
          activeId: document.activeElement && document.activeElement.id || null,
        });
      }, true);
    }, { monitor: PY_MONITOR });

    const url = `http://127.0.0.1:${options.port}/windowed.html?gate=1280x720`;
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: options.timeoutMs });
    await page.waitForFunction(() => {
      const state = document.querySelector('#state');
      return state && state.textContent.includes('main loop (WM_main)');
    }, null, { timeout: options.timeoutMs, polling: 100 });

    async function waitState(name) {
      const deadline = Date.now() + options.timeoutMs;
      while (Date.now() < deadline) {
        const match = states.find((state) => state.name === name);
        if (match) return match;
        await sleep(20);
      }
      throw new Error(`timed out waiting for state ${name}; saw ${states.map((x) => x.name).join(',')}`);
    }

    const ready = await waitState('READY');
    const view3d = ready.view3d;
    if (!view3d) throw new Error('READY marker lacks VIEW_3D region');
    const canvas = page.locator('#canvas');
    const box = await canvas.boundingBox();
    if (!box) throw new Error('canvas has no bounding box');
    const mouseX = box.x + view3d.x;
    const mouseY = box.y + box.height - view3d.y;
    await page.mouse.move(mouseX, mouseY);
    await canvas.focus();
    canvasReceipt = await page.evaluate(() => {
      const element = document.querySelector('#canvas');
      const bounds = element.getBoundingClientRect();
      return {
        selector: '#canvas', backing: [element.width, element.height],
        css: [bounds.width, bounds.height], dpr: window.devicePixelRatio,
        activeId: document.activeElement && document.activeElement.id || null,
        crossOriginIsolated: window.crossOriginIsolated,
        hasRuntimeModule: typeof window.__bwModule === 'object' && window.__bwModule !== null,
        shellState: document.querySelector('#state')?.textContent || null,
      };
    });

    // The shipping windowed path opens Blender's startup splash. Dismiss it via
    // the same trusted browser input seam before exercising VIEW_3D shortcuts.
    await page.keyboard.press('Escape');
    await sleep(500);

    for (const action of ACTIONS) {
      const before = Date.now();
      await page.keyboard.press(action.press);
      const state = await waitState(action.expect);
      actionReceipts.push({
        id: action.id, playwrightPress: action.press, expectedState: action.expect,
        observedState: state, actionToStateMs: Date.now() - before,
      });
      // A mode switch can publish its bpy state before the associated tool/UI
      // transition has finished consuming the event. This is orchestration
      // settling only; M5 latency is measured by the independent latency rig.
      await sleep(INTER_ACTION_SETTLE_MS);
    }
  } catch (error) {
    fatal = error && error.stack ? error.stack : String(error);
  } finally {
    if (page && !page.isClosed()) {
      try { trustedKeys = await page.evaluate(() => window.__m5TrustedKeys || []); }
      catch (_) {}
      try { await page.screenshot({ path: join(outDir, 'canvas-final.png') }); }
      catch (_) {}
    }
    await browser.close();
  }

  const trace = sanitizeTrace(consoleLines);
  const traceMatch = orderedSubsequence(trace, required);
  const externalRequests = requests.filter((item) => {
    try {
      const url = new URL(item.url);
      return !['127.0.0.1', 'localhost'].includes(url.hostname);
    } catch (_) { return true; }
  });
  const stateNames = states.map((state) => state.name);
  const statePass = ACTIONS.every((action) => stateNames.includes(action.expect));

  // The keyboard receipt is pulled before the context closes. Missing records
  // fail closed rather than silently turning this into another injected test.
  const nonModifierKeys = trustedKeys.filter((event) =>
    !['Alt', 'Control', 'Meta', 'Shift'].includes(event.key));
  const keyPass = nonModifierKeys.every((event) =>
    event.isTrusted && event.targetId === 'canvas' && event.activeId === 'canvas') &&
    JSON.stringify(nonModifierKeys.map((event) => event.key)) ===
      JSON.stringify(EXPECTED_NON_MODIFIER_KEYS) &&
    nonModifierKeys[3].altKey === true && nonModifierKeys[4].altKey === false;
  const screenshotPath = join(outDir, 'canvas-final.png');
  const pass = !fatal && pageErrors.length === 0 && statePass && traceMatch.pass &&
    keyPass && externalRequests.length === 0 && existsSync(screenshotPath) &&
    canvasReceipt?.activeId === 'canvas' && canvasReceipt?.crossOriginIsolated === true &&
    canvasReceipt?.hasRuntimeModule === true &&
    JSON.stringify(canvasReceipt?.backing) === JSON.stringify([1280, 720]) &&
    JSON.stringify(canvasReceipt?.css) === JSON.stringify([1280, 720]);

  const tracePath = join(outDir, 'operator-trace.txt');
  const statesPath = join(outDir, 'states.json');
  const keysPath = join(outDir, 'trusted-keys.json');
  const requestsPath = join(outDir, 'requests.json');
  const screenshotLicensePath = join(outDir, 'canvas-final.png.license');
  writeFileSync(tracePath, trace.join('\n') + (trace.length ? '\n' : ''));
  writeFileSync(statesPath, JSON.stringify(states, null, 2) + '\n');
  writeFileSync(keysPath, JSON.stringify(trustedKeys, null, 2) + '\n');
  writeFileSync(requestsPath, JSON.stringify(requests, null, 2) + '\n');
  if (existsSync(screenshotPath)) {
    writeFileSync(screenshotLicensePath,
      'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  }

  const receipt = {
    schema: 'blender-web.m5-playwright-canvas-smoke.v1',
    run: options.run,
    status: pass ? 'PASS' : 'FAIL',
    startedAt,
    finishedAt: new Date().toISOString(),
    contract: {
      shell: 'shipping platform_web/shell/windowed.html',
      input: 'Playwright trusted keyboard events targeted at #canvas',
      stateObservation: 'read-only bpy.app.timer on WM worker; no operator injection',
      nativeTraceComparison: 'ordered action subsequence derived from unchanged native goldens',
      actions: ACTIONS,
      runtimeArtifacts: RUNTIME_BINARY_PATHS,
    },
    result: {
      fatal, pageErrors, statePass, tracePass: traceMatch.pass,
      tracePositions: traceMatch.positions, traceMissing: traceMatch.missing,
      keyPass, externalRequestCount: externalRequests.length,
      canvas: canvasReceipt, actionReceipts,
    },
    browser: { playwrightRoot, headed: options.headed, trustedKeys },
    provenance: {
      driver: fileReceipt(fileURLToPath(import.meta.url)),
      runtimeContract: fileReceipt(RUNTIME_CONTRACT_SOURCE), splitManifest,
      shell: [
        fileReceipt(join(REPO, 'platform_web/shell/windowed.html')),
        fileReceipt(join(REPO, 'platform_web/shell/boot-windowed.js')),
      ],
      nativeGoldens: [fileReceipt(GOLDEN_EDIT), fileReceipt(GOLDEN_SELECT)],
      existingWasmReceipts: [fileReceipt(WASM_EDIT), fileReceipt(WASM_SELECT)],
      binaryFiles,
    },
    artifacts: {
      screenshot: existsSync(screenshotPath) ? fileReceipt(screenshotPath) : null,
      screenshotLicense: existsSync(screenshotLicensePath) ? fileReceipt(screenshotLicensePath) : null,
      operatorTrace: fileReceipt(tracePath), states: fileReceipt(statesPath),
      trustedKeys: fileReceipt(keysPath), requests: fileReceipt(requestsPath),
    },
  };

  writeFileSync(join(outDir, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  writeFileSync(join(outDir, 'receipt.sha256'), `${sha256File(join(outDir, 'receipt.json'))}  receipt.json\n`);
  process.stdout.write(JSON.stringify({ status: receipt.status, outDir, result: receipt.result }, null, 2) + '\n');
  if (!pass) process.exitCode = 1;
}

main().catch((error) => {
  process.stderr.write((error && error.stack ? error.stack : String(error)) + '\n');
  process.exitCode = 1;
});
