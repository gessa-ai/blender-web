<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 direct-dolly depth continuation

## Outcome

Commit `1f06cdb` (patch 0260) routes the direct Dolly View operator through the same owned generic
navigation-depth continuation as ordinary mouse navigation. A pending browser read now returns to
the WM loop before dolly's perspective, delta, trackpad, or modal tail executes. Settlement resumes
the exact invoke event once; the latest safe queued event is replayed through the normal dolly apply
callback.

The stock external execute path remains context-only. Interactive delta and vertical/horizontal
trackpad one-shots still apply their original factors, while modal motion, confirm, Escape,
autokey, undo, and move/rotate switching retain their existing behavior. Context drift, readback
failure, timeout, or external cancellation restores the backed-up producing view and frees the
owned request before any stale dolly movement.

## Evidence

- The patch-0259 predecessor rejects before evidence allocation because direct dolly has neither
  the derived-file provenance nor the owned generic wiring:
  `ledger/buildlogs/20260824T205907-461096.log`.
- Final Linux native/wasm32 verification passes eight byte-identical contracts across 16 cases at
  556 bytes, SHA-256
  `7fb251b08bb32d209573080ed199fdf1f794c8d6ccd089de7b0ce7916c362c67`. The ten-file source
  receipt is SHA-256
  `d2d0f46c39a8789df95da8156d7d5b220cdaee8f41fe9d4bffb00a6e47ebce24`, all 24 source
  mutations fail closed, and numbered patch 0260 round-trips its exact source file at SHA-256
  `f182470f8cee54eec4384ff8fdeeb1b6b775a15a4e754f051794b1862222c67d`:
  `ledger/buildlogs/20260824T211104-470894.log`.
- The exact final `view3d_navigate_view_dolly.cc` postimage compiles with the locked product
  commands under clang++ 17 and em++ 6.0.5 (12,560-byte and 8,038-byte scratch objects). The
  broader owned-readback contract remains byte-identical at 627 bytes, adds the direct-dolly
  source boundary, and still reports exactly `depth_pick`, `depth_cache`, and `window_capture`:
  `ledger/buildlogs/20260824T211104-470894.log` and
  `ledger/buildlogs/20260824T210742-468163.log`.
- A clean-pin freeze retains 20,258 entries with identical live/replay manifest SHA-256
  `f86acb88986286ab7a21691ff10477da840ad10b871ca93aa8ea6705eab9d34d`. The 280-path
  canonical patch is 2,007,419 bytes at SHA-256
  `9bf4b5bb81528d87edcf8e9d713820e904754b83e6d3512a3a7b4ac903f2eb45`, and independent replay
  matches the isolated postimage:
  `ledger/buildlogs/20260824T210522-465849.log` and
  `ledger/buildlogs/20260824T211234-473545.log`.
- The immutable-upstream `blender_browser` graph rebuild and dry run are locked no-work. OFF
  preflight still binds the 657,928-byte JavaScript, 118,955,345-byte Wasm, and 167,143,248-byte
  data product: `ledger/buildlogs/20260824T210819-469598.log`,
  `ledger/buildlogs/20260824T210819-469627.log`, and
  `ledger/buildlogs/20260824T210820-469597.log`. This product does not incorporate patch 0260;
  the exact canonical postimage was compiled separately above.
- Required M5 remains honestly red only at the absent current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T210957-470354.log`. Container-backed regression restores M0 to 6/6
  green while M1-M8 retain their existing strict-receipt, browser, split-product, hardware, and
  release boundaries: `ledger/buildlogs/20260824T211212-472593.log`.

## Remaining boundary

This closes direct dolly, not the depth-pick family. Painting, zoom-border, and NDOF consumers
still reach synchronous depth paths; the full depth-cache and WM window-capture families also
remain. `ledger/deferred.json` therefore stays `partial` with a truthful count of three synchronous
families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5 acceptance
remain separately deferred by the named blocker `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart path was
attempted.
