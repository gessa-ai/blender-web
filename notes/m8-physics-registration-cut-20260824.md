<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed physics editing registration cut — 2026-08-24

## Outcome

The windowed browser profile no longer registers the central physics operator set or Particle
Edit keymap. Patch 0255 guards only `ED_operatortypes_physics()` and
`ED_keymap_physics(keyconf)`. Physics DNA/RNA, generic `.blend` loading, modifiers, simulation
data, and the complete editor library remain compiled; native and headless Wasm builds retain
Blender's stock registration path through `WITH_BLENDER_WEB_PHYSICS=ON`.

This removes 117,398 raw Wasm bytes and exactly 13,116 Brotli-q11 bytes from the current windowed
module. The resulting Wasm is 23,471,033 q11 bytes. M8 therefore remains honestly RED: the Wasm
alone is still 8,471,033 bytes over LAUNCH.md's complete 15 MB interactive-payload budget before
stage-0 data.

## Oracle and implementation boundary

The pinned Blender 5.2.0 Linux oracle exposes 84 operators across the `particle`, `rigidbody`,
`boid`, `ptcache`, `dpaint`, and `fluid` groups while retaining the factory Camera/Cube/Light
scene (`ledger/buildlogs/20260824T080138-3897567.log`). These are useful desktop workflows, but
none is part of GOAL.md's declared launch tier.

The focused verifier rejected the unchanged tree before evidence allocation because patch 0255
was absent (`ledger/buildlogs/20260824T074616-3886322.log`).

The accepted patch leaves `source/blender/editors/physics/`, physics DNA/RNA, blenkernel
simulation data, loader versioning, and modifier code intact. It guards only the two central
`space_api` registration calls, allowing the shipped linker's function-level dead-code
elimination to collect otherwise unreachable editor implementations. The numbered patch touches
only `source/blender/editors/space_api/CMakeLists.txt` and
`source/blender/editors/space_api/spacetypes.cc`; its focused gate rejects edits crossing the
retained physics, data, loader, or kernel boundaries.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0254 baseline | `dc6a78809d45aabafed11e4708f01f3ea9962d380e638d1333a35effcf35d880` | 111,637,460 | 27,795,458 | 23,484,149 |
| patch-0255 candidate | `7f3a4e720523366dc1b589797cb0faf900f4359fffae9ecc8f7e261d3e96da58` | 111,520,062 | 27,734,470 | 23,471,033 |
| reduction | — | **117,398** | **60,988** | **13,116** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T074813-3887909.log` and
`ledger/buildlogs/20260824T075552-3892810.log`.

## Verification

- The real locked `blender_browser` relink and exact no-work check are GREEN
  (`ledger/buildlogs/20260824T075503-3892410.log`,
  `ledger/buildlogs/20260824T075919-3895514.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their generated compile rules
  contain `WITH_BLENDER_WEB_PHYSICS`; the windowed rule does not
  (`ledger/buildlogs/20260824T075931-3895601.log`,
  `ledger/buildlogs/20260824T075939-3895683.log`,
  `ledger/buildlogs/20260824T075949-3895765.log`).
- The focused verifier binds both distinct registration calls, default-ON and forced-OFF
  configuration, seven rejecting mutations, the exact two-file boundary, and an isolated exact
  reverse/forward patch round trip. Patch 0255 is SHA-256
  `eac7e691b754c260e2c8e0cd34a18e99ceae06655ec42b60fa4706dcae1186b4`
  (`ledger/buildlogs/20260824T075949-3895765.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch is
  SHA-256 `14e590daabc071d6ec2ee24d9f0ea9687d3255f0269c1a5f9db8d7bdfb162bf6`,
  and its manifest is SHA-256
  `3d05ca00546b7a3791033de96b9c9af17365d7d9e86050bdc8805b562b533146`
  (`ledger/buildlogs/20260824T080010-3895927.log`,
  `ledger/buildlogs/20260824T080101-3896494.log`).
- OFF product preflight binds 647,701 JavaScript bytes, 111,520,062 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T080119-3897165.log`).
- The deferral registry remains valid with 44 unique IDs and binds the physics-editing omission as
  an M8 deferral (`ledger/buildlogs/20260824T080313-3898377.log`).
- Pinned REUSE 6.2.0 is GREEN for 2,281/2,281 files
  (`ledger/buildlogs/20260824T080327-3898502.log`).
- Required M8 remains RED at its unchanged 25 technical-release boundaries
  (`ledger/buildlogs/20260824T080338-3898607.log`). Container-backed regression restores M0 to
  6/6 GREEN while M1-M8 retain their strict-receipt, split-product, browser, run-label, hardware,
  and release boundaries (`ledger/buildlogs/20260824T080344-3898661.log`).

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-physics-editing-windowed`. The browser retains physics data, modifiers, and generic
`.blend` loading, but it does not register particle, rigid-body, boid, point-cache,
dynamic-paint, or fluid editing operators or the Particle Edit keymap. Author or bake those
workflows in desktop Blender; ordinary launch-tier modeling, edit mode, modifiers, geometry
nodes, animation, viewport, and small Cycles-CPU paths remain available.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
