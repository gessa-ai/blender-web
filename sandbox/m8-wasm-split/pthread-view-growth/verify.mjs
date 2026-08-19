// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import { createHash } from 'crypto';
import { createRequire } from 'module';
import { createServer } from 'net';
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { spawn, spawnSync } from 'child_process';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '..', '..', '..');
const label = process.argv[2];
if (!label || !/^[a-z0-9][a-z0-9._-]*$/i.test(label)) throw new Error('safe label required');
const out = join(here, 'evidence', label);
if (existsSync(out)) throw new Error(`refusing overwrite: ${out}`);
mkdirSync(out, { recursive: true });

const sha = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
const relative = (path) => path.startsWith(repo) ? path.slice(repo.length + 1) : path;
const artifact = (path) => ({ path:relative(path), bytes:statSync(path).size, sha256:sha(path) });
const artifactIfPresent = (path) => existsSync(path) ? artifact(path) : null;
const occurrences = (source, needle) => source.split(needle).length - 1;
const writeExclusive = (path, value) => writeFileSync(path, value, { flag:'wx' });

const finalizer = join(repo, 'scripts/finalize-wasm-split.py');
const htmlSource = join(here, 'index.html');
const observerSource = join(here, 'gsab-observer.js');
const helperFixture = join(here, 'helper.fixture.js');
const productionTransformTest = join(repo, 'sandbox/m8-wasm-split/test_shared_memory_view_refresh.py');
const driver = fileURLToPath(import.meta.url);
const serverScript = join(repo, 'sandbox/m8-wasm-split/serve_split.py');
const html = join(out, 'index.html');
const observer = join(out, 'gsab-observer.js');
const helper = join(out, 'helper.js');
const serverLog = join(out, 'server.jsonl');
const transformStdout = join(out, 'transform.stdout');
const transformStderr = join(out, 'transform.stderr');
const productionTestStdout = join(out, 'production-transform-test.stdout');
const productionTestStderr = join(out, 'production-transform-test.stderr');

copyFileSync(htmlSource, html);
copyFileSync(observerSource, observer);
copyFileSync(helperFixture, helper);

const transformProgram = String.raw`
import importlib.util, json, pathlib, sys
finalizer, target = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("finalize_wasm_split", finalizer)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.patch_shared_memory_view_refresh(target), sort_keys=True))
`;
const transformCommand = ['python3', '-c', transformProgram, finalizer, helper];
const productionTestCommand = ['python3', productionTransformTest];

let server = null;
let browser = null;
let port = null;
let headers = null;
let result = null;
let browserFacts = null;
let helperFacts = null;
let pageErrors = [];
let serverStdout = '';
let serverStderr = '';
let failure = null;

try {
  const productionTest = spawnSync(productionTestCommand[0], productionTestCommand.slice(1),
    { cwd:repo, encoding:'utf8' });
  writeExclusive(productionTestStdout, productionTest.stdout || '');
  writeExclusive(productionTestStderr, productionTest.stderr || '');
  if (productionTest.status !== 0 ||
      !productionTest.stdout.includes(
        'growable fixed view, replaced buffer, length-tracking no-op + 5 negative PASS')) {
    throw new Error(`production transform fixture failed ${productionTest.status}`);
  }
  const transformed = spawnSync(transformCommand[0], transformCommand.slice(1), { cwd:repo, encoding:'utf8' });
  writeExclusive(transformStdout, transformed.stdout || '');
  writeExclusive(transformStderr, transformed.stderr || '');
  if (transformed.status !== 0) throw new Error(`helper transformation failed ${transformed.status}`);
  const transformReceipt = JSON.parse(transformed.stdout);
  const helperSource = readFileSync(helper, 'utf8');
  const refreshMarker = 'BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1';
  const guardMarker = 'BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1';
  const exactHelper = 'function growMemViews(){/*' + refreshMarker +
    '*/var b=wasmMemory.buffer;if(b!=HEAP8.buffer||b.byteLength!=HEAP8.byteLength){updateMemoryViews()}}';
  const exactGuard = 'if(HEAP8?.buffer?.growable&&HEAP8.byteLength==getMemoryBuffer().byteLength){/*' +
    guardMarker + '*/return}';
  helperFacts = {
    transformReceipt,
    refreshMarkerCount:occurrences(helperSource, refreshMarker),
    guardMarkerCount:occurrences(helperSource, guardMarker),
    refreshAnchorCount:occurrences(helperSource,
      'function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){updateMemoryViews()}}'),
    guardAnchorCount:occurrences(helperSource, 'if(HEAP8?.buffer?.growable)return;'),
    exactHelperCount:occurrences(helperSource, exactHelper),
    exactGuardCount:occurrences(helperSource, exactGuard),
    identityPredicateCount:occurrences(helperSource, 'b!=HEAP8.buffer'),
    lengthPredicateCount:occurrences(helperSource, 'b.byteLength!=HEAP8.byteLength'),
    growableLengthGuardCount:occurrences(
      helperSource,
      'HEAP8?.buffer?.growable&&HEAP8.byteLength==getMemoryBuffer().byteLength'),
  };
  if (transformReceipt.contract !== 'shared-memory-fixed-view-refresh-v2' ||
      transformReceipt.refresh_anchor_count_before !== 1 ||
      transformReceipt.refresh_anchor_count_after !== 0 ||
      transformReceipt.refresh_marker_count_after !== 1 ||
      transformReceipt.refresh_replacement_count_after !== 1 ||
      transformReceipt.guard_anchor_count_before !== 1 ||
      transformReceipt.guard_anchor_count_after !== 0 ||
      transformReceipt.guard_marker_count_after !== 1 ||
      transformReceipt.guard_replacement_count_after !== 1 ||
      helperFacts.refreshMarkerCount !== 1 || helperFacts.guardMarkerCount !== 1 ||
      helperFacts.refreshAnchorCount !== 0 || helperFacts.guardAnchorCount !== 0 ||
      helperFacts.exactHelperCount !== 1 || helperFacts.exactGuardCount !== 1 ||
      helperFacts.identityPredicateCount !== 1 || helperFacts.lengthPredicateCount !== 1 ||
      helperFacts.growableLengthGuardCount !== 1) {
    throw new Error(`invalid transformed helper contract: ${JSON.stringify(helperFacts)}`);
  }
  const observerText = readFileSync(observer, 'utf8');
  if (occurrences(observerText, 'new SharedArrayBuffer(initialBytes, {maxByteLength:finalBytes})') !== 1 ||
      occurrences(observerText, 'buffer.grow(grownBytes)') !== 1 ||
      occurrences(observerText, 'buffer.grow(finalBytes)') !== 1 ||
      occurrences(observerText, 'function oldUpdateMemoryViews()') !== 1 ||
      occurrences(observerText, 'function oldIdentityOnlyGrowMemViews()') !== 1 ||
      occurrences(observerText, 'importScripts("helper.js")') !== 1) {
    throw new Error('growable-SAB product-path source contract mismatch');
  }

  port = await new Promise((resolvePort, reject) => {
    const socket = createServer();
    socket.once('error', reject);
    socket.listen(0, '127.0.0.1', () => {
      const value = socket.address().port;
      socket.close(() => resolvePort(value));
    });
  });
  server = spawn('python3', [serverScript, String(port), out, serverLog, '--identity-root', out],
    { cwd:repo, stdio:['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', (chunk) => { serverStdout += String(chunk); });
  server.stderr.on('data', (chunk) => { serverStderr += String(chunk); });
  let ready = false;
  for (let i = 0; i < 100 && !ready; i++) {
    if (server.exitCode !== null) throw new Error(`server exited ${server.exitCode}: ${serverStderr}`);
    try { const response = await fetch(`http://127.0.0.1:${port}/index.html`); ready = response.ok; }
    catch {}
    if (!ready) await new Promise((resolveWait) => setTimeout(resolveWait, 25));
  }
  if (!ready) throw new Error('server readiness timeout');

  const require = createRequire(join('/Users/paws/plushly/game-platform/node_modules', 'package.json'));
  const chromium = require('playwright').chromium;
  const executable = chromium.executablePath();
  browser = await chromium.launch({ headless:true });
  browserFacts = { version:browser.version(), executable:artifact(executable) };
  const page = await browser.newPage();
  page.on('pageerror', (error) => pageErrors.push({
    name:error.name, message:error.message, stack:error.stack || null,
  }));
  const response = await page.goto(`http://127.0.0.1:${port}/index.html`,
    { waitUntil:'domcontentloaded', timeout:30000 });
  headers = await response.allHeaders();
  await page.waitForFunction(() => window.__bwViewGrowth, null, { timeout:30000 });
  result = await page.evaluate(() => window.__bwViewGrowth);
} catch (error) {
  failure = { name:error?.name || 'Error', message:String(error?.message || error), stack:error?.stack || null };
} finally {
  if (browser) await browser.close();
  if (server && server.exitCode === null) {
    server.kill('SIGTERM');
    await new Promise((resolveExit) => server.once('exit', resolveExit));
  }
}

writeExclusive(join(out, 'server.stdout'), serverStdout);
writeExclusive(join(out, 'server.stderr'), serverStderr);

const allLengthsEqual = (lengths, expected) => lengths &&
  Object.keys(lengths).length === 10 && Object.values(lengths).every((value) => value === expected);
const zeroCounters = (row) => row?.calls === 0 && row?.earlyReturns === 0 &&
  row?.rebuilds === 0 && row?.returns === 0;
const oneRebuild = (row) => row?.calls === 1 && row?.earlyReturns === 0 &&
  row?.rebuilds === 1 && row?.returns === 1;
const twoRebuilds = (row) => row?.calls === 2 && row?.earlyReturns === 0 &&
  row?.rebuilds === 2 && row?.returns === 2;
const fixedBufferFacts = (row, bytes) => row?.bytes === bytes && row?.growable === false &&
  row?.maxBytes === bytes && row?.shared === true;
const legacyCrossWorkerPass = failure === null && pageErrors.length === 0 && result && !result.fatal &&
  helperFacts?.transformReceipt?.contract === 'shared-memory-fixed-view-refresh-v1' &&
  helperFacts.markerCount === 1 && helperFacts.anchorCount === 0 && helperFacts.exactHelperCount === 1 &&
  helperFacts.identityPredicateCount === 1 && helperFacts.lengthPredicateCount === 1 &&
  result.crossOriginIsolated === true && result.pageSharedBuffer === true &&
  result.configuredPages?.initialPages === 8192 && result.configuredPages?.maximumPages === 32768 &&
  result.configuredPages?.firstGrowthPages === 1639 && result.configuredPages?.secondGrowthPages === 3351 &&
  fixedBufferFacts(result.growerInitialized?.state?.memoryBuffer, 536870912) &&
  result.growerInitialized?.state?.heap8Bytes === 536870912 &&
  zeroCounters(result.growerInitialized?.state?.counters) &&
  fixedBufferFacts(result.observerInitialized?.state?.memoryBuffer, 536870912) &&
  fixedBufferFacts(result.observerInitialized?.state?.heap8Buffer, 536870912) &&
  result.observerInitialized?.state?.memorySameAsHeap8 === true &&
  result.observerInitialized?.state?.memorySameAsTracked === true &&
  result.observerInitialized?.state?.heap8Bytes === 536870912 &&
  result.observerInitialized?.state?.allViewsUseMemoryBuffer === true &&
  allLengthsEqual(result.observerInitialized?.state?.viewBytes, 536870912) &&
  zeroCounters(result.observerInitialized?.state?.counters) &&
  result.firstGrowth?.pages === 1639 && result.firstGrowth?.previousPages === 8192 &&
  fixedBufferFacts(result.firstGrowth?.before?.memoryBuffer, 536870912) &&
  result.firstGrowth?.before?.heap8Bytes === 536870912 &&
  result.firstGrowth?.before?.memorySameAsHeap8 === true &&
  result.firstGrowth?.before?.memorySameAsTracked === true &&
  zeroCounters(result.firstGrowth?.before?.counters) &&
  fixedBufferFacts(result.firstGrowth?.after?.memoryBuffer, 644284416) &&
  result.firstGrowth?.after?.heap8Bytes === 644284416 &&
  result.firstGrowth?.after?.memorySameAsHeap8 === true &&
  result.firstGrowth?.after?.memorySameAsTracked === false &&
  oneRebuild(result.firstGrowth?.after?.counters) &&
  fixedBufferFacts(result.synchronized?.before?.memoryBuffer, 644284416) &&
  result.synchronized?.before?.heap8Bytes === 536870912 &&
  result.synchronized?.before?.memorySameAsHeap8 === false &&
  fixedBufferFacts(result.synchronized?.before?.heap8Buffer, 536870912) &&
  zeroCounters(result.synchronized?.before?.counters) &&
  fixedBufferFacts(result.synchronized?.afterUpdate?.memoryBuffer, 644284416) &&
  fixedBufferFacts(result.synchronized?.afterUpdate?.heap8Buffer, 644284416) &&
  result.synchronized?.afterUpdate?.heap8Bytes === 644284416 &&
  result.synchronized?.afterUpdate?.allViewsUseMemoryBuffer === true &&
  allLengthsEqual(result.synchronized?.afterUpdate?.viewBytes, 644284416) &&
  oneRebuild(result.synchronized?.afterUpdate?.counters) &&
  result.synchronized?.tracked?.memorySameAsTracked === true &&
  zeroCounters(result.synchronized?.countersAfterReset) &&
  result.secondGrowth?.pages === 3351 && result.secondGrowth?.previousPages === 9831 &&
  fixedBufferFacts(result.secondGrowth?.before?.memoryBuffer, 644284416) &&
  result.secondGrowth?.before?.heap8Bytes === 644284416 &&
  result.secondGrowth?.before?.memorySameAsHeap8 === true &&
  result.secondGrowth?.before?.memorySameAsTracked === true &&
  oneRebuild(result.secondGrowth?.before?.counters) &&
  fixedBufferFacts(result.secondGrowth?.after?.memoryBuffer, 863895552) &&
  result.secondGrowth?.after?.heap8Bytes === 863895552 &&
  result.secondGrowth?.after?.memorySameAsHeap8 === true &&
  result.secondGrowth?.after?.memorySameAsTracked === false &&
  twoRebuilds(result.secondGrowth?.after?.counters) &&
  result.observed?.before?.memorySameAsTracked === true &&
  result.observed?.before?.memorySameAsHeap8 === true &&
  fixedBufferFacts(result.observed?.before?.memoryBuffer, 863895552) &&
  fixedBufferFacts(result.observed?.before?.heap8Buffer, 863895552) &&
  result.observed?.before?.heap8Bytes === 644284416 &&
  result.observed?.before?.heap32Length === 161071104 &&
  allLengthsEqual(result.observed?.before?.viewBytes, 644284416) && zeroCounters(result.observed?.before?.counters) &&
  result.observed?.afterControl?.memorySameAsTracked === true &&
  result.observed?.afterControl?.heap8Bytes === 644284416 &&
  fixedBufferFacts(result.observed?.afterControl?.memoryBuffer, 863895552) &&
  fixedBufferFacts(result.observed?.afterControl?.heap8Buffer, 863895552) &&
  zeroCounters(result.observed?.afterControl?.counters) &&
  result.observed?.controlError?.name === 'RangeError' &&
  /atomic access index/i.test(result.observed.controlError.message) &&
  result.highIndex === 161071104 && result.highIndex < 215973888 &&
  fixedBufferFacts(result.observed?.afterRefresh?.memoryBuffer, 863895552) &&
  result.observed?.afterRefresh?.heap8Bytes === 863895552 &&
  result.observed?.afterRefresh?.heap32Length === 215973888 &&
  result.observed?.afterRefresh?.allViewsUseMemoryBuffer === true &&
  allLengthsEqual(result.observed?.afterRefresh?.viewBytes, 863895552) &&
  oneRebuild(result.observed?.afterRefresh?.counters) &&
  result.observed?.loaded === result.nonce &&
  JSON.stringify(result.observed?.afterNoop?.counters) === JSON.stringify(result.observed?.afterRefresh?.counters) &&
  result.observed?.afterNoop?.memorySameAsTracked === true &&
  result.observed?.afterNoop?.memorySameAsHeap8 === true &&
  result.observed?.afterNoop?.heap8Bytes === 863895552 &&
  result.observed?.afterNoop?.heap32Length === 215973888 &&
  result.observed?.afterNoop?.allViewsUseMemoryBuffer === true &&
  allLengthsEqual(result.observed?.afterNoop?.viewBytes, 863895552) &&
  result.ackCounts?.growerInitialized === 1 && result.ackCounts?.observerInitialized === 1 &&
  result.ackCounts?.firstGrown === 1 && result.ackCounts?.observerSynced === 1 &&
  result.ackCounts?.secondGrown === 1 && result.ackCounts?.observerResult === 1 &&
  result.ackCounts?.unexpected === 0 &&
  headers?.['cross-origin-opener-policy'] === 'same-origin' &&
  headers?.['cross-origin-embedder-policy'] === 'require-corp' &&
  headers?.['cross-origin-resource-policy'] === 'same-origin';

const oneEarlyReturn = (row) => row?.calls === 1 && row?.earlyReturns === 1 &&
  row?.rebuilds === 0 && row?.returns === 1;
const growableState = (row, bufferBytes, viewBytes) =>
  row?.memoryBufferBytes === bufferBytes && row?.memoryBufferGrowable === true &&
  row?.memoryBufferMaxBytes === 196608 && row?.memoryBufferShared === true &&
  row?.heap8BufferBytes === bufferBytes && row?.heap8BufferGrowable === true &&
  row?.heap8BufferMaxBytes === 196608 && row?.heap8BufferShared === true &&
  row?.memorySameAsHeap8 === true && row?.memorySameAsOriginal === true &&
  row?.heap8Bytes === viewBytes && row?.heap32Length === viewBytes / 4 &&
  row?.allViewsUseMemoryBuffer === true && allLengthsEqual(row?.viewBytes, viewBytes);
const pass = failure === null && pageErrors.length === 0 && result && !result.fatal &&
  helperFacts?.transformReceipt?.contract === 'shared-memory-fixed-view-refresh-v2' &&
  helperFacts.refreshMarkerCount === 1 && helperFacts.guardMarkerCount === 1 &&
  helperFacts.refreshAnchorCount === 0 && helperFacts.guardAnchorCount === 0 &&
  helperFacts.exactHelperCount === 1 && helperFacts.exactGuardCount === 1 &&
  helperFacts.identityPredicateCount === 1 && helperFacts.lengthPredicateCount === 1 &&
  helperFacts.growableLengthGuardCount === 1 &&
  result.crossOriginIsolated === true && result.ackCount === 1 &&
  result.nonce === 0x42575331 && result.result?.cmd === 'result' &&
  result.result?.initialBytes === 65536 && result.result?.grownBytes === 131072 &&
  result.result?.finalBytes === 196608 && result.result?.highIndex === 16384 &&
  growableState(result.result?.stale, 131072, 65536) &&
  zeroCounters(result.result?.stale?.counters) &&
  growableState(result.result?.afterOldIdentityHelper?.state, 131072, 65536) &&
  zeroCounters(result.result?.afterOldIdentityHelper?.counters) &&
  growableState(result.result?.afterOldDirectUpdate?.state, 131072, 65536) &&
  oneEarlyReturn(result.result?.afterOldDirectUpdate?.counters) &&
  result.result?.oldControlError?.name === 'RangeError' &&
  /atomic access index/i.test(result.result.oldControlError.message) &&
  growableState(result.result?.refreshed, 131072, 131072) &&
  oneRebuild(result.result?.refreshed?.counters) &&
  result.result?.loaded === result.nonce &&
  growableState(result.result?.trackingBefore, 196608, 196608) &&
  zeroCounters(result.result?.trackingBefore?.counters) &&
  growableState(result.result?.trackingAfterGrowHelper, 196608, 196608) &&
  zeroCounters(result.result?.trackingAfterGrowHelper?.counters) &&
  growableState(result.result?.trackingAfterDirectUpdate, 196608, 196608) &&
  oneEarlyReturn(result.result?.trackingAfterDirectUpdate?.counters) &&
  headers?.['cross-origin-opener-policy'] === 'same-origin' &&
  headers?.['cross-origin-embedder-policy'] === 'require-corp' &&
  headers?.['cross-origin-resource-policy'] === 'same-origin';

const final = {
  schema:'blender-web.shared-view-growth.v4', status:pass?'PASS':'FAIL', label, port,
  scope:'Chrome growable-SAB fixed-view evidence for the production-transformed growMemViews and updateMemoryViews guards, combined with the Python production-transform fixtures.',
  result, failure, pageErrors, headers, browser:browserFacts, helperContract:helperFacts,
  commands:{
    productionTransformTest:productionTestCommand.map((value) => value.startsWith(repo) ? relative(value) : value),
    transform:transformCommand.map((value) => value.startsWith(repo) ? relative(value) : value),
  },
  artifacts:{
    htmlSource:artifact(htmlSource), observerSource:artifact(observerSource),
    executedObserver:artifact(observer), helperFixture:artifact(helperFixture),
    productionTransformTest:artifact(productionTransformTest),
    executedHelper:artifactIfPresent(helper), driver:artifact(driver), finalizer:artifact(finalizer),
    server:artifact(serverScript), transformStdout:artifactIfPresent(transformStdout),
    transformStderr:artifactIfPresent(transformStderr), serverLog:artifactIfPresent(serverLog),
    productionTestStdout:artifactIfPresent(productionTestStdout),
    productionTestStderr:artifactIfPresent(productionTestStderr),
    serverStdout:artifact(join(out, 'server.stdout')), serverStderr:artifact(join(out, 'server.stderr')),
  },
};
writeExclusive(join(out, 'receipt.json'), JSON.stringify(final, null, 2) + '\n');
process.stdout.write(JSON.stringify(final) + '\n');
if (!pass) process.exitCode = 1;
