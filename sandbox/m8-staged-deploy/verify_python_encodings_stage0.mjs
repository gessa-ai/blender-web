// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prove that Python's registry/UTF-8 codec closure remains in Stage 0 while
// boot-cold legacy codecs move to Stage 1 and recover exact behavior afterward.

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
  throw new Error("usage: verify_python_encodings_stage0.mjs MONOLITH_PORT STAGED_PORT");
}

const coldModules = ["encodings.cp1252", "encodings.latin_1", "encodings.shift_jis"];
const coldPaths = [
  "/bw/python/lib/python3.13/encodings/cp1252.py",
  "/bw/python/lib/python3.13/encodings/latin_1.py",
  "/bw/python/lib/python3.13/encodings/shift_jis.py",
];
const bootPaths = [
  "/bw/python/lib/python3.13/encodings/__init__.py",
  "/bw/python/lib/python3.13/encodings/aliases.py",
  "/bw/python/lib/python3.13/encodings/idna.py",
  "/bw/python/lib/python3.13/encodings/utf_8.py",
  "/bw/python/lib/python3.13/encodings/utf_8_sig.py",
];

const pythonProbe = String.raw`
import bpy, hashlib, importlib, json, os, sys, traceback

_bw_cold_modules = ${JSON.stringify(coldModules)}
_bw_cold_paths = ${JSON.stringify(coldPaths)}
_bw_boot_paths = ${JSON.stringify(bootPaths)}
_bw_initial_result = '/projects/_bw_encodings_stage0.json'
_bw_stage1_trigger = '/projects/_bw_encodings_stage1_trigger'
_bw_stage1_result = '/projects/_bw_encodings_stage1.json'
for _bw_path in (_bw_initial_result, _bw_stage1_trigger, _bw_stage1_result):
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
        return {'bytes': None, 'sha256': None, 'error': type(error).__name__ + ': ' + str(error)}

def _bw_encoding_modules():
    return sorted(name for name in sys.modules if name == 'encodings' or name.startswith('encodings.'))

def _bw_initial_probe():
    info = {
        'version': bpy.app.version_string,
        'addons': sorted(addon.module for addon in bpy.context.preferences.addons),
        'areas': sorted(area.type for area in bpy.context.screen.areas),
        'objects': sorted(obj.name for obj in bpy.data.objects),
        'encoding_modules': _bw_encoding_modules(),
        'cold_modules': sorted(name for name in _bw_cold_modules if name in sys.modules),
        'cold_files': {path: _bw_file_info(path) for path in _bw_cold_paths},
        'boot_files': {path: _bw_file_info(path) for path in _bw_boot_paths},
        'utf8_roundtrip': 'café_Δ'.encode('utf-8').decode('utf-8'),
    }
    with open(_bw_initial_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

def _bw_stage1_probe():
    if not os.path.exists(_bw_stage1_trigger):
        return 0.1
    try:
        importlib.invalidate_caches()
        imported = {}
        for name in _bw_cold_modules:
            module = importlib.import_module(name)
            imported[name] = _bw_file_info(module.__file__)
        info = {
            'error': None,
            'imported': imported,
            'samples': {
                'cp1252': 'café €'.encode('cp1252').hex(),
                'latin_1': 'café'.encode('latin_1').hex(),
                'shift_jis': '日本'.encode('shift_jis').hex(),
            },
        }
    except BaseException:
        info = {'error': traceback.format_exc()}
    with open(_bw_stage1_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

bpy.app.timers.register(_bw_initial_probe, first_interval=2.0)
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

async function runCase(browser, label, port, loadStage1) {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(180000);
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => {
      const line = message.text();
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
      await waitForWasmText(page, "/projects/_bw_encodings_stage0.json"),
    );
    await page.waitForFunction(
      () => Number(window.__bwModule?._bw_wm_tick_count?.()) >= 5,
      null,
      {polling: 100, timeout: 30000},
    );
    const before = await page.evaluate(() => ({
      ticks: Number(window.__bwModule._bw_wm_tick_count()),
      presents: Number(window.__bwModule._bw_present_count()),
    }));
    await page.locator("#canvas").click({position: {x: 640, y: 360}});
    await page.keyboard.press("n");
    await page.waitForTimeout(1200);
    await page.keyboard.press("n");
    await page.waitForTimeout(1200);
    const after = await page.evaluate(() => ({
      ticks: Number(window.__bwModule._bw_wm_tick_count()),
      presents: Number(window.__bwModule._bw_present_count()),
    }));

    let stage1 = null;
    let restored = null;
    if (loadStage1) {
      await page.addScriptTag({path: STAGE1_LOADER});
      stage1 = await page.evaluate(() => window.__bwStage1Load());
      await page.evaluate(() => {
        window.__bwModule.FS.writeFile("/projects/_bw_encodings_stage1_trigger", "1");
      });
      restored = JSON.parse(
        await waitForWasmText(page, "/projects/_bw_encodings_stage1.json"),
      );
    }
    return {label, initial, before, after, stage1, restored, consoleErrors, pageErrors};
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
  staged = await runCase(browser, "python-encodings-stage0", stagedPort, true);
}
finally {
  await browser.close();
}

const failures = [];
for (const key of ["version", "addons", "areas", "objects", "encoding_modules",
                   "utf8_roundtrip"]) {
  if (JSON.stringify(baseline.initial[key]) !== JSON.stringify(staged.initial[key])) {
    failures.push(`startup state differs: ${key}`);
  }
}
if (baseline.initial.utf8_roundtrip !== "café_Δ") {
  failures.push("Stage-0 UTF-8 round-trip changed");
}
if (baseline.initial.cold_modules.length || staged.initial.cold_modules.length) {
  failures.push("legacy codecs entered the first-pixel import closure");
}
for (const path of coldPaths) {
  const source = baseline.initial.cold_files[path];
  const placeholder = staged.initial.cold_files[path];
  if (source?.error !== null || !(source?.bytes > 0)) {
    failures.push(`monolith codec is absent: ${path}`);
  }
  if (placeholder?.error !== null || placeholder?.bytes !== 0) {
    failures.push(`Stage-0 codec is not a zero-length placeholder: ${path}`);
  }
}
for (const path of bootPaths) {
  if (!(baseline.initial.boot_files[path]?.bytes > 0) ||
      JSON.stringify(staged.initial.boot_files[path]) !==
        JSON.stringify(baseline.initial.boot_files[path])) {
    failures.push(`registry/UTF-8 boot file left Stage 0: ${path}`);
  }
}
for (const result of [baseline, staged]) {
  if (result.pageErrors.length) failures.push(`${result.label} page errors`);
  if (result.consoleErrors.length) failures.push(`${result.label} serious console errors`);
  if (!(result.after.ticks > result.before.ticks)) failures.push(`${result.label} WM ticks stalled`);
  if (!(result.after.presents > result.before.presents)) {
    failures.push(`${result.label} presentation count stalled after trusted input`);
  }
}
if (staged.stage1?.phase !== "done" || staged.stage1?.error !== null ||
    staged.stage1?.filesDone !== staged.stage1?.filesTotal ||
    staged.stage1?.bytesDone !== staged.stage1?.bytesTotal) {
  failures.push("Stage-1 loader did not restore every deferred byte");
}
const expectedSamples = {
  cp1252: "636166e92080",
  latin_1: "636166e9",
  shift_jis: "93fa967b",
};
if (staged.restored?.error !== null ||
    JSON.stringify(staged.restored?.samples) !== JSON.stringify(expectedSamples)) {
  failures.push("restored codec round-trip contract failed");
}
for (const [index, name] of coldModules.entries()) {
  if (JSON.stringify(staged.restored?.imported?.[name]) !==
      JSON.stringify(baseline.initial.cold_files[coldPaths[index]])) {
    failures.push(`restored codec source differs: ${name}`);
  }
}
if (failures.length) {
  console.error(JSON.stringify({failures, baseline, staged}, null, 2));
  throw new Error(`BW_STAGE0_PYTHON_ENCODINGS_FAIL ${failures.join("; ")}`);
}
console.log(
  `BW_STAGE0_PYTHON_ENCODINGS_PASS cold=${coldPaths.length} boot=${bootPaths.length} ` +
  `restored=${staged.stage1.filesDone}/${staged.stage1.bytesDone} codecs=3 ` +
  `input=2 errors=0`,
);
