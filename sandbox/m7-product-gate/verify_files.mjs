// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Fail-closed browser acceptance for M7's real file product paths. This uses the
// public staged bundle (dev query hooks disabled), Chrome protocol drag events
// carrying an actual .blend path, native File System Access API availability +
// trusted-activation probes, standards-shaped FSA handles, and real fallback
// upload/download bytes. CI cannot accept a macOS native system dialog; the probe
// fails closed on API absence or a shipped call made after user activation expires.

import {createRequire} from 'module';
import {createHash} from 'crypto';
import {readFileSync, writeFileSync, mkdtempSync} from 'fs';
import {tmpdir} from 'os';
import {join} from 'path';

const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const {chromium} = require('playwright');

const BASE = process.env.BW_BASE || 'http://localhost:8165';
const ROOT = '/Users/paws/blender-web';
const BLEND = '/Users/paws/blender-web/sandbox/m4-goldens/default_cube.blend';
const OUT = '/Users/paws/blender-web/sandbox/m7-product-gate/verify_files.json';
const BUNDLE = '/Users/paws/blender-web/sandbox/m8-staged-deploy/bundle-staged';
const BUNDLE_MANIFEST = process.env.BW_M7_BUNDLE_IDENTITY ||
  '/Users/paws/blender-web/sandbox/m7-product-gate/bundle-identity.json';
const bundleIdentity = JSON.parse(readFileSync(BUNDLE_MANIFEST, 'utf8'));
if (bundleIdentity.schema !== 'blender-web.m7-bundle-identity.v1' ||
    !Array.isArray(bundleIdentity.files) || bundleIdentity.files.length === 0) {
  throw new Error('missing/invalid exact M8-derived bundle identity');
}
const BUNDLE_FILES = Object.freeze(bundleIdentity.files);
const bundleIdentityBytes = readFileSync(BUNDLE_MANIFEST);
const splitManifestPath = `${ROOT}/build-wasm-windowed-opt/bin/blender_browser.split-build.json`;
const publicSplitManifestPath = `${BUNDLE}/bin/split-build.json`;
if (createHash('sha256').update(readFileSync(splitManifestPath)).digest('hex') !==
      bundleIdentity.splitManifestSha256 ||
    createHash('sha256').update(readFileSync(publicSplitManifestPath)).digest('hex') !==
      bundleIdentity.publicSplitManifestSha256) {
  throw new Error('M8-derived bundle identity is stale');
}
const blendBytes = readFileSync(BLEND);
const blendB64 = blendBytes.toString('base64');
const receipt = {
  schema: 'blender-web.m7-files-browser.v2',
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
  bundle_artifacts: Object.fromEntries(BUNDLE_FILES.map((relative) => {
    const path = `${BUNDLE}/${relative}`;
    const bytes = readFileSync(path);
    return [relative, {
      path,
      bytes: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex'),
    }];
  })),
  bundle_identity: {
    path: BUNDLE_MANIFEST,
    bytes: bundleIdentityBytes.length,
    sha256: createHash('sha256').update(bundleIdentityBytes).digest('hex'),
    split_manifest_sha256: bundleIdentity.splitManifestSha256,
    public_split_manifest_sha256: bundleIdentity.publicSplitManifestSha256,
  },
};
const failures = [];
const fail = (message) => { failures.push(message); console.error('FAIL  ' + message); };
const pass = (message) => console.log('PASS  ' + message);

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

const browser = await chromium.launch({headless: false});
const context = await browser.newContext({
  viewport: {width: 1280, height: 720}, deviceScaleFactor: 1, acceptDownloads: true,
});
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
const external = [];
const gpuErrors = [];
page.on('request', (request) => {
  try { if (new URL(request.url()).origin !== new URL(BASE).origin) external.push(request.url()); }
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
  await page.goto(BASE + '/index.html', {waitUntil: 'domcontentloaded', timeout: 240000});
  await waitBoot(page);

  // 1. Actual Chrome drag pipeline with a real local file path. CDP synthesizes
  // browser input, not a script-created DataTransfer, so Event.isTrusted is true.
  await page.evaluate(() => window.addEventListener('drop', (event) => {
    window.__bwPhysicalDropTrusted = event.isTrusted;
    window.__bwPhysicalDropName = event.dataTransfer?.files?.[0]?.name || '';
  }, {capture: true, once: true}));
  const dragData = {
    items: [{mimeType: 'application/x-blender', data: ''}],
    files: [BLEND],
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
  // synchronously under a trusted click. CDP cannot accept/dismiss a macOS FSA
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
  writeFileSync(OUT, JSON.stringify(receipt, null, 2) + '\n');
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
  console.log(`M7_FILES_VERDICT ${receipt.verdict} -> ${OUT}`);
  process.exit(failures.length ? 1 : 0);
}
