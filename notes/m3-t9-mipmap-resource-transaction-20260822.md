<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU mipmap resource transaction — 2026-08-22

## Outcome

Patch 0207 makes `WGPUTexture::generate_mipmap()` fail closed across shader-module,
command-encoder, texture-view, bind-group, render-pass, and finished-command-buffer creation.
Any failed handle now abandons the local encoder before queue submission, so a dependent mip
chain cannot be partially generated after a later layer or mip fails.

## Diagnosis and implementation

The mipmap fallback checked only render-pipeline creation. A null shader module could reach that
pipeline, a null encoder could reach pass allocation, and null bind-group, render-pass, or command-
buffer handles could reach dependent work. A missing source or destination view used `continue`,
which allowed already encoded passes plus later passes to be submitted with a hole in the
dependent mip chain.

The shipping method now validates each fallible handle before its first dependent operation.
Missing views return instead of continuing, and a failed later pass leaves the method without
calling `Finish()` or `Submit()`. A failed `Finish()` is also rejected before the only queue
submission. Previously encoded work remains private to the abandoned local encoder.

## Verification

- The unchanged extracted method fails the module-failure ordering case before valid evidence can
  be produced (`20260822T232058-2053305`).
- Final root and descendant-CWD native/wasm32 runs pass all 24 integrated texture contracts with
  byte-identical 2,503-byte output at SHA-256
  `2f38544ff7b5f24c598688f2ce8d81864a5dc19ddb5beb83fa70428a74a15dba`; the 25 shipping inputs
  bind at SHA-256 `8388985fd4c1b9271817da23221c907559f9e499b6be03c4026ab8074dd75c42`
  (`20260822T233259-2065669`, `20260822T232414-2057100`). The exact-method contract covers nine
  cases: one successful two-layer, three-mip chain encodes four passes and submits once, while all
  eight injected resource failures stop before submission. Wrong Node 22.22.1 is rejected before
  evidence allocation (`20260822T232557-2059239`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,653,352-byte
  canonical patch is SHA-256
  `cd9260eb2f714cd59a9075135dd2f6e8d0e8e34fc49fa09b958110d4ea86dedf`; both manifests are
  SHA-256 `98a5154e3fb1e4f09b287f80db642725917e009a0378d90a5c4d03d86e68cc2d`
  (`20260822T232256-2054799`, `20260822T232813-2062180`). The final 1,922-byte patch 0207 is
  SHA-256 `07c99b0a80e161982932f773da8f61925ba2af66482a69b7afb556bd1948d740` and passes ordinary
  reverse application (`20260822T233259-2065668`).
- The real `blender_browser` rebuild compiles `wgpu_texture.cc`, relinks, and ends exact locked
  no-work (`20260822T232431-2057758`, `20260822T232525-2058948`). OFF preflight binds the
  118,072,207-byte primary Wasm (`20260822T232813-2062185`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T232625-2059813`). Container-backed regression keeps M0 at 6/6 while M1-M8 retain
  their existing strict-receipt/product/browser/run-label/hardware boundaries
  (`20260822T232633-2059933`).
- Exact REUSE 6.2.0 reports all 2,138 files compliant (`20260822T233454-2066907`).

## Boundary

No WebGPU instance, adapter, device, module, encoder, view, bind group, pass, command buffer,
submission, pixel, or browser receipt is claimed. Live proof remains blocked by **no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or milestone promise changed.
