<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed Mask registration cut rejected — 2026-08-24

## Outcome

An exact windowed-only guard of `ED_operatortypes_mask()`, `ED_operatormacros_mask()`, and
`ED_keymap_mask(keyconf)` preserved Mask data, DNA/RNA, generic `.blend` loading, image/movie
paths, and stock native/headless registration. It removed only 49,690 raw Wasm bytes and 1,452
Brotli-q11 bytes while hiding 40 user-visible Mask operators.

The candidate was rejected. Its numbered patch, build option, focused verifier, applied
postimage, and generated build rules were removed. No Mask feature cut or deferral ships, and the
windowed product was restored byte-for-byte to the patch-0255 physics-cut baseline.

## Behavior and candidate boundary

The pinned Blender 5.2.0 Linux oracle exposes 40 `bpy.ops.mask` operators and retains the factory
Camera/Cube/Light scene (`ledger/buildlogs/20260824T081635-3911367.log`). The candidate touched
only `source/blender/editors/space_api/CMakeLists.txt` and `spacetypes.cc`; it did not alter Mask
data, RNA, loader, image, movie, or editor implementation code.

The focused verifier first rejected the unchanged tree before evidence allocation because the
candidate patch was absent (`ledger/buildlogs/20260824T081818-3912113.log`). With the candidate
applied, it bound all three calls, default-ON and windowed-OFF configuration, seven rejecting
mutations, an exact two-file patch boundary, isolated reverse/forward round trip, and distinct
windowed/native/headless generated rules (`ledger/buildlogs/20260824T082603-3917382.log`).
The candidate windowed relink and locked no-work check were green
(`ledger/buildlogs/20260824T082207-3915111.log`,
`ledger/buildlogs/20260824T082604-3917381.log`), as were the headless Wasm and native preservation
targets (`ledger/buildlogs/20260824T082336-3915761.log`,
`ledger/buildlogs/20260824T082341-3915760.log`).

## Exact size result

Both rows use the pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` path with
`BROTLI_PARAM_QUALITY=11`.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0255 baseline | `7f3a4e720523366dc1b589797cb0faf900f4359fffae9ecc8f7e261d3e96da58` | 111,520,062 | 27,734,470 | 23,471,033 |
| Mask candidate | `8fecab98f9fe77f8e5a220edce24cc2baf9e80e55625175e6aecd1ef608b2cd3` | 111,470,372 | 27,718,147 | 23,469,581 |
| reduction | — | **49,690** | **16,323** | **1,452** |

The baseline and candidate measurements are
`ledger/buildlogs/20260824T081931-3913376.log` and
`ledger/buildlogs/20260824T082255-3915599.log`.

## Rejection rationale and restored state

The 1,452-byte q11 reduction closes only 0.017% of the remaining 8,471,033-byte Wasm gap to the
complete 15 MB interactive budget. That negligible gain does not justify removing 40 visible
operators under the fidelity-first decision in `notes/decisions.md` D-10. The remaining size gap
requires a structural profile-driven split or removal of a genuinely large non-shipping closure;
serial marginal registration cuts are spent as a useful lever.

After reversing the candidate, the real locked product rebuilt green
(`ledger/buildlogs/20260824T082631-3918390.log`) and returned to the exact baseline SHA-256 and
111,520,062-byte raw size (`ledger/buildlogs/20260824T082729-3918873.log`). Native and headless
preservation rebuilds, locked product no-work, and OFF preflight were green
(`ledger/buildlogs/20260824T082729-3918898.log`,
`ledger/buildlogs/20260824T082734-3918944.log`,
`ledger/buildlogs/20260824T082739-3918989.log`,
`ledger/buildlogs/20260824T082739-3918872.log`).

Canonical replay remains exact at 261 paths and patch SHA-256 prefix `14e590daabc0`
(`ledger/buildlogs/20260824T082833-3919341.log`). Pinned REUSE 6.2.0 is green for
2,282/2,282 files (`ledger/buildlogs/20260824T082837-3919340.log`). The required M8 scope remains
honestly RED at its unchanged 25 technical boundaries, and the container-backed regression at
08:29Z restores M0 to 6/6 GREEN while M1-M8 retain their existing strict-manifest, split-product,
browser, hardware, and release boundaries.

No adapter, device, browser, profile, split product, accepted receipt, result promotion,
dependency decision, tolerance, golden, blacklist, or promise changed. Mesa dzn and the staged
Windows path were not attempted, and WSL was not restarted.
