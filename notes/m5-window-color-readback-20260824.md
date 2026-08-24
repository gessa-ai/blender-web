<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 asynchronous window-colour sampling

## Outcome

Commit `c9b0118` and numbered patch 0252 convert the non-viewport colour-sampling fallback used
by all three modal eyedropper consumers. `EyedropperWindowColorSampleSession` owns one exact
full-window WM asynchronous capture, polls it without blocking the WM worker, and shares the settled
snapshot across the main colour eyedropper, colour-band gradient/point sampling, and grease-pencil
material sampling. Native front-buffer sampling remains immediate.

A full-window snapshot is deliberate. Colour-band sampling interpolates many points along one
confirmed line, so a sequence of one-pixel GPU requests would both serialize callbacks and risk
mixing frames. One owned snapshot gives every point the same frame, preserves the established
bottom-up WM pixel coordinates and exact RGBA8-to-float conversion, and is reusable until the
window changes or the modal operation exits.

Each consumer retains the event data and action needed to resume after settlement. Pending work
returns to a bounded timer; ready work resumes exactly once; failure, timeout, cancellation, and
window replacement retire the request before releasing its pixels. No shared sampling path calls
the synchronous offscreen fallback in the windowed profile.

## Evidence

- The dedicated verifier rejects the predecessor before evidence allocation because the shared
  session is absent: `ledger/buildlogs/20260824T155349-214312.log`.
- Final source verification rejects 11 mutations. Native and wasm32 compile the actual
  `gpu_readback.cc` and pass six contracts / 13 cases with byte-identical 306-byte output at
  SHA-256 `7f67855bb4abc520784b47e78078583320306a2b96654b81b67e6a0e27dd5464`; the six-file source
  receipt is SHA-256 `f95e2afe706277da9e9f0ab150ce05a6d815ff5868a856eff40dda0a961007e3`:
  `ledger/buildlogs/20260824T155547-216321.log`.
- The broader owned-readback contract remains byte-identical and now reports four synchronous
  caller families: `ledger/buildlogs/20260824T155805-219151.log`. The reconciled viewport-colour
  and screenshot contracts also remain green:
  `ledger/buildlogs/20260824T155746-218358.log` and
  `ledger/buildlogs/20260824T155756-218744.log`.
- Patch 0252 is SHA-256
  `09448cbff4fce7013fae1dd80d28c7f2a1ca868ab092a1e9945b4f47a2429b6c` and round-trips its four
  exact pre/postimages. Canonical freeze/replay passes with 20,258 entries, 271 paths, patch
  SHA-256 `c4140214bd8851ef8a7b552b903ae804f05f8d95772b2ed7a86030dd24392f42`, and manifest SHA-256
  `a135e34a1d5ad8d62a4520acce3c8cdbcc40d2b98bf5b1c9dc1db32a940c5603`:
  `ledger/buildlogs/20260824T155451-215573.log` and
  `ledger/buildlogs/20260824T155539-216202.log`.
- The actual native GPU/window-manager/editor libraries build and end locked-Ninja no-work:
  `ledger/buildlogs/20260824T154611-208971.log` and
  `ledger/buildlogs/20260824T160412-226323.log`. The optimized windowed browser product relinks,
  ends locked-Ninja no-work, and passes the strict OFF preflight with 657,928-byte JavaScript,
  118,918,379-byte Wasm, and 167,143,248-byte data:
  `ledger/buildlogs/20260824T155814-219359.log`,
  `ledger/buildlogs/20260824T160208-225216.log`, and
  `ledger/buildlogs/20260824T160401-226245.log`.
- Required M5 remains honestly red only at the absent `blender_browser.deferred.wasm` complete
  product: `ledger/buildlogs/20260824T160417-227031.log`. Pinned-container regression restores M0
  to 6/6 green while retaining the existing M1-M8 strict receipt, APPLY/browser, product, and
  release boundaries: `ledger/buildlogs/20260824T160449-227981.log`.
- The post-regression compliance refresh removes both transient staleness diagnostics and leaves
  M8's unchanged 23 technical boundaries; REUSE 6.2.0 covers all 2,328 files:
  `ledger/buildlogs/20260824T160735-230708.log`,
  `ledger/buildlogs/20260824T160739-230739.log`,
  `ledger/buildlogs/20260824T160748-230878.log`, and
  `ledger/buildlogs/20260824T160751-230932.log`.

## Remaining boundary

Four synchronous caller families remain under `gpu-sync-readback-windowed`: legacy selection
buffer, depth pick, depth cache, and WM window capture. Patch 0252 closes only the shared WM
window-colour family at the source/device-free contract boundary.

This work creates no WebGPU adapter/device, browser profile, split product, live receipt, result
promotion, dependency decision, tolerance, golden, blacklist, or promise. Live C1 and aggregate
M5 acceptance remain separately deferred by the named blocker `no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL restart
path was attempted.
