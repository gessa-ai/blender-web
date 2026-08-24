<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed sculpt/paint registration cut — 2026-08-24

> **Historical rejected experiment.** `AUDIT-R9-M8-FIDELITY-RESTORE` reverted this cut and
> retired its size-only deferral. The measurements below remain audit evidence; they do not
> describe the shipping windowed profile. See `notes/m8-registration-fidelity-restore-20260824.md`.

## Outcome

The windowed browser profile no longer registers the non-launch mesh/curves sculpt operators,
texture/vertex/weight-paint operators, paint macros, or sculpt/paint keymaps. Patch 0248 guards
only those central registration roots. Blender's sculpt/paint data and RNA, file-reading
structures, shared Workbench helpers, mode-exit and undo support remain compiled; native and
headless Wasm builds retain the stock registration path through
`WITH_BLENDER_WEB_SCULPT_PAINT=ON`.

This removes 2,825,954 raw Wasm bytes and exactly 489,232 Brotli-q11 bytes from the current
windowed module. It is an honest M8 reduction, not a launch-gate pass: the resulting Wasm alone is
24,236,667 q11 bytes, already 9,236,667 bytes over LAUNCH.md's complete 15 MB interactive-payload
budget before stage-0 data.

## Fail-first boundary

The first experiment omitted the entire 16.3 MB `bf_editor_sculpt_paint` archive. The real locked
link rejected that cut in five seconds: Workbench shading, generated RNA, undo, mesh editing, and
space registration still require shared paint/sculpt helpers. That experiment was reversed
exactly and never entered a numbered patch (`ledger/buildlogs/20260824T041203-3708945.log`).

The accepted cut instead relies on the shipped linker's function-level dead-code elimination.
Removing only six ordinary registration/keymap roots makes their operator implementation closure
unreachable while leaving the shared symbols above intact.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; the q5 diagnostic also matched ambient Node 25 byte-for-byte.

| module | SHA-256 | raw bytes | q11 bytes |
|---|---|---:|---:|
| pre-cut saved baseline | `cace05581a682aa92ca4a94c7430cf4af30c3726de93bf4fe79b8fbc081a4380` | 118,772,391 | 24,725,899 |
| patch 0248 candidate | `1e9c2b8cc9ff45a3c49d0b20899c1feab4a5b30727e6c7dba19b44ada8a4bda3` | 115,946,437 | 24,236,667 |
| reduction | — | **2,825,954** | **489,232** |

The lower-quality diagnostic independently moved 29,177,346 to 28,635,964 bytes, a 541,382-byte
reduction.

## Verification

- The accepted `blender_browser` build is green, followed by an exact locked no-work dry run
  (`ledger/buildlogs/20260824T041604-3712128.log`,
  `ledger/buildlogs/20260824T041908-3714027.log`).
- The headless Wasm and native parity `bf_editor_space_api` targets both rebuild green and their
  generated compile rules contain `-DWITH_BLENDER_WEB_SCULPT_PAINT`; the windowed rule does not
  (`ledger/buildlogs/20260824T041946-3715149.log`,
  `ledger/buildlogs/20260824T041954-3715237.log`).
- The focused verifier binds all six guarded calls, the default-ON/headless and forced-OFF/windowed
  CMake contracts, patch 0248, and its series entry. Four in-memory mutations are rejected
  (`ledger/buildlogs/20260824T043008-3722359.log`).
- Patch 0248 reverses and reapplies byte-identically. The isolated source freezer starts from the
  exact pin and replays 20,258 entries across 259 paths; canonical patch SHA-256 is
  `65826257a770bdb03a4fcc52278a298418c3bc0fe81d18b369fa78292379e7a3`
  (`ledger/buildlogs/20260824T042806-3720519.log`,
  `ledger/buildlogs/20260824T042904-3721165.log`).
- Pinned REUSE 6.2.0 is green for 2,258/2,258 files
  (`ledger/buildlogs/20260824T044320-3731830.log`).
- Container-backed regression at 2026-08-24T04:31Z keeps M0 6/6 green. M1–M8 retain their existing
  strict-manifest, APPLY/split-product, browser/hardware, and release boundaries. Required M8
  remains honestly red with 25 technical failures; no result was promoted.

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-sculpt-paint-windowed`, with desktop authoring as the workaround and an explicit
revisit condition. Re-enable the feature and rerun all size/runtime receipts if a truthful
accepted-hardware profile split later clears the 15 MB bar without this cut.

No browser, adapter, profile, split product, or receipt was created. Mesa dzn and Windows were not
attempted, and WSL was not restarted.
