<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 windowed NLA editor registration cut — 2026-08-24

## Outcome

The windowed browser profile no longer registers the NLA editor space or its operator macros.
Patch 0254 guards only `ED_spacetype_nla()` and `ED_operatormacros_nla()`. NLA data, DNA/RNA,
generic `.blend` loading, core animation code, and the editor library remain compiled; native and
headless Wasm builds retain Blender's stock registration path through
`WITH_BLENDER_WEB_NLA=ON`.

This removes 60,283 raw Wasm bytes and exactly 31,745 Brotli-q11 bytes from the current windowed
module. The resulting Wasm is 23,484,149 q11 bytes. M8 therefore remains honestly RED: the Wasm
alone is still 8,484,149 bytes over LAUNCH.md's complete 15 MB interactive-payload budget before
stage-0 data.

## Fail-first and implementation boundary

The focused verifier rejected the unchanged tree before evidence allocation because patch 0254
was absent (`ledger/buildlogs/20260824T065914-3846426.log`).

The accepted patch leaves `bf_editor_space_nla`, NLA DNA/RNA, blenkernel animation data, loader
versioning, and all `space_nla` implementation sources intact. It guards only the two central
`space_api` registration calls, allowing the shipped linker's function-level dead-code elimination
to collect their otherwise unreachable editor closure. The numbered patch touches only
`source/blender/editors/space_api/CMakeLists.txt` and
`source/blender/editors/space_api/spacetypes.cc`; its focused gate rejects edits crossing the
retained data, loader, kernel, or editor implementation boundaries.

The option defaults ON. Only `WITH_BLENDER_WEB_WINDOWED` forces it OFF, while the `space_api`
CMake fallback preserves stock registration for generic native and headless configurations.

## Size evidence

Both rows use the same pinned emsdk Node 22.16.0 `zlib.brotliCompressSync` call with
`BROTLI_PARAM_QUALITY=11`. The q5 diagnostic is reported honestly but is not the release metric;
whole-module q5 block selection grew by 23,872 bytes even as raw and q11 release bytes fell.

| module | SHA-256 | raw bytes | q5 bytes | q11 bytes |
|---|---|---:|---:|---:|
| patch-0253 baseline | `8ded9da0eb18d2652d2183bb6dc85fa5511366386c880ad682d09cbbcb477d12` | 111,697,743 | 27,771,586 | 23,515,894 |
| patch-0254 candidate | `dc6a78809d45aabafed11e4708f01f3ea9962d380e638d1333a35effcf35d880` | 111,637,460 | 27,795,458 | 23,484,149 |
| reduction | — | **60,283** | **+23,872 (increase)** | **31,745** |

The baseline and candidate receipts are
`ledger/buildlogs/20260824T063519-3826533.log` and
`ledger/buildlogs/20260824T070109-3848059.log`.

## Verification

- The real locked `blender_browser` relink and exact no-work check are GREEN
  (`ledger/buildlogs/20260824T070018-3847629.log`,
  `ledger/buildlogs/20260824T070611-3852465.log`).
- Headless Wasm and native `bf_editor_space_api` both build GREEN. Their generated compile rules
  contain `WITH_BLENDER_WEB_NLA`; the windowed rule does not
  (`ledger/buildlogs/20260824T070350-3849742.log`,
  `ledger/buildlogs/20260824T070357-3849829.log`,
  `ledger/buildlogs/20260824T071439-3859860.log`).
- The focused verifier binds both distinct registration calls, default-ON and forced-OFF
  configuration, the retained editor library, seven rejecting mutations, the exact two-file
  boundary, and an isolated exact reverse/forward patch round trip. Patch 0254 is SHA-256
  `3bb56e36a4d9550506a93136f113e23eddcdde0baf0aa0c6c052a2e48c028f34`
  (`ledger/buildlogs/20260824T071439-3859860.log`).
- The canonical freezer independently replays 20,258 entries across 261 paths. The frozen patch is
  SHA-256 `0285efe74bff72c9234ea94b3020ed412d90b9581578fa464d165b13c5d9380f`,
  and its manifest is SHA-256
  `b4121cf69585adcf3151690ce962d281aa212ec47206997df257a16d35144524`
  (`ledger/buildlogs/20260824T070457-3851420.log`,
  `ledger/buildlogs/20260824T070543-3852177.log`).
- OFF product preflight binds 647,701 JavaScript bytes, 111,637,460 Wasm bytes, and 167,143,248
  data bytes (`ledger/buildlogs/20260824T070605-3852421.log`).
- The deferral registry remains valid with 43 unique IDs and binds the NLA omission as an M8
  deferral (`ledger/buildlogs/20260824T070652-3853527.log`).
- Pinned REUSE 6.2.0 is GREEN for 2,277/2,277 files
  (`ledger/buildlogs/20260824T070814-3854036.log`).
- Required M8 remains RED at its unchanged technical-release boundaries
  (`ledger/buildlogs/20260824T070827-3854143.log`). Container-backed regression restores M0 to
  6/6 GREEN while M1-M8 retain their strict-receipt, split-product, browser, run-label, hardware,
  and release boundaries (`ledger/buildlogs/20260824T070856-3855150.log`).

## Product boundary

`ledger/deferred.json` records the user-visible omission as
`feature-off-nla-editor-windowed`. The browser retains NLA data/RNA and generic `.blend` loading,
but it does not expose the NLA editor or register its operator macros. Author NLA tracks and strips
in desktop Blender; browser keyframing, Timeline, Dope Sheet, Graph Editor, modeling,
geometry-node, viewport, and small Cycles-CPU paths remain available.

Re-enable the feature and rerun all size/runtime receipts if a truthful accepted-hardware profile
split later clears the 15 MB bar without this cut. No browser, adapter, profile, split product, or
accepted receipt was created. Mesa dzn and the Windows path were not attempted, and WSL was not
restarted.
