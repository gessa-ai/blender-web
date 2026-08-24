<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 texture-paint depth continuation

## Outcome

Commit `91f2974` (patch 0261) converts texture paint's inverted-clone cursor pick to the shared
owned progressive-depth request. The projection handle retains the exact scene, View3D,
RegionView3D, region, window, mouse coordinate, and pre-request cursor. A native-ready request
keeps the stock immediate path; a browser-pending request returns to the WM event loop and commits
the sampled cursor only after the producing context and protected cursor snapshot still match.

The generic paint operator now propagates complete/pending/failed state across its opaque mode
boundary. If mouse release or keyboard confirmation arrives while depth is pending, it owns that
exact custom-data-free finish event and replays a sanitized copy through the stock modal dispatcher
after settlement. New motion supersedes the previous request. Context or cursor drift, unsafe event
payloads, readback failure, timeout, or cancellation remove the timer before destroying the stroke
handle and cannot publish a stale cursor.

## Evidence

- The unchanged predecessor rejects before evidence allocation because the clone cursor still
  calls synchronous auto-distance and has no owned continuation:
  `ledger/buildlogs/20260824T213449-488291.log`.
- Final Linux native/wasm32 verification passes eight byte-identical contracts across 13 cases at
  521 bytes, SHA-256
  `137f8f550443e11e912ea3c284205f3ffeb997ee99480de8541e1db2465c5d84`. The seven-file
  source receipt is SHA-256
  `05fd039b2be6c1b5296485c483f41d37ab2ac3269dc71c6e880b6e495dc93ec9`, all 16 source
  mutations fail closed, and numbered patch 0261 round-trips its three exact source files at
  SHA-256 `c3a794c8097d2947e28787c36fba78dc53d04ea13c21071d68c215bbc479bc7b`:
  `ledger/buildlogs/20260824T220055-509353.log`.
- The exact final projection and operator translation units compile with the locked product
  commands under clang++ 17 (331,656 and 43,888 bytes) and em++ 6.0.5 (242,444 and 31,889
  bytes). The 41-file aggregate owned-readback contract remains byte-identical at 627 bytes,
  binds the painting continuation, and still reports exactly `depth_pick`, `depth_cache`, and
  `window_capture`: `ledger/buildlogs/20260824T220055-509353.log` and
  `ledger/buildlogs/20260824T220116-509701.log`.
- A clean-pin isolated freeze retains 20,258 entries and 283 canonical paths. Its 2,030,141-byte
  patch is SHA-256
  `f0abf626dfcd876e4bca0657baf6448a14aa183470757549f7a18c3469cc60a8`; live and replay
  manifests are byte-identical at SHA-256
  `51501e27a87c2881880f0ec2faa57f75b1dc4acab71cca51c3507d4c34861b28`:
  `ledger/buildlogs/20260824T215735-505811.log`.
- The immutable-upstream `blender_browser` graph and dry run are locked no-work. Strict OFF
  preflight binds the 657,928-byte JavaScript, 118,955,345-byte Wasm, and 167,143,248-byte data
  product: `ledger/buildlogs/20260824T215858-506656.log`,
  `ledger/buildlogs/20260824T215903-506718.log`, and
  `ledger/buildlogs/20260824T215903-506717.log`. This product does not incorporate patch 0261;
  the exact canonical postimages were compiled separately above.
- Required M5 remains honestly red only at the absent current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T215915-506879.log`. Container-backed regression restores M0 to
  6/6 green while M1-M8 retain their existing strict receipt, product, browser, hardware, and
  release boundaries: `ledger/buildlogs/20260824T215944-507388.log`.

## Remaining boundary

This closes texture painting, not the depth-pick family. Zoom-border and NDOF still reach
synchronous depth paths; the full depth-cache and WM window-capture families also remain.
`ledger/deferred.json` therefore stays `partial` with a truthful count of three synchronous
families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5 acceptance
remain separately deferred by the named blocker `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart path was
attempted.
