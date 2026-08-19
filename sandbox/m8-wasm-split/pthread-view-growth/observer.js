// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

importScripts("helper.js");

let wasmMemory, trackedBuffer;
let HEAP8, HEAPU8, HEAP16, HEAPU16, HEAP32, HEAPU32, HEAPF32, HEAPF64, HEAP64, HEAPU64;
const counters = {calls:0, earlyReturns:0, rebuilds:0, returns:0};

function bufferFacts(buffer) {
  return {
    bytes:buffer.byteLength,
    growable:buffer.growable ?? null,
    maxBytes:buffer.maxByteLength ?? null,
    shared:buffer instanceof SharedArrayBuffer,
  };
}

function updateMemoryViews() {
  counters.calls++;
  if (HEAP8?.buffer?.growable) {
    counters.earlyReturns++;
    counters.returns++;
    return;
  }
  const b = wasmMemory.buffer;
  HEAP8 = new Int8Array(b);
  HEAPU8 = new Uint8Array(b);
  HEAP16 = new Int16Array(b);
  HEAPU16 = new Uint16Array(b);
  HEAP32 = new Int32Array(b);
  HEAPU32 = new Uint32Array(b);
  HEAPF32 = new Float32Array(b);
  HEAPF64 = new Float64Array(b);
  HEAP64 = new BigInt64Array(b);
  HEAPU64 = new BigUint64Array(b);
  counters.rebuilds++;
  counters.returns++;
}

function resetCounters() {
  counters.calls = counters.earlyReturns = counters.rebuilds = counters.returns = 0;
}

function state() {
  const memoryBuffer = wasmMemory.buffer;
  const views = {HEAP8, HEAPU8, HEAP16, HEAPU16, HEAP32, HEAPU32, HEAPF32, HEAPF64, HEAP64, HEAPU64};
  return {
    memoryBuffer:bufferFacts(memoryBuffer),
    heap8Buffer:bufferFacts(HEAP8.buffer),
    memorySameAsHeap8:memoryBuffer === HEAP8.buffer,
    memorySameAsTracked:memoryBuffer === trackedBuffer,
    heap8Bytes:HEAP8.byteLength,
    heap32Length:HEAP32.length,
    viewBytes:Object.fromEntries(Object.entries(views).map(([name, view]) => [name, view.byteLength])),
    allViewsUseMemoryBuffer:Object.values(views).every((view) => view.buffer === memoryBuffer),
    counters:{...counters},
  };
}

function identityOnlyGrowMemViews() {
  if (wasmMemory.buffer != HEAP8.buffer) updateMemoryViews();
}

onmessage = ({data}) => {
  if (data.cmd === "init") {
    wasmMemory = data.memory;
    trackedBuffer = wasmMemory.buffer;
    updateMemoryViews();
    resetCounters();
    postMessage({cmd:"observerInitialized", state:state()});
    return;
  }
  if (data.cmd === "sync") {
    const before = state();
    updateMemoryViews();
    const afterUpdate = state();
    trackedBuffer = wasmMemory.buffer;
    const tracked = state();
    resetCounters();
    postMessage({cmd:"observerSynced", before, afterUpdate, tracked, countersAfterReset:{...counters}});
    return;
  }
  if (data.cmd === "test") {
    const before = state();
    identityOnlyGrowMemViews();
    const afterControl = state();
    let controlError = null;
    try { Atomics.store(HEAP32, data.highIndex, data.nonce); }
    catch (error) { controlError = {name:error.name, message:error.message}; }
    growMemViews();
    const afterRefresh = state();
    Atomics.store(HEAP32, data.highIndex, data.nonce);
    const loaded = Atomics.load(HEAP32, data.highIndex);
    growMemViews();
    const afterNoop = state();
    postMessage({cmd:"observerResult", before, afterControl, controlError,
      afterRefresh, loaded, afterNoop});
  }
};
