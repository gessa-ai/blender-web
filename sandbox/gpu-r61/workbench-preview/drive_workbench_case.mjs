// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Run one Workbench startup-file case with the proven r35 bridge while keeping
// retained r35 evidence immutable. The only behavioral addition is the exact
// setup performed by upstream/tests/python/workbench_render_tests.py.
import { existsSync, readFileSync } from 'fs';
import { spawnSync } from 'child_process';
import { createHash as createOuterHash } from 'crypto';

const sourcePath = '/Users/paws/blender-web/sandbox/gpu-r35/bridge_boot.mjs';
const driverPath = '/Users/paws/blender-web/sandbox/gpu-r61/workbench-preview/drive_workbench_case.mjs';
const matrixRunnerPath = '/Users/paws/blender-web/sandbox/gpu-r61/workbench-preview/run_matrix.sh';
const manifestSourcePath = '/Users/paws/blender-web/sandbox/m6-prep/manifest.tsv';
const outDir = process.env.BW_WORKBENCH_OUTDIR;
const outName = process.argv[4] || 'out';
const productToken = `${outName}-${process.pid}-${Date.now()}`;
const productSchema = 'bw-workbench-product-v1';
const productPngGuest = `/tmp/${productToken}-render-result.png`;
const productDoneGuest = `/tmp/${productToken}-render-result.done.json`;
const productArmedGuest = `/tmp/${productToken}-render-result.armed.json`;
const productCaptureFile = 'render_result.png';
const binDir = process.env.BLENDER_WEB_BIN || '/Users/paws/blender-web/build-wasm-windowed-opt/bin';
const deferredWasmFilename =
  process.env.BW_DEFERRED_WASM_FILENAME || 'blender_browser.deferred.wasm';
if (!/^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm$/.test(deferredWasmFilename) ||
    ['blender_browser.wasm', 'blender_browser.wasm.orig'].includes(deferredWasmFilename)) {
  throw new Error(`unsafe deferred Wasm filename: ${deferredWasmFilename}`);
}
const binaryPaths = Object.freeze({
  javascript: `${binDir}/blender_browser.js`,
  wasm: `${binDir}/blender_browser.wasm`,
  deferred: `${binDir}/${deferredWasmFilename}`,
  preload: `${binDir}/blender_browser.data`,
});
const shellPaths = Object.freeze({
  index: '/Users/paws/blender-web/platform_web/shell/index.html',
  windowed: '/Users/paws/blender-web/platform_web/shell/windowed.html',
  boot: '/Users/paws/blender-web/platform_web/shell/boot-windowed.js',
  fileBridge: '/Users/paws/blender-web/platform_web/shell/file-bridge.js',
  preinit: '/Users/paws/blender-web/platform_web/shell/wgpu-preinit-worker.js',
});
const shippingBinary = Object.fromEntries(Object.entries(binaryPaths).map(([name, path]) => {
  const bytes = readFileSync(path);
  return [name, {
    path,
    bytes: bytes.length,
    sha256: createOuterHash('sha256').update(bytes).digest('hex'),
  }];
}));
const expectedServedShell = Object.fromEntries(Object.entries(shellPaths).map(([name, path]) => {
  const bytes = readFileSync(path);
  return [name, {
    path,
    bytes: bytes.length,
    sha256: createOuterHash('sha256').update(bytes).digest('hex'),
  }];
}));

async function captureServedShell(page, expected) {
  const served = await page.evaluate(async () => {
    const paths = {index: '/index.html', windowed: '/windowed.html', boot: '/boot-windowed.js',
      fileBridge: '/file-bridge.js', preinit: '/wgpu-preinit-worker.js'};
    const result = {};
    for (const [name, path] of Object.entries(paths)) {
      const response = await fetch(path, {cache: 'no-store'});
      if (!response.ok) throw new Error(`served shell fetch failed: ${path} status=${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      result[name] = {
        url: new URL(path, location.href).href,
        bytes: bytes.length,
        sha256: Array.from(new Uint8Array(digest),
          (value) => value.toString(16).padStart(2, '0')).join(''),
      };
    }
    return result;
  });
  for (const [name, local] of Object.entries(expected)) {
    if (served?.[name]?.bytes !== local.bytes || served?.[name]?.sha256 !== local.sha256) {
      throw new Error(`served shell mismatch: ${name}`);
    }
  }
  return served;
}
const sourceReceipts = Object.fromEntries(Object.entries({
  driver: driverPath,
  matrixRunner: matrixRunnerPath,
  bridge: sourcePath,
  manifest: manifestSourcePath,
}).map(([name, path]) => {
  const bytes = readFileSync(path);
  return [name, {
    path,
    bytes: bytes.length,
    sha256: createOuterHash('sha256').update(bytes).digest('hex'),
  }];
}));
const hostBlendPath = process.argv[2];
const hostBlendReceipt = existsSync(hostBlendPath) ? (() => {
  const bytes = readFileSync(hostBlendPath);
  return {
    path: hostBlendPath,
    bytes: bytes.length,
    sha256: createOuterHash('sha256').update(bytes).digest('hex'),
  };
})() : null;

if (!outDir || !outDir.startsWith('/Users/paws/blender-web/sandbox/gpu-r61/workbench-preview/runs/')) {
  throw new Error('BW_WORKBENCH_OUTDIR must name a unique gpu-r61 Workbench run directory');
}
if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(outName)) {
  throw new Error(`unsafe output name: ${outName}`);
}
if (existsSync(`${outDir}/caps/${outName}`)) {
  throw new Error(`refusing to reuse capture directory: ${outDir}/caps/${outName}`);
}

function validateProductReceipt(receipt, expected) {
  const errors = [];
  const expectedValues = expected.width * expected.height * 4;
  if (!receipt || typeof receipt !== 'object') errors.push('receipt missing');
  else {
    if (receipt.schema !== expected.schema) errors.push('schema mismatch');
    if (receipt.status !== 'OK') errors.push(`status=${receipt.status}`);
    if (receipt.engine !== 'BLENDER_WORKBENCH') errors.push(`engine=${receipt.engine}`);
    if (receipt.png !== expected.png) errors.push('guest PNG path mismatch');
    if (receipt.width !== expected.width || receipt.height !== expected.height) {
      errors.push(`receipt dimensions=${receipt.width}x${receipt.height}`);
    }
    if (receipt.channels !== 4 || receipt.bit_depth !== 8 || receipt.color_type !== 'RGBA') {
      errors.push('receipt is not 8-bit RGBA');
    }
    if (receipt.finite_values !== expectedValues || receipt.nonfinite_values !== 0) {
      errors.push('receipt contains non-finite values');
    }
    if (receipt.pre_count !== 1 || receipt.complete_count !== 1 || receipt.cancel_count !== 0) {
      errors.push('render handler counts are not exactly 1/1/0');
    }
    if (!Number.isInteger(receipt.png_size) || receipt.png_size <= 0) errors.push('empty PNG');
  }
  return { ok: errors.length === 0, errors };
}

function validateArmedReceipt(receipt, expected) {
  const errors = [];
  if (!receipt || typeof receipt !== 'object') errors.push('ARMED receipt missing');
  else {
    if (receipt.schema !== expected.schema || receipt.status !== 'ARMED') {
      errors.push('ARMED receipt identity mismatch');
    }
    if (receipt.engine !== 'BLENDER_WORKBENCH') errors.push('ARMED engine mismatch');
    if (receipt.width !== expected.width || receipt.height !== expected.height ||
        receipt.resolution_percentage !== 100) {
      errors.push('ARMED dimensions mismatch');
    }
  }
  return { ok: errors.length === 0, errors };
}

function validateProductCapture(capture, receipt, expected) {
  const errors = [];
  if (!capture || typeof capture !== 'object') errors.push('capture missing');
  else {
    if (capture.file !== expected.file) errors.push('host capture name mismatch');
    if (capture.guestPath !== expected.png) errors.push('capture guest path mismatch');
    if (capture.width !== expected.width || capture.height !== expected.height) {
      errors.push(`capture dimensions=${capture.width}x${capture.height}`);
    }
    if (capture.bitDepth !== 8 || capture.colorType !== 6) errors.push('PNG IHDR is not RGBA8');
    if (capture.byteLength !== receipt?.png_size || capture.byteLength <= 0) {
      errors.push('capture byte length mismatch');
    }
    if (!/^[0-9a-f]{64}$/.test(capture.sha256 || '')) errors.push('capture SHA-256 missing');
    if (capture.nonBlackPixels <= 0 || capture.nonBlackFraction <= 0 || capture.rgbMax <= 0) {
      errors.push('capture is black');
    }
    if (capture.finitePixels !== true) errors.push('capture contains non-finite pixels');
  }
  return { ok: errors.length === 0, errors };
}

function validatePhysicalF12(receipt) {
  return Array.isArray(receipt) && receipt.length === 1 && receipt[0].key === 'F12' &&
    receipt[0].code === 'F12' && receipt[0].isTrusted === true && receipt[0].repeat === false &&
    receipt[0].targetId === 'canvas' && receipt[0].activeId === 'canvas';
}

function evaluateProductGate(state) {
  const errors = [];
  const armedCheck = validateArmedReceipt(state.armedReceipt, state.expected);
  if (!armedCheck.ok) errors.push(...armedCheck.errors);
  if (!validatePhysicalF12(state.physicalKeyReceipt)) errors.push('physical trusted F12 receipt invalid');
  if (!String(state.sentinel || '').startsWith('OK')) errors.push('render sentinel is not OK');
  const receiptCheck = validateProductReceipt(state.receipt, state.expected);
  if (!receiptCheck.ok) errors.push(...receiptCheck.errors);
  if (state.captures.length !== 1) errors.push(`product capture count=${state.captures.length}`);
  else {
    const captureCheck = validateProductCapture(state.captures[0], state.receipt, state.expected);
    if (!captureCheck.ok) errors.push(...captureCheck.errors);
  }
  if (state.captureError) errors.push(`capture error: ${state.captureError}`);
  if (state.gpuErrorCount !== 0) errors.push(`GPU errors=${state.gpuErrorCount}`);
  if (state.pageErrorCount !== 0) errors.push(`page errors=${state.pageErrorCount}`);
  if (state.pageCrashed) errors.push('page crashed');
  if (state.pageUnresponsive) errors.push('page unresponsive');
  return { pass: errors.length === 0, errors };
}

let source = readFileSync(sourcePath, 'utf8');

function replaceOnce(needle, replacement, label) {
  const first = source.indexOf(needle);
  const last = source.lastIndexOf(needle);
  if (first < 0 || first !== last) {
    throw new Error(`r35 bridge seam drifted (${label})`);
  }
  source = source.replace(needle, replacement);
}

replaceOnce(
  "const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r35';",
  `const OUTDIR = '${outDir}';`,
  'output root',
);
replaceOnce(
  "import { writeFileSync, readFileSync, mkdirSync } from 'fs';",
  "import { writeFileSync, readFileSync, mkdirSync } from 'fs';\nimport { createHash } from 'crypto';",
  'product SHA-256 import',
);
replaceOnce("  'import bpy, os, glob',", "  'import bpy, os, glob, json',", 'Python imports');
replaceOnce(
  "  'os.environ[\"BW_DIAG\"] = \"1\"',",
  "  'os.environ.pop(\"BW_DIAG\", None)',",
  'production mode strips diagnostic readback',
);

const productPython = [
  `_bw_product_schema = ${JSON.stringify(productSchema)}`,
  `_bw_product_png = ${JSON.stringify(productPngGuest)}`,
  `_bw_product_done = ${JSON.stringify(productDoneGuest)}`,
  `_bw_product_armed = ${JSON.stringify(productArmedGuest)}`,
  '_bw_product_pre_count = 0',
  '_bw_product_complete_count = 0',
  '_bw_product_cancel_count = 0',
  '_bw_product_export_armed = False',
  'def _bw_product_write(receipt):',
  '    tmp = _bw_product_done + ".tmp"',
  '    with open(tmp, "w") as f:',
  '        json.dump(receipt, f, sort_keys=True)',
  '        f.flush()',
  '    os.replace(tmp, _bw_product_done)',
  'def _bw_product_pre(*_args):',
  '    global _bw_product_pre_count',
  '    _bw_product_pre_count += 1',
  'def _bw_product_export():',
  '    global _bw_product_export_armed',
  '    sc = bpy.context.scene',
  '    rr = None',
  '    render_result_size = None',
  '    render_result_channels = None',
  '    expected_dimensions = [int(sc.render.resolution_x * sc.render.resolution_percentage // 100), int(sc.render.resolution_y * sc.render.resolution_percentage // 100)]',
  '    scene_resolution = [int(sc.render.resolution_x), int(sc.render.resolution_y)]',
  '    try:',
  '        rr = bpy.data.images.get("Render Result")',
  '        if rr is None:',
  '            raise RuntimeError("Render Result missing")',
  '        render_result_size = [int(rr.size[0]), int(rr.size[1])]',
  '        render_result_channels = int(rr.channels)',
  '        # Workbench can expose a stale Render Result.size while the completed view/layer',
  '        # is already saveable. Match the accepted EEVEE/Cycles path: save first, then',
  '        # make the produced PNG IHDR authoritative for product dimensions.',
  '        rr.save_render(filepath=_bw_product_png, scene=sc)',
  '        with open(_bw_product_png, "rb") as f:',
  '            png_header = f.read(26)',
  '        if len(png_header) != 26 or png_header[:8] != b"\\x89PNG\\r\\n\\x1a\\n":',
  '            raise RuntimeError("Render Result export is not a PNG")',
  '        width = int.from_bytes(png_header[16:20], "big")',
  '        height = int.from_bytes(png_header[20:24], "big")',
  '        bit_depth = int(png_header[24])',
  '        png_color_type = int(png_header[25])',
  '        if [width, height] != expected_dimensions:',
  '            raise RuntimeError("exported PNG dimensions do not match effective resolution")',
  '        if bit_depth != 8 or png_color_type != 6:',
  '            raise RuntimeError("exported PNG is not RGBA8")',
  '        channels = 4',
  '        finite_values = width * height * channels',
  '        receipt = {"schema":_bw_product_schema, "status":"OK", "engine":sc.render.engine, "png":_bw_product_png, "png_size":os.path.getsize(_bw_product_png), "width":width, "height":height, "channels":channels, "bit_depth":bit_depth, "color_type":"RGBA", "finite_values":finite_values, "nonfinite_values":0, "render_result_size":render_result_size, "render_result_channels":render_result_channels, "scene_resolution":scene_resolution, "resolution_percentage":int(sc.render.resolution_percentage), "expected_dimensions":expected_dimensions, "pre_count":_bw_product_pre_count, "complete_count":_bw_product_complete_count, "cancel_count":_bw_product_cancel_count}',
  '        _bw_product_write(receipt)',
  '        open("/tmp/m6_bridge_done", "w").write("OK " + sc.render.engine)',
  '        os.write(2, ("M6_BRIDGE_DONE engine=" + sc.render.engine + "\\n").encode("utf-8"))',
  '        os.write(2, ("M6_BRIDGE_PRODUCT_DONE bytes=%d\\n" % receipt["png_size"]).encode("utf-8"))',
  '    except Exception as e:',
  '        _bw_product_write({"schema":_bw_product_schema, "status":"FAIL", "error":repr(e), "render_result_size":render_result_size, "render_result_channels":render_result_channels, "scene_resolution":scene_resolution, "resolution_percentage":int(sc.render.resolution_percentage), "expected_dimensions":expected_dimensions, "pre_count":_bw_product_pre_count, "complete_count":_bw_product_complete_count, "cancel_count":_bw_product_cancel_count})',
  '        open("/tmp/m6_bridge_done", "w").write("ERR " + repr(e))',
  '        os.write(2, ("M6_BRIDGE_FAIL " + repr(e) + "\\n").encode("utf-8"))',
  '        os.write(2, ("M6_BRIDGE_PRODUCT_FAIL " + repr(e) + "\\n").encode("utf-8"))',
  '    _bw_product_export_armed = False',
  '    return None',
  'def _bw_product_complete(*_args):',
  '    global _bw_product_complete_count, _bw_product_export_armed',
  '    _bw_product_complete_count += 1',
  '    if not _bw_product_export_armed:',
  '        _bw_product_export_armed = True',
  '        bpy.app.timers.register(_bw_product_export, first_interval=0.0)',
  'def _bw_product_cancel(*_args):',
  '    global _bw_product_cancel_count',
  '    _bw_product_cancel_count += 1',
  '    _bw_product_write({"schema":_bw_product_schema, "status":"FAIL", "error":"render cancelled", "pre_count":_bw_product_pre_count, "complete_count":_bw_product_complete_count, "cancel_count":_bw_product_cancel_count})',
  '    open("/tmp/m6_bridge_done", "w").write("ERR render cancelled")',
  '    os.write(2, b"M6_BRIDGE_FAIL render cancelled\\n")',
  'bpy.app.handlers.render_pre.append(_bw_product_pre)',
  'bpy.app.handlers.render_complete.append(_bw_product_complete)',
  'bpy.app.handlers.render_cancel.append(_bw_product_cancel)',
];
const productPythonSource = productPython.map((line) => `  ${JSON.stringify(line)},`).join('\n');
replaceOnce(
  "  'bpy.context.preferences.view.show_splash = False',",
  `  'bpy.context.preferences.view.show_splash = False',\n${productPythonSource}`,
  'product render-complete handler',
);

const engineLine = '  \'        sc.render.engine = "\' + ENGINE + \'"\',';
replaceOnce(
  engineLine,
  [
    engineLine,
    "  '        _bw_setup_scenes = 0',",
    "  '        if sc.render.engine == \"BLENDER_WORKBENCH\":',",
    "  '            for _scene in bpy.data.scenes:',",
    "  '                if _scene.get(\"Workbench_skip_setup\", False):',",
    "  '                    continue',",
    "  '                _scene.display.shading.light = \"STUDIO\"',",
    "  '                _scene.display.shading.color_type = \"TEXTURE\"',",
    "  '                _scene.render.hair_type = \"STRIP\"',",
    "  '                _bw_setup_scenes += 1',",
    "  '            os.write(2, (\"M6_BRIDGE_SETUP workbench scenes=%d\\\\n\" % _bw_setup_scenes).encode(\"utf-8\"))',",
    "  '        _bw_color = {\"display\": sc.display_settings.display_device, \"view\": sc.view_settings.view_transform, \"look\": sc.view_settings.look, \"exposure\": sc.view_settings.exposure, \"gamma\": sc.view_settings.gamma}',",
    "  '        os.write(2, (\"M6_BRIDGE_COLOR \" + json.dumps(_bw_color, sort_keys=True) + \"\\\\n\").encode(\"utf-8\"))',",
    "  '        sc.render.image_settings.color_mode = \"RGBA\"',",
    "  '        sc.render.image_settings.color_depth = \"8\"',",
  ].join('\n'),
  'Workbench setup',
);
replaceOnce(
  [
    "  '        bpy.ops.render.render(write_still=True)',",
    "  '        open(\"/tmp/m6_bridge_done\", \"w\").write(\"OK \" + sc.render.engine)',",
    "  '        os.write(2, (\"M6_BRIDGE_DONE engine=\" + sc.render.engine + \"\\\\n\").encode(\"utf-8\"))',",
  ].join('\n'),
  [
    "  '        _bw_armed_receipt = {\"schema\":_bw_product_schema, \"status\":\"ARMED\", \"engine\":sc.render.engine, \"width\":sc.render.resolution_x, \"height\":sc.render.resolution_y, \"resolution_percentage\":sc.render.resolution_percentage}',",
    "  '        _bw_armed_tmp = _bw_product_armed + \".tmp\"',",
    "  '        with open(_bw_armed_tmp, \"w\") as _bw_armed_file:',",
    "  '            json.dump(_bw_armed_receipt, _bw_armed_file, sort_keys=True)',",
    "  '            _bw_armed_file.flush()',",
    "  '        os.replace(_bw_armed_tmp, _bw_product_armed)',",
    "  '        os.write(2, (\"M6_BRIDGE_ARMED engine=\" + sc.render.engine + \"\\\\n\").encode(\"utf-8\"))',",
  ].join('\n'),
  'arm WM render job without synchronous operator',
);

replaceOnce(
  "const BLEND_PATH = '/projects/' + OPFS_NAME;",
  [
    "const BLEND_PATH = '/projects/' + OPFS_NAME;",
    `const SHIPPING_BINARY = ${JSON.stringify(shippingBinary)};`,
    `const EXPECTED_SERVED_SHELL = ${JSON.stringify(expectedServedShell)};`,
    `const HOST_BLEND_RECEIPT = ${JSON.stringify(hostBlendReceipt)};`,
    `const SOURCE_RECEIPTS = ${JSON.stringify(sourceReceipts)};`,
    `const PRODUCT_SCHEMA = ${JSON.stringify(productSchema)};`,
    `const PRODUCT_PNG_GUEST = ${JSON.stringify(productPngGuest)};`,
    `const PRODUCT_DONE_GUEST = ${JSON.stringify(productDoneGuest)};`,
    `const PRODUCT_ARMED_GUEST = ${JSON.stringify(productArmedGuest)};`,
    `const PRODUCT_CAPTURE_FILE = ${JSON.stringify(productCaptureFile)};`,
    validateProductReceipt.toString(),
    validateArmedReceipt.toString(),
    validateProductCapture.toString(),
    validatePhysicalF12.toString(),
    evaluateProductGate.toString(),
    captureServedShell.toString(),
  ].join('\n'),
  'product JS contract',
);
replaceOnce(
  "await page.goto(url, { waitUntil: 'domcontentloaded' });",
  "await page.goto(url, { waitUntil: 'domcontentloaded' });\nconst servedShell = await captureServedShell(page, EXPECTED_SERVED_SHELL);",
  'served shell capture',
);
replaceOnce(
  'const marks = [], gpuErrors = [], kicks = [], dones = [];',
  'const marks = [], gpuErrors = [], pageErrors = [], kicks = [], dones = [];\nlet productArmedReceipt = null;\nlet physicalKeyReceipt = null;',
  'page error collection',
);
replaceOnce(
  'const page = await ctx.newPage();',
  `const page = await ctx.newPage();
await page.addInitScript(() => {
  window.__bwWorkbenchF12KeyEvents = [];
  addEventListener('keydown', (event) => {
    if (event.key !== 'F12') return;
    window.__bwWorkbenchF12KeyEvents.push({
      key: event.key,
      code: event.code,
      isTrusted: event.isTrusted,
      repeat: event.repeat,
      targetId: event.target?.id || null,
      activeId: document.activeElement?.id || null,
      at: performance.now(),
    });
  }, true);
});`,
  'browser-side trusted F12 receipt',
);
replaceOnce(
  "page.on('console', (m) => {",
  "page.on('pageerror', (error) => { pageErrors.push(String(error)); });\npage.on('console', (m) => {",
  'page error listener',
);
replaceOnce(
  'let doneTxt = null;\nconst caps = [];',
  'let doneTxt = null;\nconst caps = [];\nconst productCaptures = [];\nlet productReceipt = null;\nlet productCaptureError = null;\nlet productGate = null;',
  'product capture state',
);

replaceOnce(
  '    // WGPUTexture::read and its BW_DIAG kick happen inside bpy.ops.render.render,\n    // before the sentinel is written. If the render has returned with no kick and',
  '    // Legacy diagnostic readback, when enabled in retained builds, is kicked before\n    // the sentinel is written. If the render has returned with no kick and',
  'remove synchronous operator wording',
);
replaceOnce(
  'try {\n  const tR2 = Date.now();',
  `try {
  const armedDeadline = Date.now() + Math.min(SETTLE_MS, 120000);
  while (Date.now() < armedDeadline && !marks.some((mark) => mark.includes('M6_BRIDGE_ARMED'))) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!marks.some((mark) => mark.includes('M6_BRIDGE_ARMED'))) {
    throw new Error('Workbench render setup did not arm');
  }
  productArmedReceipt = await page.evaluate((path) => {
    const text = window.__bwModule.FS.readFile(path, { encoding: 'utf8' });
    return JSON.parse(text);
  }, PRODUCT_ARMED_GUEST);
  if (productArmedReceipt.schema !== PRODUCT_SCHEMA || productArmedReceipt.status !== 'ARMED' ||
      productArmedReceipt.engine !== ENGINE || productArmedReceipt.width !== RESW ||
      productArmedReceipt.height !== RESH || productArmedReceipt.resolution_percentage !== 100) {
    throw new Error('invalid Workbench ARMED receipt: ' + JSON.stringify(productArmedReceipt));
  }
  await page.bringToFront();
  await page.keyboard.press('F12');
  await page.waitForFunction(() => window.__bwWorkbenchF12KeyEvents?.length === 1, undefined, { timeout: 5000 });
  physicalKeyReceipt = await page.evaluate(() => window.__bwWorkbenchF12KeyEvents);
  if (!validatePhysicalF12(physicalKeyReceipt)) {
    throw new Error('invalid physical F12 receipt: ' + JSON.stringify(physicalKeyReceipt));
  }
  log('physical trusted F12 dispatched exactly once');

  const tR2 = Date.now();`,
  'trusted WM render entry',
);

const productPull = `
  try {
    let receiptText = null;
    const productDeadline = Date.now() + 30000;
    while (Date.now() < productDeadline && !pageCrashed && !pageUnresponsive) {
      receiptText = await safeEval((path) => {
        try { return window.__bwModule.FS.readFile(path, { encoding: 'utf8' }); }
        catch (_) { return null; }
      }, PRODUCT_DONE_GUEST, 'product-receipt');
      if (receiptText) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (!receiptText) throw new Error('product completion receipt missing');
    productReceipt = JSON.parse(receiptText);
    const expected = {
      schema: PRODUCT_SCHEMA,
      png: PRODUCT_PNG_GUEST,
      file: PRODUCT_CAPTURE_FILE,
      width: RESW,
      height: RESH,
    };
    const receiptCheck = validateProductReceipt(productReceipt, expected);
    if (!receiptCheck.ok) throw new Error('invalid product receipt: ' + receiptCheck.errors.join('; '));
    const captured = await safeEval(async (path) => {
      const bytes = window.__bwModule.FS.readFile(path);
      const signature = [137, 80, 78, 71, 13, 10, 26, 10];
      if (bytes.length < 33 || !signature.every((value, index) => bytes[index] === value)) {
        throw new Error('invalid PNG signature');
      }
      const header = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const blob = new Blob([bytes], { type: 'image/png' });
      const bitmap = await createImageBitmap(blob);
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(bitmap, 0, 0);
      const pixels = context.getImageData(0, 0, bitmap.width, bitmap.height).data;
      let nonBlackPixels = 0;
      let rgbMax = 0;
      let finitePixels = true;
      for (let offset = 0; offset < pixels.length; offset += 4) {
        finitePixels = finitePixels && Number.isFinite(pixels[offset]) &&
          Number.isFinite(pixels[offset + 1]) && Number.isFinite(pixels[offset + 2]) &&
          Number.isFinite(pixels[offset + 3]);
        const pixelMax = Math.max(pixels[offset], pixels[offset + 1], pixels[offset + 2]);
        if (pixelMax !== 0) nonBlackPixels += 1;
        rgbMax = Math.max(rgbMax, pixelMax);
      }
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
      }
      return {
        width: bitmap.width,
        height: bitmap.height,
        bitDepth: bytes[24],
        colorType: bytes[25],
        ihdrWidth: header.getUint32(16, false),
        ihdrHeight: header.getUint32(20, false),
        byteLength: bytes.length,
        nonBlackPixels,
        nonBlackFraction: nonBlackPixels / (bitmap.width * bitmap.height),
        rgbMax,
        finitePixels,
        b64: btoa(binary),
      };
    }, PRODUCT_PNG_GUEST, 'product-png');
    if (!captured?.b64) throw new Error('product PNG read failed');
    const renderBytes = Buffer.from(captured.b64, 'base64');
    delete captured.b64;
    const capture = {
      file: PRODUCT_CAPTURE_FILE,
      guestPath: PRODUCT_PNG_GUEST,
      sha256: createHash('sha256').update(renderBytes).digest('hex'),
      ...captured,
    };
    writeFileSync(CAPDIR + '/' + PRODUCT_CAPTURE_FILE, renderBytes);
    const captureCheck = validateProductCapture(capture, productReceipt, expected);
    if (capture.ihdrWidth !== capture.width || capture.ihdrHeight !== capture.height) {
      captureCheck.ok = false;
      captureCheck.errors.push('decoded and IHDR dimensions differ');
    }
    if (!captureCheck.ok) throw new Error('invalid product PNG: ' + captureCheck.errors.join('; '));
    productCaptures.push(capture);
    log('product Render Result captured: ' + JSON.stringify(capture));
  } catch (error) {
    productCaptureError = error.stack || error.message || String(error);
    log('product capture rejected: ' + productCaptureError);
  }
`;
replaceOnce(
  "  log(`render sentinel: ${doneTxt ? JSON.stringify(doneTxt) : (pageCrashed ? '(page crashed)' :\n    pageUnresponsive ? '(page unresponsive at ' + pageUnresponsiveAt + ')' : '(timeout)')}`);",
  "  log(`render sentinel: ${doneTxt ? JSON.stringify(doneTxt) : (pageCrashed ? '(page crashed)' :\n    pageUnresponsive ? '(page unresponsive at ' + pageUnresponsiveAt + ')' : '(timeout)')}`);" + productPull,
  'product pull after sentinel',
);
replaceOnce(
  'while (Date.now() - tD < 60000 && !pageCrashed && !pageUnresponsive) {',
  'while (productCaptures.length === 0 && Date.now() - tD < 60000 && !pageCrashed && !pageUnresponsive) {',
  'legacy diagnostic fallback',
);
replaceOnce(
  '  if (!pageUnresponsive) {',
  '  if (!pageUnresponsive && productCaptures.length === 0) {',
  'legacy PNG fallback',
);
replaceOnce(
  "  const manifest = { mode: 'boot', hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],\n                     opfs: seedRes, sentinel: doneTxt, pageCrashed, pageUnresponsive,\n                     pageUnresponsiveAt, gpuErrorCount: gpuErrors.length,\n                     kicks: kicks.length, dones: dones.length, caps, marks,\n                     doneLines: dones.slice(-8), gpuErrorSample: gpuErrors.slice(0, 8) };",
  "  productGate = evaluateProductGate({\n    armedReceipt: productArmedReceipt,\n    physicalKeyReceipt,\n    captures: productCaptures,\n    receipt: productReceipt,\n    sentinel: doneTxt,\n    captureError: productCaptureError,\n    gpuErrorCount: gpuErrors.length,\n    pageErrorCount: pageErrors.length,\n    pageCrashed,\n    pageUnresponsive,\n    expected: { schema: PRODUCT_SCHEMA, png: PRODUCT_PNG_GUEST, file: PRODUCT_CAPTURE_FILE, width: RESW, height: RESH },\n  });\n  const manifest = { schema: 'blender-web.workbench-product.v2', mode: 'boot', hostBlend: HOST_BLEND, engine: ENGINE, res: [RESW, RESH],\n                     opfs: seedRes, sentinel: doneTxt, pageCrashed, pageUnresponsive,\n                     pageUnresponsiveAt, gpuErrorCount: gpuErrors.length,\n                     pageErrorCount: pageErrors.length, pageErrorSample: pageErrors.slice(0, 8),\n                     invocation: { method: 'page.keyboard.press(F12)', count: physicalKeyReceipt?.length || 0, physicalTrustedF12: validatePhysicalF12(physicalKeyReceipt), keyReceipt: physicalKeyReceipt },\n                     inputs: { shippingBinary: SHIPPING_BINARY },\n                     productArmedReceipt, physicalKeyReceipt, productReceipt, productCaptureError, productCaptures, productGate,\n                     kicks: kicks.length, dones: dones.length, caps, marks,\n                     doneLines: dones.slice(-8), gpuErrorSample: gpuErrors.slice(0, 8) };",
  'product manifest',
);
replaceOnce(
  'inputs: { shippingBinary: SHIPPING_BINARY }',
  'inputs: { blend: HOST_BLEND_RECEIPT, shippingBinary: SHIPPING_BINARY }',
  'host blend receipt',
);
replaceOnce(
  'inputs: { blend: HOST_BLEND_RECEIPT, shippingBinary: SHIPPING_BINARY }',
  'sources: SOURCE_RECEIPTS, inputs: { blend: HOST_BLEND_RECEIPT, shippingBinary: SHIPPING_BINARY, servedShell, expectedServedShell: EXPECTED_SERVED_SHELL }',
  'Workbench source receipts',
);
replaceOnce(
  'process.exit(0);',
  'process.exit(productGate?.pass ? 0 : 5);',
  'product gate exit status',
);

if (process.env.BW_WORKBENCH_SELF_CHECK === '1') {
  const engineSource = readFileSync(
    '/Users/paws/blender-web/upstream/source/blender/draw/engines/workbench/workbench_engine.cc',
    'utf8',
  );
  const declarationStart = source.indexOf('const PYEXPR = [');
  const declarationEnd = source.indexOf("].join('\\n');", declarationStart);
  const declaration = source.slice(declarationStart, declarationEnd + "].join('\\n');".length);
  const pyexpr = Function('ENGINE', 'RESW', 'RESH', `${declaration}; return PYEXPR;`)(
    'BLENDER_WORKBENCH', 128, 128,
  );
  const compile = spawnSync(
    'python3',
    ['-c', 'import base64,sys; compile(base64.b64decode(sys.argv[1]), "<workbench-pyexpr>", "exec")',
     Buffer.from(pyexpr).toString('base64')],
    { encoding: 'utf8' },
  );
  const transformedCompile = spawnSync(process.execPath, ['--input-type=module', '--check', '-'], {
    input: source,
    encoding: 'utf8',
  });
  const expected = {
    schema: productSchema, png: productPngGuest, file: productCaptureFile, width: 128, height: 128,
  };
  const receipt = {
    schema: productSchema, status: 'OK', engine: 'BLENDER_WORKBENCH', png: productPngGuest,
    png_size: 1024, width: 128, height: 128, channels: 4, bit_depth: 8, color_type: 'RGBA',
    finite_values: 128 * 128 * 4, nonfinite_values: 0,
    pre_count: 1, complete_count: 1, cancel_count: 0,
  };
  const armedReceipt = {
    schema: productSchema, status: 'ARMED', engine: 'BLENDER_WORKBENCH',
    width: 128, height: 128, resolution_percentage: 100,
  };
  const capture = {
    file: productCaptureFile, guestPath: productPngGuest, width: 128, height: 128,
    bitDepth: 8, colorType: 6, ihdrWidth: 128, ihdrHeight: 128, byteLength: 1024,
    sha256: '0'.repeat(64),
    nonBlackPixels: 100, nonBlackFraction: 100 / (128 * 128), rgbMax: 255, finitePixels: true,
  };
  const physicalKeyReceipt = [{
    key: 'F12', code: 'F12', isTrusted: true, repeat: false,
    targetId: 'canvas', activeId: 'canvas',
  }];
  const positiveGate = evaluateProductGate({
    armedReceipt, physicalKeyReceipt, captures: [capture], receipt, sentinel: 'OK BLENDER_WORKBENCH',
    captureError: null, gpuErrorCount: 0, pageErrorCount: 0,
    pageCrashed: false, pageUnresponsive: false, expected,
  });
  const negativeGate = evaluateProductGate({
    armedReceipt, physicalKeyReceipt: [],
    captures: [{ ...capture, nonBlackPixels: 0, nonBlackFraction: 0, rgbMax: 0 }],
    receipt, sentinel: 'OK BLENDER_WORKBENCH', captureError: null, gpuErrorCount: 1, pageErrorCount: 0,
    pageCrashed: false, pageUnresponsive: false, expected,
  });
  const checks = {
    isolatedOutput: source.includes(`const OUTDIR = '${outDir}';`) &&
      !source.includes("const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r35';"),
    exactSetup: source.includes('_scene.display.shading.light = "STUDIO"') &&
      source.includes('_scene.display.shading.color_type = "TEXTURE"') &&
      source.includes('_scene.render.hair_type = "STRIP"') &&
      source.includes('Workbench_skip_setup'),
    setupReceipt: source.includes('M6_BRIDGE_SETUP workbench scenes=%d'),
    colorReceipt: source.includes('M6_BRIDGE_COLOR ') && source.includes('view_transform'),
    productionMode: source.includes('os.environ.pop("BW_DIAG", None)') &&
      !source.includes('os.environ["BW_DIAG"] = "1"'),
    atomicReceipt: pyexpr.includes('os.replace(tmp, _bw_product_done)') &&
      pyexpr.includes('bpy.app.handlers.render_complete.append(_bw_product_complete)'),
    rgba8Finite: pyexpr.includes('sc.render.image_settings.color_mode = "RGBA"') &&
      pyexpr.includes('sc.render.image_settings.color_depth = "8"') &&
      pyexpr.includes('png_color_type != 6') &&
      pyexpr.includes('finite_values = width * height * channels'),
    effectiveDimensions: pyexpr.includes('sc.render.resolution_percentage // 100') &&
      pyexpr.includes('"expected_dimensions":expected_dimensions') &&
      pyexpr.includes('"render_result_size":render_result_size'),
    timingSafeExport: pyexpr.indexOf('rr.save_render') < pyexpr.indexOf('width = int.from_bytes') &&
      !pyexpr.includes('if [width, height] != [sc.render.resolution_x, sc.render.resolution_y]'),
    uniqueGuestPaths: pyexpr.includes(productPngGuest) && pyexpr.includes(productDoneGuest),
    wmRenderJob: !pyexpr.includes('bpy.ops.render.render') &&
      (source.match(/page\.keyboard\.press\('F12'\)/g) || []).length === 1 &&
      source.includes('physical trusted F12 dispatched exactly once') &&
      pyexpr.includes('M6_BRIDGE_ARMED engine=') && pyexpr.includes(productArmedGuest),
    engineAsyncContinuation: engineSource.includes('GPU_texture_read_async(dtxl->color') &&
      engineSource.includes('GPU_texture_read_async(dtxl->depth') &&
      engineSource.includes('DRW_render_to_image_step(') &&
      engineSource.includes('/*render_step*/ &workbench_render_step') &&
      engineSource.includes('/*render_step_cancel*/ &workbench_render_cancel'),
    enginePassParity: engineSource.includes('if (combined == nullptr && depth == nullptr)') &&
      engineSource.includes('if (combined != nullptr) {') &&
      engineSource.includes('if (depth != nullptr) {'),
    engineBorderOrientation: engineSource.includes(
      'const int source_row = rect.ymin + row;',
    ) && !engineSource.includes('source_height - 1 - (rect.ymin + row)') &&
      engineSource.includes('rect.xmin') && engineSource.includes('rect.xmax > source_width'),
    engineNativeSync: engineSource.includes(
      'DRW_render_to_image(engine, depsgraph, workbench_render_to_image',
    ),
    productManifest: source.includes('productCaptures, productGate') &&
      source.includes('physicalTrustedF12: validatePhysicalF12(physicalKeyReceipt)') &&
      source.includes('shippingBinary: SHIPPING_BINARY') && source.includes('sources: SOURCE_RECEIPTS') &&
      source.includes('expectedServedShell: EXPECTED_SERVED_SHELL'),
    driverExitGate: source.includes('process.exit(productGate?.pass ? 0 : 5);'),
    positiveGate: positiveGate.pass,
    negativeGate: !negativeGate.pass && negativeGate.errors.some((error) => error.includes('black')) &&
      negativeGate.errors.some((error) => error.includes('GPU errors')) &&
      negativeGate.errors.some((error) => error.includes('physical trusted F12')),
    pyexprCompile: compile.status === 0,
    transformedSourceCompile: transformedCompile.status === 0,
  };
  console.log(JSON.stringify(checks));
  if (transformedCompile.status !== 0) {
    console.error(transformedCompile.stderr || transformedCompile.stdout);
  }
  if (Object.values(checks).some((value) => !value)) {
    process.exit(1);
  }
  if (process.env.BW_WORKBENCH_PRINT_PYEXPR === '1') {
    console.log(`PYEXPR_BASE64=${Buffer.from(pyexpr).toString('base64')}`);
  }
  process.exit(0);
}

await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
