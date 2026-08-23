<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 compute bind-group scope contract — 2026-08-23

## Outcome

Commit `88003fd` and patch 0243 close R7's compute bind-group error-scope defect. The shared
direct/indirect group-0 builder now reserves an ordered transient resource gate and creates the
bind group under validation, out-of-memory, and internal scopes. A rejected non-null error object
poisons only its frame epoch, so the dependent dispatch cannot reach queue submission; a later
clean epoch recreates the group and may submit normally.

## Evidence

- The unchanged source fails the new source-order contract before evidence allocation because its
  compute bind group has no scoped resource gate (`20260823T192318-3207680`).
- Root and descendant-CWD native/wasm32 runs pass 36 byte-identical integrated contracts. The four
  new direct/indirect cases reject two non-null error objects with zero uncaptured errors and two
  canceled dispatch publications, then publish only two accepted retries. Evidence is 4,421 bytes
  at SHA-256 `6858f710cbf79f270fa90163ca30edbcb6e4b742187137631002ed8f8b0c4e88`;
  exact shipping inputs are SHA-256
  `6593bb255f6de1189c6968d6f91283bfed3583ea63feab3dd5f5d8b7ec3b5a70`
  (`20260823T192730-3211358`, `20260823T192957-3214560`).
- Pinned Dawn on llvmpipe returns a real non-null invalid bind group, leaves
  `compute_bind_group_uncaptured=0`, blocks its dependent work, and releases the clean next-epoch
  retry. The transcript is explicitly `SOFTWARE_CONTROL_NON_RECEIPT`
  (`20260823T192827-3212933`, `20260823T192837-3213058`).
- Numbered patch 0243 is 971 bytes at SHA-256
  `31d8b231a8ebd7b1724d8a14d1235ad60dfd6e4888e0b28ceffdd6f4afa3ffe4` and passes isolated
  reverse/forward exact-byte round trip. Canonical freeze/replay retains 257 paths and 20,258
  entries; its 1,753,151-byte patch is SHA-256
  `f6c3e3897b13213b51a0baa936b8fb8deb8b9b08c3dd72a9e753e3bb8bc4059f`, with byte-identical
  3,477,335-byte manifests at SHA-256
  `100930fa93abe7b57f440ed598c70d9bcab18887bf36e06d15965043509c998b`
  (`20260823T192611-3209739`, `20260823T192721-3211258`).
- The real `blender_browser` target rebuilds and ends locked no-work
  (`20260823T192849-3213208`, `20260823T192933-3214372`). OFF preflight binds the 657,928-byte JS,
  118,752,148-byte Wasm, and 167,143,248-byte data product (`20260823T192949-3214533`).
- Final REUSE 6.2.0 is green for all 2,230 tracked files (`20260823T193643-3221642`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T193212-3217353`). Final container-backed regression restores M0 6/6 green while M1-M8
  retain their existing strict-receipt, product, browser, run-label, hardware, and release
  boundaries (`20260823T193253-3217921`). No gate result was promoted.

## Boundary

This is device-free CPU/source and compile/link proof plus an explicit software-Dawn API control.
It creates no accepted hardware adapter, browser/pixel receipt, profile, split product, result
promotion, dependency decision, new deferral, tolerance, golden, blacklist, or milestone promise.
Live hardware proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry dzn, attempt the
staged Windows path, or restart WSL.
