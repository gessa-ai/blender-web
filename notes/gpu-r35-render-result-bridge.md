<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M6 round 35 (gpu readback-bridge worker) - the TICK-PUMPED RENDER-RESULT BRIDGE (patch 0125): the F12 render's true device bytes now reach the M6 comparator, which UNBLOCKS suite measurement and FALSIFIES the r34 premise that "readback is the sole M6 blocker". The readback path WORKS; the real M6 blockers are RENDER-SIDE (workbench BindGroup entry-count mismatch, EEVEE-Next storage-texture pipeline failure).

Continues notes/m6-gpu-suite-truth-pass.md (r34, which correctly localised the extraction to
`gpu-sync-readback-windowed` but wrongly assumed every render was otherwise correct). Builds on
the r31 diagnostic primitive (notes/gpu-r31-readback-discriminator.md, patch 0117) and the r33
solid-cube fix (patch 0118). Rig = headed node-Playwright, bundled Chromium,
`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, opt tree `build-wasm-windowed-opt`
port 8126. Drivers under `sandbox/gpu-r35/`.

## THE BRIDGE (patch 0125) - one hook, inert unless BW_DIAG

`bpy.ops.render.render` for the GPU engines reads the offscreen result back through
`GPU_texture_read` and `GPU_framebuffer_read_color`. Both funnel through
`WGPUTexture::read` (the framebuffer path calls `tex->read(0, format, ...)` at
wgpu_framebuffer.cc:271). That WaitAny returns zeros in the imported-device windowed WM-worker
profile (ADR-006/007), so the render OP writes a BLACK PNG.

Patch 0125 adds ONE BW_DIAG-gated line at the top of `WGPUTexture::read`:
`webgpu::diag::on_texture_read(this)`. When `BW_DIAG` is set it KICKS the r31 tick-pumped
readback (`diag_kick_readback`, `CopyTextureToBuffer` + `MapAsync(AllowSpontaneous)`) of `this`
and returns; `read()` then proceeds and returns zeros exactly as before. The copy is queued
while the source texture still holds the render result, so the staging buffer keeps the true
bytes even after the transient render texture is pooled; the map completion rides a LATER
main-loop tick (the keepalive keeps ticks coming) and lands the bytes + an 8-word header in
`/tmp/bw_readback_<seq>.bin`. Bounded by `kMaxReadCaptures`. INERT (immediate no-op) with
`BW_DIAG` unset, so native/headless and the pixel goldens read back byte-identically.

File fence honoured: only `wgpu_diag_readback.{cc,hh}` (new `on_texture_read`) and
`wgpu_texture.cc` (the include + the one hook call) were edited. No framebuffer/context/draw
edit was needed - the framebuffer readback already flows through `WGPUTexture::read`.

Census GREEN, unchanged (the hook is a comment+one-call addition, inert without the env):
148 PASS / 8 FAIL / 2 CRASH (158) + static_shaders 956/973; patches_series attests 0117, 0118,
0125 applied. build-native-gpu relinked, build-wasm-windowed-opt relinked (my hook strings
present in the shipped wasm).

## RIGS (sandbox/gpu-r35/)

- `bridge_render.mjs` - factory self-test + open_mainfile inject driver.
- `bridge_boot.mjs` - the SUITE driver. Seeds the .blend into OPFS root (which
  `bw_mount_opfs` mounts at `/projects`, persists per origin) from a same-origin page
  (`/bin/bw_seed.html`), then boots `windowed.html?args=/projects/bw_suite.blend` so creator
  opens it as the STARTUP FILE - a CLEAN GPU context, no live `open_mainfile` (see below).
- `decode_readback.py` - pure-python (no numpy/PIL): parse the BWRB header, decode
  RGBA16Float/RGBA8/BGRA8 device bytes, apply the sRGB OETF (Blender's Standard view transform
  for these scenes: display_device=sRGB, view_transform=Standard, look=None, exposure 0,
  gamma 1 - verified on the oracle), vertical flip, emit an 8-bit PNG. The sRGB OETF was
  cross-checked against oiiotool's linear->sRGB (mean 0.0034, 8-bit-quantisation only).
- `score.py` - pick the render-result dump (last full-res colour read), decode, oiiotool
  `--fail thr --failpercent fp --diff` against the golden (exit-code = verdict), and cluster.
- `run_suite.sh` + `make_note.py` - iterate the manifest, checkpoint after every test.

## SELF-TEST WITH TEETH (per engine) - the honest gate before any suite number

- WORKBENCH, factory default cube, F12 render: the bridge captured EXACTLY ONE
  `WGPUTexture::read` (the combined result), 128x128 **RGBA16Float** (fmt 40), scene-linear,
  0 GPU errors. Decoded (linear->sRGB, vflip) = a SOLID SHADED CUBE on the world background,
  non-uniform (nzFrac 1.0, sRGB min 31 max 76), upright, matching the in-tab composite
  screenshot. This is the FIRST real F12 workbench render pixel extracted from a browser.
  Evidence: `evidence/selftest_workbench_render.png` + composite.
- WORKBENCH, real suite scene `light_flat_attribute` (renders CLEAN, 0 GPU errors): decoded
  render matches the golden's STRUCTURE and ORIENTATION exactly (two mushrooms + two noise
  spheres) - proof the bridge extracts faithful geometry - but is ~2x dimmer (a real workbench
  shading/colour delta, mean err 0.25). Colour space + orientation were locked against this
  real golden.
- EEVEE, factory scene, F12 render: **ZERO** `WGPUTexture::read` calls captured, and 30 GPU
  errors: `Storage texture WriteOnly used with visibility Vertex|Fragment -> Invalid
  BindGroupLayout -> CreatePipeline`. EEVEE-Next's pipelines fail to CREATE on this WebGPU
  backend (registered deferral: vertex-stage-rw-storage / storage-texture-atomics), so the
  render never runs and there is no final texture to read. The EEVEE seam does not "differ" -
  there is simply nothing to capture until the render works. This is NOT a readback blocker.

## KEY FINDINGS (the r34 truth-pass premise corrected)

1. **The readback path is NOT the M6 blocker.** The bridge extracts real, faithful F12 pixels
   from the workbench render (factory cube; light_flat_attribute structure). The
   `gpu-sync-readback-windowed` deferral remains open only for the caller-facing SYNCHRONOUS
   contract (RenderResult bytes, screenshots, pick-select) - its own architectural cycle,
   deliberately not attempted here.
2. **open_mainfile in a live windowed session corrupts GPU bind state** (42 GPU errors,
   6-vs-7 BindGroup mismatch), BUT booting the same blend as the STARTUP FILE reproduces the
   SAME errors - so the workbench render bug is REAL and scene/feature dependent, not an
   open_mainfile artefact. (An intervening viewport redraw between open_mainfile and render
   device-loses the tab; the suite driver avoids open_mainfile entirely.)
3. **Workbench render bug: WebGPU BindGroup entry-count mismatch** (6-vs-7, 6-vs-10, 1-vs-4
   seen) -> Invalid CommandBuffer -> Submit rejected -> black or corrupted render. The factory
   default cube renders CLEAN, so it is a specific shader-permutation bind-completion defect
   (the class patch 0116 fixed for one case), not universal. REPORTED, not fixed (measure lane).
4. **EEVEE-Next does not render on this backend at all** - pipeline creation fails on the
   storage-texture visibility deferral. All EEVEE scenes are render-blocked, not readback-blocked.

## HANDOFF (fix rounds, not this lane)

- Workbench: root-cause the BindGroup entry-count mismatch in the F12 render draw path (why
  the factory cube binds correctly but studio/flat/matcap/dof/x-ray permutations short a bind
  entry). Likely the same append_resource_bind_entries / shader-interface-map seam r31 flagged.
- EEVEE-Next: the storage-texture-in-graphics-stage deferral must land before EEVEE renders;
  then re-run the bridge - the readback side is already proven.
- Caller-facing sync/poll readback contract (gpu-sync-readback-windowed open half) stays its
  own cycle.

## Landing state (this round)
- [x] Bridge landed: patch **0125-gpu-webgpu-render-result-bridge.patch** (+ series entry).
      Round-trips: `git apply --check --reverse` clean on the live tree.
- [x] Native census GREEN 148/158 + 956/973 (0125 applied), windowed-opt relinked.
- [x] Per-engine self-test proof (workbench real cube; EEVEE render-blocked, proven).
- [x] Full 50-row suite table: notes/m6-gpu-suite-real-scores.md (checkpointed per test).
- [x] ledger/deferred.json gpu-sync-readback-windowed updated honestly.
- Evidence: `sandbox/gpu-r35/evidence/` (CC0 sidecars); caps under `sandbox/gpu-r35/caps/`.
