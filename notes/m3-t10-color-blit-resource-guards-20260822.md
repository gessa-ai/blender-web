<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU color-blit resource guards — 2026-08-22

## Outcome

Patch 0206 makes the cross-format color-blit render fallback stop after a failed shader-module,
uniform-buffer, or bind-group creation. None of those failure paths can now reach pipeline,
`Queue::WriteBuffer`, command-encoder, or render-pass work with a null handle.

## Diagnosis and implementation

`WGPUContext::blit_color_render()` validated its texture views and cached render pipeline but did
not validate three fallible resources used around that pipeline. A null lazy module was forwarded
to pipeline creation, a null 16-byte parameter uniform was forwarded to `WriteBuffer`, and a null
bind group was forwarded into the render pass.

`buffer_create_if_valid()` in `wgpu_common.hh` now owns the create/check/publish transaction used
by both the existing multi-viewport uniform and the color-blit uniform. Failure leaves the caller's
handle unchanged. Exact source-order guards require the lazy module before pipeline lookup, the
uniform before its queue write, and the bind group before encoder/pass allocation.

## Verification

- The unchanged source fails before compilation or evidence allocation at the absent checked-buffer
  transaction (`20260822T225048-2024259`).
- Root and descendant-CWD native/wasm32 runs pass all 17 device-free pipeline contracts. Their
  1,631-byte outputs are byte-identical at SHA-256 `83d1fb7d61b4`, with shipping-source SHA-256
  `2330d72999c9` (`20260822T225534-2029726`, `20260822T225651-2031756`). Wrong Node 22.22.1 is
  rejected before evidence allocation (`20260822T225719-2032531`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,653,105-byte patch is
  SHA-256 `01a119a38ea9`; both manifests are SHA-256 `b00b34743534`. Canonical replay and numbered
  patch reverse-application are green (`20260822T225452-2029111`,
  `20260822T230003-2035983`, `20260822T230553-2040345`). Patch 0206 itself is 2,603 bytes at
  SHA-256 `dd0b560b7de0`.
- The real `blender_browser` rebuild compiles `wgpu_context.cc`, relinks, and then ends exact locked
  no-work (`20260822T225546-2030378`, `20260822T225629-2031515`). OFF preflight binds the resulting
  118,072,081-byte primary Wasm (`20260822T225645-2031711`).
- Required M3 remains honestly red for the absent strict candidate (`20260822T225859-2034179`).
  Container-backed regression restores M0 to 6/6 while M1-M8 retain their existing
  strict-receipt/product/browser/run-label/hardware boundaries (`20260822T225935-2035084`).
- Exact REUSE 6.2.0 reports all 2,134 files compliant (`20260822T230036-2036263`).

## Boundary

No WebGPU instance, adapter, device, module, buffer, bind group, pipeline, pass, draw, pixel, or
browser receipt is claimed. Live proof remains blocked by **no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or milestone promise changed.
