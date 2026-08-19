// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const RUNTIME = join(REPO, 'platform_web', 'split', 'single-flight.js');
const FINALIZER = join(REPO, 'scripts', 'finalize-wasm-split.py');
const source = readFileSync(RUNTIME, 'utf8');
const finalizer = readFileSync(FINALIZER, 'utf8');
const emptyModule = new WebAssembly.Module(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));

const preparedAssignment = source.indexOf(
  'bwSplitPreparedWorkerIds = status.workerIds.slice().sort(function (a, b) { return a - b; });');
const preparedRefresh = source.indexOf('status = bwSplitStatus();', preparedAssignment);
const preparedNativeRequest = source.indexOf(
  'bwSplitNativeCall("BW_web_split_request_prepared", [', preparedAssignment);
const preparedReturn = source.indexOf('return { split: status, native: nativeStatus };', preparedAssignment);
assert.ok(preparedAssignment >= 0 && preparedRefresh > preparedAssignment &&
  preparedNativeRequest > preparedRefresh && preparedReturn > preparedNativeRequest,
  'PREPARED must refresh copied status after publishing exact prepared worker IDs');

class FakeWorker {
  constructor(name) {
    this.name = name;
    this.onmessage = () => {};
    this.messages = [];
    this.rejectPostEntry = false;
  }

  postMessage(message) {
    this.messages.push(message);
    if (this.rejectPostEntry) throw new Error(`${this.name}: post-entry message rejected`);
  }
}

function createHarness() {
  const prepared = Array.from({ length: 8 }, (_, index) => new FakeWorker(`prepared-${index + 1}`));
  const PThread = {
    unusedWorkers: prepared.slice(), pthreads: {},
    loadWasmModuleToWorker(worker) {
      worker.originalHandler = () => {};
      worker.onmessage = worker.originalHandler;
      worker.postMessage({ cmd: 1 });
      return Promise.resolve(worker);
    },
  };
  const native = {
    phase: 6, appliedGeneration: 1, pageReadyGeneration: 0, errorGeneration: 0,
    resumedGeneration: 0, preparedStabilizationEpoch: 1,
  };
  const pageReadyCalls = [];
  const resumeCalls = [];
  const Module = {};
  const nativeNames = Array.from(source.matchAll(/bwSplitNativeRead\("([A-Za-z0-9_]+)"\)/g),
    (match) => match[1]);
  for (const name of nativeNames) {
    Module[`_${name}`] = () => Number(native[name.replace(/^BW_web_split_/, '')] ?? 0);
  }
  // The status reader uses lower-camel object fields, while export names are
  // snake_case. Supply explicit values for the transition fields exercised.
  Module._BW_web_split_phase = () => native.phase;
  Module._BW_web_split_applied_generation = () => native.appliedGeneration;
  Module._BW_web_split_page_ready_generation = () => native.pageReadyGeneration;
  Module._BW_web_split_error_generation = () => native.errorGeneration;
  Module._BW_web_split_resumed_generation = () => native.resumedGeneration;
  Module._BW_web_split_prepared_stabilization_epoch = () => native.preparedStabilizationEpoch;
  Module._BW_web_split_request_page_ready = (...args) => {
    pageReadyCalls.push(args);
    native.phase = 8;
    native.pageReadyGeneration = args[0];
    return 1;
  };
  Module._BW_web_split_request_resume = (generation) => {
    resumeCalls.push(generation);
    native.phase = 10;
    native.resumedGeneration = generation;
    return 1;
  };
  const context = vm.createContext({
    Module, PThread, ENVIRONMENT_IS_PTHREAD: false, wasmExports: Module,
    wasmRawExports: {}, loadSplitModule: () => {}, locateFile: (value) => value,
    WebAssembly, crypto: globalThis.crypto, fetch: globalThis.fetch,
    console, setTimeout, clearTimeout, Date, Promise, Set, Array, Object, Number, Error, String,
  });
  vm.runInContext(source, context, { filename: RUNTIME });

  context.bwSplitGeneration = 1;
  context.bwSplitSecondaryModule = emptyModule;
  context.bwSplitSecondaryInstance = {};
  context.bwSplitLocalInstanceCount = 1;
  for (const worker of prepared) {
    worker.__bwSplitReadyGeneration = 1;
    worker.__bwSplitAckGeneration = 1;
    worker.__bwSplitInstanceCount = 1;
    worker.__bwSplitInstallDelivery = 'command';
  }
  context.bwSplitPreparedWorkerIds = prepared.map((worker) => worker.__bwSplitId);
  context.bwSplitStabilizationEpoch = 1;
  context.bwSplitPreparedStabilizationEpoch = 1;
  return { context, Module, PThread, prepared, native, pageReadyCalls, resumeCalls };
}

{
  const harness = createHarness();
  harness.context.bwSplitPreparedWorkerIds = [];
  const stale = harness.context.bwSplitStatus();
  harness.context.bwSplitPreparedWorkerIds = harness.prepared.map((worker) => worker.__bwSplitId);
  const refreshed = harness.context.bwSplitStatus();
  assert.deepEqual(Array.from(stale.preparedWorkerIds), []);
  assert.deepEqual(Array.from(refreshed.preparedWorkerIds),
    harness.prepared.map((worker) => worker.__bwSplitId));
}

async function deliver(harness, worker, message) {
  const promise = harness.context.bwSplitInstallWorker(worker, true);
  queueMicrotask(() => worker.onmessage({ data: message }));
  return await promise;
}

async function positive() {
  const harness = createHarness();
  harness.prepared.forEach((worker) => { worker.rejectPostEntry = true; });
  const late = new FakeWorker('late');
  harness.context.bwSplitEnsureWorkerId(late);
  harness.context.bwSplitAttachWorker(late);
  late.__bwSplitInitialDelivery = true;
  harness.PThread.pthreads.late = late;
  await deliver(harness, late, {
    cmd: 'bwSplitReady', generation: 1, workerId: late.__bwSplitId,
    ok: true, error: null, instanceCount: 1, delivery: 'initial-before-start',
  });
  late.rejectPostEntry = true;
  const preparedMessages = harness.prepared.map((worker) => worker.messages.length);
  const lateMessages = late.messages.length;

  const result = await harness.Module.bwMarkSplitPageReady(1);
  assert.equal(result.native.pageReadyGeneration, 1);
  assert.deepEqual(Array.from(result.split.lateWorkerIds), [late.__bwSplitId]);
  assert.deepEqual(Array.from(result.split.lateInitialAckWorkerIds), [late.__bwSplitId]);
  assert.equal(result.split.errorWorkerIds.length, 0);
  assert.equal(result.split.pendingWorkerIds.length, 0);
  assert.equal(result.lateWorkers, 1);
  assert.deepEqual(harness.prepared.map((worker) => worker.messages.length), preparedMessages);
  assert.equal(late.messages.length, lateMessages, 'PAGE_READY must not message a ready long-lived worker');
  assert.equal(harness.pageReadyCalls.length, 1);
  assert.equal(harness.pageReadyCalls[0][7], 1, 'native late-worker count must be exact');
  const resumed = await harness.Module.bwResumeSplitScheduler(1);
  assert.equal(resumed.native.resumedGeneration, 1);
  assert.equal(resumed.native.phase, 10);
  assert.deepEqual(harness.resumeCalls, [1]);
  assert.deepEqual(harness.prepared.map((worker) => worker.messages.length), preparedMessages);
  assert.equal(late.messages.length, lateMessages, 'RESUME must not message a ready long-lived worker');
}

async function malformedAck(label, patch, pattern) {
  const harness = createHarness();
  const late = new FakeWorker(label);
  harness.context.bwSplitEnsureWorkerId(late);
  harness.context.bwSplitAttachWorker(late);
  late.__bwSplitInitialDelivery = true;
  const base = {
    cmd: 'bwSplitReady', generation: 1, workerId: late.__bwSplitId,
    ok: true, error: null, instanceCount: 1, delivery: 'initial-before-start',
  };
  await assert.rejects(deliver(harness, late, { ...base, ...patch }), pattern, label);
  assert.ok(harness.context.bwSplitStats.rejectedAckCount > 0 ||
    harness.context.bwSplitStats.duplicateAckCount > 0);
}

await positive();

{
  const harness = createHarness();
  const worker = new FakeWorker('preobserved-before-load');
  harness.context.bwSplitEnsureWorkerId(worker);
  harness.context.bwSplitAttachWorker(worker);
  const preLoadAttachedHandler = worker.onmessage;
  harness.context.bwSplitSecondaryModule = null;
  await harness.PThread.loadWasmModuleToWorker(worker);
  assert.notEqual(worker.onmessage, worker.originalHandler,
    'shipping wrapper must reattach after the original loader overwrites onmessage');
  assert.notEqual(worker.onmessage, preLoadAttachedHandler,
    'shipping wrapper must not let an old attached flag suppress the new handler');
  assert.equal(worker.__bwSplitAttachedHandler, worker.onmessage);
}

{
  const harness = createHarness();
  const worker = new FakeWorker('fifo-late-load');
  harness.context.bwSplitSecondaryModule = emptyModule;
  const loading = harness.PThread.loadWasmModuleToWorker(worker);
  assert.deepEqual(worker.messages.map((message) => message.cmd), [1, 'bwSplitInitialInstall'],
    'shipping wrapper must synchronously post cmd1 then the initial install');
  const install = worker.messages[1];
  assert.equal(install.module, emptyModule);
  assert.equal(install.generation, 1);
  assert.equal(install.workerId, worker.__bwSplitId);
  assert.equal(worker.__bwSplitInitialDelivery, true);
  queueMicrotask(() => worker.onmessage({ data: {
    cmd: 'bwSplitReady', generation: 1, workerId: worker.__bwSplitId,
    ok: true, error: null, instanceCount: 1, delivery: 'initial-before-start',
  } }));
  await loading;
  assert.equal(worker.__bwSplitInstallDelivery, 'initial-before-start');
}

await malformedAck('wrong delivery', { delivery: 'command' }, /delivery/);
await malformedAck('missing delivery', { delivery: undefined }, /delivery/);
await malformedAck('wrong generation', { generation: 2 }, /generation/);
await malformedAck('wrong worker ID', { workerId: 999 }, /worker id/);
await malformedAck('wrong instance count', { instanceCount: 2 }, /delivery|install exactly once|instance/);

{
  const harness = createHarness();
  const late = new FakeWorker('duplicate');
  harness.context.bwSplitEnsureWorkerId(late);
  harness.context.bwSplitAttachWorker(late);
  late.__bwSplitInitialDelivery = true;
  const message = { cmd: 'bwSplitReady', generation: 1, workerId: late.__bwSplitId,
    ok: true, error: null, instanceCount: 1, delivery: 'initial-before-start' };
  await deliver(harness, late, message);
  late.onmessage({ data: message });
  assert.equal(harness.context.bwSplitStats.duplicateAckCount, 1);
  assert.match(String(harness.context.bwSplitProtocolError), /duplicate ACK/);
}

{
  const harness = createHarness();
  harness.prepared.forEach((worker) => { worker.rejectPostEntry = true; });
  const late = new FakeWorker('drift-initial');
  harness.context.bwSplitEnsureWorkerId(late);
  harness.context.bwSplitAttachWorker(late);
  late.__bwSplitInitialDelivery = true;
  harness.PThread.pthreads.late = late;
  await deliver(harness, late, { cmd: 'bwSplitReady', generation: 1,
    workerId: late.__bwSplitId, ok: true, error: null, instanceCount: 1,
    delivery: 'initial-before-start' });
  late.rejectPostEntry = true;
  await harness.Module.bwMarkSplitPageReady(1);

  const drift = new FakeWorker('drift-after-ready');
  harness.context.bwSplitEnsureWorkerId(drift);
  harness.context.bwSplitAttachWorker(drift);
  drift.__bwSplitInitialDelivery = true;
  harness.PThread.pthreads.drift = drift;
  await deliver(harness, drift, { cmd: 'bwSplitReady', generation: 1,
    workerId: drift.__bwSplitId, ok: true, error: null, instanceCount: 1,
    delivery: 'initial-before-start' });
  drift.rejectPostEntry = true;
  await assert.rejects(harness.Module.bwResumeSplitScheduler(1), /RESUME attestation drift/);
  assert.deepEqual(harness.resumeCalls, [], 'worker drift must fail before native RESUME');
  assert.equal(late.messages.length, 0);
  assert.equal(drift.messages.length, 0);
}

{
  const harness = createHarness();
  const late = new FakeWorker('command-late');
  harness.context.bwSplitEnsureWorkerId(late);
  harness.context.bwSplitAttachWorker(late);
  late.__bwSplitReadyGeneration = 1;
  late.__bwSplitAckGeneration = 1;
  late.__bwSplitInstanceCount = 1;
  late.__bwSplitInstallDelivery = 'command';
  harness.PThread.pthreads.late = late;
  late.rejectPostEntry = true;
  await assert.rejects(harness.Module.bwMarkSplitPageReady(1), /lacks initial-before-start ACK/);
  assert.equal(late.messages.length, 0);
}

// Bind the page-side FIFO and generated core dispatch to the real sources.
// Emscripten synchronously posts cmd1 inside the original loader; this wrapper
// attaches its ACK handler and posts the initial install before returning, so
// getNewWorker() can only post cmd2 afterward.
const loadWrapper = source.split('PThread.loadWasmModuleToWorker = function (worker) {', 2)[1]
  .split('for (var bwSplitInitialWorker', 1)[0];
const originalLoad = loadWrapper.indexOf('var loading = bwSplitOriginalLoadWorker(worker);');
const attachAfter = loadWrapper.indexOf('bwSplitAttachWorker(worker);', originalLoad);
const initialPost = loadWrapper.indexOf('cmd: "bwSplitInitialInstall"', attachAfter);
const returnAfter = loadWrapper.indexOf('return loading.then', initialPost);
assert.ok(originalLoad >= 0 && attachAfter > originalLoad && initialPost > attachAfter &&
  returnAfter > initialPost, 'page loader order must be cmd1 -> attach -> initial install -> return');
assert.match(finalizer, /single-flight cmd1 secondary-module piggyback remains/,
  'finalizer must reject obsolete cmd1 secondary-module piggyback output');
assert.match(source, /delivery !== "initial-before-start"[\s\S]*delivery !== "command"/);
assert.match(finalizer,
  /BW_SPLIT_WORKER_INITIAL_INSTALL_FIFO_V1[\s\S]*msgData\.workerId,\\"initial-before-start\\"/,
  'generated worker core must fail closed on the FIFO initial install');
assert.match(finalizer,
  /BW_SPLIT_WORKER_CORE_DISPATCH_V1[\s\S]*msgData\.workerId,\\"command\\"/,
  'generated worker-core command dispatch must pass the exact command delivery discriminator');

{
  const workerAcks = [];
  const workerContext = vm.createContext({
    Module: {}, PThread: {}, ENVIRONMENT_IS_PTHREAD: true, wasmExports: {}, wasmRawExports: {},
    loadSplitModule: () => {}, locateFile: (value) => value, handleMessage: () => {},
    postMessage: (message) => workerAcks.push(message), WebAssembly,
    crypto: globalThis.crypto, fetch: globalThis.fetch, console, setTimeout, clearTimeout,
    Date, Promise, Set, Array, Object, Number, Error, String,
  });
  vm.runInContext(source, workerContext, { filename: RUNTIME });
  workerContext.handleMessage({ data: {
    cmd: 'bwSplitInstall', module: emptyModule, generation: 1, workerId: 8,
  } });
  assert.equal(workerAcks.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(workerAcks[0])), {
    cmd: 'bwSplitReady', generation: 1, workerId: 8, ok: true, error: null,
    instanceCount: 1, delivery: 'command',
  });
}
const order = ['cmd1-post', 'initial-post', 'cmd2-post'];
const queued = [
  () => { order.push('install'); order.push('ack'); },
  () => { order.push('cmd2'); order.push('invoke'); },
];
const startWorker = () => {
  order.push('startWorker');
  order.push('cmd3');
  for (const command of queued) command();
};
startWorker();
assert.deepEqual(order, ['cmd1-post', 'initial-post', 'cmd2-post', 'startWorker', 'cmd3',
  'install', 'ack', 'cmd2', 'invoke']);

console.log('BW_SINGLE_FLIGHT_LATE_WORKER_ATTESTATION_TEST PASS positive=1 negatives=8 fifo-ordering=1');
