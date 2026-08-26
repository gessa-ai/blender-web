// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prove that boot-cold Blender support scripts and inactive presets can ride
// Stage 1 while the active Blender keymap and trusted viewport input remain
// usable from Stage 0. Stage 1 must restore every representative byte and the
// deferred Python modules must import normally afterward.

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
  throw new Error("usage: verify_python_support_stage0.mjs MONOLITH_PORT STAGED_PORT");
}

const coldPaths = [
  "/bw/scripts/addons_core/bl_pkg/tests/test_cli.py",
  "/bw/scripts/freestyle/modules/freestyle/utils.py",
  "/bw/scripts/modules/_bl_i18n_utils/utils.py",
  "/bw/scripts/modules/_rna_manual_reference.py",
  "/bw/scripts/presets/camera/Fullframe.py",
  "/bw/scripts/presets/keyconfig/Industry_Compatible.py",
  "/bw/scripts/presets/keyconfig/keymap_data/industry_compatible_data.py",
  "/bw/scripts/templates_osl/basic_shader.osl",
  "/bw/scripts/templates_py/Operator/simple.py",
  "/bw/scripts/templates_toml/blender_manifest.toml",
];
const bootPaths = [
  "/bw/scripts/addons_core/bl_pkg/bl_extension_ops.py",
  "/bw/scripts/presets/keyconfig/Blender.py",
  "/bw/scripts/presets/keyconfig/keymap_data/blender_default.py",
  "/bw/scripts/startup/bl_ui/space_view3d.py",
];
const supportPrefixes = [
  "/bw/scripts/addons_core/bl_pkg/tests/",
  "/bw/scripts/freestyle/",
  "/bw/scripts/modules/_bl_i18n_utils/",
  "/bw/scripts/modules/_rna_manual_reference.py",
  "/bw/scripts/templates_osl/",
  "/bw/scripts/templates_py/",
  "/bw/scripts/templates_toml/",
];

const pythonProbe = String.raw`
import bpy, hashlib, importlib, json, os, sys, traceback

_bw_cold_paths = ${JSON.stringify(coldPaths)}
_bw_boot_paths = ${JSON.stringify(bootPaths)}
_bw_support_prefixes = ${JSON.stringify(supportPrefixes)}
_bw_initial_result = '/projects/_bw_support_stage0.json'
_bw_stage1_trigger = '/projects/_bw_support_stage1_trigger'
_bw_stage1_result = '/projects/_bw_support_stage1.json'
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
        return {'bytes': None, 'sha256': None,
                'error': type(error).__name__ + ': ' + str(error)}

def _bw_support_modules():
    result = {}
    for name, module in sys.modules.items():
        filename = getattr(module, '__file__', None)
        if filename and any(filename.startswith(prefix) for prefix in _bw_support_prefixes):
            result[name] = filename
    return result

def _bw_initial_probe():
    keyconfig = bpy.context.window_manager.keyconfigs.active
    tab_bindings = sorted(
        (keymap.name, item.idname, item.value)
        for keymap in keyconfig.keymaps
        for item in keymap.keymap_items
        if item.type == 'TAB'
    )
    info = {
        'version': bpy.app.version_string,
        'addons': sorted(addon.module for addon in bpy.context.preferences.addons),
        'areas': sorted(area.type for area in bpy.context.screen.areas),
        'objects': sorted(obj.name for obj in bpy.data.objects),
        'keymap': {
            'name': keyconfig.name,
            'maps': len(keyconfig.keymaps),
            'items': sum(len(keymap.keymap_items) for keymap in keyconfig.keymaps),
            'tab_bindings': tab_bindings,
        },
        'support_modules': _bw_support_modules(),
        'cold_files': {path: _bw_file_info(path) for path in _bw_cold_paths},
        'boot_files': {path: _bw_file_info(path) for path in _bw_boot_paths},
    }
    with open(_bw_initial_result, 'w') as handle:
        handle.write(json.dumps(info, separators=(',', ':')))
    return None

def _bw_stage1_probe():
    if not os.path.exists(_bw_stage1_trigger):
        return 0.1
    try:
        importlib.invalidate_caches()
        manual = importlib.import_module('_rna_manual_reference')
        i18n_settings = importlib.import_module('_bl_i18n_utils.settings')
        template_path = '/bw/scripts/templates_py/Operator/simple.py'
        with open(template_path, 'r', encoding='utf-8') as handle:
            compile(handle.read(), template_path, 'exec')
        i18n_utils_path = '/bw/scripts/modules/_bl_i18n_utils/utils.py'
        with open(i18n_utils_path, 'r', encoding='utf-8') as handle:
            compile(handle.read(), i18n_utils_path, 'exec')
        info = {
            'error': None,
            'restored': {path: _bw_file_info(path) for path in _bw_cold_paths},
            'imports': {
                '_rna_manual_reference': manual.__file__,
                '_bl_i18n_utils.settings': i18n_settings.__file__,
            },
            'manual_mapping_count': len(manual.url_manual_mapping),
            'i18n_language_count': len(i18n_settings.LANGUAGES),
            'i18n_utils_compiles': True,
            'template_compiles': True,
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
      await waitForWasmText(page, "/projects/_bw_support_stage0.json"),
    );
    await page.waitForFunction(
      () => Number(window.__bwModule?._bw_wm_tick_count?.()) >= 5,
      null,
      {polling: 100, timeout: 30000},
    );
    const before = await counters(page);
    await page.locator("#canvas").click({position: {x: 640, y: 360}});
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    await page.keyboard.press("n");
    await page.waitForTimeout(800);
    await page.keyboard.press("n");
    await page.waitForTimeout(800);
    const after = await counters(page);

    let stage1 = null;
    let restored = null;
    if (loadStage1) {
      await page.addScriptTag({path: STAGE1_LOADER});
      stage1 = await page.evaluate(() => window.__bwStage1Load());
      await page.evaluate(() => {
        window.__bwModule.FS.writeFile("/projects/_bw_support_stage1_trigger", "1");
      });
      restored = JSON.parse(
        await waitForWasmText(page, "/projects/_bw_support_stage1.json"),
      );
    }
    return {label, initial, before, after, stage1, restored,
            consoleErrors, pageErrors};
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
  staged = await runCase(browser, "python-support-stage0", stagedPort, true);
}
finally {
  await browser.close();
}

const failures = [];
for (const key of ["version", "addons", "areas", "objects", "keymap",
                   "support_modules"]) {
  if (JSON.stringify(baseline.initial[key]) !== JSON.stringify(staged.initial[key])) {
    failures.push(`startup state differs: ${key}`);
  }
}
if (baseline.initial.keymap.name !== "Blender" || baseline.initial.keymap.maps < 20 ||
    baseline.initial.keymap.items < 100 || baseline.initial.keymap.tab_bindings.length === 0) {
  failures.push(`active Blender keymap is incomplete: ${JSON.stringify(baseline.initial.keymap)}`);
}
if (Object.keys(baseline.initial.support_modules).length !== 0) {
  failures.push(`support modules unexpectedly loaded at boot: ${JSON.stringify(baseline.initial.support_modules)}`);
}
for (const path of coldPaths) {
  const source = baseline.initial.cold_files[path];
  const placeholder = staged.initial.cold_files[path];
  if (!(source?.bytes > 0) || source.error) {
    failures.push(`monolith support source missing: ${path}`);
  }
  if (placeholder?.bytes !== 0 || placeholder.error) {
    failures.push(`support source did not become a Stage-0 placeholder: ${path}`);
  }
}
for (const path of bootPaths) {
  if (!(baseline.initial.boot_files[path]?.bytes > 0) ||
      JSON.stringify(staged.initial.boot_files[path]) !==
        JSON.stringify(baseline.initial.boot_files[path])) {
    failures.push(`active boot source left Stage 0: ${path}`);
  }
}
for (const result of [baseline, staged]) {
  if (!(result.after.ticks > result.before.ticks) ||
      !(result.after.presents > result.before.presents)) {
    failures.push(`${result.label} did not advance WM/presentation across trusted input`);
  }
  if (result.consoleErrors.length || result.pageErrors.length) {
    failures.push(`${result.label} emitted serious/page errors: ${JSON.stringify({consoleErrors: result.consoleErrors, pageErrors: result.pageErrors})}`);
  }
}
if (!staged.stage1 || staged.stage1.phase !== "done" || staged.stage1.error ||
    staged.stage1.filesDone !== staged.stage1.filesTotal ||
    staged.stage1.bytesDone !== staged.stage1.bytesTotal) {
  failures.push("Stage-1 loader did not restore every deferred byte");
}
if (!staged.restored || staged.restored.error ||
    staged.restored.manual_mapping_count < 100 ||
    staged.restored.i18n_language_count < 20 ||
    staged.restored.i18n_utils_compiles !== true ||
    staged.restored.template_compiles !== true) {
  failures.push(`post-Stage-1 support behavior failed: ${JSON.stringify(staged.restored)}`);
}
for (const path of coldPaths) {
  if (JSON.stringify(staged.restored?.restored?.[path]) !==
      JSON.stringify(baseline.initial.cold_files[path])) {
    failures.push(`Stage 1 did not restore support source byte-exactly: ${path}`);
  }
}

if (failures.length) {
  console.error(JSON.stringify({failures, baseline, staged}, null, 2));
  process.exit(1);
}
console.log(
  `BW_STAGE0_PYTHON_SUPPORT_PASS cold=${coldPaths.length} boot=${bootPaths.length} ` +
  `restored=${staged.stage1.filesDone}/${staged.stage1.bytesDone} input=2 errors=0`,
);
