<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-H ordered-present boot-crash rollback — 2026-08-27

## Outcome

Patch 0289 retires patch 0288's deferred window-present seam and restores the synchronous GHOST
swap contract. The relinked CAPTURE product is byte-identical in all five recorded artifacts to
the `94cccc1` generation that the Apple M4 Pro rig had already proven boots cleanly. P0-H is
therefore removed without layering another resize experiment onto a hard-crashing product.

P0-E remains open. The rollback returns to its last safe, known-grey resize baseline; it does not
claim that the 10/10 zero-input resize pixel bar passes.

## Regression isolation

The driver measured ten boot aborts in ten fresh Apple hardware attempts against `.wasm.orig`
SHA-256 `e3d284c7da0e11f09beada6c9a4b788044b0c8f9715dcee42bc80839d70c8238`:

```text
BLI_assert failed: source/blender/blenlib/intern/string.cc:34,
  BLI_strdupn(), at 'BLI_strnlen(str, len) == len'
Aborted()
```

The predecessor `94cccc1` generation boots cleanly on the same rig. In the intervening Git range,
`a2532aa`, `9f5037e`, and `ae446ba` change only tests or documentation; `2c887da`/patch 0288 is the
only runtime delta.

Patch 0288 also violates a platform boundary independently of the eventual corrupted string:
`GHOST_ContextWGPUWeb::swapBufferRelease()` returned success after enqueueing the actual surface
acquire/blit/submit for a later asynchronous backend turn. The WM could begin later frame epochs
while the prior swap still existed only as a callback owned by `WGPUContext`'s scheduler. The exact
downstream allocation that made the Blender assertion visible was not symbolicated on the hardware
build, so this pass does not invent a more specific memory-corruption story. A hardware-only hard
abort plus an exact one-runtime-commit bisect is sufficient to reject that cross-frame design.

## Fix

- Patch 0289 reverses patch 0288's `WGPUContext` callback registration and teardown hook while
  retaining 0288 in numbered history as the rejected experiment.
- `GHOST_ContextWGPUWeb` again acquires, encodes, submits, and returns the real result synchronously
  inside `swapBufferRelease()`; the deferred callback types, setter, and member are removed.
- The resize source contract fails if any of the five deferred-present interface markers returns,
  and mutation-tests both an injected backend registration and a bypassed immediate swap.
- The integrated native/Wasm suite retains the scheduler's draw/write chronology contracts but
  removes the test that treated deferred window presentation as desired behavior.

Any future submission-order fix must preserve the synchronous WM/GHOST swap boundary. P0-E work
continues from the backbuffer lifecycle and bounded trace evidence rather than reviving patch 0288.

## Evidence

- Fail-first source rejection: `ledger/buildlogs/20260827T104002-1918739.log`.
- Final four-source, 12-check/11-mutation rollback contract:
  `ledger/buildlogs/20260827T104346-1921736.log`.
- Resize-trace consumer self-check: `ledger/buildlogs/20260827T104346-1921744.log`.
- Patch 0289 inverse/forward byte-exact round-trip:
  `ledger/buildlogs/20260827T105210-1930715.log`.
- Canonical source freeze/replay and receipt mutation self-check:
  `ledger/buildlogs/20260827T104414-1922700.log` and
  `ledger/buildlogs/20260827T104346-1921732.log`.
- Native/Wasm 42-contract integrated GPU suite:
  `ledger/buildlogs/20260827T104433-1922910.log`.
- Locked relink and exact no-work replay:
  `ledger/buildlogs/20260827T104500-1924523.log` and
  `ledger/buildlogs/20260827T105309-1931149.log`.
- Hardware-resize producer, capture producer, and split-preflight self-checks:
  `ledger/buildlogs/20260827T104714-1926200.log`,
  `ledger/buildlogs/20260827T104714-1926204.log`, and
  `ledger/buildlogs/20260827T104714-1926212.log`.
- Fresh fallback-adapter windowed boot reaches running/first-present in 5.578 seconds with zero page
  errors and no Blender assertion: `ledger/buildlogs/20260827T104735-1926401.log`. This binds no
  hardware pixel or performance receipt.

## Relinked CAPTURE generation

| file | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,565 | `9541470a7ee08e9963276fa2e73b6ddf73a65c5bd3efddc23a4ea67a3c1c33ca` |
| `blender_browser.wasm` | 120,501,395 | `bf09a9f563657ada1511ad8a665503243634b18e478563d8301a3a4f7571da7f` |
| `blender_browser.wasm.orig` | 119,148,240 | `aed9ba633f08b02d5fecaa461713cfbc2fabe880c0aad09ab3b88d037e47863a` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `6fd6951fa9afdf27d9159274b43fbde31eae17f73241fda21e6f4ad36b415698` |

These are exactly the recorded `94cccc1` artifact identities. No APPLY/public bundle, tag,
profile, receipt, result, tolerance, golden, blacklist, deferral, or milestone promise changed.
