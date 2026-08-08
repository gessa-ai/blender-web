<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M6 GPU render suites (workbench + EEVEE) - truth pass against HEAD

Measure lane, no fixes. Question the driver asked: with the M4 solid-cube defect
fixed (patch 0118, commit 68e2bce), what does M6 look like for the staged GPU
render suites (workbench 20 + EEVEE 30) run on the wasm WebGPU build?

## Verdict (one line)

**The GPU render suites are UNMEASURABLE at HEAD.** Rendering now WORKS (0118 lands
the solid cube), but the offscreen render-to-file EXTRACTION path returns
constant `(0,0,0,0)` for every scene - the caller-facing synchronous GPU readback
is the still-open `gpu-sync-readback-windowed` deferral. Every test's PNG is all
black, so a parity comparison measures only the golden's own brightness, not the
render. Per the measure-lane mandate this is reported as the blocker; no rows are
faked as PASS and none are labelled FAIL (the render is not wrong - it cannot be
read back).

## Binary measured

- `build-wasm-windowed-opt/bin/blender_browser.{js,wasm,data}` (WITH_HEADLESS=OFF,
  GHOST-web + WebGPU/emdawnwebgpu), link mtime **2026-08-08 10:03**.
- Repo HEAD at measurement: **`1ce0103`** (`git rev-parse HEAD`). This build was
  relinked with patch 0118 per notes/gpu-r33-depth-attachment.md; confirmed here:
  `strings blender_browser.wasm` contains `wgpuRenderPassEncoderSetStencilReference`
  (0118's dynamic stencil-reference call) and the composite screenshot shows the
  solid shaded cube. Node oracle emulator: `tools/emsdk/node/22.16.0_64bit`.
- Comparator: system `oiiotool 3.1.16.0` (Blender's own idiff, exit-code = verdict).
- Serve: `scripts/serve-web.sh 8126` with `BLENDER_WEB_BIN=build-wasm-windowed-opt/bin`
  (COOP/COEP, SharedArrayBuffer). Rig: headed node-Playwright, bundled Chromium,
  `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`. Port 8126 only.

## Why the node build is not an option (ruled out first, cheap)

`node build-wasm-cycles/bin/blender.js --background -E BLENDER_WORKBENCH <blend>`
aborts at `blender::WM_system_gpu_context_activate(GHOST_IContext*)` ->
`DRW_render_context_enable` with `null function or function signature mismatch`:
the headless node build has no GHOST/GPU context, so workbench/EEVEE cannot render
there at all. The GPU suites can only run in the browser (WebGPU) build - which is
where the extraction blocker lives. (This confirms the m6-prep note's WASM-side
requirement: "a WebGPU render path ... not just the viewport.")

## Extraction-path proof (self-test FIRST, before trusting any suite result)

Three renders, three ways, all decoded with `oiiotool --stats`:

| # | scene | engine | render op | sentinel | decoded raster | file |
|---|-------|--------|-----------|----------|----------------|------|
| 1 | factory default cube | BLENDER_WORKBENCH | `bpy.ops.render.render(write_still=True)` -> /tmp -> `FS.readFile` | `OK` (16 s) | **Constant (0,0,0,0)**, 128x128 | evidence/selftest_BLENDER_WORKBENCH.png |
| 2 | factory default cube | BLENDER_EEVEE | same | `OK` (21 s) | **Constant (0,0,0,0)**, 128x128 | evidence/selftest_BLENDER_EEVEE.png |
| 3 | real suite `workbench/aa-disabled.blend` (injected via `FS.writeFile`, `open_mainfile(load_ui=False)`) | BLENDER_WORKBENCH | same | `OK` (18 s) | **Constant (0,0,0)**, 128x128 | evidence/wb_aa-disabled.png |

- The render OP completes cleanly every time (sentinel `OK`); the PNG is a valid
  128x128 file. The PNG *container* is 671-4129 bytes with high byte-entropy, but
  that is zlib/CRC overhead - the **decoded pixels are constant zero** (`Constant:
  Yes`, `Constant Color: 0 0 0 0`). Byte-entropy of the file is NOT a proxy for
  pixel content; only the decoded raster is.
- What a mechanical suite run WOULD print (test 3 vs its staged golden, Blender's
  own `--fail 0.016 --failpercent 1`): golden avg 126.67 / stddev 103 (a real
  render) vs extracted constant 0 -> `Mean error 0.4967, Max error 1, 62.2% of
  pixels over 0.016 -> FAILURE`. That number is the golden's brightness, not a
  parity delta. Reporting 50 such rows as "FAIL" would be measurement theater;
  they are BLOCKED, not FAIL.
- **Rendering itself WORKS** (extraction is the only failure): the CDP composite
  screenshot (compositor-level, faithful) shows the full Blender UI with a SOLID
  SHADED CUBE in the viewport - evidence/selftest_BLENDER_WORKBENCH_composite.png.
  So patch 0118 is real in this binary; the pixels exist on the GPU. Only the
  synchronous GPU->CPU readback the render OP uses returns zeros.

## Root cause (cited, not re-derived)

`ledger/deferred.json` id **`gpu-sync-readback-windowed`**:
> "synchronous GPU readback still returns all-zero buffers for unconverted callers
> in the windowed profile: bpy.ops.screen.screenshot and bpy.ops.render.opengl
> write constant-zero PNGs ... they still WaitAny -> zeros."

`bpy.ops.render.render` for the GPU engines reads the offscreen result back through
the same `GPU_texture_read` -> `WGPUTexture::read()` -> `instance.WaitAny(...)`
path (notes/gpu-wasm-render-harness.md blocker D): emdawnwebgpu does not deliver a
synchronous `WaitAny` map-completion in the imported-device windowed profile, so
the staging buffer is never mapped and the copy returns uninitialised/zero memory.
The DIAGNOSTIC readback (patch 0117, `BW_DIAG` + `AllowSpontaneous`) works around
this for hard-coded textures pulled between main-loop ticks, but it is NOT wired
into the render OP's `RenderResult` framebuffer and cannot target an F12 render at
the golden's camera/resolution. The remaining deferred work is a caller-facing
poll/async readback contract - explicitly a **backend edit** (upstream/gpu),
owned by another lane; out of scope for this measure lane.

## The table - all 50 GPU tests: BLOCKED-READBACK

Thresholds are Blender's own (suite_plan.tsv), transcribed for the record; they are
not exercised because no real pixels reach the comparator. `diff` column = N/A
(the only number available is golden-vs-black, which is not a parity metric).

### Workbench (20) - fail_threshold 0.016 / fail_percent 1

| # | dir/test | verdict | diff | note |
|---|----------|---------|------|------|
| 1 | workbench/aa-disabled | BLOCKED-READBACK | n/a | extract=const(0); render OK, readback zeros (proof render #3) |
| 2 | workbench/aa-single-pass | BLOCKED-READBACK | n/a | same |
| 3 | workbench/dof | BLOCKED-READBACK | n/a | same |
| 4 | workbench/in_front | BLOCKED-READBACK | n/a | same |
| 5 | workbench/in_front_dof | BLOCKED-READBACK | n/a | same |
| 6 | workbench/light_flat_attribute | BLOCKED-READBACK | n/a | same |
| 7 | workbench/light_flat_custom | BLOCKED-READBACK | n/a | same |
| 8 | workbench/light_flat_random | BLOCKED-READBACK | n/a | same |
| 9 | workbench/light_matcap | BLOCKED-READBACK | n/a | same |
| 10 | workbench/light_matcap_no_specular | BLOCKED-READBACK | n/a | same |
| 11 | workbench/light_studio_material | BLOCKED-READBACK | n/a | same |
| 12 | workbench/light_studio_object | BLOCKED-READBACK | n/a | same |
| 13 | workbench/light_studio_object_no_specular | BLOCKED-READBACK | n/a | same |
| 14 | workbench/x-ray | BLOCKED-READBACK | n/a | same |
| 15 | workbench/x-ray_0 | BLOCKED-READBACK | n/a | same |
| 16 | workbench/x-ray_1 | BLOCKED-READBACK | n/a | same |
| 17 | workbench/x-ray_back_cull | BLOCKED-READBACK | n/a | same |
| 18 | workbench/x-ray_in_front | BLOCKED-READBACK | n/a | same |
| 19 | colorspace/acescg_blackbody | BLOCKED-READBACK | n/a | same |
| 20 | colorspace/rec2020_lights | BLOCKED-READBACK | n/a | same |

### EEVEE (30) - fail_threshold 0.0156862745 / fail_percent 0.08

| # | dir/test | verdict | diff | note |
|---|----------|---------|------|------|
| 1 | colorspace/acescg_blackbody | BLOCKED-READBACK | n/a | extract=const(0); render OK, readback zeros (proof render #2) |
| 2 | colorspace/rec2020_lights | BLOCKED-READBACK | n/a | same |
| 3 | transparency/transparency_blended | BLOCKED-READBACK | n/a | same |
| 4 | transparency/transparency_dithered | BLOCKED-READBACK | n/a | same |
| 5 | shadow/shadow_filter | BLOCKED-READBACK | n/a | same |
| 6 | shadow/shadow_min_pool_size | BLOCKED-READBACK | n/a | same |
| 7 | shadow/shadow_resolution | BLOCKED-READBACK | n/a | same |
| 8 | shadow/shadow_resolution_scale | BLOCKED-READBACK | n/a | same |
| 9 | raycast/raycast_attribute | BLOCKED-READBACK | n/a | same |
| 10 | raycast/raycast_bump | BLOCKED-READBACK | n/a | (also upstream EEVEE BLOCKLIST) |
| 11 | raycast/raycast_direction_constant | BLOCKED-READBACK | n/a | same |
| 12 | raycast/raycast_hit | BLOCKED-READBACK | n/a | same |
| 13 | raycast/raycast_normal | BLOCKED-READBACK | n/a | same |
| 14 | raycast/raycast_position | BLOCKED-READBACK | n/a | same |
| 15 | raycast/raycast_visibility | BLOCKED-READBACK | n/a | same |
| 16 | principled_bsdf/principled_bsdf_coat | BLOCKED-READBACK | n/a | same |
| 17 | principled_bsdf/principled_bsdf_coat_zero_weight | BLOCKED-READBACK | n/a | same |
| 18 | principled_bsdf/principled_bsdf_default | BLOCKED-READBACK | n/a | same |
| 19 | principled_bsdf/principled_bsdf_emission | BLOCKED-READBACK | n/a | same |
| 20 | principled_bsdf/principled_bsdf_emission_alpha | BLOCKED-READBACK | n/a | same |
| 21 | principled_bsdf/principled_bsdf_metallic | BLOCKED-READBACK | n/a | same |
| 22 | principled_bsdf/principled_bsdf_sheen | BLOCKED-READBACK | n/a | same |
| 23 | principled_bsdf/principled_bsdf_specular | BLOCKED-READBACK | n/a | same |
| 24 | principled_bsdf/principled_bsdf_subsurface | BLOCKED-READBACK | n/a | same |
| 25 | principled_bsdf/principled_bsdf_thin_glass | BLOCKED-READBACK | n/a | same |
| 26 | principled_bsdf/principled_bsdf_thin_subsurface | BLOCKED-READBACK | n/a | same |
| 27 | principled_bsdf/principled_bsdf_thinfilm_metallic | BLOCKED-READBACK | n/a | same |
| 28 | principled_bsdf/principled_bsdf_thinfilm_reflection | BLOCKED-READBACK | n/a | same |
| 29 | principled_bsdf/principled_bsdf_thinfilm_transmission | BLOCKED-READBACK | n/a | (also upstream EEVEE BLOCKLIST) |
| 30 | principled_bsdf/principled_bsdf_transmission | BLOCKED-READBACK | n/a | same |

### Aggregate

| suite | tests | PASS | FAIL | CRASH | BLOCKED-READBACK | SKIP-BLACKLIST |
|-------|-------|------|------|-------|------------------|----------------|
| Workbench | 20 | 0 | 0 | 0 | 20 | 0 |
| EEVEE | 30 | 0 | 0 | 0 | 30 | 0 |
| **GPU total** | **50** | **0** | **0** | **0** | **50** | **0** |

`blacklist.txt` is committed empty, so 0 SKIP-BLACKLISTED. (The two upstream-
blocklisted EEVEE scenes are noted above but not skipped, because the blocker is
extraction, not an adapter delta - blacklisting is moot until pixels are readable.)

## Triage - one cluster, not many

There is a SINGLE failure cluster. It is not shader-compile, not missing-feature,
not precision, not crash:

- **Cluster A - GPU readback (all 50): `gpu-sync-readback-windowed`.** The offscreen
  render succeeds and rasterizes correctly (composite shows the shaded cube); the
  synchronous GPU->CPU readback in the imported-device windowed profile returns
  zeros. Fix is a caller-facing async/poll readback in upstream/gpu (another lane).
  Until then no workbench/EEVEE test can be scored.
- No shader-compile errors surfaced (0 GPU errors on the factory renders; the 30/42
  GPU errors on the injected-blend run are from `open_mainfile` swapping the file
  in a live windowed session, not from the render pipeline - the factory-scene
  renders had 0 and still extracted zero, so they are not the blocker).

## Cycles-CPU context (not this lane's GPU work; already measured, node build)

Cycles-CPU needs no GPU and reads back from CPU memory, so it is NOT affected by
this blocker. The prep lane already ran it (`sandbox/m6-prep/run_wasm_cycles.sh` ->
`results-wasm-cycles.tsv`, node `build-wasm-cycles`): **25/27 PASS**, 2 FAIL
(`principled_bsdf_default` pixel-drift 20.8% over; `principled_bsdf_emission_alpha`
11.4% over). Those are real, extractable, comparator-scored results. Recorded here
only to complete the M6 picture; unchanged by this pass.

## What M6 needs to become measurable (for the driver, no fix attempted)

1. A caller-facing synchronous/poll GPU readback so `bpy.ops.render.render` (and
   `render.opengl` / `screen.screenshot`) return real pixels in the windowed
   profile - the open half of `gpu-sync-readback-windowed` (upstream/gpu, other
   lane). This is THE gate; everything else below is downstream of it.
2. Then the extraction rig here (`inject_render.mjs`, generalise the manifest loop)
   drives all 50, and the existing exit-code oiiotool comparator scores them at the
   staged thresholds - no golden re-authoring.
3. Per-test blacklist re-derived on the actual WebGPU/Dawn adapter (candidate set:
   the 2 upstream-blocklisted EEVEE scenes above) once pixels are readable.

## Reproduce

```
# 1. serve the windowed-opt WebGPU build on 8126 (COOP/COEP)
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8126 &

# 2. extraction self-test (factory scene) - proves readback returns constant zero
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m6-measure/selftest.mjs BLENDER_WORKBENCH 8126 120000
oiiotool --stats sandbox/m6-measure/evidence/selftest_BLENDER_WORKBENCH.png   # Constant: Yes, 0 0 0 0

# 3. same on a REAL suite blend (injected), + the would-be comparator line
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m6-measure/inject_render.mjs \
  "$PWD/upstream/tests/files/render/workbench/aa-disabled.blend" BLENDER_WORKBENCH wb_aa-disabled 8126 180000
oiiotool sandbox/m6-prep/goldens/workbench/workbench/aa-disabled.png \
  sandbox/m6-measure/evidence/wb_aa-disabled.png --fail 0.016 --failpercent 1 --diff

# 4. node headless build cannot do GPU engines at all (context abort):
tools/emsdk/node/22.16.0_64bit/bin/node build-wasm-cycles/bin/blender.js \
  --background --factory-startup upstream/tests/files/render/workbench/aa-disabled.blend \
  --python sandbox/m6-measure/render_gpu_test.py   # -> WM_system_gpu_context_activate null-fn
```

Evidence renders (representative handful, CC0 sidecars) under
`sandbox/m6-measure/evidence/`. Rigs + drivers under `sandbox/m6-measure/`.
