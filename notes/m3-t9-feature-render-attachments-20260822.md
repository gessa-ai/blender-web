# M3.T9 WebGPU feature-backed render attachments — 2026-08-22

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0165 makes WebGPU texture allocation honor the optional format features enabled on the
live device when deciding whether to request `RenderAttachment`. This restores Grease Pencil's
production `UNORM_16` render mask, which maps to `R16Unorm`, while withholding attachment usage
from optional formats whose render feature is absent.

### Audited correction - patch 0173

The original outcome's “sampled-only” claim was false for feature-gated format creation.
`R/RG/RGBA16Unorm` cannot be created unless `Unorm16TextureFormats` or `TextureFormatsTier1` is
enabled, and `Depth32FloatStencil8` cannot be created without its named feature. Dawn may return a
non-null error texture for an invalid descriptor, so the later null-handle check was not a
fail-closed guard. Patch 0173 adds a pure `format_creation_supported` predicate shared with the
render-attachment feature set and rejects these gates before `CreateTexture`. It preserves BC's
existing feature/type rejection, SNORM16 Uint emulation, and Float32/RG11 capability-only gates.

## Diagnosis and implementation

Grease Pencil selects `UNORM_16` for its render mask and attaches that texture to `mask_fb` at
`upstream/source/blender/draw/engines/gpencil/gpencil_engine_c.cc:709`. GHOST already requests
`Unorm16TextureFormats`, `TextureFormatsTier1`, `RG11B10UfloatRenderable`, and
`Depth32FloatStencil8` when the adapter exposes them at
`upstream/intern/ghost/intern/GHOST_ContextWGPU.cc:95`.

The allocation path nevertheless consulted only the core capability table. Because the core table
correctly marks optional `R16Unorm` renderability false, it stripped `RenderAttachment` even when
the device feature was enabled. The resulting texture could not make the production framebuffer
complete.

`render_attachment_supported` now combines the core table with pinned Dawn's exact feature
matrix: Unorm16 or Tier1 promotes R/RG/RGBA16Unorm; Tier1 promotes R/RG/RGBA8Snorm;
RG11B10 requires its independent renderable feature; and D32/S8 requires its depth-stencil
feature. The last distinction is explicit because Tier1 grants RG11B10 storage, not renderability,
in `build-dawn/dawn/src/dawn/native/Format.cpp:343` and `:394`. SNORM16 emulation and 1D textures
remain non-attachments.

## Evidence

- The unchanged pre-fix exact contract fails to compile because the feature-aware API is absent
  (`20260822T043708-1008593`). The final native and wasm32 executions cover 16 positive/negative
  cases (10 accepted, 6 rejected) byte-identically at 657 bytes, SHA-256
  `cf5f4e91c545287c97e0ad8844cf1ffc160262019be5551aaa20ee118fb1d491`; all eight texture
  contracts pass with exact source SHA-256
  `185a124f80f79dc14960210c0204eee703a31f5c6b4620bb631d0ff7da763432`
  (`20260822T044410-1015617`).
- Canonical freeze and independent replay retain 257 paths and 20,258 entries. The canonical patch
  is 1,547,630 bytes at SHA-256
  `fe90f9b96bd83c02443b3e154fecc17201f86f96cf0ef1bcaa693330520537b3`; live/replay manifests
  are byte-identical at SHA-256
  `48bf8892265d0be659778b5fc44d63c3171e7f3956ec10844db24c5c1c506f4c`
  (`20260822T044339-1015202`, `20260822T045045-1022323`).
- The real windowed wasm product recompiles the affected GPU translation units, links, and then
  reports exact locked-Ninja no-work (`20260822T044427-1016778`, `20260822T044506-1016777`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T044604-1018096`). Container-backed regression restores M0 6/6 green and retains
  M1-M8 red on their existing strict-manifest, APPLY/artifact, browser, run-label, and hardware
  boundaries (`20260822T044607-1018162`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, framebuffer, command, browser
receipt, or result promotion. Live attachment creation and pixel proof remain owned by
`M3-LINUX-REPLAY`, still blocked by the named s7 software-adapter condition.
