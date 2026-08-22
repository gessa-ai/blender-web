# M3.T6 signed-I10 subrange-update parity — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0169 makes `WGPUVertexBuffer::update_sub` preserve the signed packed-normal conversion
already used by full uploads. WebGPU declares normalized `GPU_COMP_I10` attributes as
`Snorm8x4`, because it has no signed 10-10-10-2 vertex format. The initial upload path converted
the four source bytes accordingly, but the subrange path forwarded raw 2-10-10-10 bytes to that
same storage. A later partial update could therefore reintroduce the negative-normal sign error
that patch 0119 removed from full uploads.

The correction factors the one-field conversion, locates fields by Blender's exact interleaved
or deinterleaved layout, and converts only fields wholly contained in the update payload. A range
that overlaps only part of a packed field rejects before changing any scratch byte. Candidate
vertex indices are derived from the byte range, so a small update does not scan the full buffer;
the contract exercises one field with a declared `UINT32_MAX` vertex census. Non-I10 updates keep
the prior direct path. The pinned `GPU_vertbuf_update_sub` API passes byte offsets and lengths
unchanged (`gpu_vertex_buffer.cc:315`), while Vulkan can copy the native signed packed format
directly (`vk_vertex_buffer.cc:72`).

The pinned call-site census currently has five production vertex subrange sites, all using
float or integer fields rather than packed I10. This is an API-parity repair for future dynamic
normal updates, not a claim that a current scene changed pixels.

## Device-free contract and integration

The first expanded contract failed against the unchanged canonical source because the
subrange-aware converter did not exist (`ledger/buildlogs/20260822T063149-1110259.log`). Final
native and Node 22.16.0 runs emit the same 499 bytes at SHA-256
`db6169c1bb53faa1da59bb5dff0bf967bfee25141c04666a6d62c520d3a161e4` and bind the 13 exact
source inputs at SHA-256
`2784e3d7f0eee8c7ac93b0c1db0b3be62142afaff4028099ee6bd50aadfa931f`.
Seven contracts now include:

- 21 subrange fields across interleaved, two deinterleaved, and whole-buffer layouts, each equal
  to the established full-upload conversion;
- leading, trailing, complete-then-partial, and overflowing ranges rejected without changing the
  caller-owned payload;
- unchanged non-I10 and empty updates; and
- a one-field `UINT32_MAX`-census control that finishes with bounded work.

Root and descendant executions plus wrong-Dawn/wrong-Node zero-allocation controls are green
(`20260822T063953-1117467`, `20260822T064254-1122171`, and
`20260822T064019-1118927`). The final-source freezer retains 257 paths and 20,258 manifest
entries; its 1,553,145-byte canonical patch is SHA-256
`e6476ec9ed391efbcf3ffcb8281d0497354246f5e2b019bcd144429400b0d76f`, with byte-identical
live/replay manifests at SHA-256
`7633f52f3646196f89530538207cc8b05cea397e6b9f20911f2b65317b46ce9d`
(`20260822T063814-1116078`). Independent canonical replay is green
(`20260822T064023-1119123`).

The real `blender_browser` target recompiles and links the corrected vertex-buffer path, then
reports exact locked-Ninja no-work (`20260822T064033-1119292` and
`20260822T064115-1119660`). Exact REUSE 6.2.0 is green for 2,048/2,048 files
(`20260822T064424-1123011`). Required M3 remains honestly red only for the absent strict candidate
(`20260822T064146-1119921`). The documented Docker-group-scoped regression restores M0 to 6/6
green while M1-M8 retain their existing receipt/APPLY/artifact/browser/run-label/hardware
boundaries (`20260822T064223-1121257`).

## Boundary

The contract creates no WebGPU instance, adapter, device, GPU buffer, upload, draw, browser
artifact, or receipt. It does not promote a result, dependency decision, deferral, tolerance,
golden, or blacklist. Live allocation and draw proof remain owned by `M3-LINUX-REPLAY`, blocked
by s7's software-only Vulkan adapter.
