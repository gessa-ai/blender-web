// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prove that source data already compiled into Blender can leave Stage 0 while
// the windowed product still boots and accepts input, and that Stage 1 restores
// the exact inspectable source bytes.

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
  throw new Error("usage: verify_compiled_sources_stage0.mjs MONOLITH_PORT STAGED_PORT");
}

const sourcePaths = [
  "/bw/datafiles/icons_svg/mesh_cube.svg",
  "/bw/datafiles/cursors/cursor_pointer.svg",
  "/bw/datafiles/DejaVuSans-Lite.sfd.bz2",
  "/bw/datafiles/bfont.pfb",
  "/bw/datafiles/userdef/userdef_default_theme.c",
  "/bw/datafiles/blender_icons_geom.py",
  "/bw/datafiles/blender_icons_geom_update.py",
  "/bw/datafiles/ctodata.py",
];
const runtimeIcon = "/bw/datafiles/icons/ops.mesh.primitive_cube_add_gizmo.dat";
const pythonProbe = String.raw`
import bpy, hashlib, json, os

_bw_source_paths = ${JSON.stringify(sourcePaths)}
_bw_runtime_icon = ${JSON.stringify(runtimeIcon)}
_bw_initial_result = '/projects/_bw_compiled_sources_stage0.json'
_bw_stage1_trigger = '/projects/_bw_compiled_sources_stage1_trigger'
_bw_stage1_result = '/projects/_bw_compiled_sources_stage1.json'
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

def _bw_snapshot():
    return {
        'version': bpy.app.version_string,
        'sources': {path: _bw_file_info(path) for path in _bw_source_paths},
        'runtime_icon': _bw_file_info(_bw_runtime_icon),
        'addons': sorted(addon.module for addon in bpy.context.preferences.addons),
        'areas': sorted(area.type for area in bpy.context.screen.areas),
        'objects': sorted(obj.name for obj in bpy.data.objects),
    }

def _bw_initial_probe():
    with open(_bw_initial_result, 'w') as handle:
        handle.write(json.dumps(_bw_snapshot(), separators=(',', ':')))
    return None

def _bw_stage1_probe():
    if not os.path.exists(_bw_stage1_trigger):
        return 0.1
    with open(_bw_stage1_result, 'w') as handle:
        handle.write(json.dumps(_bw_snapshot(), separators=(',', ':')))
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
  for (let attempt = 0; attempt < 160; attempt++) {
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
      await waitForWasmText(page, "/projects/_bw_compiled_sources_stage0.json"),
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
        window.__bwModule.FS.writeFile("/projects/_bw_compiled_sources_stage1_trigger", "1");
      });
      restored = JSON.parse(
        await waitForWasmText(page, "/projects/_bw_compiled_sources_stage1.json"),
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
  staged = await runCase(browser, "compiled-source-stage0", stagedPort, true);
}
finally {
  await browser.close();
}

const failures = [];
for (const key of ["version", "addons", "areas", "objects"]) {
  if (JSON.stringify(baseline.initial[key]) !== JSON.stringify(staged.initial[key])) {
    failures.push(`startup state differs: ${key}`);
  }
}
for (const path of sourcePaths) {
  const original = baseline.initial.sources[path];
  const absent = staged.initial.sources[path];
  const restored = staged.restored?.sources?.[path];
  if (original?.error !== null || !(original?.bytes > 0)) {
    failures.push(`monolith source is absent: ${path}`);
  }
  if (absent?.bytes !== null || !absent?.error?.startsWith("FileNotFoundError:")) {
    failures.push(`Stage-0 source was materialized: ${path}`);
  }
  if (JSON.stringify(restored) !== JSON.stringify(original)) {
    failures.push(`Stage-1 source restoration differs: ${path}`);
  }
}
if (!(baseline.initial.runtime_icon?.bytes > 0) ||
    JSON.stringify(staged.initial.runtime_icon) !== JSON.stringify(baseline.initial.runtime_icon)) {
  failures.push("compiled/runtime icon payload left Stage 0");
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
if (failures.length) {
  console.error(JSON.stringify({failures, baseline, staged}, null, 2));
  throw new Error(`BW_STAGE0_COMPILED_SOURCES_FAIL ${failures.join("; ")}`);
}
console.log(
  `BW_STAGE0_COMPILED_SOURCES_PASS sources=${sourcePaths.length} absent=8 ` +
  `restored=${staged.stage1.filesDone}/${staged.stage1.bytesDone} input=2 errors=0`,
);
