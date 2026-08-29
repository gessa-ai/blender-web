<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection draw retry — 2026-08-29

## Outcome

The exact slow/sparse post-`Alt+A` sequence now completes a real viewport Cube selection and a
later isolated orbit on the software diagnostic lane. Patch
`0306-gpu-webgpu-select-draw-retry.patch` prevents a first-use WebGPU selection pass from accepting
its cleared output after any required draw was deferred. The final CAPTURE product is relinked, but
P0-I/J remain open until the driver passes the unchanged 10/10 Apple-hardware pixel bar and the
same-generation composed interaction/resize gauntlet.

## Root cause

The prior stream-continuation candidate fixed `GPU_READBACK_ERROR_SOURCE_UNAVAILABLE`, but its
valid readback could still be semantically false. An exact projected click reached Blender at
`(524, 387)`, built four selection IDs, and mapped four untouched `0xffffffff` words. Bounded live
instrumentation showed the real mesh selection pass (`overlay_depth_mesh_conservative_selectable`)
and its related selectable overlay variants returning while browser shader modules were still
pending. The batch module gate did not increment `redraw_drop_generation`, so select-next classified
the attempt as clean and published zero hits.

The first retry prototype exposed a second ordering constraint: a one-draw selection manager cannot
wait for a persistent buffer allocation to publish after that manager is destroyed. Retrying such
an attempt simply recreated the same pending buffers. Selection-created storage, uniform, vertex,
index, and float texel-buffer allocations must therefore share the current ordered queue epoch.

## Fix

- Select-next snapshots the draw-drop generation at the start of each exact request. If the
  generation changes before readback ownership transfers, it cancels the cleared readback and waits
  for a later resource-readiness edge before rerunning the request. A clean empty readback remains a
  valid miss.
- Batch direct/indirect and Immediate now classify shader-module deferral as a dropped draw. Their
  pipeline-null paths do the same; compute and framebuffer helper pipeline-null paths participate in
  the same signal.
- `Buffer::create_for_draw_scope()` keeps ordinary allocations persistent, but routes buffers first
  created under Emscripten `G_FLAG_PICKSEL` through the current transient resource gate. The
  provisional handle can be encoded immediately while validation still orders all dependent queue
  work.
- The slow/sparse producer now performs the exact isolated orbit, clicks the live projected Cube
  position, waits for native selection plus GHOST/WM/content retirement, and sends the recovery
  orbit only after that selection settles.

## Evidence

- fail-first retry contract: `ledger/buildlogs/20260829T065734-3897676.log`
- first retry prototype compiled/relinked but reproduced the persistent-allocation loop:
  `ledger/buildlogs/20260829T070018-3899395.log`,
  `ledger/buildlogs/20260829T070033-3899489.log`,
  `ledger/buildlogs/20260829T070333-3902740.log`
- final 11-file numbered patch reverse/forward replay and 13-mutation source/model self-check:
  `P0J_PATCH_REVERSE_FORWARD_PASS files=11`,
  `ledger/buildlogs/20260829T074118-3930133.log`
- affected Wasm objects and final deterministic relink/no-work:
  `ledger/buildlogs/20260829T071431-3909734.log`,
  `ledger/buildlogs/20260829T073855-3928270.log`,
  `ledger/buildlogs/20260829T074122-3930272.log`,
  `ledger/buildlogs/20260829T074231-3931408.log`
- final slow/sparse diagnostic: real Cube selection, recovery orbit, zero page/lifecycle/selection
  errors; selection drain 13,514 ms and recovery orbit 2,116 ms on cold SwiftShader:
  `ledger/buildlogs/20260829T074236-3931471.log`
- rapid diagnostic also completes with zero wrapper failure:
  `ledger/buildlogs/20260829T074631-3934427.log`
- select-stream, rapid-drain, hardware-gauntlet, pinned capture-profile, and Node syntax self-checks:
  `ledger/buildlogs/20260829T074118-3930132.log`,
  `ledger/buildlogs/20260829T074118-3930149.log`,
  `ledger/buildlogs/20260829T074118-3930141.log`,
  `ledger/buildlogs/20260829T074625-3934379.log`,
  `ledger/buildlogs/20260829T074118-3930134.log`
- canonical freeze/replay: 20,258 entries, 305 paths, snapshot SHA-256
  `adf671e3c2b34802c85b49bb371c9ef6b0e6564d1497c29059713642cdaf495f`:
  `ledger/buildlogs/20260829T074348-3932171.log`,
  `ledger/buildlogs/20260829T074435-3933321.log`
- REUSE 6.2.0: `ledger/buildlogs/20260829T074555-3934172.log`

The numbered-history diagnostic retains its long-standing independent failure at patch 0016's
overlapping `gpu/CMakeLists.txt` hunk (`ledger/buildlogs/20260829T074435-3933328.log`); canonical
replay is the release authority and passed with the new patch. No receipt, profile, APPLY product,
public bundle, tag, result promotion, tolerance, golden, blacklist, deferral, or launch claim is
changed by the software-adapter evidence.

## Candidate identity and closure bar

- `blender_browser.js`: `90f60eb449c1`
- `blender_browser.wasm`: `20ad4e454355`
- `blender_browser.wasm.orig`: `5b95408deafe`
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `f2c58964c8af`

The driver must run the exact slow/sparse selection/recovery sequence 10/10 on the accepted Apple
adapter, require zero visible artifacts and zero selection report/page error, and bind those runs to
this exact product inventory. The same generation must then pass the composed P0-E interaction
gauntlet. Until then this is a testable hardware candidate, not P0 closure.
