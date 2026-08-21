<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7 shader-frontend integrated Linux reconciliation — 2026-08-21

## Outcome

The shipping WebGPU shader frontend had one untested type-spelling hole: signed atomic 2D-array
images passed the dimension switch but not the array-suffix switch. The direct canonical-source
contract failed before the fix with enum 36 producing `isampler2D` / `iimage2D` instead of
`isampler2DArray` / `iimage2DArray` (`20260821T220550-647560`). Patch 0150 adds the missing
`AtomicInt2DArray` arm beside the existing unsigned arm. No shader name, resource name, harness
input, expected output, blacklist, tolerance, or backend other than WebGPU is special-cased.

The source freezer composed the verified postimage into the clean-pin authority. The canonical
patch remains exactly 257 paths and the manifest remains 20,258 entries; the new patch is
1,530,681 bytes at SHA-256
`c0b3b32291fd0d680785c53c4f668d7130b90dd6391d726234db1162313a9684`, with byte-identical
live/replay manifests at SHA-256
`ce8b0bc4ae8d9fa253ac3e191b22c989fe24603ba08c7823cd706e2e3f0da3ce`
(`20260821T220714-648885`). Reverse-apply, stored SHA-256, and canonical replay checks are green.

## Contract

`sandbox/wgpu-shader-frontend-integrated-smoke/` includes the canonical shipping
`wgpu_shader.cc` translation unit once and section-collects its uncalled live-device half. Four
contracts cover:

- all 39 distinct `ImageType` values through both sampler and image spelling paths (78 outputs);
- all 63 texture formats, the three WebGPU storage promotions, and 32 GLSL format spellings;
- all eight qualifier bit patterns through image and storage-buffer rules (16 outputs); and
- 30 scalar/matrix and three-element-array std140 alignment/size cases.

The file-scope log registration keeps a small runtime edge alive, so both legs link Blender's real
`clog.cc` and guardedalloc closure instead of supplying test symbols. Exact Dawn
`36cf1fae0cd8`, emcc 6.0.5, Node 22.16.0, canonical source, and byte-identical native/Wasm fmt
headers are required before evidence.

Root and descendant-CWD runs produce the same 313 bytes at SHA-256
`113d65236becca57b7af8c773556029b9a731124d76c22f48f36cd924c87b3bf`; the 19 bound source
inputs hash to SHA-256 `786e4d30104183ec5244ab8a0d6ee133abec695eeea00c751b3236db086f03cc`, and every target ends
locked-Ninja no-work (`20260821T220945-652017`, `20260821T220956-652394`). Wrong Dawn and Node
identities reject before evidence allocation (`20260821T221046-654223`). The affected shipping
windowed target rebuilt through locked Ninja and then reached exact no-work
(`20260821T220902-651607`, `20260821T221006-653024`). REUSE 6.2.0 is 1,990/1,990 green
(`20260821T221256-656325`).

## Boundary

This is CPU code-generation parity only. The driver creates no WebGPU instance, adapter, device,
shader module, pipeline, browser capture, or M3 receipt. Required M3 remains red for the absent
fresh strict candidate, and final container-backed regression keeps M0 6/6 green while M1-M8
remain red on the existing strict-receipt, APPLY/artifact, browser, run-label, and s7 hardware
boundaries at 2026-08-21T22:11Z. No result is promoted and no milestone promise is emitted.
