<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Shipping build-profile reconciliation (2026-08-26)

## Outcome

Commit `5246f7b` makes the two CMake inputs used by the current optimized windowed product direct
committed inputs at HEAD:

- `patches/blender_web.cmake` enables the measured launch-tier Cycles-CPU, OpenSubdiv, and OpenUSD
  core paths while keeping every unsupported Cycles GPU/JIT path and Hydra/Imaging path disabled.
- `patches/platform_wasm.cmake` carries the CAPTURE/APPLY finalizer, USD and Cycles payload roots,
  the 32 MiB proxied-main versus 8 MiB ordinary-pthread stack policy, and the exact WebGPU browser
  link profile.

The active cache and schema-1 split manifest prove those are the settings used to produce the
current CAPTURE generation. The commit changes repository history, not the product: locked Ninja
is exact no-work, and `.wasm.orig` remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Verification

- Both profile paths are byte-identical to HEAD (`20260826T085304-591974`).
- The current cache and split receipt agree on CAPTURE mode, Cycles-CPU/OpenUSD/WebGPU enablement,
  disabled unsupported backends, split flags, CAPTURE-only post-JS, and the 32/8 MiB stack policy
  (`20260826T085304-592004`).
- The stack parser, two-phase scheduler source contract, four-mode product-preflight fixture suite,
  and exact current CAPTURE inventory are green (`20260826T085304-592013`,
  `20260826T085304-592022`, `20260826T085304-592031`, `20260826T085304-592040`).
- `blender_browser` is exact locked no-work (`20260826T085304-592049`).
- REUSE 6.2.0 is green (`20260826T085304-591973`).
- M8 remains honestly red at its existing APPLY/browser/aggregate boundaries
  (`20260826T085333-592739`). Container-backed regression restores M0 to 6/6 green and leaves
  M1-M8 at their existing strict red boundaries (`20260826T085408-593508`).

No artifact, hardware profile, receipt, result promotion, tolerance, golden, blacklist, deferral,
or promise changed.

## Remaining release residue

The separate dirty compliance/ledger slice remains uncommitted and is not claimed by this change:
`PROVENANCE.md`, `REUSE.toml`, `THIRD-PARTY.md`, `ledger/deps.json`, and
`ledger/deferred.json`. Its reconciliation must include a factual correction: the pending
`ledger/deps.json` text calls `libosdGPU.a` empty, while the harvested archive contains
`version.cpp.o` and `glslPatchShaderSource.cpp.o`, matching the accepted OpenSubdiv rebuild note
and dependency recipe. Custom TOST-1.0 compatibility judgments must remain explicit human-review
facts rather than being inferred during that cleanup.
