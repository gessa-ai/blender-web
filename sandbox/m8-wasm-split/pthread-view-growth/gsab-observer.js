// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

importScripts("helper.js");

let wasmMemory;
let HEAP8, HEAPU8, HEAP16, HEAPU16, HEAP32, HEAPU32, HEAPF32, HEAPF64, HEAP64, HEAPU64;
const counters = {calls:0, earlyReturns:0, rebuilds:0, returns:0};
const oldCounters = {calls:0, earlyReturns:0, rebuilds:0, returns:0};

function resetCounters() {
  counters.calls = counters.earlyReturns = counters.rebuilds = counters.returns = 0;
}

function oldUpdateMemoryViews() {
  oldCounters.calls++;
  if (HEAP8?.buffer?.growable) {
    oldCounters.earlyReturns++;
    oldCounters.returns++;
    return;
  }
  installFixedViews(wasmMemory.buffer, wasmMemory.buffer.byteLength);
  oldCounters.rebuilds++;
  oldCounters.returns++;
}

function oldIdentityOnlyGrowMemViews() {
  if (wasmMemory.buffer != HEAP8.buffer) oldUpdateMemoryViews();
}

function installFixedViews(buffer, bytes) {
  HEAP8 = new Int8Array(buffer, 0, bytes);
  HEAPU8 = new Uint8Array(buffer, 0, bytes);
  HEAP16 = new Int16Array(buffer, 0, bytes / 2);
  HEAPU16 = new Uint16Array(buffer, 0, bytes / 2);
  HEAP32 = new Int32Array(buffer, 0, bytes / 4);
  HEAPU32 = new Uint32Array(buffer, 0, bytes / 4);
  HEAPF32 = new Float32Array(buffer, 0, bytes / 4);
  HEAPF64 = new Float64Array(buffer, 0, bytes / 8);
  HEAP64 = new BigInt64Array(buffer, 0, bytes / 8);
  HEAPU64 = new BigUint64Array(buffer, 0, bytes / 8);
}

function viewState(buffer) {
  const views = {HEAP8, HEAPU8, HEAP16, HEAPU16, HEAP32, HEAPU32, HEAPF32, HEAPF64, HEAP64, HEAPU64};
  return {
    memoryBufferBytes:wasmMemory.buffer.byteLength,
    memoryBufferGrowable:wasmMemory.buffer.growable ?? null,
    memoryBufferMaxBytes:wasmMemory.buffer.maxByteLength ?? null,
    memoryBufferShared:wasmMemory.buffer instanceof SharedArrayBuffer,
    heap8Bytes:HEAP8.byteLength,
    heap32Length:HEAP32.length,
    heap8BufferBytes:HEAP8.buffer.byteLength,
    heap8BufferGrowable:HEAP8.buffer.growable ?? null,
    heap8BufferMaxBytes:HEAP8.buffer.maxByteLength ?? null,
    heap8BufferShared:HEAP8.buffer instanceof SharedArrayBuffer,
    memorySameAsHeap8:wasmMemory.buffer === HEAP8.buffer,
    memorySameAsOriginal:wasmMemory.buffer === buffer,
    viewBytes:Object.fromEntries(Object.entries(views).map(([name, view]) => [name, view.byteLength])),
    allViewsUseMemoryBuffer:Object.values(views).every((view) => view.buffer === wasmMemory.buffer),
    counters:{...counters},
  };
}

onmessage = ({data}) => {
  if (data.cmd !== "run") return;
  const initialBytes = 65536;
  const grownBytes = 131072;
  const finalBytes = 196608;
  const buffer = new SharedArrayBuffer(initialBytes, {maxByteLength:finalBytes});
  wasmMemory = {buffer};
  installFixedViews(buffer, initialBytes);
  resetCounters();
  buffer.grow(grownBytes);
  const stale = viewState(buffer);
  oldIdentityOnlyGrowMemViews();
  const afterOldIdentityHelper = {
    state:viewState(buffer), counters:{...oldCounters},
  };
  oldUpdateMemoryViews();
  const afterOldDirectUpdate = {
    state:viewState(buffer), counters:{...oldCounters},
  };
  let oldControlError = null;
  const highIndex = initialBytes >>> 2;
  try { Atomics.store(HEAP32, highIndex, data.nonce); }
  catch (error) { oldControlError = {name:error.name, message:error.message}; }
  growMemViews();
  const refreshed = viewState(buffer);
  Atomics.store(HEAP32, highIndex, data.nonce);
  const loaded = Atomics.load(HEAP32, highIndex);
  resetCounters();
  buffer.grow(finalBytes);
  const trackingBefore = viewState(buffer);
  growMemViews();
  const trackingAfterGrowHelper = viewState(buffer);
  updateMemoryViews();
  const trackingAfterDirectUpdate = viewState(buffer);
  postMessage({cmd:"result", initialBytes, grownBytes, finalBytes, highIndex,
    stale, afterOldIdentityHelper, afterOldDirectUpdate, oldControlError, refreshed, loaded,
    trackingBefore, trackingAfterGrowHelper, trackingAfterDirectUpdate});
};
