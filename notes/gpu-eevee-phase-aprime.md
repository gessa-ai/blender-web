<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE storage Phase A-prime and final mip dispatch

Date: 2026-08-09

Status: applied on top of accepted patches 0138 and 0143. Locked native and shipping wasm builds
completed. Static-shader acceptance passed, and the targeted principled-default run proves that
the RG11 storage family is gone. Full Phase A-prime pixel acceptance remains open because the
render still stops on the independent shadow shader blockers before Film readback.

## Scope

Patch `patches/0144-gpu-eevee-storage-format-and-final-mip.patch` contains two independent fixes:

1. WebGPU promotes EEVEE storage-backed `UFLOAT_11_11_10` allocations and storage-image
   declarations to `SFLOAT_16_16_16_16`. Metal, Vulkan, and OpenGL retain the native packed
   format and the same pass structure.
2. The generic mipmap generator uses a true one-output pipeline for a final single-level dispatch.
   The existing paired-level path still writes two levels per dispatch.

There is no qualifier demotion, packing, dummy output, resource-name discrimination, or pass
split. Phase B storage-texture atomics and the readback work in 0138/0139 remain separate.

## RG11 allocation and declaration identity

`eevee_storage_format.hh` is the allocation-side policy. It returns RGBA16Float only when the
active backend is WebGPU and the requested format is RG11B10Ufloat. The helper covers:

- all raytrace radiance allocations, including the black dummy, inactive-layer validation dummy,
  fast-GI mip chain, temporal/history buffers, bilateral outputs, and alloc-only/dummy paths;
- the deferred-layer black storage dummy;
- the subsurface radiance array;
- the volume property images, both history swap chains, and both integrated outputs; and
- the four DoF tile images, which are separate read and write bindings but share the same WebGPU
  RG11 storage declaration format.

The two planar-probe RG11 allocations remain unchanged. Their usage is attachment plus sampling,
not storage images, so changing them would be unrelated and would lose the native packed format.
The new helper is registered in the explicit `bf_draw` source/header manifest.

The WebGPU shader backend applies the matching promotion at all three format-bearing seams:

- emitted GLSL storage-image layout qualifiers;
- bind-group storage texture descriptors; and
- shader-interface image-format metadata used by debug validation.

The pin has no non-EEVEE RG11 storage-image declarations. This makes the backend conversion exact
without shader-name or resource-name rules.

## Latent RG16 audit

The separate `deferred_thickness_amend` residual remains unchanged. Its create-info declares
`gbuf_normal_img` as read-write `UNORM_16_16`, while the g-buffer normal allocation remains
RG16Unorm. Texture format tiers do not add RG16Unorm read-write access. Patch 0144 neither demotes
that qualifier nor substitutes or packs that image; it must be measured separately after RG11 no
longer stops pipeline creation.

## One-output final mip

The mipmap resource table adds an `is_one_level` compilation constant. In a one-level
specialization, binding 2 is absent and all second-output code is statically removed. The CPU
dispatcher selects that specialization only when one output level remains and binds only the input
view and output-1 view. When two levels remain, it selects the original paired specialization and
binds both output views.

There are seven supported formats and layered/non-layered forms, so this intentionally adds 14
static shader pipelines, 14 built-in enum entries, and 14 built-in name mappings. The stable native
build must measure the denominator increase from 973 to 987. If the same 17 pre-existing shaders
remain non-passing and all new variants compile, the expected receipt is 970/987; the measured
value, not that expectation, is authoritative.

## Static verification

- Patch 0144 passes a read-only forward apply-check against the live restored pre-0144 baseline.
- A reconstructed applied-stack preimage reverse/forward round trip reproduces all 12 source files
  byte-for-byte.
- The patch contains only the 12 source paths named in this note, including the `bf_draw` header
  manifest registration.
- Source grep counts exactly 14 one-level pipeline objects, 14 enum entries, and 14 name mappings.
- `git diff --check` passes for the owned source and patch.

No native build, wasm build, browser run, census, oracle, threshold, result, ledger, dashboard, or
series edit was part of the original preparation stage.

## Stable-tree behavioral gates

The exact deferred probe sequence is recorded in
`sandbox/gpu-eevee-phase-aprime/probe-plan.md`. Patch 0138 is source-disjoint. Patch 0143 owns the
texture-view lifetime/subresource contract exercised by the mip views, so 0144 browser acceptance
must start only after both dependencies are committed and independently audited.

Acceptance includes fresh `camera_depth_of_field.blend` and representative EEVEE volume-corpus
runs. Each must have zero RG11B10Ufloat storage-texture bind-group-layout errors, produce non-black
pixels, and pass the existing unchanged-golden comparison without harness, oracle, golden, or
threshold changes.

## Live stacked evidence, 2026-08-10

The live source contains patch 0144 after accepted patch 0143. Patch 0146 is stacked after 0144 and
is source-disjoint. In a disposable 13-path copy, reversing `0146` then `0144` and applying `0144`
then `0146` passed with `--whitespace=error-all` and reproduced every live source hash exactly.
Patch 0144 remains the 12-path, 275-insertion, 77-deletion artifact with SHA-256
`b4fdb24cb2c34740d2e60cff5dc9fcf33e8ac94d784f85f106ba2ae706f1d032`.

The locked native build reached the final `blender_test` link. The locked shipping wasm build
reached the final `blender_browser.js` link. The unchanged census script measured:

- GPUWebGPUTest: 164 PASS / 7 FAIL / 2 CRASH / 173;
- static shaders: 970 / 987, exactly the prior 956 / 973 plus all 14 new variants; and
- the I10 control still passes.

The targeted `principled_bsdf_default` browser run reached `OK BLENDER_EEVEE`, did not crash or
become unresponsive, and recorded zero Dawn validation errors. The previous
`RG11B10Ufloat ReadWrite` family is absent. The later compiler failures are now exposed precisely:
`eevee_shadow_tag_update` still has a vertex-stage read-write storage declaration before 0146, and
`MADefault_Surface_shadow_mesh` still reaches Tint's unsupported `OpImageTexelPointer` path.

This is an honest partial behavioral acceptance. The run recorded zero readback kicks, zero
completions, and no device-byte capture; the 128 by 128 render-operator PNG is constant black.
Therefore 0144 does not claim a non-black EEVEE pixel pass. The remaining acceptance matrix from
the probe plan, including all seven former RG11 rows, camera DoF, volume, transmission display,
and explicit paired versus one-output mip dispatches, must still run after the shadow shader path
reaches Film readback.

Exact logs, manifests, image hashes, source hashes, and artifact hashes are recorded in
`sandbox/gpu-eevee-phase-aprime/0144-final-receipt.txt` and
`sandbox/gpu-eevee-phase-aprime/0144-final-integrity.txt`.
