<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M3.T6 integrated buffer parity

This device-free contract compiles the canonical in-tree `wgpu_buffer`,
`wgpu_pixel_buffer`, and `wgpu_readback` postimages directly for native Dawn and
WebAssembly. It also extracts `WGPUIndexBuffer::strip_restart_indices` byte-for-byte
and executes it through Blender's real `IndexBuf::init()` without retaining the
live-device index-buffer vtable. The same translation unit includes the canonical
`index_binding_plan()` header helper used by `WGPUBatch`. It checks the exact buffer-usage
matrix, ordinary and checked alignment/range helpers, storage-copy source/destination bounds,
invalid-buffer behavior, move lifetime,
the CPU-backed pixel-upload buffer's map/unmap and byte-preservation lifecycle, and the real
readback registry's invalid-request lifecycle. The index cases cover mixed and all-restart point lists,
wide u32 indices, rebased u16 squeezing, build-on-device metadata, and both u16 and
u32 subrange binding plans (byte offset plus base vertex). Direct plans bind the
subrange byte window; indirect plans bind offset zero because Blender's generated
`DrawCommandIndexed` already contains the absolute first index and base vertex.
Exact source checks bind both modes to the shipping draw arms and to the command
producer, then separately census EEVEE's multi-viewport shadow path and mesh
triangle-subrange producers. The live combinations remain part of the hardware-owned
M3 replay.
The readback cases fill the 256-record exact-ticket cap, prove overflow is fail-closed,
retire half the records, refill the released capacity, and prove full reuse before
requiring byte-identical native/Node evidence.
The arithmetic cases reach `SIZE_MAX`, reject alignment overflow without mutating the
output sentinel, and prove that a wrapped `offset + size` cannot pass allocation bounds.
Exact source checks bind those helpers to buffer creation, updates, readback, and the shipping
vertex-to-storage copy path.

Run it only through the build wrapper:

```text
harness/buildwrap.sh bash sandbox/wgpu-buffer-integrated-smoke/build.sh
```

The driver rejects malformed extraction before generated-output allocation, requests
no instance, adapter, or device, and creates no M3 receipt. The historical live
copy/readback/index cases remain part of `M3-LINUX-REPLAY` and must not run against
a software adapter.
