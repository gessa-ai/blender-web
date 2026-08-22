<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU framebuffer scissored clear — 2026-08-22

## Outcome

Patch 0194 restores Blender's scissor-sensitive framebuffer clear contract. Disabled and
exact-full scissors retain WebGPU's whole-attachment `loadOp=Clear` fast path. A proper clipped
rectangle instead draws one typed fullscreen triangle over `loadOp=Load` for each selected
color/depth/stencil attachment and layer; an empty intersection is a no-op. Explicit attachment
load-action materialization remains a full-subresource operation independent of frontend
scissor state.

## Oracle, diagnosis, and implementation

The pinned native Blender oracle initializes a 6x5 color/depth framebuffer, enables scissor
`[1,1,3,2]`, and clears exactly its six lower-left-coordinate pixels for both aspects. With the
scissor disabled, a one-pixel viewport still clears all 30 pixels. Attaching one color texture
across three array layers gives the same six-pixel footprint on every layer. This separates clear
semantics from the ordinary draw viewport work in patch 0193.

The old `WGPUFrameBuffer::submit_clear()` unconditionally encoded attachment
`loadOp=Clear`, which WebGPU defines over the complete attachment and which cannot observe
`SetScissorRect()`. The new atomic policy at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:330` uses widened clipping and chooses no-op,
whole-attachment load clear, or scissored draw before device work. Its exact typed WGSL lives at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:278`, so the same source consumed by production
is parsed by pinned Tint.

The draw executors at `upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:205` and `:361`
preserve normalized/float, unsigned, signed, depth, and stencil output semantics; pipeline keys
also bind format and sample count. Stencil uses an always-pass replace operation and dynamic
reference. The dispatcher at `:502` reuses the existing active/inactive/invalid per-layer
selector. `clear_attachment_full()` at `:849` keeps explicit load-action materialization on its
full-attachment path, preventing dynamic scissor state from narrowing a render-pass load action.

Audit patch 0201 corrects every scissored-clear rectangle from Blender bottom-origin to WebGPU
top-origin coordinates, including ordinary offscreens. Patch 0202 checks each newly created color
or depth/stencil pipeline before inserting it into the cache, preserving a later retry after a
transient null creation result.

## Verification

- Native oracle: exact six-pixel color/depth rectangle, 30-pixel disabled-scissor clear, and all
  three array layers (`20260822T183116-1756194`).
- Fail-first: unchanged source stops on the absent clear aspect/method/plan API before producing
  new evidence (`20260822T183340-1757625`).
- Root and descendant-CWD contracts pass 23 byte-identical native/wasm32 contracts, including 18
  clear-policy cases (3 full, 7 draw, 5 no-op, 3 rejected), four real format-flag classifications,
  four exact WGSL variants, and four layer-boundary decisions (`20260822T190636-1787867`,
  `20260822T190657-1788833`). Exact stdout is 2,399 bytes at SHA-256
  `3170624811efe6bfc59d415e2ee41a18686c0536992b3c77dd51956c8850814b`; the bound shipping source
  set is SHA-256 `00383027aead63274f20ba5015b863b980a2738a1f49504db9b3cc9dfb6c4d77`.
  The original matrix treated raw offscreen Y as correct and did not cover cache-publication
  ordering. The audit contracts correct those two source-level gaps; the historical hashes remain
  evidence for patch 0194 only.
- Wrong Node and Dawn identities reject before their requested evidence directories exist
  (`20260822T185006-1771883`, `20260822T185026-1772337`).
- The canonical freezer passes with byte-identical 20,258-entry live/replay manifests. Its
  1,646,549-byte, 257-path patch has SHA-256
  `b71019f7be98dcb8c63c153cdf8bf214a097a52850138c70d05398c78bd42e2e`; the manifest SHA-256 is
  `833c802f01c018a484ec9a6d0515a0e035965133c76347edb6e234fb83dadbcb`
  (`20260822T190521-1785919`), and the checked-in authority verifies independently
  (`20260822T190636-1787866`). Numbered patch 0194 also passes live reverse application
  (`20260822T190636-1787871`).
- The real `blender_browser` product recompiles and links through locked Ninja, then ends exact
  no-work; OFF-mode artifact preflight remains green (`20260822T190521-1785914`,
  `20260822T190657-1788832`, `20260822T190657-1788861`).
- REUSE 6.2.0 reports copyright and license information for all 2,108 files
  (`20260822T190657-1788855`).
- Required M3 remains red only because no fresh strict candidate is named
  (`20260822T190736-1789699`). The final container-backed regression restores M0 to 6/6 green;
  M1-M8 retain their existing strict-receipt, product, browser, run-label, and hardware
  boundaries (`20260822T190745-1789838`).

## Boundary

The device-free contract creates no WebGPU instance, adapter, device, render pass, draw, pixel,
browser receipt, or result promotion. The product path is compiled but cannot be executed on the
required hardware adapter because ornith-lab exposes only llvmpipe. Required M3 therefore remains
red for the absent fresh strict candidate, and live pixel proof remains owned by
`M3-LINUX-REPLAY` behind the named s7 blocker.
