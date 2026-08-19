// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// This exact generated-style pair is transformed by finalize-wasm-split.py before execution.
function getMemoryBuffer(){return wasmMemory.buffer}
function updateMemoryViews(){counters.calls++;let rebuilt=false;try{if(HEAP8?.buffer?.growable)return;var b=getMemoryBuffer();HEAP8=new Int8Array(b);HEAPU8=new Uint8Array(b);HEAP16=new Int16Array(b);HEAPU16=new Uint16Array(b);HEAP32=new Int32Array(b);HEAPU32=new Uint32Array(b);HEAPF32=new Float32Array(b);HEAPF64=new Float64Array(b);HEAP64=new BigInt64Array(b);HEAPU64=new BigUint64Array(b);rebuilt=true;counters.rebuilds++}finally{if(!rebuilt)counters.earlyReturns++;counters.returns++}}
function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){updateMemoryViews()}}
