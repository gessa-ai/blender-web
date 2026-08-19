// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, '..', '..', 'platform_web', 'split', 'profile-export.js');
const source = readFileSync(SOURCE, 'utf8');

class FakeWorker {
  constructor(name) {
    this.name = name;
    this.onmessage = () => {};
    this.messages = [];
    this.rejectPostEntry = false;
  }

  postMessage(message) {
    this.messages.push(message);
    if (this.rejectPostEntry) {
      throw new Error(`${this.name}: post-entry message rejected`);
    }
    if (message.cmd === 'bwCaptureProbe') {
      queueMicrotask(() => this.onmessage({ data: {
        cmd: 'bwCaptureProbeAck', token: message.token, workerId: message.workerId,
      } }));
    }
  }
}

function controllerExports(resumeCalls) {
  const names = Array.from(source.matchAll(/read\("([A-Za-z0-9_]+)"\)/g), (match) => match[1]);
  const exports = Object.fromEntries(names.map((name) => [`_${name}`, () => 0]));
  exports._BW_web_split_request_apply = () => 1;
  exports._BW_web_split_request_resume = (generation) => {
    resumeCalls.push(generation);
    return 1;
  };
  return exports;
}

function createHarness() {
  const prepared = Array.from({ length: 8 }, (_, index) => new FakeWorker(`prepared-${index + 1}`));
  const PThread = {
    unusedWorkers: prepared.slice(),
    pthreads: {},
    loadWasmModuleToWorker(worker) {
      worker.originalHandler = () => {};
      worker.onmessage = worker.originalHandler;
      return worker.loadPromise || Promise.resolve(worker);
    },
  };
  const resumeCalls = [];
  const Module = controllerExports(resumeCalls);
  const context = vm.createContext({
    Module, PThread, ENVIRONMENT_IS_PTHREAD: false,
    wasmExports: {}, wasmRawExports: {}, HEAPU8: new Uint8Array(8),
    _malloc: () => 1, _free: () => {}, console, setTimeout, clearTimeout,
    Date, Promise, Set, Array, Object, Number, Error, String,
  });
  vm.runInContext(source, context, { filename: SOURCE });
  return { context, Module, PThread, prepared, resumeCalls };
}

async function prepare(harness) {
  const result = await harness.Module.bwCaptureStabilizeWorkers(1);
  assert.deepEqual(Array.from(result.workerIds), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(result.postApplyProbeCount, 0);
  assert.ok(harness.prepared.every((worker) => worker.messages.length === 3),
    'PREPARED must retain three stable-round probe ACKs');
  harness.Module.bwCaptureSplitCall('BW_web_split_request_apply', [1, 8]);
  return result;
}

async function addLateThroughActualLoader(harness, name = 'late') {
  const late = new FakeWorker(name);
  const events = [];
  const original = harness.PThread.loadWasmModuleToWorker;
  late.loadPromise = Promise.resolve(late);
  // The actual wrapper must assign the ID before calling the original loader,
  // then reattach after that loader overwrites onmessage.
  const loading = original.call(harness.PThread, late);
  events.push(late.__bwCaptureId ? 'id-before-return' : 'missing-id');
  events.push(late.onmessage === late.originalHandler ? 'not-reattached' : 'reattached');
  await loading;
  events.push(late.__bwCaptureLoadState);
  harness.PThread.pthreads[`late-${late.__bwCaptureId}`] = late;
  assert.deepEqual(events, ['id-before-return', 'reattached', 'ready-before-entry']);
  return late;
}

async function positive() {
  const harness = createHarness();
  const prepared = await prepare(harness);
  const preparedMessageCounts = harness.prepared.map((worker) => worker.messages.length);
  harness.prepared.forEach((worker) => { worker.rejectPostEntry = true; });
  const late = await addLateThroughActualLoader(harness);
  late.rejectPostEntry = true;

  const ready = await harness.Module.bwCaptureAttestPageReady(1, prepared.workerIds);
  assert.deepEqual(Array.from(ready.lateWorkerIds), [9]);
  assert.deepEqual(Array.from(ready.latePreEntryLoadIds), [9]);
  assert.deepEqual(Array.from(ready.pendingWorkerIds), []);
  assert.deepEqual(Array.from(ready.errorWorkerIds), []);
  assert.equal(ready.postApplyProbeCount, 0);
  assert.deepEqual(harness.prepared.map((worker) => worker.messages.length), preparedMessageCounts);
  assert.equal(late.messages.length, 0, 'late worker must receive no post-entry message');

  const resumed = await harness.Module.bwCaptureResumeAfterStable(1, ready.workerIds);
  assert.deepEqual(Array.from(resumed.workerIds), Array.from(ready.workerIds));
  assert.deepEqual(harness.resumeCalls, [1]);
  assert.equal(late.messages.length, 0);
}

async function expectFailure(label, mutate, pattern) {
  const harness = createHarness();
  const prepared = await prepare(harness);
  await mutate(harness, prepared);
  await assert.rejects(
    harness.Module.bwCaptureAttestPageReady(1, prepared.workerIds), pattern, label);
}

await positive();

await expectFailure('missing late load', async (harness) => {
  harness.PThread.pthreads.missing = new FakeWorker('missing');
}, /lacks pre-entry load/);

await expectFailure('late load error', async (harness) => {
  const late = new FakeWorker('error');
  late.__bwCaptureLoadState = 'error';
  late.__bwCaptureLoadError = 'injected';
  harness.PThread.pthreads.error = late;
}, /late worker load failed/);

await expectFailure('late load pending', async (harness) => {
  const late = new FakeWorker('pending');
  late.__bwCaptureLoadState = 'pending';
  late.__bwCaptureLoadPromise = Promise.resolve(late);
  harness.PThread.pthreads.pending = late;
}, /late worker load incomplete/);

await expectFailure('prepared shrink', async (harness) => {
  harness.PThread.unusedWorkers.shift();
}, /shrink\/replacement\/duplicate/);

await expectFailure('prepared replacement', async (harness) => {
  harness.PThread.unusedWorkers.shift();
  const replacement = await addLateThroughActualLoader(harness, 'replacement');
  assert.ok(replacement.__bwCaptureId > 8);
}, /shrink\/replacement\/duplicate/);

await expectFailure('duplicate worker ID', async (harness) => {
  const duplicate = new FakeWorker('duplicate');
  duplicate.__bwCaptureId = 1;
  duplicate.__bwCaptureLoadState = 'ready-before-entry';
  duplicate.__bwCaptureLoadGeneration = 1;
  harness.PThread.pthreads.duplicate = duplicate;
}, /shrink\/replacement\/duplicate/);

{
  const harness = createHarness();
  const prepared = await prepare(harness);
  const late = await addLateThroughActualLoader(harness, 'drift-1');
  late.rejectPostEntry = true;
  const ready = await harness.Module.bwCaptureAttestPageReady(1, prepared.workerIds);
  const drift = await addLateThroughActualLoader(harness, 'drift-2');
  drift.rejectPostEntry = true;
  await assert.rejects(harness.Module.bwCaptureResumeAfterStable(1, ready.workerIds),
    /PAGE_READY worker set drift|attestation drift/);
  assert.deepEqual(harness.resumeCalls, [], 'drift must fail before native RESUME publication');
}

{
  const harness = createHarness();
  const prepared = await prepare(harness);
  await assert.rejects(harness.Module.bwCaptureAttestPageReady(2, prepared.workerIds),
    /wrong attestation generation/);
}

console.log('BW_CAPTURE_LATE_WORKER_ATTESTATION_TEST PASS positive=1 negatives=7');
