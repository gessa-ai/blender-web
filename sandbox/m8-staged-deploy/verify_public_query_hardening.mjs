// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser-free execution contract for the development/public shell seam. The
// full M8 runtime still proves the same attacks in a real browser and product.

import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import * as fs from 'node:fs';
import * as vm from 'node:vm';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const BOOT = join(ROOT, 'platform_web/shell/boot-windowed.js');
const STAGE1 = process.argv[2] ? resolve(process.argv[2]) : join(HERE, 'stage1-loader.js');
const POSITIVE_ONLY = process.argv[3] === '--positive-only';
if (process.argv.length > (POSITIVE_ONLY ? 4 : 3)) {
  throw new Error('usage: verify_public_query_hardening.mjs [stage1-loader.js [--positive-only]]');
}
const MEASURE = join(HERE, 'measure_boot.mjs');
const DEVELOPMENT_SEAM = 'const BW_ALLOW_QUERY_DEV_HOOKS = true;';
const PUBLIC_SEAM = 'const BW_ALLOW_QUERY_DEV_HOOKS = false;';
const CUTOFF = '// DOM handles (hidden diagnostics preserve the boot-windowed.js + rig contract)';
const ATTACK_QUERY = '?pyexpr=query-python&args=--background%20--debug-gpu' +
  '&gate=1x1&keepalive=0&ka_active=999999&ka_idle=999998';

function count(text, needle) {
  return text.split(needle).length - 1;
}

function replaceOnce(text, before, after) {
  assert.equal(count(text, before), 1, `expected one mutation target: ${before}`);
  return text.replace(before, after);
}

function harden(source) {
  assert.equal(count(source, DEVELOPMENT_SEAM), 1, 'development hardening seam must be unique');
  assert.equal(count(source, PUBLIC_SEAM), 0, 'development source already contains public seam');
  const result = source.replace(DEVELOPMENT_SEAM, PUBLIC_SEAM);
  assert.equal(count(result, PUBLIC_SEAM), 1, 'public hardening seam must be unique');
  assert.equal(count(result, DEVELOPMENT_SEAM), 0, 'public source retained development seam');
  return result;
}

function execute(source, search, overrides = {}) {
  const cutoff = source.indexOf(CUTOFF);
  assert.ok(cutoff > 0, 'boot-shell executable prefix cutoff is missing');
  const window = {...overrides};
  const context = vm.createContext({window, location: {search}, URLSearchParams});
  vm.runInContext(source.slice(0, cutoff) + `
    globalThis.__bwContractResult = JSON.stringify({
      allowed: window.__bwDevHooksAllowed,
      python: bootPythonExpr(),
      args: bootExtraArgs(),
      gate: GATE,
      keepalive: KEEPALIVE,
      exportedKeepalive: window.__bwKeepaliveConfig,
    });`, context, {filename: 'boot-windowed.contract.js'});
  return JSON.parse(context.__bwContractResult);
}

function assertPublic(result) {
  assert.equal(result.allowed, false);
  assert.equal(result.python, null);
  assert.deepEqual(result.args, []);
  assert.equal(result.gate, null);
  assert.deepEqual(result.keepalive, {enabled: 1, active: 0, idle: 0});
  assert.deepEqual(result.exportedKeepalive, {enabled: 1, active: 0, idle: 0});
}

const source = fs.readFileSync(BOOT, 'utf8');
assert.equal(count(source, 'const pyexpr = bootPythonExpr();'), 1,
  'boot no longer consumes the guarded Python hook exactly once');
assert.equal(count(source, 'const extraArgs = bootExtraArgs();'), 1,
  'boot no longer consumes the guarded argv hook exactly once');
assert.equal(count(source, 'const GATE = gateMode();'), 1,
  'boot no longer consumes the guarded gate hook exactly once');
assert.equal(count(source, 'const KEEPALIVE = keepaliveConfig();'), 1,
  'boot no longer consumes the guarded keepalive hook exactly once');

const developmentQuery = execute(source, ATTACK_QUERY);
assert.equal(developmentQuery.allowed, true);
assert.equal(developmentQuery.python, 'query-python');
assert.deepEqual(developmentQuery.args, ['--background', '--debug-gpu']);
assert.deepEqual(developmentQuery.gate, {w: 1, h: 1});
assert.deepEqual(developmentQuery.keepalive,
  {enabled: 0, active: 999999, idle: 999998});

const developmentGlobals = execute(source, '', {
  __BW_PYEXPR: 'global-python',
  __BW_ARGS: ['--global-arg'],
  __BW_GATE: '3x4',
  __BW_KEEPALIVE: '0',
});
assert.equal(developmentGlobals.python, 'global-python');
assert.deepEqual(developmentGlobals.args, ['--global-arg']);
assert.deepEqual(developmentGlobals.gate, {w: 3, h: 4});
assert.deepEqual(developmentGlobals.keepalive, {enabled: 0, active: 0, idle: 0});

const publicSource = harden(source);
const publicAttack = execute(publicSource, ATTACK_QUERY, {
  __BW_PYEXPR: 'global-python',
  __BW_ARGS: ['--global-arg'],
  __BW_GATE: '3x4',
  __BW_KEEPALIVE: '0',
});
assertPublic(publicAttack);

let negative = 0;
function reject(name, mutated) {
  try {
    assertPublic(execute(mutated, ATTACK_QUERY, {
      __BW_PYEXPR: 'global-python',
      __BW_ARGS: ['--global-arg'],
      __BW_GATE: '3x4',
      __BW_KEEPALIVE: '0',
    }));
  }
  catch (_) {
    negative += 1;
    return;
  }
  throw new Error(`public query hardening mutation survived: ${name}`);
}

reject('public_literal_reenabled', replaceOnce(publicSource, PUBLIC_SEAM, DEVELOPMENT_SEAM));
reject('public_marker_forged', replaceOnce(publicSource,
  'window.__bwDevHooksAllowed = BW_ALLOW_QUERY_DEV_HOOKS;',
  'window.__bwDevHooksAllowed = true;'));
reject('python_guard_removed', replaceOnce(publicSource,
  'function bootPythonExpr() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;',
  'function bootPythonExpr() {'));
reject('argv_guard_removed', replaceOnce(publicSource,
  'function bootExtraArgs() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return [];',
  'function bootExtraArgs() {'));
reject('gate_guard_removed', replaceOnce(publicSource,
  'function gateMode() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;',
  'function gateMode() {'));
reject('keepalive_guard_removed', replaceOnce(publicSource,
  '  const cfg = { enabled: 1, active: 0, idle: 0 };\n' +
  '  if (!BW_ALLOW_QUERY_DEV_HOOKS) return cfg;',
  '  const cfg = { enabled: 1, active: 0, idle: 0 };'));

assert.equal(negative, 6);

function makeStageEnvironment(stageSource, {
  search = '', devHooksAllowed = false, trustedManual = false, bodyGate = false,
  stream = true, httpFailure = false, dataFailures = [],
  chunks = [[1, 2, 3], [4, 5, 6]], total = 6, manifestFiles = null,
  manifestBootstrap = undefined, bridge = null, initialFiles = {},
  allocationLimit = Number.POSITIVE_INFINITY, oversizedStreamChunkLength = null,
} = {}) {
  const elements = new Map();
  const writes = [];
  const temporaryFiles = new Map();
  const installedFiles = new Map(Object.entries(initialFiles).map(
    ([filename, bytes]) => [filename, Array.from(bytes)]));
  const directoryModes = new Map();
  const timers = [];
  let now = 0;
  let fetchCount = 0;
  let dataFetchCount = 0;
  let arrayBufferCount = 0;
  let largestAllocation = 0;
  const loader = {
    id: 'loader',
    classList: {contains: (name) => name === 'bw-hidden'},
  };
  elements.set(loader.id, loader);

  const document = {
    body: {
      classList: {contains: (name) => bodyGate && name === 'bw-gate'},
      appendChild(element) {
        if (element.id) elements.set(element.id, element);
      },
    },
    createElement(tagName) {
      return {
        tagName, id: '', textContent: '', style: {}, dataset: {}, attributes: {},
        setAttribute(name, value) { this.attributes[name] = String(value); },
        remove() { if (this.id) elements.delete(this.id); },
      };
    },
    getElementById(id) { return elements.get(id) || null; },
  };
  const window = {
    __bwDevHooksAllowed: devHooksAllowed,
    __BW_STAGE1_MANUAL: trustedManual,
    BWFileBridge: bridge,
    __bwModule: {
      FS: {
        stat(filename) {
          return {mode: directoryModes.get(filename) ?? 0o40555};
        },
        chmod(filename, mode) {
          directoryModes.set(filename, mode);
        },
        writeFile(filename, bytes) {
          const slash = filename.lastIndexOf('/');
          const parent = filename.slice(0, slash) || '/';
          if (!((directoryModes.get(parent) ?? 0o40555) & 0o200)) {
            throw new Error(`parent is not writable: ${parent}`);
          }
          const row = {filename, bytes: Array.from(bytes)};
          if (!filename.slice(slash + 1).includes('.bw-stage1-')) {
            throw new Error(`non-transactional write: ${filename}`);
          }
          temporaryFiles.set(filename, row.bytes);
        },
        rename(source, filename) {
          if (!temporaryFiles.has(source)) throw new Error(`missing temporary file: ${source}`);
          const sourceParent = source.slice(0, source.lastIndexOf('/')) || '/';
          const finalParent = filename.slice(0, filename.lastIndexOf('/')) || '/';
          if (sourceParent !== finalParent) throw new Error('cross-directory rename rejected');
          if (!((directoryModes.get(finalParent) ?? 0o40555) & 0o200)) {
            throw new Error(`parent is not writable: ${finalParent}`);
          }
          const bytes = temporaryFiles.get(source);
          installedFiles.set(filename, bytes);
          writes.push({filename, bytes});
          temporaryFiles.delete(source);
        },
        unlink(filename) {
          if (!temporaryFiles.delete(filename)) throw new Error(`missing temporary file: ${filename}`);
        },
        readFile(filename) {
          if (!installedFiles.has(filename)) throw new Error(`missing installed file: ${filename}`);
          return Uint8Array.from(installedFiles.get(filename));
        },
      },
    },
  };
  const manifest = {
    total_bytes: total,
    files: manifestFiles || [
      {filename: '/bw/a', start: 0, end: Math.min(3, total)},
      {filename: '/bw/b', start: Math.min(3, total), end: total},
    ],
  };
  if (manifestBootstrap !== undefined) manifest.bootstrap = manifestBootstrap;
  const fetch = async (url) => {
    fetchCount += 1;
    if (url.endsWith('stage1-manifest.json')) return {json: async () => manifest};
    assert.ok(url.endsWith('stage1.data'));
    const failure = dataFailures[dataFetchCount++] || null;
    if (httpFailure || failure === 'http') {
      const payload = Uint8Array.from(chunks.flat());
      return {ok: false, status: 503, headers: {get: () => null}, body: null,
        arrayBuffer: async () => payload.buffer};
    }
    const responseChunks = failure === 'underflow' ? [[1, 2, 3]] : chunks;
    const payload = Uint8Array.from(responseChunks.flat());
    let chunkIndex = 0;
    return {
      ok: true,
      status: 200,
      headers: {get: (name) => name === 'content-length' ? String(total) : null},
      body: stream ? {
        getReader() {
          return {read: async () => {
            if (failure === 'interrupted' && chunkIndex === 1) {
              throw new Error('stream interrupted');
            }
            if (oversizedStreamChunkLength !== null && chunkIndex++ === 0) {
              return {done: false, value: {
                length: oversizedStreamChunkLength,
                subarray() { throw new Error('oversized chunk was consumed'); },
              }};
            }
            return chunkIndex < responseChunks.length ?
              {done: false, value: Uint8Array.from(responseChunks[chunkIndex++])} : {done: true};
          }};
        },
      } : null,
      arrayBuffer: async () => {
        arrayBufferCount += 1;
        return payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.byteLength);
      },
    };
  };
  const setTimeout = (callback, delay) => {
    timers.push({callback, delay});
    return timers.length;
  };
  const TrackedUint8Array = new Proxy(Uint8Array, {
    construct(target, args) {
      const view = Reflect.construct(target, args, target);
      largestAllocation = Math.max(largestAllocation, view.byteLength);
      if (view.byteLength > allocationLimit) {
        throw new RangeError(`typed-array allocation ${view.byteLength} exceeds ${allocationLimit}`);
      }
      return view;
    },
  });
  const context = vm.createContext({
    window, document, location: {search}, URLSearchParams, Uint8Array: TrackedUint8Array,
    performance: {now: () => (now += 100)}, fetch, setTimeout,
    clearTimeout() {}, console, crypto: webcrypto,
  });
  vm.runInContext(stageSource, context, {filename: 'stage1-loader.contract.js'});
  return {window, elements, writes, timers,
    fetchCount: () => fetchCount, dataFetchCount: () => dataFetchCount,
    arrayBufferCount: () => arrayBufferCount, largestAllocation: () => largestAllocation,
    temporaryFileCount: () => temporaryFiles.size,
    directoryMode: (filename) => directoryModes.get(filename) ?? 0o40555};
}

async function assertStageContract(stageSource) {
  const publicAttack = makeStageEnvironment(stageSource, {
    search: '?stage1=manual&gate=1x1',
  });
  assert.equal(publicAttack.window.__bwStage1.phase, 'idle',
    'public query unexpectedly disabled automatic Stage-1 loading');
  const publicState = await publicAttack.window.__bwStage1Load();
  assert.equal(publicState.phase, 'done');
  assert.equal(publicState.error, null);
  assert.equal(publicState.filesDone, 2);
  assert.equal(publicState.filesTotal, 2);
  assert.equal(publicState.bytesDone, 6);
  assert.equal(publicState.bytesTotal, 6);
  assert.equal(publicState.writableDirectoryCount, 1);
  assert.equal(publicAttack.directoryMode('/bw'), 0o40555);
  assert.deepEqual(Array.from(publicState.visiblePhases),
    ['Downloading assets', 'Installing assets', 'Assets ready']);
  assert.deepEqual(publicAttack.writes, [
    {filename: '/bw/a', bytes: [1, 2, 3]},
    {filename: '/bw/b', bytes: [4, 5, 6]},
  ]);
  const progress = publicAttack.elements.get('bw-stage-progress');
  assert.ok(progress, 'public Stage-1 progress element is missing');
  assert.equal(progress.attributes.role, 'status');
  assert.equal(progress.attributes['aria-live'], 'polite');
  assert.match(progress.textContent, /^Assets ready .* MB$/);
  assert.equal(progress.dataset.bytesDone, '6');
  assert.equal(progress.dataset.bytesTotal, '6');

  const bounded = makeStageEnvironment(stageSource, {
    trustedManual: true,
    chunks: [[1, 2, 3, 4], [5, 6, 7, 8, 9, 10, 11], [12, 13, 14, 15, 16, 17, 18]],
    total: 18,
    manifestFiles: [
      {filename: '/bw/a', start: 0, end: 6},
      {filename: '/bw/b', start: 6, end: 12},
      {filename: '/bw/c', start: 12, end: 18},
    ],
    allocationLimit: 6,
  });
  const boundedState = await bounded.window.__bwStage1Load();
  assert.equal(boundedState.phase, 'done');
  assert.equal(boundedState.peakBufferedBytes, 6);
  assert.equal(boundedState.bufferedBytes, 0);
  assert.equal(boundedState.largestFileBytes, 6);
  assert.equal(boundedState.bytesFetched, 18);
  assert.equal(boundedState.bufferLimitBytes, 16 * 1024 * 1024);
  assert.equal(boundedState.streamChunkLimitBytes, 16 * 1024 * 1024);
  assert.equal(boundedState.transientLimitBytes, 32 * 1024 * 1024);
  assert.equal(boundedState.peakChunkBytes, 7);
  assert.equal(boundedState.peakTransientBytes, 13);
  assert.equal(boundedState.chunkBytes, 0);
  assert.ok(boundedState.peakBufferedBytes <= boundedState.bufferLimitBytes);
  assert.ok(bounded.largestAllocation() <= 6,
    'streaming loader allocated more than one manifest file');
  assert.deepEqual(bounded.writes, [
    {filename: '/bw/a', bytes: [1, 2, 3, 4, 5, 6]},
    {filename: '/bw/b', bytes: [7, 8, 9, 10, 11, 12]},
    {filename: '/bw/c', bytes: [13, 14, 15, 16, 17, 18]},
  ]);
  assert.equal(bounded.temporaryFileCount(), 0);
  assert.equal(bounded.directoryMode('/bw'), 0o40555);

  let fontRefreshCount = 0;
  const stage0Font = Uint8Array.from([66, 87]);
  const stage0FontHash = createHash('sha256').update(stage0Font).digest('hex');
  const restoredFont = Uint8Array.from([70, 79, 78, 84]);
  const restoredFontHash = createHash('sha256').update(restoredFont).digest('hex');
  const bootstrap = makeStageEnvironment(stageSource, {
    trustedManual: true,
    chunks: [Array.from(restoredFont)],
    total: restoredFont.length,
    manifestFiles: [{filename: '/bw/font.woff2', start: 0, end: restoredFont.length}],
    manifestBootstrap: [{
      filename: '/bw/font.woff2',
      stage0_bytes: 2,
      stage0_sha256: stage0FontHash,
      restored_bytes: restoredFont.length,
      restored_sha256: restoredFontHash,
      action: 'reload-interface-fonts',
    }],
    bridge: {
      ready: async () => true,
      refreshInterfaceFonts: async () => {
        fontRefreshCount += 1;
        return {ok: true, fontBytes: restoredFont.length};
      },
    },
    initialFiles: {'/bw/font.woff2': stage0Font},
  });
  const bootstrapState = await bootstrap.window.__bwStage1Load();
  assert.equal(bootstrapState.phase, 'done');
  assert.equal(bootstrapState.bootstrapTotal, 1);
  assert.equal(bootstrapState.bootstrapDone, 1);
  assert.equal(bootstrapState.fontRefresh, 'done');
  assert.equal(fontRefreshCount, 1);
  assert.equal(bootstrap.directoryMode('/bw'), 0o40555);

  const corruptBootstrap = makeStageEnvironment(stageSource, {
    trustedManual: true,
    chunks: [Array.from(restoredFont)],
    total: restoredFont.length,
    manifestFiles: [{filename: '/bw/font.woff2', start: 0, end: restoredFont.length}],
    manifestBootstrap: [{
      filename: '/bw/font.woff2',
      stage0_bytes: 2,
      stage0_sha256: stage0FontHash,
      restored_bytes: restoredFont.length,
      restored_sha256: '0'.repeat(64),
      action: 'reload-interface-fonts',
    }],
    bridge: {ready: async () => true, refreshInterfaceFonts: async () => ({ok: true})},
    initialFiles: {'/bw/font.woff2': stage0Font},
  });
  const corruptBootstrapState = await corruptBootstrap.window.__bwStage1Load();
  assert.equal(corruptBootstrapState.phase, 'done-with-errors');
  assert.match(corruptBootstrapState.error, /restored bootstrap identity mismatch/);
  assert.equal(corruptBootstrapState.fontRefresh, 'error');

  const corruptStage0 = makeStageEnvironment(stageSource, {
    trustedManual: true,
    chunks: [Array.from(restoredFont)],
    total: restoredFont.length,
    manifestFiles: [{filename: '/bw/font.woff2', start: 0, end: restoredFont.length}],
    manifestBootstrap: [{
      filename: '/bw/font.woff2',
      stage0_bytes: stage0Font.length,
      stage0_sha256: stage0FontHash,
      restored_bytes: restoredFont.length,
      restored_sha256: restoredFontHash,
      action: 'reload-interface-fonts',
    }],
    bridge: {ready: async () => true, refreshInterfaceFonts: async () => ({ok: true})},
    initialFiles: {'/bw/font.woff2': [0, 0]},
  });
  const corruptStage0State = await corruptStage0.window.__bwStage1Load();
  assert.equal(corruptStage0State.phase, 'error');
  assert.match(corruptStage0State.error, /Stage-0 bootstrap identity mismatch/);
  assert.equal(corruptStage0.dataFetchCount(), 0);

  const oversizedFile = makeStageEnvironment(stageSource, {
    trustedManual: true,
    chunks: [],
    total: 16 * 1024 * 1024 + 1,
    manifestFiles: [
      {filename: '/bw/oversized', start: 0, end: 16 * 1024 * 1024 + 1},
    ],
  });
  const oversizedFileState = await oversizedFile.window.__bwStage1Load();
  assert.equal(oversizedFileState.phase, 'error');
  assert.match(oversizedFileState.error, /buffer limit is 16777216/);
  assert.equal(oversizedFile.dataFetchCount(), 0);
  assert.equal(oversizedFile.writes.length, 0);

  const oversizedFallback = makeStageEnvironment(stageSource, {
    trustedManual: true,
    stream: false,
    chunks: [],
    total: 16 * 1024 * 1024 + 2,
    manifestFiles: [
      {filename: '/bw/a', start: 0, end: 8 * 1024 * 1024 + 1},
      {filename: '/bw/b', start: 8 * 1024 * 1024 + 1, end: 16 * 1024 * 1024 + 2},
    ],
  });
  const oversizedFallbackState = await oversizedFallback.window.__bwStage1Load();
  assert.equal(oversizedFallbackState.phase, 'error');
  assert.match(oversizedFallbackState.error, /streaming response required/);
  assert.equal(oversizedFallback.arrayBufferCount(), 0);
  assert.equal(oversizedFallback.writes.length, 0);

  const oversizedChunk = makeStageEnvironment(stageSource, {
    trustedManual: true,
    oversizedStreamChunkLength: 16 * 1024 * 1024 + 1,
  });
  const oversizedChunkState = await oversizedChunk.window.__bwStage1Load();
  assert.equal(oversizedChunkState.phase, 'error');
  assert.match(oversizedChunkState.error, /response chunk 16777217 exceeds limit 16777216/);
  assert.equal(oversizedChunk.writes.length, 0);

  const developmentManual = makeStageEnvironment(stageSource, {
    search: '?stage1=manual', devHooksAllowed: true,
  });
  assert.equal(developmentManual.window.__bwStage1.phase, 'manual');
  const trustedManual = makeStageEnvironment(stageSource, {trustedManual: true});
  assert.equal(trustedManual.window.__bwStage1.phase, 'manual');

  const trustedGate = makeStageEnvironment(stageSource, {bodyGate: true});
  const gateState = await trustedGate.window.__bwStage1Load();
  assert.equal(gateState.phase, 'done');
  assert.deepEqual(Array.from(gateState.visiblePhases), []);
  assert.equal(trustedGate.elements.has('bw-stage-progress'), false);

  const fallback = makeStageEnvironment(stageSource, {stream: false});
  const fallbackState = await fallback.window.__bwStage1Load();
  assert.equal(fallbackState.phase, 'done');
  assert.equal(fallbackState.bytesDone, 6);

  const fallbackUnderflow = makeStageEnvironment(stageSource, {
    stream: false, chunks: [[1, 2, 3]],
  });
  const fallbackUnderflowState = await fallbackUnderflow.window.__bwStage1Load();
  assert.equal(fallbackUnderflowState.phase, 'error');
  assert.match(fallbackUnderflowState.error, /stage1\.data size 3 != 6/);
  assert.equal(fallbackUnderflow.writes.length, 0);
  assert.ok(!Array.from(fallbackUnderflowState.visiblePhases).includes('Assets ready'));

  const fallbackOverflow = makeStageEnvironment(stageSource, {
    stream: false, chunks: [[1, 2, 3, 4, 5, 6, 7]],
  });
  const fallbackOverflowState = await fallbackOverflow.window.__bwStage1Load();
  assert.equal(fallbackOverflowState.phase, 'error');
  assert.match(fallbackOverflowState.error, /stage1\.data size 7 != 6/);
  assert.equal(fallbackOverflow.writes.length, 0);
  assert.ok(!Array.from(fallbackOverflowState.visiblePhases).includes('Assets ready'));

  const spanOverflow = makeStageEnvironment(stageSource, {
    manifestFiles: [
      {filename: '/bw/a', start: 0, end: 3},
      {filename: '/bw/b', start: 3, end: 7},
    ],
  });
  const spanOverflowState = await spanOverflow.window.__bwStage1Load();
  assert.equal(spanOverflowState.phase, 'error');
  assert.match(spanOverflowState.error, /stage1 manifest span 1 is out of bounds/);
  assert.equal(spanOverflow.writes.length, 0);

  const spanGap = makeStageEnvironment(stageSource, {
    manifestFiles: [
      {filename: '/bw/a', start: 0, end: 2},
      {filename: '/bw/b', start: 3, end: 6},
    ],
  });
  const spanGapState = await spanGap.window.__bwStage1Load();
  assert.equal(spanGapState.phase, 'error');
  assert.match(spanGapState.error, /stage1 manifest span 1 starts at 3 instead of 2/);
  assert.equal(spanGap.writes.length, 0);

  const spanTail = makeStageEnvironment(stageSource, {
    manifestFiles: [
      {filename: '/bw/a', start: 0, end: 3},
      {filename: '/bw/b', start: 3, end: 5},
    ],
  });
  const spanTailState = await spanTail.window.__bwStage1Load();
  assert.equal(spanTailState.phase, 'error');
  assert.match(spanTailState.error, /stage1 manifest spans end at 5 instead of 6/);
  assert.equal(spanTail.writes.length, 0);

  const concurrent = makeStageEnvironment(stageSource, {trustedManual: true});
  const firstConcurrent = concurrent.window.__bwStage1Load();
  const secondConcurrent = concurrent.window.__bwStage1Load();
  assert.strictEqual(secondConcurrent, firstConcurrent,
    'concurrent Stage-1 calls did not share one in-flight Promise');
  assert.equal((await firstConcurrent).phase, 'done');
  assert.equal(concurrent.dataFetchCount(), 1);

  const transientHttp = makeStageEnvironment(stageSource, {
    trustedManual: true, dataFailures: ['http'],
  });
  const transientHttpState = await transientHttp.window.__bwStage1Load();
  assert.equal(transientHttpState.phase, 'done');
  assert.equal(transientHttpState.error, null);
  assert.equal(transientHttpState.attempt, 2);
  assert.equal(transientHttp.dataFetchCount(), 2);
  assert.equal(transientHttp.writes.length, 2);
  assert.ok(Array.from(transientHttpState.visiblePhases).includes('Retrying assets'));
  assert.equal(Array.from(transientHttpState.visiblePhases).at(-1), 'Assets ready');

  const transientStream = makeStageEnvironment(stageSource, {
    trustedManual: true, dataFailures: ['interrupted'],
  });
  const transientStreamState = await transientStream.window.__bwStage1Load();
  assert.equal(transientStreamState.phase, 'done');
  assert.equal(transientStreamState.error, null);
  assert.equal(transientStreamState.attempt, 2);
  assert.equal(transientStream.dataFetchCount(), 2);
  assert.deepEqual(transientStream.writes, [
    {filename: '/bw/a', bytes: [1, 2, 3]},
    {filename: '/bw/b', bytes: [4, 5, 6]},
  ]);

  const httpError = makeStageEnvironment(stageSource, {httpFailure: true});
  const httpState = await httpError.window.__bwStage1Load();
  assert.equal(httpState.phase, 'error');
  assert.match(httpState.error, /stage1\.data HTTP 503/);
  assert.equal(httpState.attempt, 3);
  assert.equal(httpState.retryable, true);
  assert.equal(httpError.dataFetchCount(), 3,
    'persistent failure did not stop at the bounded automatic-attempt ceiling');
  assert.equal(httpError.writes.length, 0);

  const explicitRetry = makeStageEnvironment(stageSource, {
    trustedManual: true, dataFailures: ['http', 'http', 'http'],
  });
  const exhaustedState = await explicitRetry.window.__bwStage1Load();
  assert.equal(exhaustedState.phase, 'error');
  assert.equal(exhaustedState.attempt, 3);
  const recoveredState = await explicitRetry.window.__bwStage1Load();
  assert.equal(recoveredState.phase, 'done');
  assert.equal(recoveredState.error, null);
  assert.equal(recoveredState.attempt, 1);
  assert.equal(explicitRetry.dataFetchCount(), 4);
  assert.equal(explicitRetry.writes.length, 2);

  const overflow = makeStageEnvironment(stageSource, {chunks: [[1, 2, 3, 4, 5, 6, 7]]});
  const overflowState = await overflow.window.__bwStage1Load();
  assert.equal(overflowState.phase, 'error');
  assert.match(overflowState.error, /stage1\.data exceeds manifest size/);
  assert.equal(overflow.writes.length, 0);

  const underflow = makeStageEnvironment(stageSource, {chunks: [[1, 2, 3]]});
  const underflowState = await underflow.window.__bwStage1Load();
  assert.equal(underflowState.phase, 'error');
  assert.match(underflowState.error, /stage1\.data size 3 != 6/);
  assert.equal(underflow.writes.length, 0);
}

const stageSource = fs.readFileSync(STAGE1, 'utf8');
await assertStageContract(stageSource);

if (POSITIVE_ONLY) {
  console.log('M8_PUBLIC_QUERY_HARDENING_MINIFIED_PASS positive=3 ' +
    'python=off argv=off controls=off stage1_positive=23 recovery=4 progress=visible memory=bounded');
  process.exit(0);
}

let stageNegative = 0;
async function rejectStage(name, mutated) {
  try {
    await assertStageContract(mutated);
  }
  catch (_) {
    stageNegative += 1;
    return;
  }
  throw new Error(`Stage-1 loader mutation survived: ${name}`);
}

await rejectStage('query_marker_forged', replaceOnce(stageSource,
  'const queryDevHooks = window.__bwDevHooksAllowed === true;',
  'const queryDevHooks = true;'));
await rejectStage('gate_query_guard_removed', replaceOnce(stageSource,
  '(queryDevHooks && new URLSearchParams(location.search).has("gate"))',
  'new URLSearchParams(location.search).has("gate")'));
await rejectStage('manual_query_guard_removed', replaceOnce(stageSource,
  'if (queryDevHooks && new URLSearchParams(location.search).get("stage1") === "manual") manual = true;',
  'if (new URLSearchParams(location.search).get("stage1") === "manual") manual = true;'));
await rejectStage('trusted_manual_removed', replaceOnce(stageSource,
  'let manual = window.__BW_STAGE1_MANUAL === true;', 'let manual = false;'));
await rejectStage('http_status_ignored', replaceOnce(stageSource,
  'if (!resp.ok) throw new Error("stage1.data HTTP " + resp.status);',
  'if (false && !resp.ok) throw new Error("stage1.data HTTP " + resp.status);'));
await rejectStage('stream_overflow_ignored', replaceOnce(stageSource,
  'if (offset + value.length > expected) throw new Error("stage1.data exceeds manifest size");',
  'if (false && offset + value.length > expected) throw new Error("stage1.data exceeds manifest size");'));
await rejectStage('stream_underflow_ignored', replaceOnce(stageSource,
  'if (offset !== expected) throw new Error("stage1.data size " + offset + " != " + expected);',
  'if (false && offset !== expected) throw new Error("stage1.data size " + offset + " != " + expected);'));
await rejectStage('fallback_size_ignored', replaceOnce(stageSource,
  'if (fallback.length !== expected) {', 'if (false && fallback.length !== expected) {'));
await rejectStage('manifest_bounds_ignored', replaceOnce(stageSource,
  '      if (!f || !Number.isSafeInteger(f.start) || !Number.isSafeInteger(f.end) ||\n' +
  '          f.start < 0 || f.end < f.start || f.end > expected) {',
  '      if (false && (!f || !Number.isSafeInteger(f.start) || !Number.isSafeInteger(f.end) ||\n' +
  '          f.start < 0 || f.end < f.start || f.end > expected)) {'));
await rejectStage('manifest_contiguity_ignored', replaceOnce(stageSource,
  'if (f.start !== cursor) {', 'if (false && f.start !== cursor) {'));
await rejectStage('manifest_coverage_ignored', replaceOnce(stageSource,
  'if (cursor !== expected) {', 'if (false && cursor !== expected) {'));
await rejectStage('installed_byte_accounting_removed', replaceOnce(stageSource,
  'state.bytesDone += (f.end - f.start);', 'state.bytesDone += 0;'));
await rejectStage('single_flight_removed', replaceOnce(stageSource,
  'if (inFlight) return inFlight;', 'if (false && inFlight) return inFlight;'));
await rejectStage('automatic_retry_removed', replaceOnce(stageSource,
  'const MAX_ATTEMPTS = 3;', 'const MAX_ATTEMPTS = 1;'));
await rejectStage('retry_release_removed', replaceOnce(stageSource,
  'if (inFlight === operation) inFlight = null;',
  'if (false && inFlight === operation) inFlight = null;'));
await rejectStage('retry_error_reset_removed', replaceOnce(stageSource,
  '    state.error = null;\n  }\n\n  let stagingGeneration',
  '  }\n\n  let stagingGeneration'));
await rejectStage('file_buffer_ceiling_removed', replaceOnce(stageSource,
  'if (fileBytes > MAX_BUFFERED_FILE_BYTES) {',
  'if (false && fileBytes > MAX_BUFFERED_FILE_BYTES) {'));
await rejectStage('fallback_ceiling_removed', replaceOnce(stageSource,
  'if (expected > MAX_BUFFERED_FILE_BYTES) {',
  'if (false && expected > MAX_BUFFERED_FILE_BYTES) {'));
await rejectStage('whole_payload_reallocated', replaceOnce(stageSource,
  'fileBuffer = new Uint8Array(fileBytes);',
  'fileBuffer = new Uint8Array(expected);'));
await rejectStage('same_directory_staging_removed', replaceOnce(stageSource,
  'return path.parent + "/." + path.basename + ".bw-stage1-" + generation + "-" + index;',
  'return "/tmp/.bw-stage1-" + generation + "-" + index;'));
await rejectStage('directory_write_enable_removed', replaceOnce(stageSource,
  'FS.chmod(parent, mode | 0o300);',
  'FS.chmod(parent, mode);'));
await rejectStage('directory_mode_restore_removed', replaceOnce(stageSource,
  '    try { restoreDirectoryModes(FS, originalModes); }\n' +
  '    catch (modeError) {\n' +
  '      if (!state.error) state.error = "permission restore: " +',
  '    try { originalModes.clear(); }\n' +
  '    catch (modeError) {\n' +
  '      if (!state.error) state.error = "permission restore: " +'));
await rejectStage('bootstrap_identity_check_removed', replaceOnce(stageSource,
  'if (restored.length !== row.restored_bytes || digest !== row.restored_sha256) {',
  'if (false && (restored.length !== row.restored_bytes || digest !== row.restored_sha256)) {'));
await rejectStage('stage0_bootstrap_identity_check_removed', replaceOnce(stageSource,
  'if (stage0.length !== row.stage0_bytes || digest !== row.stage0_sha256) {',
  'if (false && (stage0.length !== row.stage0_bytes || digest !== row.stage0_sha256)) {'));
await rejectStage('bootstrap_font_refresh_removed', replaceOnce(stageSource,
  'const ack = await bridge.refreshInterfaceFonts();',
  'const ack = {ok: true, fontBytes: row.restored_bytes};'));
await rejectStage('stream_chunk_ceiling_removed', replaceOnce(stageSource,
  'if (bytes > MAX_STREAM_CHUNK_BYTES) {',
  'if (false && bytes > MAX_STREAM_CHUNK_BYTES) {'));
await rejectStage('transient_peak_accounting_removed', replaceOnce(stageSource,
  'state.peakTransientBytes = Math.max(state.peakTransientBytes, transient);',
  'state.peakTransientBytes += 0;'));

assert.equal(stageNegative, 27);
const measureSource = fs.readFileSync(MEASURE, 'utf8');
assert.equal(count(measureSource, 'window.__BW_STAGE1_MANUAL = true;'), 2,
  'cold and warm timing contexts must install the trusted Stage-1 manual control');
assert.equal(count(measureSource, 'stage1=manual'), 0,
  'timing harness still relies on a public query-controlled Stage-1 hook');
console.log('M8_PUBLIC_QUERY_HARDENING_CONTRACT_PASS positive=3 negative=6 ' +
  'python=off argv=off controls=off stage1_positive=23 stage1_negative=27 recovery=4 ' +
  'progress=visible memory=bounded stage1_query_controls=off trusted_measurement_contexts=2');
