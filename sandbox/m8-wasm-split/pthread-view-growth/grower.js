// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

let wasmMemory;
let HEAP8;
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
  HEAP8 = new Int8Array(wasmMemory.buffer);
  counters.rebuilds++;
  counters.returns++;
}

function state(tracked) {
  const memoryBuffer = wasmMemory.buffer;
  return {
    memoryBuffer:bufferFacts(memoryBuffer),
    heap8Buffer:HEAP8 ? bufferFacts(HEAP8.buffer) : null,
    memorySameAsHeap8:HEAP8 ? memoryBuffer === HEAP8.buffer : null,
    memorySameAsTracked:tracked ? memoryBuffer === tracked : null,
    heap8Bytes:HEAP8?.byteLength ?? null,
    counters:{...counters},
  };
}

onmessage = ({data}) => {
  if (data.cmd === "init") {
    wasmMemory = data.memory;
    updateMemoryViews();
    counters.calls = counters.earlyReturns = counters.rebuilds = counters.returns = 0;
    postMessage({cmd:"growerInitialized", state:state(wasmMemory.buffer)});
    return;
  }
  if (data.cmd === "grow") {
    const tracked = wasmMemory.buffer;
    const before = state(tracked);
    const previousPages = wasmMemory.grow(data.pages);
    updateMemoryViews();
    const after = state(tracked);
    postMessage({cmd:data.ack, pages:data.pages, previousPages, before, after});
  }
};
