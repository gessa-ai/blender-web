<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 shader-layout resource transaction - 2026-08-23

## Outcome

Patch 0228 (`8bb9908`) distinguishes an intentional semantic auto-layout fallback from failed
WebGPU layout-resource creation. `WGPUShader::finalize()` now fails when either required layout
handle is null, and the bind-group/pipeline-layout pair is published only after both handles have
been created successfully.

## Diagnosis and implementation

`WGPUShader::build_explicit_layout()` formerly returned `void`: an interface binding not covered
by the explicit-layout map, a null bind-group layout, and a null pipeline layout all left
`explicit_layout_ok_` false. The first case is the intentional Dawn auto-layout fallback; the two
resource failures must not enter that path because doing so can revive the depth-texture and
unfilterable-float inference mismatch that the explicit layout exists to prevent.

Patch 0228 changes the method to return a success/failure result while preserving the uncovered
binding as a successful semantic fallback. A small shipping-source transaction creates both
handles in local candidates, short-circuits before pipeline-layout creation when the first handle
is null, and moves neither candidate into caller state unless the complete pair is valid.

## Evidence

- The unchanged shipping source fails before compilation or evidence allocation at the absent
  transaction (`20260823T061939-2458619`).
- Final root and descendant-CWD native/wasm32 runs pass 11 byte-identical integrated contracts
  and 649 cases at 946 bytes, SHA-256
  `249482b4173fb5ad0fa8a025045a759d54b62417e09d9f19c0091ef8c8b67ba3`. The three new cases
  prove first-handle failure is closed without the second call, second-handle failure preserves
  both outputs, and success publishes the pair. The 22 shipping inputs are SHA-256
  `0570146c4a3bea50da58403497546d99dc8c1f3e431c58f7135808241105c108`
  (`20260823T062314-2461146`, `20260823T062350-2461875`). Ambient Node v22.22.1 is rejected
  before its requested evidence directory exists (`20260823T062409-2462353`), and harness
  self-check is green (`20260823T062606-2464380`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,665,023-byte
  patch is SHA-256 `953e7a4e6f7175607e2e0c1157266d969c20084bf9ec095d36fb6faf3f690d5b`,
  and both manifests are SHA-256
  `487309b58d529a84a9f32b96a8a8c81c16239a6c21b79d9c6d8f5aff7f55cf6d`
  (`20260823T062227-2460567`). Canonical-only replay is green
  (`20260823T062441-2463571`). Numbered patch 0228 is 6,343 bytes at SHA-256
  `368b7442c4f20405c4ba9ddda9fdc3d57c5bf50a4e7334b208fe4cb882b457e0`; isolated exact
  forward and reverse comparisons are green.
- The real `blender_browser` recompiles `wgpu_shader.cc` and relinks, then reaches exact
  locked-Ninja no-work (`20260823T062453-2463700`, `20260823T062539-2464167`). OFF preflight
  binds the 118,079,583-byte primary Wasm at SHA-256
  `61e0aa7e80e614a1ffa88fc61f7dc89f3dfe502d8d592992564e7eb77b74b5e9`
  (`20260823T062557-2464332`).
- Final REUSE 6.2.0 is green for all 2,185 files (`20260823T063149-2469209`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T062634-2465522`). Container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and
  independent M8 performance boundaries (`20260823T062654-2465751`).

## Boundary

This is device-free layout-publication proof. It creates no WebGPU instance, accepted adapter,
device, bind-group layout, pipeline layout, pipeline, draw, pixel, browser receipt, profile, or
split product. Live proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA
ships none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or milestone promise changed.
