<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 ordinary-navigation depth continuation

## Outcome

Commit `7f71566` (patch 0259) converts ordinary mouse rotate, move, pan, and zoom initialization to
the shared owned progressive-depth request. The first call preserves Blender's stock camera-lock,
state-backup, perspective-ensure, depth-override order, then stops before the navigation-state tail
when browser mapping is pending. The continuation retains the exact invoke event, fallback point,
effective flags, producing window/screen/area/region/view, and latest safely copyable event. Once
ready, it resolves the stock hit or fallback pivot, completes initialization exactly once, and
replays that latest event through the normal modal function.

Native-ready requests still complete in the invoking event. Browser-pending requests use a bounded
240-by-10-ms timer. Context or view-matrix drift, Escape/modal cancel, external cancellation,
readback failure, and timeout retire the request and restore the backed-up view before freeing the
operator. The embedded transform-navigation utility is explicitly unable to start an unowned
continuation; direct dolly remains on `viewops_data_create`, and NDOF's custom event data keeps its
existing synchronous path.

## Evidence

- The unchanged navigation source rejects before evidence allocation because it has no owned
  continuation or derived-file provenance: `ledger/buildlogs/20260824T202953-436688.log`.
- Final Linux native/wasm32 verification passes six byte-identical contracts covering nine cases
  at 407 bytes, SHA-256
  `bbf3e8d175caeeab19b0d7a51af24ec0586ed8723b297800966908ea51291426`. The ten-file source
  receipt is SHA-256
  `87e7a5f4fc06edcad19b1f59443aec52d341b564ccfdc828ff648fc641ff9a1a`, all 18 source mutations
  fail closed, and numbered patch 0259 round-trips both exact source files at SHA-256
  `504c99c326dcf03b60d74a53c2360329a47e8fd66064c2382ce5463c239653c6`:
  `ledger/buildlogs/20260824T203717-442946.log`.
- The exact final `view3d_navigate.cc` postimage compiles with the locked product commands under
  clang++ 17 and em++ 6.0.5 (41,560-byte and 25,909-byte scratch objects). The broader owned
  readback contract is byte-identical at 627 bytes and still reports exactly `depth_pick`,
  `depth_cache`, and `window_capture`:
  `ledger/buildlogs/20260824T203717-442946.log` and
  `ledger/buildlogs/20260824T203837-443790.log`.
- A clean-pin isolated freeze retains 20,258 entries at canonical patch SHA-256
  `7b50a937b043a58ab2dff7638319daa7efa6d8e16e72fcfdcb19a02b8fddd467` and manifest SHA-256
  `31afa0e3cc47366e416b75e57f7d22182fcde70d45dcffb5570d11cb7beb62a9`; independent replay
  matches the isolated postimage:
  `ledger/buildlogs/20260824T203508-440978.log` and
  `ledger/buildlogs/20260824T203707-442768.log`.
- The unchanged `blender_browser` graph is locked no-work and OFF preflight still binds the
  657,928-byte JS, 118,955,345-byte Wasm, and 167,143,248-byte data product:
  `ledger/buildlogs/20260824T203901-444336.log` and
  `ledger/buildlogs/20260824T203906-444366.log`. Because `upstream/` is immutable, this product
  does not incorporate patch 0259; the exact canonical postimage was compiled separately above.
- Required M5 remains honestly red only at the absent current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T204115-446193.log`. Container-backed regression restores M0 to 6/6
  green while M1-M8 retain their strict receipt, browser, split-product, hardware, and release
  boundaries: `ledger/buildlogs/20260824T204149-446665.log`.
- Repository-local REUSE 6.2.0 covers 2,371/2,371 files with no licensing errors:
  `ledger/buildlogs/20260824T204401-448825.log`.

## Remaining boundary

This closes ordinary mouse navigation, not the depth-pick family. Direct dolly, painting,
zoom-border, and NDOF consumers still reach synchronous depth paths; full depth-cache and WM
window-capture families also remain. `ledger/deferred.json` therefore stays `partial` with a
truthful count of three synchronous families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5 acceptance
remain separately deferred by the named blocker `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart path was
attempted.
