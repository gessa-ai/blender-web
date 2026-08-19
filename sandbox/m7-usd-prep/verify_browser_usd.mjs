// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Real browser/Wasm OpenUSD acceptance. Boots the frozen development artifact,
// authors a Blender mesh, exports ASCII USD through bpy.ops.wm.usd_export,
// deletes the source, imports the emitted bytes, and checks geometry values.

import {createRequire} from 'module';
import {createHash} from 'crypto';
import {
  existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync,
  writeFileSync,
} from 'fs';
import {fileURLToPath} from 'url';

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const {chromium} = require('playwright');

const BASE = process.env.BW_BASE || 'http://127.0.0.1:8165';
const ROOT = '/Users/paws/blender-web';
const BIN = `${ROOT}/build-wasm-windowed-opt/bin`;
const label = process.argv[2] || '';
if (!/^[a-z0-9][a-z0-9._-]{0,79}$/.test(label)) {
  throw new Error('required safe receipt label: /^[a-z0-9][a-z0-9._-]{0,79}$/');
}
const OUT_ROOT = `${ROOT}/sandbox/m7-usd-prep/browser-roundtrip`;
const OUT_DIR = `${OUT_ROOT}/${label}`;
const OUT = `${OUT_DIR}/receipt.json`;
const SELECTOR = `${OUT_DIR}/selector.json`;
const FREEZE = '/Users/paws/blender-web-final-source-freeze/receipt.json';
const SELECTOR_SCHEMA = 'blender-web.m7-usd-selector.v1';
mkdirSync(OUT_ROOT, {recursive: true});
if (lstatSync(OUT_ROOT).isSymbolicLink() || realpathSync(OUT_ROOT) !== OUT_ROOT) {
  throw new Error(`browser receipt root is indirect: ${OUT_ROOT}`);
}
for (const entry of readdirSync(OUT_ROOT, {withFileTypes: true})) {
  const path = `${OUT_ROOT}/${entry.name}`;
  if (entry.isSymbolicLink()) throw new Error(`indirect browser receipt entry: ${path}`);
  if (entry.isDirectory() && existsSync(`${path}/selector.json`)) {
    throw new Error(`an immutable browser USD selector already exists: ${path}/selector.json`);
  }
}
mkdirSync(OUT_DIR);

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function fileIdentity(path, relativePath = null) {
  const info = lstatSync(path);
  if (info.isSymbolicLink() || !info.isFile() || realpathSync(path) !== path) {
    throw new Error(`receipt input is not a canonical regular file: ${path}`);
  }
  return {path: relativePath || path, bytes: info.size, sha256: sha256(path)};
}

const artifactPaths = {
  js: `${BIN}/blender_browser.js`, wasm: `${BIN}/blender_browser.wasm`,
  data: `${BIN}/blender_browser.data`,
};
const artifacts = Object.fromEntries(Object.entries(artifactPaths).map(([key, path]) =>
  [key, fileIdentity(path, path.slice(ROOT.length + 1))]));
const sourceFreeze = fileIdentity(FREEZE);
const driverIdentity = fileIdentity(fileURLToPath(import.meta.url),
  'sandbox/m7-usd-prep/verify_browser_usd.mjs');

const pyexpr = [
  'import bpy, json, hashlib, os',
  'p="/tmp/bw_m7_triangle.usda"',
  '[bpy.data.objects.remove(o, do_unlink=True) for o in list(bpy.data.objects)]',
  'm=bpy.data.meshes.new("BW_M7_TriangleMesh")',
  'm.from_pydata([(0.0,0.0,0.0),(2.0,0.0,0.0),(0.0,3.0,0.0)], [], [(0,1,2)])',
  'm.update()',
  'o=bpy.data.objects.new("BW_M7_Triangle",m)',
  'bpy.context.collection.objects.link(o)',
  'bpy.context.view_layer.objects.active=o',
  'o.select_set(True)',
  'ex=sorted(bpy.ops.wm.usd_export(filepath=p, selected_objects_only=True, export_materials=False))',
  'with open(p,"rb") as f:',
  '    raw=f.read()',
  '[bpy.data.objects.remove(x, do_unlink=True) for x in list(bpy.data.objects)]',
  'im=sorted(bpy.ops.wm.usd_import(filepath=p))',
  'meshes=[x for x in bpy.context.scene.objects if x.type=="MESH"]',
  'coords=sorted([[round(c,5) for c in v.co] for x in meshes for v in x.data.vertices])',
  'polys=[len(poly.vertices) for x in meshes for poly in x.data.polygons]',
  'r={"build_option_usd":bool(bpy.app.build_options.usd),"export":ex,"import":im,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"magic":raw[:5].decode("ascii","replace"),"mesh_count":len(meshes),"coords":coords,"polygon_sizes":polys}',
  'r["ok"]=(r["build_option_usd"] and ex==["FINISHED"] and im==["FINISHED"] and len(raw)>100 and r["magic"]=="#usda" and len(meshes)==1 and coords==[[0.0,0.0,0.0],[0.0,3.0,0.0],[2.0,0.0,0.0]] and polys==[3])',
  'os.write(2,("M7_USD_ROUNDTRIP "+json.dumps(r,sort_keys=True)+"\\n").encode())',
].join('\n');

const url = `${BASE}/windowed.html?gate=1280x720&pyexpr=${encodeURIComponent(pyexpr)}`;
const browser = await chromium.launch({headless: false});
const browserVersion = browser.version();
const context = await browser.newContext({viewport: {width: 1280, height: 720}, deviceScaleFactor: 1});
const page = await context.newPage();
const consoleLines = [];
const pageErrors = [];
const pageCrashes = [];
const external = [];
const badResponses = [];
const gpuErrors = [];
page.on('console', (message) => {
  const line = `[${message.type()}] ${message.text()}`;
  consoleLines.push(line);
  if (/ValidationError|GPU-ERROR|uncaptured WebGPU error/i.test(line)) gpuErrors.push(line);
});
page.on('pageerror', (error) => pageErrors.push(String(error)));
page.on('crash', () => pageCrashes.push('page crash'));
page.on('request', (request) => {
  try {
    if (new URL(request.url()).origin !== new URL(BASE).origin) external.push(request.url());
  }
  catch (_) { external.push(request.url()); }
});
page.on('response', (response) => {
  if (response.status() >= 400) badResponses.push({status: response.status(), url: response.url()});
});

let result = null;
let browserLoadedArtifacts = null;
let verdict = 'FAIL';
try {
  await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 240000});
  await page.waitForFunction(() => document.querySelector('#log')?.textContent.includes('M7_USD_ROUNDTRIP'),
                             null, {timeout: 240000});
  const log = await page.locator('#log').textContent();
  const line = log.split('\n').find((value) => value.includes('M7_USD_ROUNDTRIP')) || '';
  result = JSON.parse(line.slice(line.indexOf('M7_USD_ROUNDTRIP') + 'M7_USD_ROUNDTRIP'.length).trim());
  browserLoadedArtifacts = await page.evaluate(async (names) => {
    const rows = {};
    for (const [key, name] of Object.entries(names)) {
      const response = await fetch(`/bin/${name}`, {cache: 'no-store', redirect: 'error'});
      const bytes = new Uint8Array(await response.arrayBuffer());
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      rows[key] = {status: response.status, bytes: bytes.length,
        sha256: Array.from(digest, value => value.toString(16).padStart(2, '0')).join('')};
    }
    return rows;
  }, {js: 'blender_browser.js', wasm: 'blender_browser.wasm', data: 'blender_browser.data'});
  const loadedExact = Object.keys(artifacts).every((key) =>
    browserLoadedArtifacts?.[key]?.status === 200 &&
    browserLoadedArtifacts[key].bytes === artifacts[key].bytes &&
    browserLoadedArtifacts[key].sha256 === artifacts[key].sha256);
  verdict = result.ok && pageErrors.length === 0 && pageCrashes.length === 0 &&
    external.length === 0 && badResponses.length === 0 && gpuErrors.length === 0 && loadedExact ?
    'PASS' : 'FAIL';
}
finally {
  const terminalArtifacts = Object.fromEntries(Object.entries(artifactPaths).map(([key, path]) =>
    [key, fileIdentity(path, path.slice(ROOT.length + 1))]));
  const terminalFreeze = fileIdentity(FREEZE);
  const terminalDriver = fileIdentity(fileURLToPath(import.meta.url),
    'sandbox/m7-usd-prep/verify_browser_usd.mjs');
  if (JSON.stringify(terminalArtifacts) !== JSON.stringify(artifacts) ||
      JSON.stringify(terminalFreeze) !== JSON.stringify(sourceFreeze) ||
      JSON.stringify(terminalDriver) !== JSON.stringify(driverIdentity)) verdict = 'FAIL';
  const receipt = {
    schema: 'blender-web.m7-usd-browser.v2',
    verdict,
    label,
    createdUtc: new Date().toISOString(),
    driver: driverIdentity,
    sourceFreeze,
    browser_version: browserVersion,
    artifacts,
    browser_loaded_artifacts: browserLoadedArtifacts,
    url: `${BASE}/windowed.html?gate=1280x720&pyexpr=<operator-roundtrip>`,
    cross_origin_isolated: await page.evaluate(() => crossOriginIsolated).catch(() => false),
    result,
    page_errors: pageErrors,
    page_crashes: pageCrashes,
    external_requests: external,
    http_errors: badResponses,
    gpu_errors: gpuErrors,
    console_tail: consoleLines.slice(-80),
  };
  const receiptPayload = JSON.stringify(receipt, null, 2) + '\n';
  writeFileSync(OUT, receiptPayload, {flag: 'wx'});
  if (verdict === 'PASS') {
    const selector = {schema: SELECTOR_SCHEMA, kind: 'browser', label,
      receipt: {path: 'receipt.json', bytes: Buffer.byteLength(receiptPayload),
        sha256: createHash('sha256').update(receiptPayload).digest('hex')}};
    writeFileSync(SELECTOR, JSON.stringify(selector, null, 2) + '\n', {flag: 'wx'});
  }
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
  console.log(`M7_USD_BROWSER_${verdict} ${OUT}`);
  if (verdict !== 'PASS') process.exitCode = 1;
}
