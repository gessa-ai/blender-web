<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M7 omitted-type load/save/reload parity — 2026-08-24

## Outcome

The restored compositor-node, VSE, Spreadsheet, Clip, and NLA registrations now have a
hardware-independent serialization regression. A pinned native Blender 5.2.0 oracle authors one
fixture containing a linked compositor tree plus active and inactive copies of all four editor
spaces. The native oracle and current Wasm32 runtime each load, save, reload, and state-dump the
same native-authored data without GPU or browser work.

The focused verifier compares complete normalized state, not registration-call text. It requires:

- exact compositor tree and node identities, all socket descriptors/defaults, two links, and the
  storage-bearing Color Balance input/output whitepoints;
- one active and one inactive `SpaceLink` for `SEQUENCE_EDITOR`, `SPREADSHEET`, `CLIP_EDITOR`, and
  `NLA_EDITOR`;
- exact type-specific state for each copy and the required registered region types after an
  inactive space is reactivated;
- no `NodeUndefined`, `SPACE_EMPTY`, missing target space, or lost region/state;
- exact parity for the native author reload, native load/save/reload, Wasm load/save/reload, and a
  second Wasm cycle starting from the native-saved output.

The fixture uses the four areas of the current Layout screen. It configures all four editor types,
deep-copies that screen for the active cases, then returns the current screen's four areas to
View3D while retaining each target as inactive `spacedata`. This avoids Blender's background-mode
behavior where assigning `area.type` on a non-current workspace changes the enum but does not
instantiate the corresponding `SpaceLink`.

## Verification

`sandbox/m7-type-roundtrip/run.sh` derives every path from its own location, requires pinned Node
22.16.0, uses the container-pinned native oracle, and consumes the current
`build-wasm-m1-parity/bin/blender.{js,wasm}` product. Temporary `.blend` files and dumps are removed
only after a complete pass.

- Root and descendant executions pass seven cross-runtime state comparisons and eight semantic
  mutation controls. The canonical parity-state SHA-256 begins `5ee6746fbaf9`; the bound Wasm
  SHA-256 begins `81d2a25bac2e` (`20260824T094434-3989252`,
  `20260824T094512-3990783`).
- Mutation controls independently reject an undefined compositor node, storage loss, socket loss,
  link loss, `SPACE_EMPTY`, an absent inactive `SpaceLink`, region loss, and type-specific editor
  state loss.
- The native binary embeds build hash `fbe6228777e7`. The established Wasm binary reports
  `bpy.app.build_hash == "Unknown"`; only that runtime metadata field is excluded from state
  equality. The JavaScript/Wasm bytes are hash-bound separately, and the semantic runtime version
  remains exactly 5.2.0.
- The locked headless-Wasm graph rebuilt 31 stale edges, including the final link, and its
  immediate locked dry-run is exact no-work (`20260824T094340-3988756`,
  `20260824T094434-3989251`). The focused receipts above therefore bind the freshly linked
  product rather than the pre-existing binary.

This is a component receipt for the R9 serialization regression. It creates no browser, adapter,
device, pixel, profile, split-product, M7 result promotion, or milestone promise.

## Newly exposed cross-ABI boundary

A stricter stock-native reload of the Wasm-saved output remains RED and is not part of the focused
receipt. The failed cross-check rejects both this fixture and a minimal factory-startup Wasm save
with `Corrupt .blend file, unexpected data size` followed by an invalid Scene root collection
(`20260824T093354-3976807`). This is generic and predates the restored editor registrations.

The existing patch 0014 fixes only `DNA_struct_reconstruct` target offsets when native-authored
LP64 files are loaded into Wasm32. Wasm32 itself aligns 64-bit scalar members to eight bytes, while
stock Blender's 32-bit file-side member walk assumes the historical unpadded i386 layout. `Scene`
is the known divergent struct. The writer's SDNA pointer walk and raw struct copy do not
canonicalize that layout, and an unmodified native oracle cannot consume a Wasm-specific layout
marker. `M7-WASM32-WRITE-CROSS-ABI` therefore owns a generic canonical-write/forced-reconstruct
fix before desktop interoperability can be claimed. The targeted omitted-type regression stays
green without claiming that separate boundary.
