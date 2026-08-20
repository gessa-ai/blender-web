// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Fail-closed browser acceptance for M7's real file product paths. This uses the
// public staged bundle (dev query hooks disabled), Chrome protocol drag events
// carrying an actual .blend path, native File System Access API availability +
// trusted-activation probes, standards-shaped FSA handles, and real fallback
// upload/download bytes. Automation cannot accept a native system dialog; the probe
// fails closed on API absence or a shipped call made after user activation expires.

import {createRequire} from 'module';
import {createHash} from 'crypto';
import {
  existsSync, lstatSync, readFileSync, realpathSync, writeFileSync, mkdtempSync,
} from 'fs';
import {tmpdir} from 'os';
import {
  delimiter, dirname, isAbsolute, join, relative, resolve,
} from 'path';
import {fileURLToPath} from 'url';
import {requireHardwareRuntimeAdapter} from '../m8-launch-gate/runtime_evidence.mjs';

const DRIVER_PATH = fileURLToPath(import.meta.url);
const HERE = dirname(DRIVER_PATH);
const ROOT = resolve(HERE, '..', '..');
const DEFAULT_BIN = join(ROOT, 'build-wasm-windowed-opt/bin');
const DEFAULT_BLEND = join(ROOT, 'sandbox/m4-goldens/default_cube.blend');
const DEFAULT_OUT = join(HERE, 'verify_files.json');
const DEFAULT_BUNDLE = join(ROOT, 'sandbox/m8-staged-deploy/bundle-staged');
const DEFAULT_BUNDLE_MANIFEST = join(HERE, 'bundle-identity.json');
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
const BROWSER_ARGS = Object.freeze([
  '--enable-unsafe-webgpu',
  ...(process.platform === 'darwin' ? ['--use-angle=metal'] : []),
]);
const SHA256_RE = /^[0-9a-f]{64}$/;

function rootPath(value) {
  return resolve(ROOT, value);
}

function parseArgs(argv, environment = process.env) {
  const options = {
    base: environment.BW_BASE || 'http://127.0.0.1:8165',
    bin: rootPath(environment.BLENDER_WEB_BIN || 'build-wasm-windowed-opt/bin'),
    blend: rootPath(environment.BW_M7_BLEND || 'sandbox/m4-goldens/default_cube.blend'),
    bundle: rootPath(environment.BW_M7_BUNDLE || 'sandbox/m8-staged-deploy/bundle-staged'),
    bundleManifest: rootPath(environment.BW_M7_BUNDLE_IDENTITY ||
      'sandbox/m7-product-gate/bundle-identity.json'),
    out: rootPath(environment.BW_M7_FILES_OUT ||
      'sandbox/m7-product-gate/verify_files.json'),
    selfcheck: false,
  };
  for (const argument of argv) {
    if (argument === '--selfcheck') options.selfcheck = true;
    else throw new Error(`unknown argument: ${argument}`);
  }
  const base = new URL(options.base);
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(base.hostname) ||
      base.username || base.password || (base.pathname !== '/' && base.pathname !== '')) {
    throw new Error(`BW_BASE must be an uncredentialed loopback HTTP origin: ${options.base}`);
  }
  options.base = base.origin;
  return options;
}

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function isRepositoryPath(path, allowRoot = false) {
  const rel = relative(ROOT, resolve(path));
  return (allowRoot || rel !== '') && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== '..';
}

function requireCanonicalFile(path, description) {
  const absolute = resolve(path);
  const info = lstatSync(absolute);
  if (info.isSymbolicLink() || !info.isFile() || realpathSync(absolute) !== absolute) {
    throw new Error(`${description} is not a canonical regular file: ${absolute}`);
  }
  return absolute;
}

function safeBundlePath(bundle, relativePath) {
  if (typeof relativePath !== 'string' || relativePath.length === 0 ||
      isAbsolute(relativePath)) {
    throw new Error(`invalid bundle identity path: ${String(relativePath)}`);
  }
  const path = resolve(bundle, relativePath);
  const rel = relative(resolve(bundle), path);
  if (!rel || isAbsolute(rel) || rel.split(/[\\/]/)[0] === '..') {
    throw new Error(`bundle identity path escapes the bundle: ${relativePath}`);
  }
  return path;
}

function validateBundleIdentity(bundleIdentity, bundle) {
  if (bundleIdentity?.schema !== 'blender-web.m7-bundle-identity.v1' ||
      !Array.isArray(bundleIdentity.files) || bundleIdentity.files.length === 0 ||
      !SHA256_RE.test(bundleIdentity.splitManifestSha256 || '') ||
      !SHA256_RE.test(bundleIdentity.publicSplitManifestSha256 || '')) {
    throw new Error('missing/invalid exact M8-derived bundle identity');
  }
  const files = bundleIdentity.files.map((relativePath) => {
    safeBundlePath(bundle, relativePath);
    return relativePath;
  });
  if (new Set(files).size !== files.length) {
    throw new Error('duplicate path in exact M8-derived bundle identity');
  }
  return Object.freeze(files);
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

function loadProductInputs(options) {
  if (!isRepositoryPath(options.bin) || !isRepositoryPath(options.blend) ||
      !isRepositoryPath(options.bundle) || !isRepositoryPath(options.bundleManifest) ||
      !isRepositoryPath(options.out)) {
    throw new Error('M7 files paths must remain inside the repository');
  }
  if (resolve(options.out) !== DEFAULT_OUT) {
    throw new Error(`M7 files output must be the gate-owned path: ${DEFAULT_OUT}`);
  }
  if (existsSync(options.out)) {
    const outputInfo = lstatSync(options.out);
    if (outputInfo.isSymbolicLink() || !outputInfo.isFile() ||
        realpathSync(options.out) !== options.out) {
      throw new Error(`M7 files output is indirect or not a regular file: ${options.out}`);
    }
  }
  const blend = requireCanonicalFile(options.blend, 'M7 input blend');
  const bundleManifest = requireCanonicalFile(options.bundleManifest, 'M7 bundle identity');
  const bundleIdentityBytes = readFileSync(bundleManifest);
  const bundleIdentity = JSON.parse(bundleIdentityBytes);
  const bundleFiles = validateBundleIdentity(bundleIdentity, options.bundle);
  const splitManifestPath = requireCanonicalFile(
    join(options.bin, 'blender_browser.split-build.json'), 'M7 split manifest');
  const publicSplitManifestPath = requireCanonicalFile(
    join(options.bundle, 'bin/split-build.json'), 'M7 public split manifest');
  if (sha256Bytes(readFileSync(splitManifestPath)) !== bundleIdentity.splitManifestSha256 ||
      sha256Bytes(readFileSync(publicSplitManifestPath)) !==
        bundleIdentity.publicSplitManifestSha256) {
    throw new Error('M8-derived bundle identity is stale');
  }
  const blendBytes = readFileSync(blend);
  const bundleArtifacts = Object.fromEntries(bundleFiles.map((relativePath) => {
    const path = requireCanonicalFile(
      safeBundlePath(options.bundle, relativePath), `M7 bundle artifact ${relativePath}`);
    const bytes = readFileSync(path);
    return [relativePath, {path, bytes: bytes.length, sha256: sha256Bytes(bytes)}];
  }));
  return {
    blend, blendBytes, blendB64: blendBytes.toString('base64'), bundleArtifacts,
    bundleIdentity, bundleIdentityBytes, bundleManifest,
  };
}

function assertSelfcheck(condition, message) {
  if (!condition) throw new Error(`selfcheck: ${message}`);
}

function runSelfcheck(options) {
  let checks = 0;
  const check = (condition, message) => {
    assertSelfcheck(condition, message);
    checks++;
  };
  check(existsSync(join(ROOT, 'GOAL.md')), 'repository root is not derived from the driver');
  check(process.version === NODE_VERSION, `node version ${process.version} != ${NODE_VERSION}`);
  check(parseArgs(['--selfcheck'], {}).base === 'http://127.0.0.1:8165',
    'default loopback base normalization drift');
  check([DEFAULT_BIN, DEFAULT_BLEND, DEFAULT_OUT, DEFAULT_BUNDLE, DEFAULT_BUNDLE_MANIFEST]
    .every(isRepositoryPath), 'default path escaped the checkout');
  check([options.bin, options.blend, options.out, options.bundle, options.bundleManifest]
    .every(isRepositoryPath), 'selected path escaped the checkout');
  check(options.out === DEFAULT_OUT, 'gate-owned output path drift');
  check(MODULE_ROOTS.every(isAbsolute) && new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
    'module roots are not absolute and unique');
  check(LOCAL_MODULE_ROOTS.every((root) => MODULE_ROOTS.includes(root)),
    'repo-local module fallback is incomplete');
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
  const hash = '0'.repeat(64);
  const identity = {
    schema: 'blender-web.m7-bundle-identity.v1', files: ['bin/a.js', 'bin/a.wasm'],
    splitManifestSha256: hash, publicSplitManifestSha256: hash,
  };
  check(validateBundleIdentity(identity, DEFAULT_BUNDLE).length === 2,
    'valid bundle identity rejected');
  for (const [mutate, description] of [
    [(value) => { value.files = ['../escape']; }, 'bundle path escape'],
    [(value) => { value.files = ['bin/a.js', 'bin/a.js']; }, 'duplicate bundle path'],
    [(value) => { value.splitManifestSha256 = '0'; }, 'invalid manifest hash'],
  ]) {
    let rejected = false;
    const fixture = structuredClone(identity);
    mutate(fixture);
    try { validateBundleIdentity(fixture, DEFAULT_BUNDLE); }
    catch (_) { rejected = true; }
    check(rejected, `${description} was accepted`);
  }
  let externalBaseRejected = false;
  try { parseArgs(['--selfcheck'], {BW_BASE: 'https://example.com'}); }
  catch (_) { externalBaseRejected = true; }
  check(externalBaseRejected, 'external base was accepted');
  const source = readFileSync(DRIVER_PATH, 'utf8');
  const retiredCheckout = ['', 'Users', 'paws'].join('/');
  const retiredModuleRoot = ['plushly', 'game-platform'].join('/');
  check(!source.includes(retiredCheckout) && !source.includes(retiredModuleRoot),
    'retired macOS path remains executable source');
  check(BROWSER_ARGS.includes('--enable-unsafe-webgpu') &&
    (process.platform === 'darwin') === BROWSER_ARGS.includes('--use-angle=metal'),
  'platform browser arguments drift');
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
    status: 'PASS', checks, repositoryRoot: ROOT, binaryDirectory: options.bin,
    bundleDirectory: options.bundle, output: options.out, moduleRoots: MODULE_ROOTS,
    nodeVersion: process.version, expectedPlaywrightVersion: PLAYWRIGHT_VERSION,
    livePlaywrightRoot, livePlaywrightVersion, browserArgs: BROWSER_ARGS,
    browserLaunches: 0,
  }, null, 2) + '\n');
}

async function waitBoot(page) {
  await page.waitForFunction(() => {
    const state = document.querySelector('#state');
    return state && state.textContent.includes('main loop (WM_main)') &&
      window.__bwModule && window.BWFileBridge;
  }, null, {timeout: 240000});
  const ready = await page.evaluate(() => window.BWFileBridge.ready());
  if (!ready) throw new Error('file-bridge daemon did not become ready');
}

async function listStore(page) {
  const ack = await page.evaluate(() => window.BWFileBridge.listStore());
  if (!ack || !ack.ok) throw new Error('listStore failed: ' + JSON.stringify(ack));
  return ack.items || [];
}

async function waitStore(page, name, timeout = 60000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if ((await listStore(page)).includes(name)) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

async function installActionButton(page, id, expression) {
  await page.evaluate(({id, expression}) => {
    document.getElementById(id)?.remove();
    const button = document.createElement('button');
    button.id = id;
    button.style.cssText = 'position:fixed;left:5px;top:5px;z-index:1000';
    button.addEventListener('click', () => {
      window[id + '_promise'] = (0, eval)(expression);
    }, {once: true});
    document.body.appendChild(button);
  }, {id, expression});
}

async function trustedPickerActivation(page, kind) {
  const id = 'bw_' + kind + '_picker';
  const api = kind === 'open' ? 'showOpenFilePicker' : 'showSaveFilePicker';
  const supported = await page.evaluate((api) => typeof window[api] === 'function', api);
  await page.evaluate(({api, kind}) => {
    window.__bwPickerActivationProbe = null;
    window[api] = async () => {
      window.__bwPickerActivationProbe = {
        kind, called: true, active: navigator.userActivation.isActive,
      };
      throw new DOMException('M7 automation probe', 'AbortError');
    };
  }, {api, kind});
  const expression = kind === 'open' ?
    `window.BWFileBridge.openFromDisk().catch(e => ({cancelled: e && e.name}))` :
    `window.BWFileBridge.saveToDisk('native_picker.blend').catch(e => ({cancelled: e && e.name}))`;
  await installActionButton(page, id, expression);
  await page.locator('#' + id).click();
  await page.waitForFunction(() => window.__bwPickerActivationProbe?.called, null, {timeout: 5000});
  const probe = await page.evaluate(() => window.__bwPickerActivationProbe);
  return {supported, active: probe?.active === true, probe};
}

async function runBrowser(options) {
  if (process.version !== NODE_VERSION) {
    throw new Error(`node version ${process.version} != ${NODE_VERSION}`);
  }
  const {chromium} = resolvePlaywright();
  const product = loadProductInputs(options);
  const {blendBytes, blendB64} = product;
  const receipt = {
    schema: 'blender-web.m7-files-browser.v3',
    runtime_adapter: null,
    physical_drop_trusted: false,
    physical_drop_opened: false,
    fsa_open_picker_supported: false,
    fsa_open_trusted_activation: false,
    fsa_open_acceptance: false,
    fallback_open_acceptance: false,
    fsa_save_picker_supported: false,
    fsa_save_trusted_activation: false,
    fsa_save_acceptance: false,
    fallback_save_acceptance: false,
    opfs_reload_roundtrip: false,
    external_request_count: -1,
    gpu_error_count: -1,
    bundle_artifacts: product.bundleArtifacts,
    bundle_identity: {
      path: product.bundleManifest,
      bytes: product.bundleIdentityBytes.length,
      sha256: sha256Bytes(product.bundleIdentityBytes),
      split_manifest_sha256: product.bundleIdentity.splitManifestSha256,
      public_split_manifest_sha256: product.bundleIdentity.publicSplitManifestSha256,
    },
  };
  const failures = [];
  const fail = (message) => { failures.push(message); console.error('FAIL  ' + message); };
  const pass = (message) => console.log('PASS  ' + message);
  const browser = await chromium.launch({headless: false, args: BROWSER_ARGS});
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720}, deviceScaleFactor: 1, acceptDownloads: true,
  });
  try {
    receipt.runtime_adapter = await requireHardwareRuntimeAdapter(context, process.platform);
  }
  catch (error) {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
    throw error;
  }
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const external = [];
  const gpuErrors = [];
  page.on('request', (request) => {
    try {
      if (new URL(request.url()).origin !== new URL(options.base).origin) {
        external.push(request.url());
      }
    }
    catch (_) { external.push(request.url()); }
  });
  page.on('console', (message) => {
    const text = message.text();
    if (/ValidationError|GPU-ERROR|uncaptured WebGPU error/i.test(text)) gpuErrors.push(text);
  });
  page.on('pageerror', (error) => gpuErrors.push('pageerror: ' + error.message));

  try {
  // Product-default boot: deferred Python/addon assets load automatically before
  // file-bridge readiness. `?stage1=manual` would manufacture a daemon timeout.
  await page.goto(options.base + '/index.html', {waitUntil: 'domcontentloaded', timeout: 240000});
  await waitBoot(page);

  // 1. Actual Chrome drag pipeline with a real local file path. CDP synthesizes
  // browser input, not a script-created DataTransfer, so Event.isTrusted is true.
  await page.evaluate(() => window.addEventListener('drop', (event) => {
    window.__bwPhysicalDropTrusted = event.isTrusted;
    window.__bwPhysicalDropName = event.dataTransfer?.files?.[0]?.name || '';
  }, {capture: true, once: true}));
  const dragData = {
    items: [{mimeType: 'application/x-blender', data: ''}],
    files: [product.blend],
    dragOperationsMask: 1,
  };
  await cdp.send('Input.dispatchDragEvent', {type: 'dragEnter', x: 640, y: 360, data: dragData});
  await cdp.send('Input.dispatchDragEvent', {type: 'dragOver', x: 640, y: 360, data: dragData});
  await cdp.send('Input.dispatchDragEvent', {type: 'drop', x: 640, y: 360, data: dragData});
  receipt.physical_drop_opened = await waitStore(page, 'default_cube.blend');
  const drop = await page.evaluate(() => ({trusted: window.__bwPhysicalDropTrusted,
                                           name: window.__bwPhysicalDropName}));
  receipt.physical_drop_trusted = drop.trusted === true && drop.name === 'default_cube.blend';
  receipt.physical_drop_opened ? pass('trusted physical .blend drop opened into OPFS') :
    fail('physical .blend drop did not reach OPFS/open path');
  receipt.physical_drop_trusted ? pass('physical drop Event.isTrusted=true') :
    fail('drop was not a trusted browser input event: ' + JSON.stringify(drop));

  // 2. Chromium exposes the native picker API and the shipped branch invokes it
  // synchronously under a trusted click. CDP cannot accept/dismiss a native FSA
  // system dialog, so the next test supplies a standards-shaped handle and owns
  // byte acceptance; the real <input> fallback below is driven end-to-end.
  const openActivation = await trustedPickerActivation(page, 'open');
  receipt.fsa_open_picker_supported = openActivation.supported;
  receipt.fsa_open_trusted_activation = openActivation.active;
  receipt.fsa_open_picker_supported ? pass('Chromium native FSA open API is available') :
    fail('Chromium native FSA open API unavailable');
  receipt.fsa_open_trusted_activation ? pass('FSA open branch invoked with trusted user activation') :
    fail('FSA open branch lost trusted user activation: ' + JSON.stringify(openActivation));

  // 3. FSA open handle acceptance with real .blend bytes.
  const fsaOpen = await page.evaluate(async ({b64, length}) => {
    const raw = atob(b64); const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    window.showOpenFilePicker = async () => [{getFile: async () =>
      new File([bytes], 'fsa_accept.blend', {type: 'application/x-blender'})}];
    const ack = await window.BWFileBridge.openFromDisk();
    return !!ack && ack.ok && ack.size === length && ack.name === 'fsa_accept.blend';
  }, {b64: blendB64, length: blendBytes.length});
  receipt.fsa_open_acceptance = fsaOpen && await waitStore(page, 'fsa_accept.blend');
  receipt.fsa_open_acceptance ? pass('FSA open handle accepted exact .blend bytes') :
    fail('FSA open handle acceptance failed');

  // 4. Browser input fallback acceptance (real Playwright file chooser).
  await page.evaluate(() => { window.showOpenFilePicker = undefined; });
  await installActionButton(page, 'bw_fallback_open',
    `window.BWFileBridge.openFromDisk().catch(e => ({error: String(e)}))`);
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser', {timeout: 15000}),
    page.locator('#bw_fallback_open').click(),
  ]);
  await chooser.setFiles({name: 'fallback_accept.blend', mimeType: 'application/x-blender',
                          buffer: blendBytes});
  receipt.fallback_open_acceptance = await waitStore(page, 'fallback_accept.blend');
  receipt.fallback_open_acceptance ? pass('input fallback accepted exact .blend bytes') :
    fail('input fallback acceptance failed');

  // 5. Real native save picker invocation. This catches the subtle ordering bug:
  // showSaveFilePicker must run before awaiting worker serialization or transient
  // user activation is lost.
  const saveActivation = await trustedPickerActivation(page, 'save');
  receipt.fsa_save_picker_supported = saveActivation.supported;
  receipt.fsa_save_trusted_activation = saveActivation.active;
  receipt.fsa_save_picker_supported ? pass('Chromium native FSA save API is available') :
    fail('Chromium native FSA save API unavailable');
  receipt.fsa_save_trusted_activation ? pass('FSA save branch invoked before user activation expired') :
    fail('FSA save branch lost trusted user activation: ' + JSON.stringify(saveActivation));

  // 6. FSA writable acceptance; bytes come from Blender's real save_as_mainfile.
  const fsaSave = await page.evaluate(async () => {
    let captured = null;
    window.showSaveFilePicker = async () => ({createWritable: async () => ({
      write: async (bytes) => { captured = new Uint8Array(bytes); }, close: async () => {},
    })});
    const result = await window.BWFileBridge.saveToDisk('fsa_save.blend',
      {addEmpty: 'BW_M7_FSA_SAVE'});
    return {via: result.via, length: captured?.length || 0,
            magic: captured ? Array.from(captured.slice(0, 4)) : []};
  });
  receipt.fsa_save_acceptance = fsaSave.via === 'fsa' && fsaSave.length > 1000 &&
    fsaSave.magic.join(',') === '40,181,47,253';
  receipt.fsa_save_acceptance ? pass('FSA writable received real compressed .blend') :
    fail('FSA save acceptance failed: ' + JSON.stringify(fsaSave));

  // 7. Download fallback acceptance and exact Blender magic.
  await page.evaluate(() => { window.showSaveFilePicker = undefined; });
  await installActionButton(page, 'bw_fallback_save',
    `window.BWFileBridge.saveToDisk('fallback_save.blend').catch(e => ({error: String(e)}))`);
  const [download] = await Promise.all([
    page.waitForEvent('download', {timeout: 60000}),
    page.locator('#bw_fallback_save').click(),
  ]);
  const temp = mkdtempSync(join(tmpdir(), 'bw-m7-download-'));
  const saved = join(temp, 'fallback_save.blend');
  await download.saveAs(saved);
  const downloaded = readFileSync(saved);
  receipt.fallback_save_acceptance = downloaded.length > 1000 &&
    downloaded.subarray(0, 4).toString('hex') === '28b52ffd';
  receipt.fallback_save_acceptance ? pass('download fallback emitted real compressed .blend') :
    fail('download fallback bytes invalid');

  // 8. Full reload, fresh wasm, same OPFS: open the FSA-saved file and prove its
  // live authoring marker survived BLO serialization.
  await page.reload({waitUntil: 'domcontentloaded', timeout: 240000});
  await waitBoot(page);
  const reopened = await page.evaluate(() => window.BWFileBridge.openStore('fsa_save.blend'));
  receipt.opfs_reload_roundtrip = !!reopened && reopened.ok &&
    (reopened.objects || []).includes('BW_M7_FSA_SAVE');
  receipt.opfs_reload_roundtrip ? pass('OPFS reload/open_store preserved authored object') :
    fail('OPFS reload round-trip failed: ' + JSON.stringify(reopened));
  }
  catch (error) {
    fail('verifier threw: ' + (error?.stack || error));
  }
  finally {
    receipt.external_request_count = external.length;
    receipt.gpu_error_count = gpuErrors.length;
    receipt.external_requests = external;
    receipt.gpu_errors = gpuErrors;
    if (external.length) fail('external requests escaped bundle: ' + external.join(', '));
    if (gpuErrors.length) fail('GPU/page errors during M7 file acceptance: ' + gpuErrors[0]);
    receipt.verdict = failures.length ? 'FAIL' : 'PASS';
    receipt.failures = failures;
    writeFileSync(options.out, JSON.stringify(receipt, null, 2) + '\n');
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
    console.log(`M7_FILES_VERDICT ${receipt.verdict} -> ${options.out}`);
    if (failures.length) process.exitCode = 1;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.selfcheck) {
    runSelfcheck(options);
    return;
  }
  await runBrowser(options);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
