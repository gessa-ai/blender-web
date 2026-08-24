<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed Grease Pencil registration cut — 2026-08-24

> **Historical rejected experiment.** `AUDIT-R9-M8-FIDELITY-RESTORE` reverted this cut and
> retired its size-only deferral. The measurements below remain audit evidence; they do not
> describe the shipping windowed profile. See `notes/m8-registration-fidelity-restore-20260824.md`.

## Outcome

The windowed browser profile no longer registers legacy annotation or Grease Pencil editing
operators, macros, and keymaps. Patch 0249 guards only five central registration roots. Grease
Pencil DNA/RNA, file loading, viewport drawing, and the rest of Blender's shared object/draw
infrastructure remain compiled; native and headless Wasm builds retain the stock registration
path through `WITH_BLENDER_WEB_GREASE_PENCIL=ON`.

This removes 1,965,548 raw Wasm bytes and exactly 336,480 Brotli-q11 bytes from the current
windowed module. The resulting Wasm is 23,900,187 q11 bytes. M8 therefore remains honestly RED:
the Wasm alone is still 8,900,187 bytes over LAUNCH.md's complete 15 MB interactive-payload
budget before stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0249,
the option contract, and guarded registration roots were absent
(`ledger/buildlogs/20260824T045225-3739341.log`).

The accepted patch leaves the editor libraries in the build and relies on the shipped linker's
function-level dead-code elimination. Only these five roots become unreachable in the windowed
profile:

- legacy annotation operator registration;
- Grease Pencil operator registration;
- Grease Pencil macro registration;
- legacy annotation keymap registration;
- Grease Pencil keymap registration.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback makes non-web and headless configurations preserve Blender's stock behavior.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`; q5 is retained only as a faster independent diagnostic.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0248 baseline | `1e9c2b8cc9ff45a3c49d0b20899c1feab4a5b30727e6c7dba19b44ada8a4bda3` | 115,946,437 | 28,635,964 | 24,236,667 |
| patch-0249 candidate | `e6cfb7adebecdb3b9616bdb8a1dbf639711b8229fee88cd8c10bb983bc5094dd` | 113,980,889 | 28,227,396 | 23,900,187 |
| reduction | — | **1,965,548** | **408,568** | **336,480** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T045356-3740748.log` and
`ledger/buildlogs/20260824T045731-3742887.log`.

## Verification

- The real `blender_browser` rebuild and exact no-work rerun are GREEN. A second rebuild after
  patch round-trip reproduced the exact candidate SHA-256 and byte count
  (`ledger/buildlogs/20260824T045639-3742381.log`,
  `ledger/buildlogs/20260824T050439-3750073.log`,
  `ledger/buildlogs/20260824T050527-3751283.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their emitted compile rules
  contain `WITH_BLENDER_WEB_GREASE_PENCIL`; the windowed rule does not
  (`ledger/buildlogs/20260824T050026-3744540.log`,
  `ledger/buildlogs/20260824T050035-3745434.log`).
- Root and descendant focused runs bind all five calls, the config/CMake contract, the series
  entry, four rejecting mutations, and an isolated reverse/forward exact-byte patch round-trip.
  Patch 0249 is SHA-256 `cbb123f9ee8d43efb16b106e4a82fa922dd738aedfaece9d7b76f6356414f85a`
  (`ledger/buildlogs/20260824T050953-3753860.log`,
  `ledger/buildlogs/20260824T050956-3753908.log`).
- The canonical freezer replays 20,258 entries across 259 paths. The frozen patch is SHA-256
  `fb521973f8cf108e2b3aaa1f58ecaffcb8e96415f991cb64f744f827dc946e4f`, and root/descendant
  canonical verification is GREEN (`ledger/buildlogs/20260824T050149-3746527.log`,
  `ledger/buildlogs/20260824T050241-3747181.log`,
  `ledger/buildlogs/20260824T050248-3747299.log`). The optional diagnostic historical replay
  retains its pre-existing patch-0016 failure; no sequential-history claim is made.
- OFF product preflight binds 650,045 JS bytes, 113,980,889 Wasm bytes, and 167,143,248 data
  bytes (`ledger/buildlogs/20260824T050416-3749898.log`). Pinned REUSE 6.2.0 is GREEN.
- Required M8 remains RED at the unchanged split-product, browser, compliance-receipt, and
  performance boundaries. Final container-backed regression restores M0 to 6/6 GREEN while
  M1-M8 retain their existing strict-receipt/product/browser/run-label/hardware/release
  boundaries.

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-grease-pencil-editing-windowed`, with desktop authoring as the workaround and an
explicit revisit condition. Re-enable the feature and rerun all size/runtime receipts if a
truthful accepted-hardware profile split later clears the 15 MB bar without this cut.

No browser, adapter, profile, split product, or accepted receipt was created. Mesa dzn and the
Windows path were not attempted, and WSL was not restarted.
