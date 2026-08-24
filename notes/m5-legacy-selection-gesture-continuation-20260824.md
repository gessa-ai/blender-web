<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 legacy selection gesture continuation

## Outcome

Commit `91cc626` (patch 0255) routes edit-mesh box, lasso, and circle visibility bitmaps through
one owned raw selection-buffer session in the windowed wasm profile. Each request retains its exact inclusive
rectangle, polygon vertices, strict circle radius, raw ID-to-bitmap mapping, and producing select
context until the operator continuation consumes it. Native and direct-execution callers retain
the synchronous path.

Box and lasso resume through a 240-by-10-ms timer after the stock gesture has finished. Circle
retains its gesture while the request is pending, preserves the producing selection operation,
center, and radius, and replays up to 512 queued input events in order behind the active request.
Terminal failure, timeout, cancellation, context/key drift, and queue overflow retire the owned
request without applying the pending selection.

All three edit-mesh paths now settle before pre-deselect, UV synchronization, or mesh selection
mutation. Multi-object edit mode consumes one context-bound bitmap and reuses it for every object
in that invocation.

## Evidence

- The unchanged predecessor rejects before evidence allocation at the missing owned-bitmap API:
  `ledger/buildlogs/20260824T173435-300723.log`.
- Final source verification rejects 28 independent mutations. Native and wasm32 pass seven
  byte-identical contracts, including all three bitmap shapes and five settlement/replay/failure
  cases, at 627 bytes and SHA-256
  `ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`; the 33-file source
  receipt is SHA-256 `9f7064868978a803728299d51a481ba7f25cc7c32d0be76c3e5e4efa943a0af6`:
  `ledger/buildlogs/20260824T175224-312862.log` and
  `ledger/buildlogs/20260824T175248-313148.log`.
- Numbered patch 0255 round-trips its three exact pre/postimages at SHA-256
  `ba5c9722bcf9d364e486f76c029434b45fb4a9b434042d0a4968c6f0351dbcdc`. Canonical replay
  retains 20,258 entries across 274 paths and 232 active patches, with patch SHA-256
  `e1a79ce8c67a7315ee905878c9760a14083090093027202dd1bb41eaed84f5af` and manifest SHA-256
  `45166173c91efddf0eb9288c1959842440c917accc09ece34cca75921bb496e0`:
  `ledger/buildlogs/20260824T175832-318333.log`.
- The actual native draw/View3D libraries build successfully, while the wasm draw/View3D and
  optimized browser graph end locked-Ninja no-work:
  `ledger/buildlogs/20260824T175840-318456.log` and
  `ledger/buildlogs/20260824T175851-318531.log`. The browser product relink and strict OFF
  preflight bind 657,928-byte JavaScript at SHA-256
  `e3c18011c1eb15487646319a83b4390129afc5d198d699c08ac7a4a08565f756`, 118,947,867-byte
  Wasm at SHA-256 `188ef4eb0e3d66198c2e7eea2c455db042429b316b27c465c8c9a7a636161a1a`, and
  167,143,248-byte data at SHA-256
  `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`:
  `ledger/buildlogs/20260824T175431-314588.log`,
  `ledger/buildlogs/20260824T175521-315095.log`, and
  `ledger/buildlogs/20260824T175544-315290.log`.
- Required M5 remains honestly red only at its missing current deferred split binary:
  `ledger/buildlogs/20260824T175600-315418.log`. Container-backed regression restores M0 to
  6/6 green while M1-M8 retain their existing strict receipt, browser, product, hardware, and
  release boundaries: `ledger/buildlogs/20260824T175649-316105.log`. Final REUSE 6.2.0 covers all
  2,335 files: `ledger/buildlogs/20260824T180354-322185.log`.

## Remaining boundary

`gpu-sync-readback-windowed` now retains three synchronous families: depth pick, depth cache, and
WM window capture. Patch 0255 closes only edit-mesh gesture selection at the source/device-free
contract boundary; it creates no live GPU evidence.

No WebGPU adapter/device, browser profile, split product, live receipt, result promotion,
dependency decision, new deferral, tolerance, golden, blacklist, or promise changed. Live C1 and
aggregate M5 acceptance remain separately deferred by the named blocker `no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or
WSL restart path was attempted.
