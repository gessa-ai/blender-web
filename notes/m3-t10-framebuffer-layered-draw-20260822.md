<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU framebuffer layered draw selection - 2026-08-22

## Outcome

Patch 0183 makes the multi-viewport/layered draw path derive its pass count from the frontend
attachment selections rather than the first texture's complete backing range. Fixed-layer
attachments now retain their selected layer in every emulated pass. Multiple all-layer attachments
must expose the same count; an incomplete layout rejects before the first pass instead of drawing a
prefix and then failing on an out-of-range WebGPU view.

## Diagnosis and implementation

`WGPUFrameBuffer::attachment_layer_count()` previously returned the full layer count of the first
bound color attachment even when the frontend selected one fixed layer. `begin_load_pass()` then
overrode every attachment with the emulated pass number. A fixed layer therefore silently moved to
layer zero on the first pass and an otherwise valid fixed selection could terminate a later pass.
Different all-layer counts likewise allowed earlier layers to draw before the first exhausted view
aborted the batch.

The shared decision model at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:333` validates fixed selections, bounds the
signed pass representation, and accumulates one atomic all-layer count. The shipping framebuffer
uses it before the batch loop at
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:778` and reuses the already-proven layered
selector for color and depth views at `:878` and `:918`. Inactive subpass color slots do not drive
the count.

The preliminary pinned-native probe also disproved a broader size-rejection patch: clearing a
2x2 and 1x1 color attachment together is valid in the oracle and affects only their shared 1x1
extent. That behavior remains unchanged and is bound by the probe; patch 0183 addresses only layer
selection and fail-closed draw completeness.

## Evidence

- The pinned Linux oracle passes the unequal-dimension intersection contract
  (`20260822T131043-1472148`).
- The unchanged canonical source rejects the new helper/wiring contract before build or evidence
  allocation (`20260822T130124-1462250`).
- Final root and descendant-CWD runs compile the real framebuffer translation unit through locked
  native and wasm32 graphs and pass 19 byte-identical contracts. Their 1,849-byte evidence has
  SHA-256 `b27f49a86d700f12a41ae659b37992ff19c30764ba854fe73f830743a3638f19` and
  source SHA-256 `caf86a2ce7469fddbb95fc6c2d9f555d38406eaa71c99891f67734181402d49b`
  (`20260822T130700-1466534`, `20260822T130736-1467397`). The new contract covers eight
  pass-count and eight per-layer decisions, including fixed/all-layer composition, mismatched
  layered counts, zero/out-of-range layers, and `INT_MAX` boundaries.
- A wrong Dawn checkout rejects before its requested evidence directory is created
  (`20260822T130814-1468220`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,591,220 bytes at
  SHA-256 `fc81c4e5bad4857f1397a7cdc16c83759dca7e1aaeadae167356637a2ab8aa53`;
  live/replay manifests are byte-identical at SHA-256
  `0aa8637722e28a9e7a481d3a4f6284561c2139dc98d9a293672ae32539a04b23`
  (`20260822T130604-1465836`, `20260822T130651-1466436`).
- `blender_browser` rebuilds through the locked graph and then reports exact no-work
  (`20260822T130822-1469055`, `20260822T130905-1469456`). The OFF-mode product preflight is green
  (`20260822T130919-1469604`).
- REUSE 6.2.0 is 2,078/2,078 green (`20260822T131220-1472988`). Required M3 and regression
  remain honestly red on the absent strict candidate while M0 remains 6/6 green; the named s7
  software-adapter blocker is unchanged.

## Boundary

The contract creates no WebGPU instance, adapter, device, framebuffer, render pass, draw, pixel,
browser receipt, or result promotion. Live layered-draw proof remains owned by `M3-LINUX-REPLAY`,
still blocked by the named s7 software-adapter condition.
