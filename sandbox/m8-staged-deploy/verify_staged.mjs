// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// verify_staged.mjs - functional integrity of the STAGED deploy bundle:
//   (1) boots on stage-0 alone to WM_main + presents real pixels (COOP/COEP);
//   (2) public-bundle `?pyexpr` and `?args` attacks are ignored;
//   (3) deferred-stage asset proof:
//       (3a) BYTE-EXACT: a file that is a ZERO-LENGTH placeholder after stage-0
//            boot becomes its real bytes after stage-1 streams, byte-verified
//            against the packaged slice;
//   (4) service-worker cache fills only after stage-1 and contains every shipped
//       boot/deferred asset under the generated content version.
//   (5) captures a viewport-exact screenshot with a CC0 .license sidecar.
//   (6) cold, online-warm, and offline-cold processes each prove trusted semantic
//       input plus the complete M7 PARK..RESUMED transition/state change; the
//       exact deferred shard hits origin once cold, then zero times warm/offline.
// Playwright drives an explicitly identified branded Chrome app on a caller-selected port;
// ?stage1=manual so the
// rig controls the stream timing. Writes a machine-readable verify_staged.json.
//
import { createRequire } from 'module';
import * as fs from 'fs';
import { delimiter, dirname, isAbsolute, join, relative, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  canonicalBundleDigest, collectArtifacts, loadArtifactContract, requireServedBundle,
} from '../m8-launch-gate/bundle_identity.mjs';
import {
  bindRuntimeVersion, browserIdentityContract, collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, requireHardwareRuntimeAdapter, revalidateBrowserRuntimeIdentity,
} from '../m8-launch-gate/runtime_evidence.mjs';
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const NODE_VERSION = 'v22.16.0';
const PLAYWRIGHT_VERSION = '1.61.1';
const PNGJS_VERSION = '7.0.0';
const LOCAL_MODULE_ROOTS = Object.freeze([
  join(ROOT, '.m4-node/node_modules'),
  join(ROOT, 'node_modules'),
]);
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  ...LOCAL_MODULE_ROOTS,
].filter(Boolean).flatMap((entry) => entry.split(delimiter)).filter(Boolean)
  .map((entry) => resolve(entry)))]);

function requireNodeVersion(version = process.version) {
  if (version !== NODE_VERSION) throw new Error(`Node ${NODE_VERSION} required, got ${version}`);
}

function resolveBrowserDependencies(
  roots = MODULE_ROOTS,
  load = (root) => {
    const require = createRequire(join(root, 'package.json'));
    return {
      chromium: require('playwright').chromium,
      playwrightVersion: require('playwright/package.json').version,
      PNG: require('pngjs').PNG,
      pngjsVersion: require('pngjs/package.json').version,
    };
  },
) {
  const failures = [];
  for (const root of roots) {
    try {
      const loaded = load(root);
      if (!loaded?.chromium || !loaded?.PNG) throw new Error('browser dependency exports are absent');
      if (loaded.playwrightVersion !== PLAYWRIGHT_VERSION || loaded.pngjsVersion !== PNGJS_VERSION) {
        throw new Error(`versions playwright=${loaded.playwrightVersion} pngjs=${loaded.pngjsVersion}`);
      }
      return {...loaded, root};
    }
    catch (error) {
      failures.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve exact browser dependencies; set BW_NODE_MODULES\n${failures.join('\n')}`);
}

function isRepositoryDescendant(path) {
  const rel = relative(ROOT, resolve(path));
  return rel !== '' && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== '..';
}

function parseInvocation(argv = process.argv.slice(2)) {
  if (argv.length === 1 && argv[0] === '--selfcheck') return {selfcheck: true};
  if (argv.length !== 2) {
    throw new Error('usage: verify_staged.mjs PORT /absolute/path/to/canonical-branded-chrome');
  }
  const [portText, executable] = argv;
  const port = Number.parseInt(portText, 10);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535 || String(port) !== portText) {
    throw new Error(`invalid port: ${portText}`);
  }
  if (!isAbsolute(executable)) {
    throw new Error('usage: verify_staged.mjs PORT /absolute/path/to/canonical-branded-chrome');
  }
  return {selfcheck: false, port, executable};
}

async function runSelfcheck() {
  let positive = 0;
  let negative = 0;
  const check = (condition, message) => {
    if (!condition) throw new Error(`M8 staged-capture self-check: ${message}`);
    positive++;
  };
  const reject = async (name, action) => {
    try { await action(); }
    catch (_) { negative++; return; }
    throw new Error(`M8 staged-capture self-check false green: ${name}`);
  };

  check(fs.readFileSync(join(ROOT, 'GOAL.md'), 'utf8').length > 0,
    'repository root is not producer-derived');
  check(MODULE_ROOTS.every(isAbsolute) && new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
    'module roots are not absolute and unique');
  check(LOCAL_MODULE_ROOTS.every((root) => MODULE_ROOTS.includes(root) && isRepositoryDescendant(root)),
    'repository-local module fallbacks are incomplete or escaped');
  requireNodeVersion();
  check(true, 'exact Node acceptance');
  await reject('wrong_node', () => requireNodeVersion('v25.1.0'));

  const chromiumToken = {};
  const pngToken = {};
  const synthetic = resolveBrowserDependencies(['/missing', '/fixture/modules'], (root) => {
    if (root === '/missing') throw new Error('fixture miss');
    return {chromium: chromiumToken, PNG: pngToken,
      playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: PNGJS_VERSION};
  });
  check(synthetic.chromium === chromiumToken && synthetic.PNG === pngToken &&
    synthetic.root === '/fixture/modules', 'dependency fallback drifted');
  await reject('wrong_playwright', () => resolveBrowserDependencies(['/fixture'], () => ({
    chromium: chromiumToken, PNG: pngToken,
    playwrightVersion: '1.61.0', pngjsVersion: PNGJS_VERSION,
  })));
  await reject('wrong_pngjs', () => resolveBrowserDependencies(['/fixture'], () => ({
    chromium: chromiumToken, PNG: pngToken,
    playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: '6.0.0',
  })));
  await reject('missing_exports', () => resolveBrowserDependencies(['/fixture'], () => ({
    playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: PNGJS_VERSION,
  })));

  const linuxContract = browserIdentityContract('chrome', 'linux');
  const darwinContract = browserIdentityContract('chrome', 'darwin');
  check(linuxContract.executablePath === '/opt/google/chrome/chrome' &&
    linuxContract.packageName === 'google-chrome-stable', 'Linux Chrome identity contract drifted');
  check(darwinContract.identifier === 'com.google.Chrome' && darwinContract.team === 'EQHXZ8M8AV',
    'Darwin Chrome identity contract drifted');
  await reject('unsupported_platform', () => browserIdentityContract('chrome', 'win32'));

  const parsed = parseInvocation(['8168', '/fixture/chrome']);
  check(parsed.port === 8168 && parsed.executable === '/fixture/chrome', 'invocation parser drifted');
  for (const [name, args] of [
    ['missing_executable', ['8168']],
    ['relative_executable', ['8168', 'fixture/chrome']],
    ['invalid_port', ['8168junk', '/fixture/chrome']],
    ['out_of_range_port', ['65536', '/fixture/chrome']],
    ['extra_argument', ['8168', '/fixture/chrome', 'extra']],
  ]) await reject(name, () => parseInvocation(args));

  const artifactRoot = join(HERE, 'artifacts');
  const screenshot = join(artifactRoot, 'staged_boot_1280x720.png');
  const receipt = join(artifactRoot, 'verify_staged.json');
  check(isRepositoryDescendant(artifactRoot) && dirname(screenshot) === artifactRoot &&
    dirname(receipt) === artifactRoot, 'canonical evidence paths escaped the repository');
  const source = fs.readFileSync(fileURLToPath(import.meta.url), 'utf8');
  check(!source.includes('/Users/' + 'paws') &&
    source.includes('browserIdentityContract(\'chrome\', HOST_PLATFORM)'),
    'producer retains the old host root or bypasses the host identity contract');

  let liveLibraryRoot = null;
  if (process.env.BW_NODE_MODULES || process.env.NODE_PATH) {
    const live = resolveBrowserDependencies();
    check(MODULE_ROOTS.includes(live.root) && live.playwrightVersion === PLAYWRIGHT_VERSION &&
      live.pngjsVersion === PNGJS_VERSION, 'live browser dependency resolution drifted');
    liveLibraryRoot = live.root;
  }
  console.log(`M8_STAGED_CAPTURE_SELFCHECK_PASS positive=${positive} negative=${negative} ` +
    `platforms=darwin+linux node=${NODE_VERSION} playwright=${PLAYWRIGHT_VERSION} ` +
    `pngjs=${PNGJS_VERSION} live=${liveLibraryRoot || 'not-requested'} browser_launches=0`);
}

const invocation = parseInvocation();
if (invocation.selfcheck) {
  await runSelfcheck();
  process.exit(0);
}
requireNodeVersion();
const {chromium, PNG} = resolveBrowserDependencies();
const PORT = invocation.port;
const EXECUTABLE = invocation.executable;
const HOST_PLATFORM = process.platform;
const identityContract = browserIdentityContract('chrome', HOST_PLATFORM);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = join(HERE, 'artifacts');
if (!isRepositoryDescendant(OUTDIR)) {
  throw new Error(`refusing evidence path outside the repository: ${OUTDIR}`);
}
const collectedRuntimeIdentity = collectBrowserRuntimeIdentity(EXECUTABLE, identityContract);
const artifactContract = loadArtifactContract(ROOT);
const OUT = join(OUTDIR, `staged_boot_${W}x${H}.png`);
const PROBE = '/bw/python/lib/python3.13/asyncio/tasks.py'; // deferred, byte-exact target
const TRANSPORT_PROOF = '/.well-known/bw-transport-proof';
const deferredRows = artifactContract.shippedWasm.filter((row) => row.role === 'deferred');
if (deferredRows.length !== 1) {
  throw new Error(`M8 runtime rig requires exactly one finalizer-owned deferred shard, got ${deferredRows.length}`);
}
const DEFERRED = deferredRows[0];
const DEFERRED_PATH = `/bin/${DEFERRED.filename}`;
const DEFERRED_KEY = `${DEFERRED_PATH}?sha256=${DEFERRED.sha256}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ATTACK_MARKER = '/tmp/bw_public_query_python_ran';
const ATTACK_EXPR = `open(${JSON.stringify(ATTACK_MARKER)},'w').write('BAD')`;
const url = `${BASE}/index.html?stage1=manual&args=${encodeURIComponent('--background')}` +
            `&pyexpr=${encodeURIComponent(ATTACK_EXPR)}&gate=1x1&keepalive=0&ka_active=999999`;
let failed = false;
const failures = [];
const fail = (m) => { failed = true; failures.push(m); console.error('VERDICT-FAIL: ' + m); };
const log = (m) => console.log('[verify] ' + m);
const receipt = {
  schema: 1,
  source_artifacts: collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames),
  bundle_artifacts: collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames),
  served_bundle_sha256: null,
  cross_origin_isolated: false,
  shared_array_buffer: false,
  stage0_boot: false,
  stage0_first_pixels: false,
  stage0_first_pixels_ms: null,
  first_pixels_present: false,
  interactive_viewport_ms: null,
  interactive_viewport_under_8s: false,
  stage1_byte_exact: false,
  stage1_complete: false,
  progress_phases_visible: false,
  service_worker_complete: false,
  service_worker_inventory_exact: false,
  trusted_semantic_interaction: false,
  deferred_after_trusted_interaction_exactly_once: false,
  two_phase_resumed_state_change: false,
  online_warm_deferred_zero_origin: false,
  online_warm_deferred_from_service_worker: false,
  offline_cold_semantic_deferred: false,
  offline_reload_wm_main: false,
  external_request_count: -1,
  query_python_disabled: false,
  query_args_disabled: false,
  query_dev_controls_disabled: false,
  native_proof_visible: false,
  desktop_limit_visible: false,
  trademark_disclaimer_visible: false,
  legal_notices_visible: false,
  offline_warm_wm_main_ms: null,
  gpu_error_count: -1,
  page_error_count: -1,
  browser: {},
  early_diagnostics: {cold_online: null, online_warm: null, offline_cold: null},
};

const browser = await chromium.launch({ headless: false, executablePath: EXECUTABLE });
const browserVersion = browser.version();
const runtimeIdentity = bindRuntimeVersion(collectedRuntimeIdentity, browserVersion);
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
let runtimeAdapter;
try {
  runtimeAdapter = await requireHardwareRuntimeAdapter(ctx, HOST_PLATFORM);
}
catch (error) {
  await ctx.close().catch(() => {});
  await browser.close().catch(() => {});
  throw error;
}
fs.mkdirSync(OUTDIR, { recursive: true });
receipt.browser = {engine: 'chrome', executable: EXECUTABLE, version: browserVersion,
  signing: legacySigning(runtimeIdentity), runtime_identity: runtimeIdentity,
  runtime_adapter: runtimeAdapter};
await ctx.addInitScript(() => {
  window.__BW_STAGE1_MANUAL = true;
  window.__bwM8TrustedInputs = [];
  for (const type of ['keydown', 'mousedown', 'mousemove', 'mouseup']) {
    addEventListener(type, (event) => {
      if (event.target?.id === 'canvas') window.__bwM8TrustedInputs.push({
        type, key: event.key || null, button: event.button ?? null, isTrusted: event.isTrusted,
      });
    }, true);
  }
});
const page = await ctx.newPage();
const navigationStart = Date.now();
const present = { count: 0 };
const errs = [], gpuErrs = [], pageErrors = [], allLines = [];
const externalRequests = [];
const assetRequests = [], assetResponses = [];
let runtimePhase = 'initial-navigation';
let pageRun = 'cold-online';
async function recordEarlyDiagnostics(key) {
  try {
    receipt.early_diagnostics[key] = await requireEmptyEarlyDiagnostics(page, `staged:${key}`);
  }
  catch (error) {
    fail(`${key} early diagnostics: ${String(error && error.message || error)}`);
  }
}
page.on('request', (request) => {
  try {
    const parsed = new URL(request.url());
    if (parsed.origin !== new URL(BASE).origin) externalRequests.push(request.url());
    assetRequests.push({url: parsed.pathname + parsed.search, phase: runtimePhase,
      run: pageRun, at_ms: Date.now() - navigationStart});
  }
  catch (_) { externalRequests.push(request.url()); }
});
page.on('response', async (response) => {
  try {
    const parsed = new URL(response.url());
    const observedPhase = runtimePhase, observedRun = pageRun;
    const headers = await response.allHeaders();
    assetResponses.push({url: parsed.pathname + parsed.search, phase: observedPhase,
      run: observedRun, status: response.status(), from_service_worker: response.fromServiceWorker(),
      content_type: headers['content-type'] || null,
      content_bytes: headers['x-bw-content-bytes'] ? Number(headers['x-bw-content-bytes']) : null,
      content_sha256: headers['x-bw-content-sha256'] || null,
      origin_request_count: headers['x-bw-origin-request-count'] ?
        Number(headers['x-bw-origin-request-count']) : null});
  } catch (_) {}
});
page.on('console', (m) => {
  const t = m.text(); allLines.push(t);
  if (t.includes('presentBackbuffer')) present.count++;
  if (m.type() === 'error' || t.includes('ValidationError') || t.includes('GPU-ERROR')) errs.push(t);
  if (/ValidationError|GPU-ERROR|uncaptured WebGPU error|Dawn:\s/i.test(t)) gpuErrs.push(t);
});
page.on('pageerror', (e) => {
  const text = 'pageerror: ' + (e.message || e);
  errs.push(text); pageErrors.push(text); allLines.push('PAGEERR ' + (e.message || e));
});
page.on('crash', () => { errs.push('PAGE CRASH'); pageErrors.push('PAGE CRASH'); });
log('booting staged bundle (stage-0 preload only)...');
const navigationResponse = await page.goto(url, { waitUntil: 'domcontentloaded' });
try {
  receipt.served_bundle_sha256 = await requireServedBundle(
    navigationResponse, canonicalBundleDigest(receipt.bundle_artifacts));
} catch (e) { fail(e.message); }
const iso = await page.evaluate(() => ({ coi: self.crossOriginIsolated === true, sab: typeof SharedArrayBuffer !== 'undefined' }));
if (!iso.coi) fail('not crossOriginIsolated'); if (!iso.sab) fail('no SharedArrayBuffer');
receipt.cross_origin_isolated = iso.coi;
receipt.shared_array_buffer = iso.sab;
log(`crossOriginIsolated=${iso.coi} SAB=${iso.sab}`);

const launchProof = await page.evaluate(() => {
  const probe = (id) => {
    const el = document.getElementById(id);
    const style = el && getComputedStyle(el);
    return {text: el?.textContent?.trim() || '', visible: !!el && style.display !== 'none' &&
      style.visibility !== 'hidden' && Number(style.opacity) > 0};
  };
  return {native: probe('bw-native-proof'), offline: probe('bw-offline-proof'),
          desktop: probe('bw-desktop-limit'), legal: probe('bw-legal-footer'),
          legalLink: probe('bw-license-link'),
          legalHref: document.getElementById('bw-license-link')?.getAttribute('href') || ''};
});
receipt.native_proof_visible = launchProof.native.visible && launchProof.offline.visible &&
  launchProof.native.text === 'Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming.' &&
  launchProof.offline.text === 'After first load, disconnect your network and reload.';
receipt.desktop_limit_visible = launchProof.desktop.visible &&
  launchProof.desktop.text === 'Desktop only for this preview · current Chrome or Edge required.';
receipt.trademark_disclaimer_visible = launchProof.legal.visible &&
  /not affiliated with or endorsed by the Blender Foundation/.test(launchProof.legal.text) &&
  /registered trademark of the Blender Foundation/.test(launchProof.legal.text);
receipt.legal_notices_visible = launchProof.legalLink.visible &&
  launchProof.legalLink.text === 'Licenses and notices' &&
  launchProof.legalHref === '/legal/THIRD-PARTY.md';
log('visible launch proof: ' + JSON.stringify(launchProof));
if (!receipt.native_proof_visible) fail('local-runtime/offline proof is missing or hidden');
if (!receipt.desktop_limit_visible) fail('desktop/browser limitation is missing or hidden');
if (!receipt.trademark_disclaimer_visible) fail('trademark/non-endorsement disclaimer is missing or hidden');
if (!receipt.legal_notices_visible) fail('same-origin licenses/notices link is missing or hidden');

const t0 = Date.now();
let stage0Reached = false;
try {
  await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 });
  stage0Reached = true;
  log(`WM_main reached in ${Date.now() - t0} ms (stage-0 only)`);
} catch (e) { fail('WM_main not reached: ' + e.message); }
receipt.stage0_boot = stage0Reached;

const gate = await page.evaluate(() => { const c = document.getElementById('canvas'); return { bw: c.width, bh: c.height, mod: typeof window.__bwModule === 'object' && !!window.__bwModule }; });
if (gate.bw !== W || gate.bh !== H) fail(`gate ${gate.bw}x${gate.bh} != ${W}x${H}`);
if (!gate.mod) fail('__bwModule missing');
log(`viewport backing ${gate.bw}x${gate.bh}  __bwModule=${gate.mod}`);

async function screenshotPixelStats() {
  // Product-pixel evidence must come from Blender's canvas.  A full-page
  // screenshot can be varied/non-black solely because the surrounding HTML
  // status, progress, and legal UI rendered while the product canvas stayed
  // black.
  const pixels = PNG.sync.read(await page.locator('#canvas').screenshot({type: 'png'}));
  let nonBlack = 0, min = 255, max = 0;
  const sampled = new Set();
  for (let i = 0; i < pixels.data.length; i += 4) {
    const r = pixels.data[i], g = pixels.data[i + 1], b = pixels.data[i + 2];
    const lum = Math.max(r, g, b);
    if (lum > 8) nonBlack++;
    min = Math.min(min, r, g, b); max = Math.max(max, r, g, b);
    if ((i & 0x3fff) === 0) sampled.add(`${r},${g},${b}`);
  }
  const pixelCount = pixels.width * pixels.height;
  return {width: pixels.width, height: pixels.height, nonBlack, pixelCount, min, max,
          sampledColors: sampled.size, content: pixels.width === W && pixels.height === H &&
            nonBlack > pixelCount / 4 && max - min > 32 && sampled.size > 8};
}

async function canvasVisualSignature() {
  const pixels = PNG.sync.read(await page.locator('#canvas').screenshot());
  const values = [];
  for (let y = 0; y < pixels.height; y += 8) {
    for (let x = 0; x < pixels.width; x += 8) {
      const i = (y * pixels.width + x) * 4;
      values.push((pixels.data[i] + pixels.data[i + 1] + pixels.data[i + 2]) / 3);
    }
  }
  return values;
}

function meanAbsoluteDifference(left, right) {
  if (!left || !right || left.length !== right.length) return null;
  return left.reduce((sum, value, index) => sum + Math.abs(value - right[index]), 0) / left.length;
}

async function waitForProductBoot(label) {
  await page.waitForFunction(() => {
    const state = document.querySelector('#state');
    return state?.textContent?.includes('main loop (WM_main)') && window.__bwModule;
  }, null, {timeout: 180000});
  const deadline = Date.now() + 60000;
  let pixels = null;
  while (Date.now() < deadline) {
    pixels = await screenshotPixelStats();
    if (pixels.content) return pixels;
    await sleep(250);
  }
  throw new Error(`${label}: semantic product pixels did not appear`);
}

async function transportProof() {
  return page.evaluate(async ({path, nonce}) => {
    const response = await fetch(`${path}?nonce=${encodeURIComponent(nonce)}`, {cache: 'no-store'});
    if (!response.ok) throw new Error(`transport proof HTTP ${response.status}`);
    return response.json();
  }, {path: TRANSPORT_PROOF, nonce: `${Date.now()}-${Math.random()}`});
}

function exactDeferredTraffic(run, phaseFloorMs = -1) {
  const requests = assetRequests.filter((row) => row.run === run && row.url.split('?', 1)[0] === DEFERRED_PATH &&
    row.at_ms > phaseFloorMs);
  const responses = assetResponses.filter((row) => row.run === run && row.url.split('?', 1)[0] === DEFERRED_PATH);
  return {requests, responses};
}

async function runTwoPhaseSemanticLifecycle(run, expectedFromServiceWorker) {
  pageRun = run;
  const requiredApis = [
    'bwRequestSplitPark', 'bwPrepareSplitSecondary', 'bwApplySplitScheduler',
    'bwMarkSplitPageReady', 'bwResumeSplitScheduler', 'bwFinalizeSplitTransition',
    'bwSplitSecondaryStatus',
    'bwSplitNativeStatus',
  ];
  const apiProof = await page.evaluate((names) => ({
    missing: names.filter((name) => typeof window.__bwModule?.[name] !== 'function'),
    bridge: typeof window.BWFileBridge?.ready === 'function' &&
      typeof window.BWFileBridge?.inspectScene === 'function',
  }), requiredApis);
  if (apiProof.missing.length || !apiProof.bridge) {
    throw new Error(`${run}: frozen M7 APIs unavailable: ${JSON.stringify(apiProof)}`);
  }
  const bridgeReady = await page.evaluate(async () => window.BWFileBridge.ready());
  if (!bridgeReady) throw new Error(`${run}: file bridge not ready`);
  const beforeScene = await page.evaluate(() => window.BWFileBridge.inspectScene());
  if (!(beforeScene?.ok === true && beforeScene.active === 'Cube' &&
        Number.isSafeInteger(beforeScene.meshVertices) && beforeScene.meshVertices >= 8 &&
        ['Camera', 'Cube', 'Light'].every((name) => beforeScene.objects?.includes(name)))) {
    throw new Error(`${run}: initial semantic scene proof failed: ${JSON.stringify(beforeScene)}`);
  }

  const canvas = page.locator('#canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error(`${run}: canvas has no bounding box`);
  await canvas.focus();
  await page.keyboard.press('Escape');
  const beforePixels = await canvasVisualSignature();
  const x = box.x + box.width * 0.55, y = box.y + box.height * 0.5;
  runtimePhase = `${run}:trusted-semantic-interaction`;
  await page.mouse.move(x - 30, y - 15);
  await page.mouse.down({button: 'middle'});
  await page.mouse.move(x + 30, y + 15, {steps: 6});
  await page.mouse.up({button: 'middle'});
  await sleep(150);
  const visualDifference = meanAbsoluteDifference(beforePixels, await canvasVisualSignature());
  const trusted = await page.evaluate(() => window.__bwM8TrustedInputs || []);
  const trustedPass = visualDifference !== null && visualDifference > 0.25 && trusted.length >= 4 &&
    trusted.every((row) => row.isTrusted === true) && trusted.some((row) => row.button === 1);
  if (!trustedPass) {
    throw new Error(`${run}: trusted semantic interaction failed: ` +
      JSON.stringify({visualDifference, trusted}));
  }
  const interactionCompleteMs = Date.now() - navigationStart;
  const early = assetRequests.filter((row) => row.run === run && row.url.split('?', 1)[0] === DEFERRED_PATH &&
    row.at_ms <= interactionCompleteMs);
  if (early.length) throw new Error(`${run}: deferred shard requested before trusted interaction`);

  const generation = 1;
  runtimePhase = `${run}:PARK`;
  const parked = await page.evaluate((value) => window.__bwModule.bwRequestSplitPark(value), generation);
  if (parked?.parkedGeneration !== generation || parked.phase !== 2 || parked.activeThreads !== 1 ||
      parked.openexrThreads !== 0 || parked.oiioThreads !== 1 || parked.errorGeneration !== 0) {
    throw new Error(`${run}: PARK contract failed: ${JSON.stringify(parked)}`);
  }
  runtimePhase = `${run}:PREPARED`;
  const prepared = await page.evaluate((value) => window.__bwModule.bwPrepareSplitSecondary(value), generation);
  const preparedSplit = prepared?.split;
  const preparedNative = prepared?.native;
  if (!preparedSplit?.ready || preparedSplit.workerCount < 8 ||
      preparedSplit.workerAckCount !== preparedSplit.workerCount ||
      preparedSplit.workerInstanceCount !== preparedSplit.workerCount ||
      preparedSplit.localInstanceCount !== 1 || preparedSplit.pendingWorkerIds?.length !== 0 ||
      preparedSplit.protocolError !== null || preparedSplit.stats?.fetchCount !== 1 ||
      preparedSplit.stats?.compileCount !== 1 || preparedSplit.stats?.pageInstanceCount !== 1 ||
      preparedNative?.preparedGeneration !== generation || preparedNative.phase !== 4 ||
      preparedNative.preparedWorkers !== preparedSplit.workerCount ||
      preparedNative.preparedAcknowledgements !== preparedSplit.workerAckCount ||
      preparedNative.preparedInstances !== preparedSplit.workerInstanceCount ||
      preparedNative.preparedLocalInstances !== 1 || preparedNative.preparedPending !== 0 ||
      preparedNative.preparedProtocolErrors !== 0 || preparedNative.preparedStabilizationEpoch <= 0) {
    throw new Error(`${run}: PREPARED contract failed: ${JSON.stringify(prepared)}`);
  }
  runtimePhase = `${run}:APPLY`;
  const applied = await page.evaluate((value) => window.__bwModule.bwApplySplitScheduler(value), generation);
  if (applied?.appliedGeneration !== generation || applied.phase !== 6 ||
      applied.activeThreads !== 8 || applied.targetThreads !== 8 || applied.nativeReady !== 1 ||
      applied.openexrThreads !== 8 || applied.oiioThreads !== 8 ||
      applied.reloadRequired !== 0 || applied.errorGeneration !== 0) {
    throw new Error(`${run}: APPLY contract failed: ${JSON.stringify(applied)}`);
  }

  runtimePhase = `${run}:queued-cold-input`;
  await page.keyboard.press('Tab');
  await page.keyboard.press('e');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await sleep(100);
  runtimePhase = `${run}:PAGE_READY`;
  // Keep PAGE_READY's final worker attestation and RESUME publication inside a
  // single page task. Splitting these across Playwright calls recreates the late-
  // worker TOCTOU that the production controller is designed to close.
  const finalized = await page.evaluate((value) =>
    window.__bwModule.bwFinalizeSplitTransition(value), generation);
  const resumed = {split: finalized?.split, native: finalized?.native};
  if (resumed?.native?.resumedGeneration !== generation || resumed.native.phase !== 10 ||
      resumed.native.errorGeneration !== 0 || resumed.native.activeThreads !== 8 ||
      resumed.native.openexrThreads !== 8 || resumed.native.oiioThreads !== 8 ||
      resumed.native.reloadRequired !== 0) {
    throw new Error(`${run}: RESUME contract failed: ${JSON.stringify(resumed)}`);
  }
  const pageReady = {
    split: resumed.split,
    native: resumed.native,
    lateWorkers: finalized?.lateWorkers,
  };
  if (resumed.native.pageReadyGeneration !== generation ||
      resumed.native.pageReadyWorkers !== resumed.split?.workerCount ||
      resumed.native.pageReadyAcknowledgements !== resumed.split?.workerAckCount ||
      resumed.native.pageReadyInstances !== resumed.split?.workerInstanceCount ||
      resumed.native.pageReadyLocalInstances !== 1 || resumed.native.pageReadyPending !== 0 ||
      resumed.native.pageReadyProtocolErrors !== 0 ||
      resumed.native.pageReadyLateWorkers !== finalized?.lateWorkers ||
      resumed.native.pageReadyStabilizationEpoch <= preparedNative.preparedStabilizationEpoch) {
    throw new Error(`${run}: PAGE_READY/RESUME contract failed: ${JSON.stringify(finalized)}`);
  }
  runtimePhase = `${run}:post-resume-state-change`;
  const stateDeadline = Date.now() + 60000;
  let afterScene = null;
  while (Date.now() < stateDeadline) {
    afterScene = await page.evaluate(() => window.BWFileBridge.inspectScene());
    if (afterScene?.ok === true && afterScene.meshVertices > beforeScene.meshVertices) break;
    await sleep(100);
  }
  if (!(afterScene?.ok === true && afterScene.meshVertices > beforeScene.meshVertices)) {
    throw new Error(`${run}: queued semantic edit did not execute after RESUME: ` +
      JSON.stringify({beforeScene, afterScene}));
  }
  await sleep(100);
  const traffic = exactDeferredTraffic(run, interactionCompleteMs);
  if (traffic.requests.length !== 1 || traffic.responses.length !== 1 ||
      traffic.requests[0].url !== DEFERRED_KEY || traffic.responses[0].url !== DEFERRED_KEY) {
    throw new Error(`${run}: deferred request/response is not exactly once: ${JSON.stringify(traffic)}`);
  }
  const response = traffic.responses[0];
  if (response.status !== 200 || response.content_type !== 'application/wasm' ||
      response.content_bytes !== DEFERRED.bytes || response.content_sha256 !== DEFERRED.sha256 ||
      (expectedFromServiceWorker !== null &&
       response.from_service_worker !== expectedFromServiceWorker)) {
    throw new Error(`${run}: deferred response identity/transport failed: ${JSON.stringify(response)}`);
  }
  return {run, interaction_complete_ms: interactionCompleteMs, trusted_input_count: trusted.length,
    visual_difference: visualDifference, before_scene: beforeScene, after_scene: afterScene,
    parked, prepared, applied, page_ready: pageReady, resumed, deferred: traffic};
}

// (2) The PUBLIC copy must fail closed against URL-controlled Python and argv.
const queryHardening = await page.evaluate((marker) => {
  let markerExists = false;
  try { window.__bwModule.FS.stat(marker); markerExists = true; } catch (_) {}
  return { allowed: window.__bwDevHooksAllowed, markerExists,
           argv: document.getElementById('argv')?.textContent || '',
           keepalive: window.__bwKeepaliveConfig,
           canvas: [document.getElementById('canvas')?.width, document.getElementById('canvas')?.height] };
}, ATTACK_MARKER);
receipt.query_python_disabled = queryHardening.allowed === false && !queryHardening.markerExists &&
  !queryHardening.argv.includes('--python-expr');
receipt.query_args_disabled = queryHardening.allowed === false && receipt.stage0_boot &&
  !queryHardening.argv.includes('--background');
receipt.query_dev_controls_disabled = queryHardening.allowed === false &&
  queryHardening.canvas[0] === W &&
  queryHardening.canvas[1] === H && queryHardening.keepalive?.enabled === 1 &&
  queryHardening.keepalive?.active === 0 && queryHardening.keepalive?.idle === 0;
log('public query hardening: ' + JSON.stringify(queryHardening));
if (!receipt.query_python_disabled) fail('public ?pyexpr executed or dev hooks stayed enabled');
if (!receipt.query_args_disabled) fail('public ?args was not fail-closed');
if (!receipt.query_dev_controls_disabled) fail('public gate/keepalive query diagnostics were not fail-closed');
if (present.count > 0) log('optional presentBackbuffer diagnostic x' + present.count);

// (3a) deferred asset BEFORE stage-1: expect zero-length placeholder
const before = await page.evaluate((p) => { try { return window.__bwModule.FS.stat(p).size; } catch (e) { return 'ERR:' + e; } }, PROBE);
log(`deferred ${PROBE} size BEFORE stage-1 = ${before} (expect 0)`);
if (before !== 0) fail('probe file not a placeholder before stage-1 (size=' + before + ')');
try {
  let stage0Pixels = await screenshotPixelStats();
  const stage0Deadline = navigationStart + 8000;
  while (!stage0Pixels.content && Date.now() < stage0Deadline) {
    await sleep(Math.min(250, Math.max(1, stage0Deadline - Date.now())));
    stage0Pixels = await screenshotPixelStats();
  }
  receipt.stage0_first_pixels = stage0Pixels.content && Date.now() - navigationStart <= 8000;
  if (receipt.stage0_first_pixels) {
    receipt.stage0_first_pixels_ms = Date.now() - navigationStart;
    receipt.first_pixels_present = true;
    receipt.interactive_viewport_ms = receipt.stage0_first_pixels_ms;
    receipt.interactive_viewport_under_8s = true;
  }
  log('stage0 displayed-pixel proof: ' + JSON.stringify({
    ...stage0Pixels, elapsed_ms: Date.now() - navigationStart,
    under_8s: receipt.stage0_first_pixels,
  }));
} catch (e) {
  fail('stage0 displayed-pixel screenshot failed: ' + e.message);
}

// A semantic, trusted viewport gesture is the only authority to begin the M7
// transition. The first process must make one origin request for the exact
// content-addressed shard and must reach RESUMED before its queued topology edit
// can alter Blender state.
let coldLifecycle = null, warmLifecycle = null, offlineLifecycle = null;
let originBeforeCold = null, originAfterCold = null, originAfterPrecache = null;
let originAfterWarm = null, originAfterOffline = null;
try {
  originBeforeCold = await transportProof();
  coldLifecycle = await runTwoPhaseSemanticLifecycle('cold-online', null);
  originAfterCold = await transportProof();
  const beforeCount = originBeforeCold.asset_get_counts?.[DEFERRED_PATH] || 0;
  const afterCount = originAfterCold.asset_get_counts?.[DEFERRED_PATH] || 0;
  const exactOriginFetch = afterCount === beforeCount + 1 &&
    coldLifecycle.deferred.responses[0].origin_request_count === afterCount;
  receipt.trusted_semantic_interaction = coldLifecycle.trusted_input_count >= 4;
  receipt.deferred_after_trusted_interaction_exactly_once = exactOriginFetch;
  receipt.two_phase_resumed_state_change =
    coldLifecycle.resumed.native.resumedGeneration === 1 &&
    coldLifecycle.after_scene.meshVertices > coldLifecycle.before_scene.meshVertices;
  if (!exactOriginFetch) fail('cold deferred shard did not hit the origin exactly once');
  log('cold two-phase semantic lifecycle: ' + JSON.stringify({
    interaction: coldLifecycle.interaction_complete_ms,
    beforeCount, afterCount, verts: [coldLifecycle.before_scene.meshVertices,
      coldLifecycle.after_scene.meshVertices],
  }));
} catch (e) {
  fail('cold two-phase semantic lifecycle failed: ' + e.message);
}
if (!receipt.trusted_semantic_interaction) fail('trusted semantic input proof missing');
if (!receipt.deferred_after_trusted_interaction_exactly_once) {
  fail('deferred shard was not requested exactly once after trusted semantic input');
}
if (!receipt.two_phase_resumed_state_change) fail('full two-phase RESUMED/state-change proof missing');

// trigger stage-1 stream + wait for completion
log('triggering stage-1 stream...');
runtimePhase = 'cold-online:stage1';
await page.evaluate(() => window.__bwStage1Load && window.__bwStage1Load());
let st = null;
for (let i = 0; i < 120; i++) { st = await page.evaluate(() => window.__bwStage1); if (st && (st.phase === 'done' || st.phase === 'done-with-errors' || st.phase === 'error')) break; await sleep(500); }
log('stage1 state: ' + JSON.stringify(st));
receipt.stage1_complete = !!st && st.phase === 'done' && !st.error &&
  st.filesDone === st.filesTotal && st.filesTotal > 0 &&
  st.bytesDone === st.bytesTotal && st.bytesTotal > 0;
if (!receipt.stage1_complete) fail('stage-1 did not install every byte/file cleanly: ' + JSON.stringify(st));
const progressProof = await page.evaluate(() => {
  const el = document.getElementById('bw-stage-progress');
  return { phases: window.__bwStage1 && window.__bwStage1.visiblePhases,
           visible: !!el && getComputedStyle(el).display !== 'none' && Number(getComputedStyle(el).opacity) > 0,
           text: el && el.textContent, done: el && el.dataset.bytesDone,
           total: el && el.dataset.bytesTotal };
});
const wantedPhases = ['Downloading assets', 'Installing assets', 'Assets ready'];
receipt.progress_phases_visible = progressProof.visible && /MB/.test(progressProof.text || '') &&
  wantedPhases.every((phase) => (progressProof.phases || []).includes(phase)) &&
  Number(progressProof.done) === Number(progressProof.total) && Number(progressProof.total) > 0;
log('visible progress proof: ' + JSON.stringify(progressProof));
if (!receipt.progress_phases_visible) fail('visible staged phase/MB progress incomplete');

// Bind the staged boot to actual displayed product pixels. Release builds need
// not emit `presentBackbuffer`, so decode compositor screenshots until Blender's
// viewport is varied/non-black. Keep the launch-budget result separate: M7 owns
// functional staging; M8 consumes the measured <=8 s launch gate fail-closed.
try {
  let pixelProof = await screenshotPixelStats();
  const deadline = Date.now() + 60000;
  while (!pixelProof.content && Date.now() < deadline) {
    await sleep(500);
    pixelProof = await screenshotPixelStats();
  }
  receipt.first_pixels_present = receipt.first_pixels_present || pixelProof.content;
  if (pixelProof.content && receipt.interactive_viewport_ms === null) {
    receipt.interactive_viewport_ms = Date.now() - navigationStart;
  }
  receipt.interactive_viewport_under_8s = receipt.stage0_first_pixels &&
    receipt.interactive_viewport_ms !== null && receipt.interactive_viewport_ms <= 8000;
  log(`displayed-pixel proof ${pixelProof.width}x${pixelProof.height} ` +
      `nonBlack=${pixelProof.nonBlack}/${pixelProof.pixelCount} range=${pixelProof.min}..${pixelProof.max} ` +
      `sampledColors=${pixelProof.sampledColors} presentLog=${present.count} ` +
      `interactiveMs=${receipt.interactive_viewport_ms} under8s=${receipt.interactive_viewport_under_8s}`);
  if (!receipt.first_pixels_present) fail('displayed canvas stayed black/static for 60 seconds');
} catch (e) {
  fail('displayed-pixel screenshot proof failed: ' + e.message);
}

// (3b) AFTER stage-1: real bytes + byte-exact vs the packaged slice
const after = await page.evaluate(async (p) => {
  const FS = window.__bwModule.FS;
  const cur = FS.readFile(p);
  const man = await (await fetch('/bin/stage1-manifest.json')).json();
  const ent = man.files.find((f) => f.filename === p);
  const buf = new Uint8Array(await (await fetch('/bin/stage1.data')).arrayBuffer());
  const want = buf.subarray(ent.start, ent.end);
  let eq = cur.length === want.length;
  if (eq) for (let i = 0; i < cur.length; i++) { if (cur[i] !== want[i]) { eq = false; break; } }
  return { size: cur.length, want: want.length, byteExact: eq };
}, PROBE);
log(`deferred ${PROBE} AFTER stage-1: size=${after.size} want=${after.want} byteExact=${after.byteExact}`);
if (after.size === 0) fail('probe file still empty after stage-1');
if (!after.byteExact) fail('streamed bytes != packaged slice (overwrite corruption)');
receipt.stage1_byte_exact = after.size > 0 && after.byteExact;

// (4) post-stage-1 service-worker precache. This is an explicit product gate,
// not merely a registration check: every launch asset must be present in the
// generated versioned cache and the browser-facing progress state must complete.
log('triggering post-stage-1 service-worker precache...');
const sw = await page.evaluate(async () => window.__bwPrecache && window.__bwPrecache());
log('service-worker state: ' + JSON.stringify(sw));
if (!sw || sw.phase !== 'done') fail('service-worker precache did not complete: ' + JSON.stringify(sw));
const deferredCacheKeys = new Map(artifactContract.shippedWasm
  .filter((row) => row.role === 'deferred')
  .map((row) => [`/bin/${row.filename}`, `/bin/${row.filename}?sha256=${row.sha256}`]));
const requiredCachePaths = ['/', ...artifactContract.bundleNames
  .filter((name) => name !== '_headers' && name !== 'service-worker.js' && !name.endsWith('.br'))
  .map((name) => deferredCacheKeys.get(`/${name}`) || `/${name}`)];
const cacheProof = await page.evaluate(async (required) => {
  const names = await caches.keys();
  const prefixNames = names.filter((n) => n.startsWith('blender-web-staged-'));
  const swVersion = window.__bwServiceWorker && window.__bwServiceWorker.version;
  const name = swVersion ? `blender-web-staged-${swVersion}` : null;
  if (!name || prefixNames.length !== 1 || prefixNames[0] !== name) {
    return { names, prefixNames, name, missing: ['<exact-singleton-versioned-cache>'],
      unexpected: [], count: 0 };
  }
  const cache = await caches.open(name);
  const missing = [];
  for (const path of required) if (!(await cache.match(path))) missing.push(path);
  const actual = (await cache.keys()).map((request) => {
    const url = new URL(request.url);
    return url.pathname + url.search;
  }).sort();
  const unexpected = actual.filter((path) => !required.includes(path));
  return { name, names, prefixNames, missing, unexpected, actual, count: actual.length };
}, requiredCachePaths);
log('service-worker cache proof: ' + JSON.stringify(cacheProof));
if (cacheProof.missing.length) fail('service-worker cache missing: ' + cacheProof.missing.join(', '));
if (cacheProof.unexpected.length) fail('service-worker cache has unexpected URLs: ' + cacheProof.unexpected.join(', '));
if (!sw || !sw.version || cacheProof.name !== `blender-web-staged-${sw.version}` ||
    cacheProof.prefixNames.length !== 1) {
  fail('service-worker cache/version mismatch');
}
receipt.service_worker_complete = !!sw && sw.phase === 'done' && !cacheProof.missing.length &&
  !cacheProof.unexpected.length && !!sw.version &&
  cacheProof.name === `blender-web-staged-${sw.version}` && cacheProof.prefixNames.length === 1;
receipt.service_worker_inventory_exact = !cacheProof.missing.length && !cacheProof.unexpected.length &&
  cacheProof.count === requiredCachePaths.length;
try {
  originAfterPrecache = await transportProof();
} catch (e) {
  fail('post-precache origin-counter proof failed: ' + e.message);
}

// (5) capture + license sidecar
try {
  const rect = await page.evaluate(() => { const r = document.getElementById('canvas').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  await page.screenshot({ path: OUT, clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H } });
  fs.writeFileSync(OUT + '.license', 'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  log('captured -> ' + OUT + ' (+ .license)');
} catch (e) { fail('screenshot: ' + e.message); }

// (6) Warm online: the content-addressed shard must come from the exact active
// service worker and produce no second origin GET. The rest of the shell remains
// network-first by policy, so this zero-origin assertion is deliberately scoped
// to the deferred cache-first URL rather than inferred from a cache inventory.
await recordEarlyDiagnostics('cold_online');
log('reloading online for zero-origin deferred-shard proof...');
try {
  pageRun = 'online-warm';
  runtimePhase = 'online-warm:navigation';
  const warmNavigation = await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
  await requireServedBundle(warmNavigation, canonicalBundleDigest(receipt.bundle_artifacts));
  await waitForProductBoot('online-warm');
  warmLifecycle = await runTwoPhaseSemanticLifecycle('online-warm', true);
  originAfterWarm = await transportProof();
  const afterColdCount = originAfterPrecache?.asset_get_counts?.[DEFERRED_PATH];
  const afterWarmCount = originAfterWarm.asset_get_counts?.[DEFERRED_PATH] || 0;
  receipt.online_warm_deferred_zero_origin = Number.isSafeInteger(afterColdCount) &&
    afterWarmCount === afterColdCount;
  receipt.online_warm_deferred_from_service_worker =
    warmLifecycle.deferred.responses.length === 1 &&
    warmLifecycle.deferred.responses[0].from_service_worker === true;
  if (!receipt.online_warm_deferred_zero_origin) {
    fail(`online warm deferred shard reached origin: ${afterColdCount} -> ${afterWarmCount}`);
  }
  if (!receipt.online_warm_deferred_from_service_worker) {
    fail('online warm deferred response was not supplied by the active service worker');
  }
  await recordEarlyDiagnostics('online_warm');
} catch (e) {
  fail('online warm deferred cache proof failed: ' + e.message);
}

// (7) A cache inventory and a warm fetch are still insufficient. Disconnect the
// browser, create a third fresh Blender process, prove semantic pixels + trusted
// interaction, and execute the complete deferred PARK..RESUME lifecycle/state
// change with the shard supplied from cache.
log('reloading with Chromium network offline for cold semantic/deferred proof...');
await ctx.setOffline(true);
const offlineStart = Date.now();
try {
  pageRun = 'offline-cold';
  runtimePhase = 'offline-cold:navigation';
  const offlineNavigation = await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
  await requireServedBundle(offlineNavigation, canonicalBundleDigest(receipt.bundle_artifacts));
  await waitForProductBoot('offline-cold');
  const offline = await page.evaluate(() => ({
    coi: self.crossOriginIsolated === true,
    sab: typeof SharedArrayBuffer !== 'undefined',
    gate: [document.getElementById('canvas').width, document.getElementById('canvas').height],
  }));
  receipt.offline_warm_wm_main_ms = Date.now() - offlineStart;
  if (!offline.coi || !offline.sab) fail('offline cached document lost COOP/COEP isolation');
  if (offline.gate[0] !== W || offline.gate[1] !== H) fail('offline cached gate extent changed');
  receipt.offline_reload_wm_main = offline.coi && offline.sab &&
    offline.gate[0] === W && offline.gate[1] === H;
  offlineLifecycle = await runTwoPhaseSemanticLifecycle('offline-cold', true);
  receipt.offline_cold_semantic_deferred = receipt.offline_reload_wm_main &&
    offlineLifecycle.resumed.native.resumedGeneration === 1 &&
    offlineLifecycle.after_scene.meshVertices > offlineLifecycle.before_scene.meshVertices &&
    offlineLifecycle.deferred.requests.length === 1 &&
    offlineLifecycle.deferred.responses.length === 1 &&
    offlineLifecycle.deferred.responses[0].from_service_worker === true;
  if (!receipt.offline_cold_semantic_deferred) {
    fail('offline cold semantic/deferred lifecycle did not complete from service-worker bytes');
  }
  await recordEarlyDiagnostics('offline_cold');
  log(`offline reload + deferred lifecycle in ${Date.now() - offlineStart} ms: ` +
    JSON.stringify({offline, verts: [offlineLifecycle.before_scene.meshVertices,
      offlineLifecycle.after_scene.meshVertices]}));
} catch (e) {
  fail('offline cold semantic/deferred proof failed: ' + e.message);
}
await ctx.setOffline(false);
try {
  originAfterOffline = await transportProof();
  const warmCount = originAfterWarm?.asset_get_counts?.[DEFERRED_PATH];
  const offlineCount = originAfterOffline.asset_get_counts?.[DEFERRED_PATH];
  if (!Number.isSafeInteger(warmCount) || offlineCount !== warmCount) {
    receipt.offline_cold_semantic_deferred = false;
    fail(`offline deferred lifecycle changed origin count: ${warmCount} -> ${offlineCount}`);
  }
} catch (e) {
  receipt.offline_cold_semantic_deferred = false;
  fail('post-offline origin-counter proof failed: ' + e.message);
}
receipt.external_request_count = externalRequests.length;
if (Object.values(receipt.early_diagnostics).some((value) => value === null)) {
  fail('one or more staged runtime scenarios lack terminal early diagnostics');
}
if (externalRequests.length) fail('external requests escaped bundle: ' + externalRequests.join(', '));
receipt.gpu_error_count = gpuErrs.length;
receipt.page_error_count = pageErrors.length;
if (gpuErrs.length) fail('GPU validation/runtime errors: ' + gpuErrs[0]);
if (pageErrors.length) fail('page errors/crashes: ' + pageErrors[0]);

if (errs.length) { log(`console errors (${errs.length}, incl. known benign inspect->dis / OIIO / multiprocessing debts); first 3:`); errs.slice(0, 3).forEach((e) => console.log('   ! ' + e.slice(0, 140))); }
else log('no console/GPU-validation errors during staged boot');
fs.writeFileSync(OUTDIR + '/verify_console.log', allLines.join('\n'));
receipt.verdict = failed ? 'FAIL' : 'PASS';
receipt.failures = failures;
receipt.cache = cacheProof;
receipt.service_worker = sw;
receipt.split_runtime = {
  deferred_identity: {filename: DEFERRED.filename, bytes: DEFERRED.bytes,
    sha256: DEFERRED.sha256, request_key: DEFERRED_KEY},
  cold_online: coldLifecycle,
  online_warm: warmLifecycle,
  offline_cold: offlineLifecycle,
};
receipt.transport = {
  proof_endpoint: TRANSPORT_PROOF,
  before_cold: originBeforeCold,
  after_cold: originAfterCold,
  after_precache: originAfterPrecache,
  after_online_warm: originAfterWarm,
  after_offline_cold: originAfterOffline,
  deferred_requests: assetRequests.filter((row) => row.url.split('?', 1)[0] === DEFERRED_PATH),
  deferred_responses: assetResponses.filter((row) => row.url.split('?', 1)[0] === DEFERRED_PATH),
};
await ctx.close(); await browser.close();
try {
  revalidateBrowserRuntimeIdentity(runtimeIdentity, identityContract);
}
catch (e) { fail('terminal Chrome runtime identity drift: ' + e.message); }
receipt.verdict = failed ? 'FAIL' : 'PASS';
receipt.failures = failures;
receipt.external_requests = externalRequests;
fs.writeFileSync(OUTDIR + '/verify_staged.json', JSON.stringify(receipt, null, 2) + '\n');
console.log(failed ? '[verify] VERDICT: FAIL' : '[verify] VERDICT: PASS');
process.exit(failed ? 1 : 0);
