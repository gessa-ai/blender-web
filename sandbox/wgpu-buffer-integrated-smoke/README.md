<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M3.T6 integrated buffer parity

This device-free contract compiles the canonical in-tree `wgpu_buffer`,
`wgpu_pixel_buffer`, and `wgpu_readback` postimages directly for native Dawn and
WebAssembly. It also extracts `WGPUIndexBuffer::strip_restart_indices` byte-for-byte
and executes it through Blender's real `IndexBuf::init()` without retaining the
live-device index-buffer vtable. It checks the exact buffer-usage matrix, alignment
and index helpers, invalid-buffer behavior, move lifetime, the CPU-backed pixel-upload
buffer's map/unmap and byte-preservation lifecycle, and the real readback registry's
invalid-request lifecycle. The index cases cover mixed and all-restart point lists,
wide u32 indices, rebased u16 squeezing, subranges, and build-on-device metadata.
The readback cases fill the 256-record exact-ticket cap, prove overflow is fail-closed,
retire half the records, refill the released capacity, and prove full reuse before
requiring byte-identical native/Node evidence.

Run it only through the build wrapper:

```text
harness/buildwrap.sh bash sandbox/wgpu-buffer-integrated-smoke/build.sh
```

The driver rejects malformed extraction before generated-output allocation, requests
no instance, adapter, or device, and creates no M3 receipt. The historical live
copy/readback/index cases remain part of `M3-LINUX-REPLAY` and must not run against
a software adapter.
