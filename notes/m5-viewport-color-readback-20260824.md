<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 viewport-colour async readback

## Outcome

Commit `c9ac6eb` and numbered patch 0249 retire the View3D eyedropper's viewport-colour
sampling family from the synchronous browser-readback inventory. The session now owns an exact
`GPUReadback` request across event-loop ticks, validates its final byte count before allocating,
consumes it once, and cancels it before releasing the copied texture on failure or destruction.
Native backends still complete immediately through the same public API.

A confirmed sample that is still pending remains modal behind a 10 ms timer. It completes only
after the retained request becomes ready, and fails closed after a readback error or 240 pending
ticks. Pending View3D sampling cannot fall through to the still-synchronous window-colour path.
The stock completion/undo return convention and ready-state background fallback remain intact.

The device-free native and wasm32 contract passes five ownership/continuation contracts and 12
cases with byte-identical 330-byte output at
`89c967ff1091530c46fbfa9d29230aefd4340ade0723abad34191456116c1bdd`. Its seven-file source
receipt is `PASS` at
`05e5649e0992c2f5a4dc0034c9b1b492ff377cd9fbfcd181ca7cf10fe392867c`; eight independent source
mutations fail closed. The broader async-readback census also passes and now names six remaining
synchronous families.

## Evidence

- Unchanged-source rejection: `ledger/buildlogs/20260824T134834-106565.log`.
- Final native/wasm32 contract plus source receipt, including descendant-CWD replay:
  `ledger/buildlogs/20260824T135843-114470.log` and
  `ledger/buildlogs/20260824T140254-119478.log`.
- Broader owned-readback contract and six-family census:
  `ledger/buildlogs/20260824T135854-114882.log`.
- Canonical freeze and clean-pin replay at patch
  `9685835fa4565eb4ee3063bcd66b876a371369c7da90be613ac767ca38e60c0f` and manifest
  `03217cbb56b30b49e20d9fddab3d0d5956f0f0232d044944bb3d02f876e06ae7`:
  `ledger/buildlogs/20260824T135744-112939.log` and
  `ledger/buildlogs/20260824T135828-114315.log`.
- Numbered patch 0249 is
  `de6a6d7962a585c1e5344326327d621631289dd9fa51269072683f8970c8e650` and reverse/forward
  round-trips the three exact pre/postimages:
  `ledger/buildlogs/20260824T140638-122768.log`.
- Actual native editor targets compile and end locked no-work:
  `ledger/buildlogs/20260824T140128-118754.log` and
  `ledger/buildlogs/20260824T140303-119698.log`.
- Actual windowed `gpu_tests` and `blender_browser` rebuild, locked no-work, and non-split OFF
  preflight: `ledger/buildlogs/20260824T135903-115089.log`,
  `ledger/buildlogs/20260824T140104-118196.log`, and
  `ledger/buildlogs/20260824T140104-118197.log`. The rebuilt JS/Wasm/data identities are
  657,928 bytes at `9c174c77fec6`, 118,910,249 bytes at `752dc69f16a1`, and 167,143,248 bytes
  at `09e58a25849e`.
- Post-source-commit contract: `ledger/buildlogs/20260824T140833-124956.log`.
- Required M5 scope: `ledger/buildlogs/20260824T140845-125171.log`; it remains honestly red only
  at the absent `blender_browser.deferred.wasm` complete-product boundary.
- Container-backed regression: `ledger/buildlogs/20260824T140918-125855.log`; M0 is 6/6 green,
  while M1-M8 retain their existing strict-manifest, APPLY, browser, product, and release
  boundaries.

## Remaining boundary

Six synchronous caller families remain under `gpu-sync-readback-windowed`: legacy selection
buffer, depth pick, depth cache, WM window capture, WM window colour sample, and the screenshot
operator. Patch 0249 does not claim to convert any of them.

The contract creates no WebGPU instance, adapter, device, browser profile, split product, or live
receipt. Live C1 and aggregate M5 acceptance therefore remain separately deferred by the named
blocker `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)`. No dzn, Windows interop, or WSL restart path was attempted.
