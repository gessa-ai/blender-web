// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prove that exact browser-cold Python/Blender sources, package support data,
// and on-demand launch assets
// can ride Stage 1 while the pre-Stage-1 product still boots and accepts trusted
// viewport input. Deferred files are absent until Stage 1 except for the
// zero-byte names Blender enumerates into startup registries; Stage 1 must
// restore representative bytes, lazy imports,
// package metadata/CA access, lazy toolbar icons, and the mono-font Console path.

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
  "/bw/scripts/modules/bpy_extras/anim_utils.py",
  "/bw/scripts/modules/_rna_info.py",
  "/bw/scripts/addons_core/bl_pkg/bl_extension_cli.py",
  "/bw/scripts/addons_core/cycles/osl.py",
  "/bw/scripts/startup/bl_ui/properties_freestyle.py",
  "/bw/python/lib/python3.13/site-packages/certifi/cacert.pem",
  "/bw/python/lib/python3.13/site-packages/requests-2.32.3.dist-info/METADATA",
  "/bw/python/lib/python3.13/site-packages/attr/__init__.pyi",
  "/bw/scripts/modules/_bpy_internal/assets/remote_library/blender_asset_library_openapi.yaml",
  "/bw/scripts/addons_core/bl_pkg/readme.rst",
  "/bw/python/lib/python3.13/LICENSE.txt",
  "/bw/python/lib/python3.13/email/architecture.rst",
  "/bw/datafiles/icons/brush.sculpt.dat",
  "/bw/datafiles/icons/ops.mesh.primitive_sphere_add_gizmo.dat",
  "/bw/datafiles/icons/ops.node.add_reroute.dat",
  "/bw/datafiles/icons/ops.sequencer.slip.dat",
  "/bw/datafiles/colormanagement/luts/AgX_False_Color.spi1d",
];
const discoveryPaths = [
  "/bw/datafiles/studiolights/matcap/basic_bright.exr",
  "/bw/datafiles/studiolights/world/forest.exr",
];
const fontContracts = [
  {
    path: "/bw/datafiles/fonts/Inter.woff2",
    source: {bytes: 351132, sha256: "fb865a5087637ba194b14aef6f0558214f3c4b3ec939e3c0812c66de41036a47"},
    stage0: {bytes: 22480, sha256: "47d56ba06d6380e40f49201b85421b5f8a22bc2b83ed7a257c9ab49fdc66421f"},
  },
  {
    path: "/bw/datafiles/fonts/DejaVuSansMono.woff2",
    source: {bytes: 145192, sha256: "eb072b01f0f06ce11530a90cc11f094c60819d65ed47156540e23198ae149612"},
    stage0: {bytes: 18272, sha256: "48af4c490eef98385cc4e4ee96b35b772880f751e72a906ec5b3ba645d57903b"},
  },
];
const bootPaths = [
  "/bw/python/lib/python3.13/_collections_abc.py",
  "/bw/python/lib/python3.13/email/message.py",
  "/bw/python/lib/python3.13/encodings/utf_8_sig.py",
  "/bw/python/lib/python3.13/logging/__init__.py",
  "/bw/python/lib/python3.13/multiprocessing/connection.py",
  "/bw/python/lib/python3.13/site-packages/idna/core.py",
  "/bw/scripts/modules/_bpy_types.py",
  "/bw/scripts/addons_core/bl_pkg/bl_extension_ops.py",
  "/bw/scripts/presets/keyconfig/keymap_data/blender_default.py",
  "/bw/datafiles/icons/ops.generic.cursor.dat",
  "/bw/datafiles/icons/ops.generic.select_box.dat",
  "/bw/datafiles/icons/ops.mesh.primitive_cube_add_gizmo.dat",
  "/bw/datafiles/icons/ops.transform.translate.dat",
  "/bw/datafiles/colormanagement/config.ocio",
  "/bw/datafiles/colormanagement/luts/AgX_Base_sRGB.cube",
  "/bw/datafiles/colormanagement/luts/Guard_Rail_Shaper_EOTF.spi1d",
  "/bw/python/lib/python3.13/site-packages/urllib3/contrib/emscripten/emscripten_fetch_worker.js",
];
const coldModuleNames = [
  "_pyrepl.reader",
  "logging.handlers",
  "multiprocessing.managers",
  "idna.uts46data",
  "xml.etree.ElementTree",
  "bpy_extras.anim_utils",
  "_rna_info",
  "bl_pkg.bl_extension_cli",
  "cycles.osl",
  "bl_ui.properties_freestyle",
];
const bootToolIcons = [
  "ops.generic.cursor",
  "ops.generic.select_box",
  "ops.gpencil.draw",
  "ops.mesh.primitive_cube_add_gizmo",
  "ops.pose.breakdowner",
  "ops.transform.resize",
  "ops.transform.rotate",
  "ops.transform.transform",
  "ops.transform.translate",
  "ops.view3d.ruler",
];
const coldIconNames = [
  "brush.sculpt",
  "ops.mesh.primitive_sphere_add_gizmo",
  "ops.node.add_reroute",
  "ops.sequencer.slip",
];

const pythonProbe = String.raw`
import bpy, hashlib, importlib, json, os, sys, traceback
from bl_ui import space_toolsystem_common

_bw_cold_paths = ${JSON.stringify(coldPaths)}
_bw_discovery_paths = ${JSON.stringify(discoveryPaths)}
_bw_font_paths = ${JSON.stringify(fontContracts.map((row) => row.path))}
_bw_boot_paths = ${JSON.stringify(bootPaths)}
_bw_cold_module_names = ${JSON.stringify(coldModuleNames)}
_bw_cold_icon_names = ${JSON.stringify(coldIconNames)}
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
    keyconfig = bpy.context.window_manager.keyconfigs.active
    info = {
        'version': bpy.app.version_string,
        'addons': sorted(addon.module for addon in bpy.context.preferences.addons),
        'areas': sorted(area.type for area in bpy.context.screen.areas),
        'objects': sorted(obj.name for obj in bpy.data.objects),
        'color_management': {
            'display': bpy.context.scene.display_settings.display_device,
            'view': bpy.context.scene.view_settings.view_transform,
            'look': bpy.context.scene.view_settings.look,
        },
        'keymap': {
            'name': keyconfig.name,
            'maps': len(keyconfig.keymaps),
            'items': sum(len(keymap.keymap_items) for keymap in keyconfig.keymaps),
        },
        'tool_icons': sorted(space_toolsystem_common._icon_cache),
        'studio_lights': sorted((light.name, light.type)
                                for light in bpy.context.preferences.studio_lights),
        'cold_modules': sorted(name for name in _bw_cold_module_names if name in sys.modules),
        'cold_files': {path: _bw_file_info(path) for path in _bw_cold_paths},
        'discovery_files': {path: _bw_file_info(path) for path in _bw_discovery_paths},
        'font_files': {path: _bw_file_info(path) for path in _bw_font_paths},
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
        metadata = importlib.import_module('importlib.metadata')
        certifi = importlib.import_module('certifi')
        anim_utils = importlib.import_module('bpy_extras.anim_utils')
        rna_info = importlib.import_module('_rna_info')
        extension_cli = importlib.import_module('bl_pkg.bl_extension_cli')
        cycles_osl = importlib.import_module('cycles.osl')
        bpy.context.scene.view_settings.view_transform = 'False Color'
        view3d_area = next((area for area in bpy.context.screen.areas
                            if area.type == 'VIEW_3D'), None)
        world_light = None
        matcap_light = None
        if view3d_area is not None:
            shading = view3d_area.spaces.active.shading
            shading.type = 'MATERIAL'
            shading.studio_light = 'forest.exr'
            world_light = shading.selected_studio_light.name
            shading.type = 'SOLID'
            shading.light = 'MATCAP'
            shading.studio_light = 'basic_bright.exr'
            matcap_light = shading.selected_studio_light.name
        for area in bpy.context.screen.areas:
            area.tag_redraw()
        reader_path = '/bw/python/lib/python3.13/_pyrepl/reader.py'
        with open(reader_path, 'r', encoding='utf-8') as handle:
            compile(handle.read(), reader_path, 'exec')
        compile_paths = [
            '/bw/scripts/startup/bl_ui/properties_freestyle.py',
            '/bw/python/lib/python3.13/site-packages/attr/__init__.pyi',
        ]
        for path in compile_paths:
            with open(path, 'r', encoding='utf-8') as handle:
                compile(handle.read(), path, 'exec')
        with open(certifi.where(), 'rb') as handle:
            ca_data = handle.read()
        console_area = next((area for area in bpy.context.screen.areas if area.type == 'VIEW_3D'), None)
        if console_area is not None:
            console_area.type = 'CONSOLE'
        cold_icons = {
            name: space_toolsystem_common.ToolSelectPanelHelper._icon_value_from_icon_handle(name)
            for name in _bw_cold_icon_names
        }
        info = {
            'error': None,
            'restored': {path: _bw_file_info(path)
                         for path in _bw_cold_paths + _bw_discovery_paths + _bw_font_paths},
            'decimal': str(decimal.Decimal('1.25') * decimal.Decimal('4')),
            'xml_tag': element_tree.Element('stage').tag,
            'logging_handler': handlers.RotatingFileHandler.__name__,
            'manager_type': managers.SyncManager.__name__,
            'uts46_rows': len(uts46.uts46data),
            'pyrepl_compiles': True,
            'anim_utils': hasattr(anim_utils, 'BakeOptions'),
            'rna_info': hasattr(rna_info, 'BuildRNAInfo'),
            'extension_cli': hasattr(extension_cli, 'cli_extension_handler'),
            'cycles_osl': hasattr(cycles_osl, 'osl_compile'),
            'false_color_view': bpy.context.scene.view_settings.view_transform,
            'studio_world': world_light,
            'studio_matcap': matcap_light,
            'studio_registry': sorted((light.name, light.type)
                                      for light in bpy.context.preferences.studio_lights),
            'compiled_sources': len(compile_paths),
            'requests_version': metadata.version('requests'),
            'ca_certificates': ca_data.count(b'-----BEGIN CERTIFICATE-----'),
            'console_area': console_area.type if console_area is not None else None,
            'cold_icons': cold_icons,
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
  /ModuleNotFoundError|ImportError:|failed to register|incomplete bind group|submission rejected|transaction rejected|GPU-LOST|Aborted\(|OpenColorIO.*(?:error|failed)|AgX_False_Color.*(?:missing|error|failed)|Could not load.*(?:cube|spi1d)/i.test(line);

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
    await page.goto(`http://127.0.0.1:${port}/index.html?${query}`, {
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
    let stage1Before = null;
    let stage1After = null;
    if (loadStage1) {
      stage1Before = await counters(page);
      await page.addScriptTag({path: STAGE1_LOADER});
      stage1 = await page.evaluate(() => window.__bwStage1Load());
      await page.evaluate(() => {
        window.__bwModule.FS.writeFile("/projects/_bw_runtime_stage1_trigger", "1");
      });
      restored = JSON.parse(
        await waitForWasmText(page, "/projects/_bw_runtime_stage1.json"),
      );
      await page.waitForTimeout(1000);
      stage1After = await counters(page);
    }
    return {label, initial, before, after, interaction, stage1, restored,
            stage1Before, stage1After, consoleErrors, traceContext, pageErrors};
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
for (const key of ["version", "addons", "areas", "objects", "color_management", "keymap", "tool_icons",
                   "studio_lights", "cold_modules"]) {
  if (JSON.stringify(baseline.initial[key]) !== JSON.stringify(staged.initial[key])) {
    failures.push(`startup state differs: ${key}`);
  }
}
if (JSON.stringify(baseline.initial.color_management) !==
    JSON.stringify({display: "sRGB", view: "AgX", look: "None"})) {
  failures.push(`factory color-management path changed: ${JSON.stringify(baseline.initial.color_management)}`);
}
if (baseline.initial.cold_modules.length !== 0) {
  failures.push(`cold Python modules unexpectedly loaded at boot: ${JSON.stringify(baseline.initial.cold_modules)}`);
}
if (baseline.initial.keymap.name !== "Blender" || baseline.initial.keymap.maps < 20 ||
    baseline.initial.keymap.items < 100) {
  failures.push(`active Blender keymap is incomplete: ${JSON.stringify(baseline.initial.keymap)}`);
}
if (JSON.stringify(baseline.initial.tool_icons) !== JSON.stringify(bootToolIcons)) {
  failures.push(`default toolbar icon closure changed: ${JSON.stringify(baseline.initial.tool_icons)}`);
}
const studioTypes = Object.fromEntries(["STUDIO", "MATCAP", "WORLD"].map((type) => [
  type, baseline.initial.studio_lights.filter((row) => row[1] === type).length,
]));
if (baseline.initial.studio_lights.length !== 41 || studioTypes.STUDIO !== 6 ||
    studioTypes.MATCAP !== 27 || studioTypes.WORLD !== 8) {
  failures.push(`factory studio-light registry changed: ${JSON.stringify({
    count: baseline.initial.studio_lights.length, studioTypes,
  })}`);
}
for (const path of coldPaths) {
  const source = baseline.initial.cold_files[path];
  const absent = staged.initial.cold_files[path];
  if (!(source?.bytes > 0) || source.error) {
    failures.push(`monolith cold file missing: ${path}`);
  }
  if (absent?.bytes !== null ||
      !absent?.error?.startsWith("FileNotFoundError:")) {
    failures.push(`cold file was materialized in Stage 0: ${path}`);
  }
}
for (const path of discoveryPaths) {
  const source = baseline.initial.discovery_files[path];
  const placeholder = staged.initial.discovery_files[path];
  if (!(source?.bytes > 0) || source.error) {
    failures.push(`monolith discovery asset missing: ${path}`);
  }
  if (placeholder?.bytes !== 0 || placeholder.error !== null) {
    failures.push(`discovery filename was not retained as a zero-byte Stage-0 entry: ${path}`);
  }
}
for (const contract of fontContracts) {
  if (JSON.stringify(baseline.initial.font_files[contract.path]) !==
      JSON.stringify({...contract.source, error: null})) {
    failures.push(`monolith font source identity changed: ${contract.path}`);
  }
  if (JSON.stringify(staged.initial.font_files[contract.path]) !==
      JSON.stringify({...contract.stage0, error: null})) {
    failures.push(`Stage-0 font bootstrap identity changed: ${contract.path}`);
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
    staged.stage1.bytesDone !== staged.stage1.bytesTotal ||
    staged.stage1.bootstrapTotal !== fontContracts.length ||
    staged.stage1.bootstrapDone !== fontContracts.length ||
    staged.stage1.fontRefresh !== "done") {
  failures.push("Stage-1 loader did not restore every deferred byte");
}
if (!staged.restored || staged.restored.error || staged.restored.decimal !== "5.00" ||
    staged.restored.xml_tag !== "stage" || staged.restored.logging_handler !== "RotatingFileHandler" ||
    staged.restored.manager_type !== "SyncManager" || !(staged.restored.uts46_rows > 1000) ||
    staged.restored.pyrepl_compiles !== true || staged.restored.anim_utils !== true ||
    staged.restored.rna_info !== true || staged.restored.extension_cli !== true ||
    staged.restored.cycles_osl !== true || staged.restored.compiled_sources !== 2 ||
    staged.restored.false_color_view !== "False Color" ||
    staged.restored.studio_world !== "forest.exr" ||
    staged.restored.studio_matcap !== "basic_bright.exr" ||
    JSON.stringify(staged.restored.studio_registry) !== JSON.stringify(baseline.initial.studio_lights) ||
    staged.restored.requests_version !== "2.32.3" ||
    !(staged.restored.ca_certificates > 100) || staged.restored.console_area !== "CONSOLE" ||
    coldIconNames.some((name) => !(staged.restored.cold_icons?.[name] > 0))) {
  failures.push(`post-Stage-1 behavior failed: ${JSON.stringify(staged.restored)}`);
}
if (!(staged.stage1After?.ticks > staged.stage1Before?.ticks) ||
    !(staged.stage1After?.presents > staged.stage1Before?.presents)) {
  failures.push(`Console transition did not advance after Stage 1: ${JSON.stringify({
    before: staged.stage1Before, after: staged.stage1After,
  })}`);
}
for (const path of coldPaths) {
  if (JSON.stringify(staged.restored?.restored?.[path]) !==
      JSON.stringify(baseline.initial.cold_files[path])) {
    failures.push(`Stage 1 did not restore cold file byte-exactly: ${path}`);
  }
}
for (const path of discoveryPaths) {
  if (JSON.stringify(staged.restored?.restored?.[path]) !==
      JSON.stringify(baseline.initial.discovery_files[path])) {
    failures.push(`Stage 1 did not restore discovery asset byte-exactly: ${path}`);
  }
}
for (const contract of fontContracts) {
  if (JSON.stringify(staged.restored?.restored?.[contract.path]) !==
      JSON.stringify(baseline.initial.font_files[contract.path])) {
    failures.push(`Stage 1 did not restore font byte-exactly: ${contract.path}`);
  }
}

if (failures.length) {
  console.error(JSON.stringify({failures, baseline, staged}, null, 2));
  process.exit(1);
}
console.log(
  `BW_STAGE0_PYTHON_RUNTIME_PASS cold=${coldPaths.length} boot=${bootPaths.length} ` +
  `fonts=${fontContracts.length}/${staged.stage1.bootstrapDone} ` +
  `restored=${staged.stage1.filesDone}/${staged.stage1.bytesDone} ` +
  `vertices=${staged.interaction.vertices} console=${staged.restored.console_area} ` +
  `ocio=${staged.initial.color_management.view}->${staged.restored.false_color_view} ` +
  `input=n-toggle errors=0`,
);
