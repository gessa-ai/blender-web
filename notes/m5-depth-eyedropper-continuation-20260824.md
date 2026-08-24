<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 depth-eyedropper continuation

## Outcome

Commit `88ac170` (patch 0258) converts the depth eyedropper to the shared owned progressive-depth
request. The operator retains its exact producing window, screen, scene, area, region, View3D,
RegionView3D, mouse coordinate, view origin, and accumulation action while browser WebGPU mapping
crosses WM-loop ticks. A settled hit computes the same center-aligned view distance and replays the
stock accumulate, reset, or accumulate-and-set action exactly once.

Native-ready requests still finish during the originating modal event. Browser-pending requests
resume through a 240-by-10-ms timer; confirmation waits behind an in-flight sample, and a newer
drag sample supersedes the old request. Context drift, Escape, failure, timeout, or cancellation
retires without a stale property write. The pinned direct-confirm behavior is preserved: normal
mouse use starts sampling through `EYE_MODAL_SAMPLE_BEGIN`.

## Evidence

- The unchanged depth-eyedropper source rejects before evidence allocation because it lacks the
  owned request and derived-file provenance: `ledger/buildlogs/20260824T194039-399201.log`.
- Linux native/wasm32 verification passes six byte-identical contracts covering 13 cases at 404
  bytes, SHA-256 `10c35e7ff45fa85ea5dc0477eae1c5a7496e3835e8c3fc90b61b6bbe742b482d`.
  The five-file source receipt is SHA-256
  `56a40818b4701105dac0c124d331daf90775163baa4f4a85fe9517cdfe76df41`, twelve source mutations
  fail closed, and numbered patch 0258 round-trips its exact pre/postimage at SHA-256
  `b83e9113c51f6eb16e860175a466158f7425938b631c4004982083112339f30e`:
  `ledger/buildlogs/20260824T195226-407678.log`.
- The actual patched eyedropper translation unit compiles with clang++ 17 and em++ 6.0.5 from the
  locked native and windowed-Wasm Ninja commands:
  `ledger/buildlogs/20260824T194539-402769.log`,
  `ledger/buildlogs/20260824T194547-402835.log`, and the focused receipt above. The broader owned
  readback contract remains green with exactly `depth_pick`, `depth_cache`, and `window_capture`
  visible: `ledger/buildlogs/20260824T195341-408295.log`.
- A fresh isolated source freeze and replay retain 20,258 entries at canonical patch SHA-256
  `d2d16ac680a3bbafc6c0f7e0f6bb16756cdfd962ea6540f90acd18e2c6f229df` and manifest SHA-256
  `d5ad23115b20ba21a77f8bc000237b45df6bf704fc0ab26e650dcfff608c4e77`:
  `ledger/buildlogs/20260824T194915-405419.log` and
  `ledger/buildlogs/20260824T195106-406399.log`.
- The unchanged `blender_browser` graph is locked no-work and OFF preflight still binds the
  657,928-byte JS, 118,955,345-byte Wasm, and 167,143,248-byte data product:
  `ledger/buildlogs/20260824T195400-408768.log` and
  `ledger/buildlogs/20260824T195423-409829.log`. Because `upstream/` is immutable, this graph does
  not incorporate patch 0258; the exact canonical postimage was compiled separately above.
- Required M5 remains honestly red only at the absent current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T195430-409855.log`. Container-backed regression restores M0 to 6/6
  green while M1-M8 retain their strict receipt, browser, split-product, hardware, and release
  boundaries: `ledger/buildlogs/20260824T195453-410122.log`.

## Remaining boundary

This closes one consumer, not the depth-pick family. Navigation, painting, zoom-border, and NDOF
consumers still reach synchronous depth paths; full depth-cache and WM window-capture families
also remain. `ledger/deferred.json` therefore stays `partial` with a truthful count of three
synchronous families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5 acceptance
remain separately deferred by the named blocker `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart path was
attempted.
