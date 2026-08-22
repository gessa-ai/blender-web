<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU initial vertex-upload padding — 2026-08-22

## Outcome

Patch 0196 makes an initial `WGPUVertexBuffer` upload preserve its logical bytes while satisfying
WebGPU's four-byte transfer granularity. Non-aligned payloads now use the existing zero-filled
owned transfer storage, while already aligned payloads retain their original pointer. A failed
preparation or transfer returns before static host data is freed or dirty/uploaded state changes.

## Diagnosis and implementation

`GPUVertFormat::pack()` stores the exact sum of its attributes and does not promise that the final
VBO byte count is a multiple of four (`source/blender/gpu/intern/gpu_vertex_format.cc:560-573`).
`WGPUVertexBuffer::upload_data()` forwarded that logical count directly to `Buffer::update_sub()`,
whose WebGPU contract rejects a non-four-byte size. The caller ignored the boolean result and then
marked the VBO uploaded, cleared its dirty flag, and for static buffers deleted the only host copy.

The upload now selects either the original bytes or the existing signed-I10 scratch conversion,
passes that logical range through `buffer_update_payload()`, and sends the resulting aligned
pointer and size to `Buffer::update_sub()`. Both decisions are checked in one guard before any
host-data or state cleanup. This reuses the caller-ownership rule already established by Class 19
in `notes/porting-patterns.md`; it does not change subrange-update semantics.

## Evidence

- The fail-first exact-source contract stopped before evidence allocation because unchanged source
  had no owned-payload wiring (`20260822T193715-1818242`).
- Root and descendant-working-directory runs compile the canonical vertex implementation for
  native and wasm32 and pass eight byte-identical contracts. The added nine-case matrix covers
  logical sizes one through eight, 36 logical bytes, 48 transfer bytes, all 12 padding bytes,
  aligned pointer retention, and atomic undersized-allocation rejection. Output is 584 bytes at
  SHA-256 `0bd73ad2c268a1f97b8508fc8d4b6349f679ce82e722b4b67145bbaf5e0c54ad`; shipping inputs are
  SHA-256 `f67139f5bfd420887d915880d2cd0ee440a355f45fcd4e726e0ebb17e8282815`
  (`20260822T193959-1820530`, `20260822T194156-1822837`). Wrong Dawn and Node identities allocate
  no requested evidence (`20260822T194014-1821203`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,647,228-byte patch is SHA-256
  `188b3de95a31f731bb1e1e618228212356a77314e2c0d9d13c3f44c949da041c`; live and replay
  manifests are byte-identical at SHA-256
  `9a8c6eafa4b7b9b9ea7aa76333c795726d7a70f9e3ec1f484dfba6736b7e748d`
  (`20260822T193907-1819107`, `20260822T194349-1825254`). Numbered patch reverse application is
  green (`20260822T194218-1823581`).
- The optimized `blender_browser` recompiles `wgpu_vertex_buffer.cc`, relinks, and finishes at exact
  locked-Ninja no-work (`20260822T194031-1821492`, `20260822T194125-1821988`,
  `20260822T194345-1825223`). OFF-mode product preflight is green
  (`20260822T194149-1822175`). Final REUSE 6.2.0 reports 2,112/2,112 files compliant
  (`20260822T194521-1826720`).
- Required M3 remains red for the absent fresh strict candidate at `2026-08-22T19:43:10Z`.
  Container-backed regression restores M0 to 6/6 green while M1-M8 retain their named
  strict-receipt, product, browser, run-label, and hardware boundaries at the same timestamp.

## Boundary

This task creates no accepted WebGPU adapter, device, buffer, command, browser receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise.
The s7 software-adapter stop condition remains live.
