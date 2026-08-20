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
import {
  basename, delimiter, dirname, isAbsolute, join, relative, resolve,
} from 'path';
import {fileURLToPath} from 'url';

const DRIVER_PATH = fileURLToPath(import.meta.url);
const HERE = dirname(DRIVER_PATH);
const ROOT = resolve(HERE, '..', '..');
const BIN = resolve(ROOT, process.env.BLENDER_WEB_BIN || 'build-wasm-windowed-opt/bin');
const DEFAULT_OUT_ROOT = join(HERE, 'browser-roundtrip');
const LOCAL_MODULE_ROOTS = Object.freeze([
  join(ROOT, '.m4-node/node_modules'),
  join(ROOT, 'node_modules'),
]);
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  ...LOCAL_MODULE_ROOTS,
]
  .filter(Boolean)
  .flatMap((entry) => entry.split(delimiter))
  .filter(Boolean)
  .map((entry) => resolve(entry)))]);
const NODE_VERSION = 'v22.16.0';
const PLAYWRIGHT_VERSION = '1.61.1';
const LABEL_RE = /^[a-z0-9][a-z0-9._-]{0,79}$/;
const SELECTOR_SCHEMA = 'blender-web.m7-usd-selector.v1';
const BROWSER_ARGS = Object.freeze([
  '--enable-unsafe-webgpu',
  ...(process.platform === 'darwin' ? ['--use-angle=metal'] : []),
]);

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

function nextArgument(argv, index, name) {
  if (index + 1 >= argv.length || argv[index + 1].startsWith('--')) {
    throw new Error(`${name} requires a value`);
  }
  return argv[index + 1];
}

function parseArgs(argv, environment = process.env) {
  const options = {
    base: environment.BW_BASE || 'http://127.0.0.1:8165',
    label: null,
    outRoot: DEFAULT_OUT_ROOT,
    selfcheck: false,
    sourceFreeze: environment.BW_SOURCE_FREEZE || null,
    timeoutMs: 240000,
  };
  const positional = [];
  for (let index = 0; index < argv.length; index++) {
    const argument = argv[index];
    if (argument === '--selfcheck') options.selfcheck = true;
    else if (argument === '--label') options.label = nextArgument(argv, index++, argument);
    else if (argument === '--source-freeze') {
      options.sourceFreeze = nextArgument(argv, index++, argument);
    }
    else if (argument === '--out-root') {
      options.outRoot = resolve(ROOT, nextArgument(argv, index++, argument));
    }
    else if (argument === '--base') options.base = nextArgument(argv, index++, argument);
    else if (argument === '--timeout-ms') {
      options.timeoutMs = Number(nextArgument(argv, index++, argument));
    }
    else if (argument.startsWith('--')) throw new Error(`unknown argument: ${argument}`);
    else positional.push(argument);
  }
  if (positional.length > 1 || (positional.length === 1 && options.label !== null)) {
    throw new Error('provide the receipt label once, either positionally or with --label');
  }
  if (positional.length === 1) options.label = positional[0];
  if (!options.selfcheck) {
    if (!LABEL_RE.test(options.label || '')) throw new Error('a safe immutable label is required');
    if (!options.sourceFreeze) throw new Error('--source-freeze (or BW_SOURCE_FREEZE) is required');
  }
  if (options.label !== null && !LABEL_RE.test(options.label)) {
    throw new Error('required safe receipt label: /^[a-z0-9][a-z0-9._-]{0,79}$/');
  }
  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs < 30000) {
    throw new Error('--timeout-ms must be at least 30000');
  }
  const base = new URL(options.base);
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(base.hostname) ||
      base.username || base.password || (base.pathname !== '/' && base.pathname !== '')) {
    throw new Error(`--base must be an uncredentialed loopback HTTP origin: ${options.base}`);
  }
  options.base = base.origin;
  if (options.sourceFreeze) options.sourceFreeze = resolve(ROOT, options.sourceFreeze);
  return options;
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function fileIdentity(path, receiptPath = null) {
  const absolute = resolve(path);
  const info = lstatSync(absolute);
  if (info.isSymbolicLink() || !info.isFile() || realpathSync(absolute) !== absolute) {
    throw new Error(`receipt input is not a canonical regular file: ${absolute}`);
  }
  return {path: receiptPath || absolute, bytes: info.size, sha256: sha256(absolute)};
}

function repositoryIdentity(path) {
  const absolute = resolve(path);
  const rel = relative(ROOT, absolute);
  if (!rel || isAbsolute(rel) || rel.split(/[\\/]/)[0] === '..') {
    throw new Error(`receipt input is outside the repository: ${absolute}`);
  }
  return fileIdentity(absolute, rel);
}

function resolvePlaywright(
  roots = MODULE_ROOTS,
  load = (root) => {
    const require = createRequire(join(root, 'package.json'));
    return {
      chromium: require('playwright').chromium,
      version: require('playwright/package.json').version,
    };
  },
) {
  const errors = [];
  for (const root of roots) {
    try {
      const loaded = load(root);
      if (!loaded?.chromium) throw new Error('playwright export lacks chromium');
      if (loaded.version !== PLAYWRIGHT_VERSION) {
        throw new Error(`playwright version ${loaded.version || 'unknown'} != ${PLAYWRIGHT_VERSION}`);
      }
      return {chromium: loaded.chromium, root, version: loaded.version};
    }
    catch (error) {
      errors.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve pinned Playwright; set BW_NODE_MODULES\n${errors.join('\n')}`);
}

function isRepositoryDescendant(path) {
  const rel = relative(ROOT, resolve(path));
  return rel !== '' && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== '..';
}

function receiptDirectory(outRoot, label) {
  const root = resolve(outRoot);
  if (!isRepositoryDescendant(root)) {
    throw new Error(`output root must be inside the repository: ${root}`);
  }
  if (!LABEL_RE.test(label)) throw new Error(`unsafe receipt label: ${label}`);
  const output = resolve(root, label);
  if (dirname(output) !== root || basename(output) !== label) {
    throw new Error(`refusing unsafe receipt directory: ${output}`);
  }
  return output;
}

function reserveReceiptDirectory(outRoot, outDir) {
  mkdirSync(outRoot, {recursive: true});
  if (lstatSync(outRoot).isSymbolicLink() || realpathSync(outRoot) !== outRoot) {
    throw new Error(`browser receipt root is indirect: ${outRoot}`);
  }
  for (const entry of readdirSync(outRoot, {withFileTypes: true})) {
    const path = join(outRoot, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`indirect browser receipt entry: ${path}`);
    if (entry.isDirectory() && existsSync(join(path, 'selector.json'))) {
      throw new Error(`an immutable browser USD selector already exists: ${path}/selector.json`);
    }
  }
  mkdirSync(outDir);
}

function assertSelfcheck(condition, message) {
  if (!condition) throw new Error(`selfcheck: ${message}`);
}

function runSelfcheck() {
  let checks = 0;
  const check = (condition, message) => {
    assertSelfcheck(condition, message);
    checks++;
  };
  check(existsSync(join(ROOT, 'GOAL.md')), 'repository root is not derived from the driver');
  check(process.version === NODE_VERSION, `node version ${process.version} != ${NODE_VERSION}`);
  check(MODULE_ROOTS.every(isAbsolute) && new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
    'module roots are not absolute and unique');
  check(LOCAL_MODULE_ROOTS.every((root) => MODULE_ROOTS.includes(resolve(root))),
    'repo-local module fallback is incomplete');
  check(LOCAL_MODULE_ROOTS.every(isRepositoryDescendant),
    'repo-local module fallback escaped the checkout');
  check(receiptDirectory(DEFAULT_OUT_ROOT, 'selfcheck') === join(DEFAULT_OUT_ROOT, 'selfcheck'),
    'safe receipt directory mismatch');
  for (const [root, label] of [[ROOT, 'root-child'], [DEFAULT_OUT_ROOT, '../escape']]) {
    let rejected = false;
    try { receiptDirectory(root, label); }
    catch (_) { rejected = true; }
    check(rejected, `unsafe output was accepted: ${root}/${label}`);
  }
  let missingFreezeRejected = false;
  try { parseArgs(['--label', 'selfcheck'], {}); }
  catch (_) { missingFreezeRejected = true; }
  check(missingFreezeRejected, 'production arguments accepted no source freeze');
  let unsafeLabelRejected = false;
  try { parseArgs(['--label', '../escape', '--source-freeze', '/fixture'], {}); }
  catch (_) { unsafeLabelRejected = true; }
  check(unsafeLabelRejected, 'unsafe production label was accepted');
  const chromiumToken = {};
  const synthetic = resolvePlaywright(['/missing', '/fixture'], (root) => {
    if (root === '/missing') throw new Error('fixture miss');
    return {chromium: chromiumToken, version: PLAYWRIGHT_VERSION};
  });
  check(synthetic.chromium === chromiumToken && synthetic.root === '/fixture',
    'Playwright root fallback drift');
  let wrongVersionRejected = false;
  try {
    resolvePlaywright(['/wrong'], () => ({chromium: chromiumToken, version: '0.0.0'}));
  }
  catch (_) { wrongVersionRejected = true; }
  check(wrongVersionRejected, 'Playwright version drift was accepted');
  check(pyexpr.includes('bpy.ops.wm.usd_export') && pyexpr.includes('bpy.ops.wm.usd_import') &&
    pyexpr.includes('coords==[[0.0,0.0,0.0],[0.0,3.0,0.0],[2.0,0.0,0.0]]'),
  'USD value-roundtrip contract drift');
  let livePlaywrightRoot = null;
  let livePlaywrightVersion = null;
  if (process.env.BW_NODE_MODULES || process.env.NODE_PATH) {
    const live = resolvePlaywright();
    check(MODULE_ROOTS.includes(live.root) && live.version === PLAYWRIGHT_VERSION,
      'live Playwright resolution drift');
    livePlaywrightRoot = live.root;
    livePlaywrightVersion = live.version;
  }
  process.stdout.write(JSON.stringify({
    status: 'PASS', checks, repositoryRoot: ROOT, binaryDirectory: BIN,
    moduleRoots: MODULE_ROOTS, nodeVersion: process.version,
    expectedPlaywrightVersion: PLAYWRIGHT_VERSION,
    livePlaywrightRoot, livePlaywrightVersion, browserArgs: BROWSER_ARGS,
    browserLaunches: 0,
  }, null, 2) + '\n');
}

async function runBrowser(options) {
  if (process.version !== NODE_VERSION) {
    throw new Error(`node version ${process.version} != ${NODE_VERSION}`);
  }
  const outRoot = resolve(options.outRoot);
  const outDir = receiptDirectory(outRoot, options.label);
  const out = join(outDir, 'receipt.json');
  const selectorPath = join(outDir, 'selector.json');
  const sourceFreeze = fileIdentity(options.sourceFreeze);
  const driverIdentity = repositoryIdentity(DRIVER_PATH);
  const artifactPaths = {
    js: join(BIN, 'blender_browser.js'),
    wasm: join(BIN, 'blender_browser.wasm'),
    data: join(BIN, 'blender_browser.data'),
  };
  const artifacts = Object.fromEntries(Object.entries(artifactPaths).map(([key, path]) =>
    [key, repositoryIdentity(path)]));
  const {chromium, root: playwrightRoot, version: playwrightVersion} = resolvePlaywright();
  reserveReceiptDirectory(outRoot, outDir);

  const url = `${options.base}/windowed.html?gate=1280x720&pyexpr=${encodeURIComponent(pyexpr)}`;
  const consoleLines = [
    `[producer] node=${process.version} playwright=${playwrightVersion} root=${playwrightRoot}`,
  ];
  const pageErrors = [];
  const pageCrashes = [];
  const external = [];
  const badResponses = [];
  const gpuErrors = [];
  let browser = null;
  let browserVersion = '';
  let context = null;
  let page = null;
  let result = null;
  let browserLoadedArtifacts = null;
  let verdict = 'FAIL';
  try {
    browser = await chromium.launch({headless: false, args: BROWSER_ARGS});
    browserVersion = browser.version();
    context = await browser.newContext({
      viewport: {width: 1280, height: 720}, deviceScaleFactor: 1,
    });
    page = await context.newPage();
    page.on('console', (message) => {
      const line = `[${message.type()}] ${message.text()}`;
      consoleLines.push(line);
      if (/ValidationError|GPU-ERROR|uncaptured WebGPU error/i.test(line)) gpuErrors.push(line);
    });
    page.on('pageerror', (error) => pageErrors.push(String(error)));
    page.on('crash', () => pageCrashes.push('page crash'));
    page.on('request', (request) => {
      try {
        if (new URL(request.url()).origin !== new URL(options.base).origin) external.push(request.url());
      }
      catch (_) { external.push(request.url()); }
    });
    page.on('response', (response) => {
      if (response.status() >= 400) badResponses.push({status: response.status(), url: response.url()});
    });

    await page.goto(url, {waitUntil: 'domcontentloaded', timeout: options.timeoutMs});
    await page.waitForFunction(() =>
      document.querySelector('#log')?.textContent.includes('M7_USD_ROUNDTRIP'),
    null, {timeout: options.timeoutMs});
    const log = await page.locator('#log').textContent();
    const line = log.split('\n').find((value) => value.includes('M7_USD_ROUNDTRIP')) || '';
    result = JSON.parse(
      line.slice(line.indexOf('M7_USD_ROUNDTRIP') + 'M7_USD_ROUNDTRIP'.length).trim());
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
  catch (error) {
    pageErrors.push(`producer failure: ${error?.stack || error}`);
  }
  finally {
    const terminalArtifacts = Object.fromEntries(Object.entries(artifactPaths).map(([key, path]) =>
      [key, repositoryIdentity(path)]));
    const terminalFreeze = fileIdentity(options.sourceFreeze);
    const terminalDriver = repositoryIdentity(DRIVER_PATH);
    if (JSON.stringify(terminalArtifacts) !== JSON.stringify(artifacts) ||
        JSON.stringify(terminalFreeze) !== JSON.stringify(sourceFreeze) ||
        JSON.stringify(terminalDriver) !== JSON.stringify(driverIdentity)) verdict = 'FAIL';
    const receipt = {
      schema: 'blender-web.m7-usd-browser.v2',
      verdict,
      label: options.label,
      createdUtc: new Date().toISOString(),
      driver: driverIdentity,
      sourceFreeze,
      browser_version: browserVersion,
      artifacts,
      browser_loaded_artifacts: browserLoadedArtifacts,
      url: `${options.base}/windowed.html?gate=1280x720&pyexpr=<operator-roundtrip>`,
      cross_origin_isolated: page ?
        await page.evaluate(() => crossOriginIsolated).catch(() => false) : false,
      result,
      page_errors: pageErrors,
      page_crashes: pageCrashes,
      external_requests: external,
      http_errors: badResponses,
      gpu_errors: gpuErrors,
      console_tail: consoleLines.slice(-80),
    };
    const receiptPayload = JSON.stringify(receipt, null, 2) + '\n';
    writeFileSync(out, receiptPayload, {flag: 'wx'});
    if (verdict === 'PASS') {
      const selector = {
        schema: SELECTOR_SCHEMA,
        kind: 'browser',
        label: options.label,
        receipt: {
          path: 'receipt.json',
          bytes: Buffer.byteLength(receiptPayload),
          sha256: createHash('sha256').update(receiptPayload).digest('hex'),
        },
      };
      writeFileSync(selectorPath, JSON.stringify(selector, null, 2) + '\n', {flag: 'wx'});
    }
    await context?.close().catch(() => {});
    await browser?.close().catch(() => {});
    console.log(`M7_USD_BROWSER_${verdict} ${out}`);
    if (verdict !== 'PASS') process.exitCode = 1;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.selfcheck) {
    runSelfcheck();
    return;
  }
  await runBrowser(options);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
