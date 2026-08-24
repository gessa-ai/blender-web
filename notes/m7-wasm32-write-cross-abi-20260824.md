<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 Wasm32 write cross-ABI correction — 2026-08-24

## Outcome

Regular Wasm32 saves now use Blender's canonical historical 32-bit file layout and are readable
by the unmodified pinned native Blender. The running module and undo memfiles retain the real
wasm32 layout. This closes `M7-WASM32-WRITE-CROSS-ABI`; it does not promote aggregate M7 or bind a
browser, WebGPU adapter, pixel, split-profile, or release receipt.

Before patch 0248, both a factory-startup save and the storage-bearing R9 semantic fixture were
written as raw wasm32 structs. Stock native Blender rejected the result with `Corrupt .blend file,
unexpected data size.` and `Scene 'Scene' had an invalid root collection`. The failure was generic:
wasm32 and historical i386 both have four-byte pointers, but wasm32 naturally eight-aligns 64-bit
scalars. SDNA records member types and type sizes, not explicit member offsets, so the embedded
wasm32 SDNA could not make those raw bytes portable.

## Correction

Patch `0248-wasm32-canonical-blend-write.patch` keeps the existing generated `DNAstr` as the exact
compiled memory description and emits `DNAstr_legacy_32` from makesdna's already-verified
`TypeInfo::size_32` model. Regular file writes decode and own that canonical SDNA; undo memfiles
continue to use the runtime SDNA.

The reconstruction path now recognizes the current wasm32 SDNA by identity and uses makesdna's
generated member-offset table on whichever side is live memory. Parsed undo SDNA is explicitly
tagged with that otherwise-unencoded runtime-layout identity; recursive pointer traversal uses the
same compiled offsets. Historical file SDNA continues to use the sequential i386 walk. Comparison
is forced when a runtime member offset or trailing size diverges even if the two schemas have
identical names. The writer reconstructs each divergent struct into the serialized layout before
replacing its pointers with stable file identifiers, so pointer traversal also follows the file
SDNA. No Scene-specific exception or stock-native reader change is involved.

Native makesdna output is preserved byte-for-byte. Before and after the native rebuild, the three
generated files retained these SHA-256 identities:

- `dna.cc`: `ed99b9db0ccf168b13d1778566aa77a5357d1a886b1bcc18e11675dba80c8c6a`
- `dna_verify.cc`: `a938a59cc9599e816f8d2b9565e8cb638d8220d6d1fa551727feba81421f07cd`
- `dna_type_offsets.h`: `9822b65b8369727d73b5ca722405676ecea41c1678873a743496298452eb83d3`

## Evidence

The dedicated fail-closed runner uses the pinned container oracle for every native phase. Its
semantic path is native author → Wasm save/reload → stock-native save/reload → Wasm save/reload,
with seven exact state comparisons over linked, storage-bearing compositor data and active/inactive
VSE, Spreadsheet, Clip, and NLA spaces. It separately loads Blender's pinned historical
`BHead4.blend` (`sha256:bbf99fe754bb426dd69fa211d6e80b4991728f1f8c201a547f7949b793edf3c2`),
saves it uncompressed in Wasm, independently parses all 1,718 structured blocks against its SDNA,
and requires stock native Blender to open that exact output. The binary contract is
`BLENDER_v502`, `ListBase=8`, file `Scene=6664`, wasm-memory `Scene=6672`, with runtime offsets
`Scene.customdata_mask=5016` and `Scene.master_collection=5408`. Fourteen semantic and binary
mutations are rejected. The same runner executes Blender's upstream global-undo component against
runtime-layout memfiles; three pushes, undo/redo traversal, and ID identity preservation pass.

- Final Wasm relink: `20260824T103732-4049407`; native preservation build:
  `20260824T103815-4049880`.
- Locked no-work proofs: `20260824T104018-4054522` and
  `20260824T104019-4053988`.
- Root and descendant cross-ABI receipts:
  `20260824T103934-4051633` and `20260824T103952-4052779`, both reporting
  `semantic_states=7 legacy_states=4 mutations=14 structured=1718 undo=PASS` against Wasm
  `sha256:f1353a95e7587e377fe23ac61ff0c7b72096fa6a57345ce2bc13bf27d43b25a4`.
- A standalone upstream global-undo run is also green: `20260824T102755-4037028`.
- The earlier focused omitted-type contract remains green with seven states, eight mutations, and
  `cross_native=OPEN`: `20260824T104011-4053989`.
- The source freezer proves 20,258 live/replay entries and a stable resnapshot at
  `20260824T103835-4050019`; canonical replay proves 261 paths at
  `sha256:cd3eea4e7050f4b19dfcbbb41965d267fd7404946fe0c096c335afc4e0b5eb75`
  with byte-identical manifests at
  `sha256:89796b9d8e1d8fc8be0c2e602df5edbd7b5aa02b8c7364baee7152636c0f88ae`
  (`20260824T103914-4050819`).
- REUSE 6.2.0 is green for all 2,280 files: `20260824T104058-4054800`.
- Required scoped M7 remains honestly red on its 36 separate staged/files/browser/bundle
  boundaries (`20260824T104109-4054932`). Container-backed regression retains M0 6/6 green and
  M1-M8 red on their existing strict-receipt, product, browser, hardware, and release boundaries
  (`20260824T104109-4054931`).

The remaining aggregate M7 boundaries are unchanged and remain subject to their existing strict
product/browser receipts. Hardware-dependent work remains blocked by the named external condition
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; neither
dzn nor the staged Windows path was attempted, and WSL was not restarted.
