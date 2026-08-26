// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prove that exact browser-cold Python runtime sources can ride Stage 1 while
// the pre-Stage-1 product still boots and accepts trusted viewport input.
// Stage 1 must restore representative sources and lazy behavior exactly.

import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const MODULE_ROOT = process.env.BW_NODE_MODULES || resolve(ROOT, ".m4-node/node_modules");
const {chromium} = createRequire(resolve(MODULE_ROOT, "package.json"))("playwright");
const STAGE1_LOADER = resolve(ROOT, "sandbox/m8-staged-deploy/stage1-loader.js");
const monolithPort = Number(process.argv[2]);
const stagedPort = Number(process.argv[3]);
if (!Number.isInteger(monolithPort) || !Number.isInteger(stagedPort)) {
  throw new Error("usage: verify_python_runtime_stage0.mjs MONOLITH_PORT STAGED_PORT");
}

const coldPaths = [
  "/bw/python/lib/python3.13/_pydecimal.py",
  "/bw/python/lib/python3.13/_pyrepl/reader.py",
  "/bw/python/lib/python3.13/logging/handlers.py",
  "/bw/python/lib/python3.13/multiprocessing/managers.py",
  "/bw/python/lib/python3.13/site-packages/idna/uts46data.py",
  "/bw/python/lib/python3.13/xml/etree/ElementTree.py",
];
const bootPaths = [
  "/bw/python/lib/python3.13/_collections_abc.py",
  "/bw/python/lib/python3.13/email/message.py",
  "/bw/python/lib/python3.13/encodings/utf_8_sig.py",
  "/bw/python/lib/python3.13/logging/__init__.py",
  "/bw/python/lib/python3.13/multiprocessing/connection.py",
  "/bw/python/lib/python3.13/site-packages/idna/core.py",
];
const coldModuleNames = [
  "_pyrepl.reader",
  "logging.handlers",
  "multiprocessing.managers",
  "idna.uts46data",
  "xml.etree.ElementTree",
];

const pythonProbe = String.raw`
import bpy, hashlib, importlib, json, os, sys, traceback

_bw_cold_paths = ${JSON.stringify(coldPaths)}
_bw_boot_paths = ${JSON.stringify(bootPaths)}
_bw_cold_module_names = ${JSON.stringify(coldModuleNames)}
_bw_initial_result = '/projects/_bw_runtime_stage0.json'
_bw_interaction_trigger = '/projects/_bw_runtime_interaction_trigger'
_bw_interaction_result = '/projects/_bw_runtime_interaction.json'
_bw_stage1_trigger = '/projects/_bw_runtime_stage1_trigger'
_bw_stage1_result = '/projects/_bw_runtime_stage1.json'
for _bw_path in (_bw_initial_result, _bw_interaction_trigger, _bw_interaction_result,
                 _bw_stage1_trigger, _bw_stage1_result):
    try:
        os.remove(_bw_path)
    except FileNotFoundError:
        pass

def _bw_file_info(path):
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
        return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'error': None}
    except BaseException as error:
        return {'bytes': None, 'sha256': None,
                'error': type(error).__name__ + ': ' + str(error)}

def _bw_initial_probe():
    info = {
        'version': bpy.app.version_string,
        'addons': sorted(addon.module for addon in bpy.context.preferences.addons),
        'areas': sorted(area.type for area in bpy.context.screen.areas),
        'objects': sorted(obj.name for obj in bpy.data.objects),
        'cold_modules': sorted(name for name in _bw_cold_module_names if name in sys.modules),
        'cold_files': {path: _bw_file_info(path) for path in _bw_cold_paths},
        'boot_files': {path: _bw_file_info(path) for path in _bw_boot_paths},
    }
    with open(_bw_initial_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

def _bw_interaction_probe():
    if not os.path.exists(_bw_interaction_trigger):
        return 0.1
    active = bpy.context.view_layer.objects.active
    info = {
        'mode': bpy.context.mode,
        'active': active.name if active else None,
        'vertices': len(active.data.vertices) if active and active.type == 'MESH' else None,
    }
    with open(_bw_interaction_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

def _bw_stage1_probe():
    if not os.path.exists(_bw_stage1_trigger):
        return 0.1
    try:
        importlib.invalidate_caches()
        decimal = importlib.import_module('decimal')
        element_tree = importlib.import_module('xml.etree.ElementTree')
        handlers = importlib.import_module('logging.handlers')
        managers = importlib.import_module('multiprocessing.managers')
        uts46 = importlib.import_module('idna.uts46data')
        reader_path = '/bw/python/lib/python3.13/_pyrepl/reader.py'
        with open(reader_path, 'r', encoding='utf-8') as handle:
            compile(handle.read(), reader_path, 'exec')
        info = {
            'error': None,
            'restored': {path: _bw_file_info(path) for path in _bw_cold_paths},
            'decimal': str(decimal.Decimal('1.25') * decimal.Decimal('4')),
            'xml_tag': element_tree.Element('stage').tag,
            'logging_handler': handlers.RotatingFileHandler.__name__,
            'manager_type': managers.SyncManager.__name__,
            'uts46_rows': len(uts46.uts46data),
            'pyrepl_compiles': True,
        }
    except BaseException:
        info = {'error': traceback.format_exc()}
    with open(_bw_stage1_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

bpy.app.timers.register(_bw_initial_probe, first_interval=2.0)
bpy.app.timers.register(_bw_interaction_probe, first_interval=0.1)
bpy.app.timers.register(_bw_stage1_probe, first_interval=0.1)
`;

const seriousConsole = (line) =>
  line.includes("Traceback (most recent call last):") ||
  /ModuleNotFoundError|ImportError:|failed to register|incomplete bind group|submission rejected|transaction rejected|GPU-LOST|Aborted\(/i.test(line);

async function readWasmText(page, path) {
  return page.evaluate((filename) => {
    try {
      return window.__bwModule.FS.readFile(filename, {encoding: "utf8"});
    }
    catch (_) {
      return null;
    }
  }, path);
}

async function waitForWasmText(page, path) {
  for (let attempt = 0; attempt < 240; attempt++) {
    const value = await readWasmText(page, path);
    if (value) return value;
    await page.waitForTimeout(250);
  }
  throw new Error(`timed out waiting for ${path}`);
}

async function counters(page) {
  return page.evaluate(() => ({
    ticks: Number(window.__bwModule._bw_wm_tick_count()),
    presents: Number(window.__bwModule._bw_present_count()),
  }));
}

async function runCase(browser, label, port, loadStage1) {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(180000);
    const consoleErrors = [];
    const traceContext = [];
    let traceLinesRemaining = 0;
    const pageErrors = [];
    page.on("console", (message) => {
      const line = message.text();
      if (line.includes("Traceback (most recent call last):")) {
        traceLinesRemaining = 24;
      }
      if (traceLinesRemaining > 0) {
        traceContext.push(line);
        traceLinesRemaining--;
      }
      if (seriousConsole(line)) consoleErrors.push(line);
    });
    page.on("pageerror", (error) => pageErrors.push(error.message || String(error)));
    const query = new URLSearchParams({
      stage1: "manual",
      pyexpr: `exec(${JSON.stringify(pythonProbe)})`,
    });
    await page.goto(`http://127.0.0.1:${port}/windowed.html?${query}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForFunction(
      () => document.querySelector("#state")?.dataset.state === "running",
      null,
      {polling: 250},
    );
    const initial = JSON.parse(
      await waitForWasmText(page, "/projects/_bw_runtime_stage0.json"),
    );
    await page.waitForFunction(
      () => Number(window.__bwModule?._bw_wm_tick_count?.()) >= 5,
      null,
      {polling: 100, timeout: 30000},
    );

    const before = await counters(page);
    const canvas = page.locator("#canvas");
    await canvas.click({position: {x: 640, y: 360}});
    await page.keyboard.press("Escape");
    await page.keyboard.press("n");
    await page.waitForTimeout(800);
    await page.keyboard.press("n");
    await page.waitForTimeout(800);
    await page.evaluate(() => {
      window.__bwModule.FS.writeFile("/projects/_bw_runtime_interaction_trigger", "1");
    });
    const interaction = JSON.parse(
      await waitForWasmText(page, "/projects/_bw_runtime_interaction.json"),
    );
    const after = await counters(page);

    let stage1 = null;
    let restored = null;
    if (loadStage1) {
      await page.addScriptTag({path: STAGE1_LOADER});
      stage1 = await page.evaluate(() => window.__bwStage1Load());
      await page.evaluate(() => {
        window.__bwModule.FS.writeFile("/projects/_bw_runtime_stage1_trigger", "1");
      });
      restored = JSON.parse(
        await waitForWasmText(page, "/projects/_bw_runtime_stage1.json"),
      );
    }
    return {label, initial, before, after, interaction, stage1, restored,
            consoleErrors, traceContext, pageErrors};
  }
  finally {
    await context.close();
  }
}

const browser = await chromium.launch({
  headless: false,
  args: ["--enable-unsafe-webgpu", "--use-webgpu-adapter=swiftshader", "--use-gpu-in-tests",
         "--ozone-platform=x11"],
});
let baseline;
let staged;
try {
  baseline = await runCase(browser, "monolith", monolithPort, false);
  staged = await runCase(browser, "python-runtime-stage0", stagedPort, true);
}
finally {
  await browser.close();
}

const failures = [];
for (const key of ["version", "addons", "areas", "objects", "cold_modules"]) {
  if (JSON.stringify(baseline.initial[key]) !== JSON.stringify(staged.initial[key])) {
    failures.push(`startup state differs: ${key}`);
  }
}
if (baseline.initial.cold_modules.length !== 0) {
  failures.push(`cold Python modules unexpectedly loaded at boot: ${JSON.stringify(baseline.initial.cold_modules)}`);
}
for (const path of coldPaths) {
  const source = baseline.initial.cold_files[path];
  const placeholder = staged.initial.cold_files[path];
  if (!(source?.bytes > 0) || source.error) {
    failures.push(`monolith cold Python source missing: ${path}`);
  }
  if (placeholder?.bytes !== 0 || placeholder.error) {
    failures.push(`cold Python source did not become a Stage-0 placeholder: ${path}`);
  }
}
for (const path of bootPaths) {
  if (!(baseline.initial.boot_files[path]?.bytes > 0) ||
      JSON.stringify(staged.initial.boot_files[path]) !==
        JSON.stringify(baseline.initial.boot_files[path])) {
    failures.push(`active Python source left Stage 0: ${path}`);
  }
}
if (JSON.stringify(baseline.interaction) !== JSON.stringify(staged.interaction) ||
    baseline.interaction.mode !== "OBJECT" || baseline.interaction.active !== "Cube" ||
    baseline.interaction.vertices !== 8) {
  failures.push(`trusted-input state differs: ${JSON.stringify({baseline: baseline.interaction, staged: staged.interaction})}`);
}
for (const result of [baseline, staged]) {
  if (!(result.after.ticks > result.before.ticks) ||
      !(result.after.presents > result.before.presents)) {
    failures.push(`${result.label} did not advance WM/presentation across launch input`);
  }
  if (result.consoleErrors.length || result.pageErrors.length) {
    failures.push(`${result.label} emitted serious/page errors: ${JSON.stringify({consoleErrors: result.consoleErrors, traceContext: result.traceContext, pageErrors: result.pageErrors})}`);
  }
}
if (!staged.stage1 || staged.stage1.phase !== "done" || staged.stage1.error ||
    staged.stage1.filesDone !== staged.stage1.filesTotal ||
    staged.stage1.bytesDone !== staged.stage1.bytesTotal) {
  failures.push("Stage-1 loader did not restore every deferred byte");
}
if (!staged.restored || staged.restored.error || staged.restored.decimal !== "5.00" ||
    staged.restored.xml_tag !== "stage" || staged.restored.logging_handler !== "RotatingFileHandler" ||
    staged.restored.manager_type !== "SyncManager" || !(staged.restored.uts46_rows > 1000) ||
    staged.restored.pyrepl_compiles !== true) {
  failures.push(`post-Stage-1 Python behavior failed: ${JSON.stringify(staged.restored)}`);
}
for (const path of coldPaths) {
  if (JSON.stringify(staged.restored?.restored?.[path]) !==
      JSON.stringify(baseline.initial.cold_files[path])) {
    failures.push(`Stage 1 did not restore Python source byte-exactly: ${path}`);
  }
}

if (failures.length) {
  console.error(JSON.stringify({failures, baseline, staged}, null, 2));
  process.exit(1);
}
console.log(
  `BW_STAGE0_PYTHON_RUNTIME_PASS cold=${coldPaths.length} boot=${bootPaths.length} ` +
  `restored=${staged.stage1.filesDone}/${staged.stage1.bytesDone} ` +
  `vertices=${staged.interaction.vertices} input=n-toggle errors=0`,
);
