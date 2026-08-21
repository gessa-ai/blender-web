# M3 T6 vertex-buffer integrated Linux reconciliation — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

The canonical WebGPU vertex-buffer CPU path now has a deterministic, device-free native/wasm32
parity contract on ornith-lab. The shared test includes the shipping `wgpu_vertex_buffer.cc`
translation unit directly, so the private signed-I10 detection/conversion and usage mapping are
tested without a copied helper or a test-only production seam. Function/data sections collect the
uncalled context/device half at link.

Native and Node 22.16.0 produce the same 422 bytes (`sha256:d40a6b47fdd7`) across six contracts:

- all 1,024 signed 10-bit component encodings, with exact `[-127, 127]` output;
- detection in every one of the 16 vertex-attribute slots, including the pinned legacy normalized
  `GPU_COMP_I10` alias behavior;
- 1,024 interleaved vertices while preserving 8,192 neighboring bytes;
- 17 deinterleaved vertices with two signed-normal blocks (34 fields) while preserving 204 bytes;
- a 13-byte truncated-input boundary with all 12 guarded bytes unchanged; and
- all four usage modes with and without `GPU_USAGE_FLAG_BUFFER_TEXTURE_ONLY`.

The `UNORM_10_10_10_2` vertex enum also collapses to normalized `GPU_COMP_I10`; the pinned vertex
call-site census uses only `SNORM_10_10_10_2`, and Vulkan/OpenGL/Metal likewise treat the legacy
I10 vertex arm as signed. The contract records this actual pinned behavior instead of inventing an
unsigned vertex promise. Texture `UNORM_10_10_10_2` remains a separate texture-format path.

## Binding and evidence

The driver binds the canonical 257-path clean-pin replay (`e03f140fe3f3`), 13 exact source inputs
(`sha256:82a580a05797`), byte-identical native/Wasm fmt headers (`sha256:ccaf61c9b593`), Dawn/Tint
`36cf1fae0cd8`, emcc 6.0.5, Node 22.16.0, and host CMake 4.0.3 before evidence allocation.

- root parity build: `ledger/buildlogs/20260821T213109-610356.log`;
- descendant parity/no-work replay: `ledger/buildlogs/20260821T213134-611003.log`;
- wrong-Dawn and wrong-Node zero-allocation self-check:
  `ledger/buildlogs/20260821T213344-613090.log`;
- independent canonical replay: `ledger/buildlogs/20260821T213400-613412.log`; and
- unchanged windowed-product locked no-work:
  `ledger/buildlogs/20260821T213356-613363.log`.

Final REUSE 6.2.0 is 1,982/1,982 green
(`ledger/buildlogs/20260821T213504-613885.log`). The required M3 scope and group-scoped full
regression remain honestly red at `2026-08-21T21:35:32Z`/`21:35:33Z`: M0 is 6/6 green, while
M1-M8 retain their existing strict-manifest, APPLY/artifact, browser, run-label, and hardware
boundaries.

## Boundary

This contract creates no WebGPU instance, adapter, device, GPU buffer, upload, pixel artifact, or
receipt. It makes no live allocation/draw claim and changes no Blender product source. Fresh live
T6 proof and the strict M3 receipt remain owned by `M3-LINUX-REPLAY`, which is blocked by s7's
llvmpipe-only adapter.
