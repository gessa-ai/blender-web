<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# EEVEE storage Phase A: C1-C4

This lane implements only Phase A from `notes/eevee-storage-emulation-design.md`:
C1 writable-storage-texture visibility narrowing, C2 optional storage-format tiers,
and the C3/C4 adapter-supported storage texture and storage buffer limits. Phase A'
format substitution and Phase B image atomics remain separate work.

## Implementation

The reproducible upstream change is patch
`patches/0136-gpu-webgpu-eevee-storage-phase-a.patch`:

- `wgpu_shader_interface_map.cc` strips Vertex from WriteOnly and ReadWrite storage
  textures while retaining Fragment and Compute. This mirrors the existing writable
  storage-buffer rule and corrects Blender's shader-wide graphics visibility mask.
- `wgpu_shader.cc` re-applies the same storage-texture strip after the explicit
  layout's WGSL stage scan, because module-scope declarations can survive in vertex
  WGSL even when vertex code does not use the resource.
- Native `GHOST_ContextWGPU.cc` requests TextureFormatsTier1 and
  TextureFormatsTier2 only when advertised by the adapter. It also requests the
  adapter ceilings for `maxStorageTexturesPerShaderStage` and
  `maxStorageBuffersPerShaderStage`. All other `wgpu::Limits` fields remain
  `kLimitU32Undefined`, preserving their default device limits.

The shipping browser creates its device before C++ starts, in
`platform_web/shell/wgpu-preinit-worker.js`, then imports it through
`GHOST_ContextWGPUWeb`. That port-owned source already requests every advertised
adapter feature, including both format tiers. It now requests only the two supported
storage ceilings and emits one feature/limit receipt. This direct port-owned change
is intentionally outside the upstream-only 0136 patch.

## Capability gate and design probe

Bundled headed Chromium 149 on the Apple M4 Pro reports both
`texture-formats-tier1` and `texture-formats-tier2`, with storage limits 8 textures
and 10 buffers per shader stage. The full adapter receipt is
`sandbox/gpu-eevee-phase-a/browser-capability-receipt.json`.

The pinned native Dawn/Metal matrix was rerun without rebuilding its existing probe
binary. The proposed device accepts 8/9 fragment-only EEVEE storage format cases,
rejects all 6 writable Vertex-visible controls, and accepts 5 and 8 compute storage
textures. The only format residual is RG16Unorm read-write. Full output is
`sandbox/gpu-eevee-phase-a/final-native-probe.log`.

## Build and behavioral verification

Final verification ran after cursor patches 0135 and 0137 were committed and their
temporary diagnostics were removed. Locked native and shipping wasm targets both
reported up to date with no work remaining. Browser artifact hashes stayed identical
before and after all captures:

- JS: `287e06e2ffb7b9d0ec322a5167ee9ab0a8dab84d55e1ce202fddd8051ef313ea`
- Wasm: `cb674f5ba95317c69e0a50bbb4d78e2024eea2958772c31acfcd09b6f23fe89e`
- data: `5aa7c461a5a05aa5f0354754bbd7de7124819334ee336c3bc0f40a1efb7741b1`

The native M3 census held the required 149 PASS / 7 FAIL / 2 CRASH of 158,
with static shaders 956/973. The only RED remains the known stale I10
`EXPECT_NONPASS` entry. Patch 0136 passes strict reverse-apply and an exact
reverse/forward round trip.

### Browser targeted result

The shipping worker receipt is exact: 22 features, Tier1 true, Tier2 true,
`maxStorageTexturesPerShaderStage=8`, and
`maxStorageBuffersPerShaderStage=10`.

The `principled_bsdf_default` F12 run reaches its `OK BLENDER_EEVEE` sentinel
without a page crash and with zero GPU errors. In particular, none of the C1-C4
families remain. This does not satisfy the pixel gate: the legacy 0117 diagnostic
seam records zero kicks, zero completions, and no color capture, while the production
write-still PNG is 128x128 constant black. The unchanged pinned scorer therefore
returns `NO-CAPTURE`, not PASS. Receipts are under
`sandbox/gpu-eevee-phase-a/caps/eevee_principled_bsdf_default_f12_noerrors/`.

A bounded rendered-viewport check then exposes the next pipeline blocker exactly:
`RG11B10Ufloat` does not support ReadWrite storage access, followed by an invalid
pipeline layout. The camera region is blank, so the whole non-constant UI screenshot
is not claimed as render pixels. This is the additional Phase A' format family that
the design's R2 required the real render to enumerate. Full evidence is under
`sandbox/gpu-eevee-phase-a/caps/eevee_principled_bsdf_default_viewport/`.

Displaying the live Render Result separately reaches a later writable-storage-texture
aliasing error between bindings 2 and 3 at mip 7 of the same RGBA16Float image, then
an invalid command buffer. That display-only result is preserved under
`sandbox/gpu-eevee-phase-a/caps/eevee_principled_bsdf_default_image_editor_alias/`.

Therefore the C1-C4 device/backend triad is behaviorally verified, but Phase A does
not claim the mandated non-black targeted pixel acceptance. A representative
non-shadow sweep was not started because the targeted scene already reached the
explicitly out-of-scope Phase A' boundary.

## Remaining work

Phase A does not claim the RG16Unorm read-write residual in
`deferred_thickness_amend` or the newly measured RG11B10Ufloat read-write residual
(Phase A'), and it does not claim the storage-texture atomic shadow path (Phase B).
The unfinished caller-facing readback conversion also remains separate. No shader
source, oracle, golden, threshold, deferral, ledger, dashboard, series, fix plan, or
decision file is changed by this lane.
