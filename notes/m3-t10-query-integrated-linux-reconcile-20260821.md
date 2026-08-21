<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 conservative-query integrated Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU query implementation now has a device-free native/wasm32 contract
for its conservative fallback state machine. The shared test compiles `wgpu_query.cc` directly
and covers initialization, five valid begin/end pairs, guarded duplicate begin/end transitions,
and seven exact zero-hit results.

The audit found a disclosure gap rather than a source defect. The exact 197-test M3 census already
contains `query_webgpu_conservative_zero_hit_fallback`, but a test that proves the fallback does not
prove browser selection parity. `ledger/deferred.json` now names `webgpu-sync-occlusion-query`:
WebGPU query results require resolve plus asynchronous buffer mapping, while Blender's legacy
`gpu_select_sample_query` caller consumes `get_occlusion_result()` synchronously inside
`GPU_select_end()`. Normal View3D object selection uses Select-Next; the remaining impact is the
legacy gizmo-map route.

## Evidence

- Root and descendant-CWD runs build only through the locked native and Wasm graphs and emit the
  same 252 bytes, SHA-256 `dffe09b06bc6`, against source digest `e32a886ce6ca`, Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0 (`20260821T224912-689927`,
  `20260821T225047-691688`). Both targets finish at exact Ninja no-work.
- Wrong Dawn and Node identities reject before evidence-directory allocation. The current
  software-only Vulkan adapter is never queried by this contract.
- `upstream/source/blender/gpu/intern/gpu_select_sample_query.cc:147` is the synchronous result
  consumption seam. The only pinned caller of the legacy non-Select-Next route is
  `upstream/source/blender/windowmanager/gizmo/intern/wm_gizmo_map.cc:618`.
- Exact REUSE 6.2.0 is green at 1,997/1,997 files (`20260821T224943-690414`), and the
  windowed product remains locked-Ninja no-work (`20260821T224958-690561`). Required M3 stays
  red for the absent strict candidate; container-backed regression keeps M0 6/6 green while
  M1-M8 retain their existing strict-receipt, APPLY/artifact, browser/run-label, and hardware
  boundaries at `2026-08-21T22:50:18Z`.

## Boundary

This is CPU state-machine and disclosure proof only. It creates no WebGPU instance, adapter,
device, query set, map callback, profile, or receipt. A real browser result path requires an M5
caller continuation (or moving gizmo picking to Select-Next). Required M3 remains red for the
absent complete strict candidate, and the s7 hardware-adapter stop condition remains live.
