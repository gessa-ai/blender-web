<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M2 pass-with-delta Linux refresh - 2026-08-24

## Outcome

The exact 75-suite native-Linux/Wasm32 tier-(b) matrix is freshly green against the current
canonical source freeze and the post-patch-0248 headless runtime. Receipt
`m2-pass-delta-refresh-ornith-linux-20260824-r2` records 65 `PASS`, seven named `DEFERRED`, and
three exact-schema `PASS_WITH_DEFERRAL` rows. Its receipt SHA-256 is
`ae2650a539585905a4af6af882b3503ac77ee7d3738505ddd81a545cd1c6205b`.

The replay answers the reason for this refresh without changing the answer to fit a desired
result: canonical wasm32 disk writes do not by themselves retire either library-related M2
delta.

- `bl_animation_action` still passes all assertions while retaining the exact
  `wasm32-animation-action-objectdata` diagnostic sequence. Its native and Wasm normalized
  SHA-256 values are `a93648e48a54` and `7378b171abdc`.
- `blendfile_library_overrides` still passes all assertions while retaining the exact six-row
  `wasm32-library-override-idname-allocation` bijection. Its native and Wasm normalized SHA-256
  values are `5778b0e7f78a` and `3c4986373a33`.

Both ledger rows therefore remain `status=deferred` with their existing named blockers and exact
`notes/m2-tierb-prep.md §8` evidence contract. No tolerance, normalizer, suite selection, or
deferral mapping changed.

## Evidence

The receipt binds Wasm SHA-256 `f1353a95e758` and Node 22.16.0 to source-freeze receipt SHA-256
`551e821a988e`; that freeze contains 20,258 byte-identical live/replay entries at canonical patch
SHA-256 `cd3eea4e7050` and manifest SHA-256 `89796b9d8e1d`.

- Full pinned-container oracle plus Wasm producer: `20260824T114936-4128643` (465 seconds).
- Independent `verify_m2` raw-log and live-file replay: `20260824T115835-4175384`.
- Runner mutation self-check: `20260824T115916-4175863`.
- Complete strict-verifier mutation self-check: `20260824T115916-4175860`.
- Canonical headless-Wasm `blender` locked no-work proof: `20260824T115932-4180078`.

An initial `r1` invocation used the retired local-oracle fallback. The producer rejected its
missing pinned allocator/banner envelope before sealing a receipt
(`20260824T114856-4128086`). The accepted `r2` run used the committed container `with-env` shim;
the failed attempt was not relabeled or reused.

## Boundary

This is fresh Linux M2 component evidence, not a complete M0-M3 candidate. Aggregate `m2b` must
remain red until the strict manifest can include the s7-blocked conformant hardware M3 receipt.
No product, source patch, dependency decision, result flag, milestone promise, or hardware/browser
receipt changes here.
