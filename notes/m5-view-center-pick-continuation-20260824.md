<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 view-center depth continuation

## Outcome

Commit `97729d0` (patch 0257) converts `VIEW3D_OT_view_center_pick`, the second concrete
consumer in the remaining View3D depth-pick family, to the shared owned progressive-depth
request. The operator retains its exact mouse coordinate, smooth-view duration, View3D,
RegionView3D, region, window, and raw view state while browser WebGPU mapping crosses WM-loop
ticks. A settled hit starts the same smooth-view target as stock Blender; a ready request with no
surface preserves the stock simple-pan fallback.

Native-ready requests still finish during invoke. Browser-pending requests resume through a
240-by-10-ms timer while unrelated input passes through. A newer center request for the same
window/region supersedes the old one; Escape, failure, timeout, cancellation, context/view drift,
or an intervening smooth-view transition retires the request without moving the view.

## Evidence

- The unchanged center-pick source rejects before evidence allocation because it has no owned
  request/list/continuation: `ledger/buildlogs/20260824T190852-372907.log`.
- Post-commit Linux native/wasm32 verification passes six byte-identical contracts covering 13
  cases at 410 bytes, SHA-256
  `d5806f9ce4279956f3070db055216693cd9408e1efffcb5aadff3e7097f67894`. The five-file source
  receipt is SHA-256
  `247af2c20b8b10048c4b950d0e0863de0704d839ccb098f6c5326af77ba6e81d`, twelve source
  mutations fail closed, and numbered patch 0257 round-trips its exact pre/postimage at SHA-256
  `5cdb148413c6eaad5cf38bba966b948478f1e28085552c417e8d9a7584f81a37`:
  `ledger/buildlogs/20260824T192700-388486.log`.
- The actual native and wasm32 View3D editor libraries compile cleanly:
  `ledger/buildlogs/20260824T191259-375933.log` and
  `ledger/buildlogs/20260824T191324-376232.log`. The broader owned-readback contract remains
  green with exactly `depth_pick`, `depth_cache`, and `window_capture` visible:
  `ledger/buildlogs/20260824T191927-380778.log`.
- A fresh source freeze and isolated replay retain 20,258 entries at canonical patch SHA-256
  `99e6a3db690776d65f70ea67707d6e746e4e6dd5991788b867f353b8905e7757` and manifest
  SHA-256 `09616055a89df06eab09fccecf6d9d9d7e42dd0fb6b2a85b06555371495afaf5`:
  `ledger/buildlogs/20260824T191754-378605.log` and
  `ledger/buildlogs/20260824T191837-379922.log`.
- The real `blender_browser` graph rebuilds and then ends locked no-work; OFF preflight binds
  657,928-byte JS, 118,955,345-byte Wasm, and 167,143,248-byte data:
  `ledger/buildlogs/20260824T191936-380987.log`,
  `ledger/buildlogs/20260824T192129-383700.log`, and
  `ledger/buildlogs/20260824T192139-383803.log`.
- Required M5 remains honestly red only at the absent current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T192220-384085.log`. Container-backed regression restores M0 to
  6/6 green while M1-M8 retain their existing strict-receipt, browser, split-product, hardware,
  and release boundaries: `ledger/buildlogs/20260824T192239-384277.log`.

## Remaining boundary

This closes one consumer, not the depth-pick family. Navigation, depth eyedropper, painting,
zoom-border, and NDOF consumers still reach synchronous depth paths; full depth-cache and WM
window-capture families also remain. `ledger/deferred.json` therefore stays `partial` with a
truthful count of three synchronous families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5 acceptance
remain separately deferred by the named blocker `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart path was
attempted.
