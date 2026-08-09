<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# gpu-r51 - boot shader-compile latency (M4.T29): OPFS WGSL translation cache

**Outcome: FIXED (warm boot).** The ~16 s dead-tab window r50 traced to the inline
first-draw shader compile is, measured per-stage, **~86 % pure CPU translation
(shaderc GLSL->SPIR-V ~81 %, Tint SPIR-V->WGSL ~5 %)** on the WM worker - device-free
work that emits byte-identical WGSL every boot. An OPFS-backed WGSL translation cache
skips shaderc+Tint on every boot after the first: **time-to-first-UI-present drops from
~16.3 s (cold) to ~3.0 s (warm)** at matched load - the compile block shrinks from ~13 s
to ~2 s. Cold boots are byte-for-byte unchanged. Fix is in-fence (wgpu_shader_compiler.cc
+ new wgpu_shader_cache.{hh,cc}); patch **0128**. 0129 (reserve) unused - one coherent
patch sufficed.

Build under test: `build-wasm-windowed-opt/bin` relinked 2026-08-09 07:12 (final landed,
salt-bump reverted). Native census: `build-native-gpu` relinked 07:01. Evidence:
`sandbox/gpu-r51-shader-latency/` (headed bundled-Chromium node-Playwright,
`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, served :8134). r50 baseline:
`notes/ghost-r50-first-composite.md`.

---

## 1. Phase 1 - per-stage breakdown of the compile block (measured, not assumed)

`BW_SHADER_TIMING`-gated stderr in `compile_shader` timed each sub-stage per shader and
emitted entry/exit steady timestamps, so the caller-side createShaderModule gap is the
delta between consecutive shaders. Zero-input boot, gate 1600x900, 101 shaders / 199
present stages (`p1-timing-timing.tsv`, `p1-timing-summary.json`; run at machine load ~9):

| stage | total | share of CPU (21.6 s) | share of wall (25.2 s) |
|---|---|---|---|
| interface map (build_interface_map, CPU) | 1.6 ms | 0.007 % | ~0 % |
| **shaderc GLSL->SPIR-V (CPU)** | **20,319.8 ms** | **93.9 %** | **80.7 %** |
| Tint SPIR-V->WGSL (CPU) | 1,319.2 ms | 6.1 % | 5.2 % |
| **CPU translation total (shaderc+Tint+iface)** | **21,640.6 ms** | 100 % | **85.9 %** |
| inter-shader gap = createShaderModule (browser) + next-shader GLSL codegen (CPU) | 3,541.8 ms | - | 14.1 % |
| wall span (first compile entry -> last exit) | 25,185.3 ms | - | 100 % |

Total emitted SPIR-V: 631,325 words. Costliest shaders by CPU are the UI batch
(`gpu_shader_text` shaderc 395 ms + tint 165 ms; `gpu_shader_2D_widget_base` shaderc
302 ms + tint 207 ms); shaderc is 250-395 ms/shader across the board.

**Verdict: shaderc dominates.** The absolute 25.2 s is inflated by instantaneous load +
the per-stage instrumentation; the **load-independent ratios** are the finding (r50's
`--log gpu.shader` run put the same block at ~16.4 s wall at load ~7-10). The dominant term
is OUR device-free CPU translation, not the browser compile - so the OPFS translation cache
is the correct highest-yield fix. If the browser createShaderModule/pipeline had dominated,
the cache would not help; it is only ~14 % (and that 14 % also contains the next shader's
GLSL codegen prep in `gpu_shader.cc`, which the cache does not skip).

The 2 s "gap" r50 saw between the UI batch (+3.18 s) and the overlay batch (+5.19 s) is
**Python init + icon-datafile loading, not shader compile** (`p1-timing-console.log` / the
r50 log lines 644-837) - excluded from the table above.

## 2. The fix - OPFS WGSL translation cache

`wgpu_shader_compiler.cc :compile_shader` now, before paying shaderc+Tint:
1. builds the interface map (cheap, pure function of `resources`; rebuilt every boot),
2. computes a 128-bit content key,
3. `cache_lookup` -> on a hit, hands the stored WGSL straight back (skips shaderc+Tint),
4. on a miss, translates as before, then `cache_store`.

`wgpu_shader_cache.{hh,cc}` (new): plain synchronous stdio under the persistent OPFS mount
`/projects/.shadercache` (the M7 store proved synchronous WasmFS-OPFS I/O from the WM
worker; `bw_mount_opfs` runs in `GHOST_SystemWeb::init` before any compile). Follows the
M3 architecture doc D-2 ("mirror the Vulkan `.spv`+sidecar disk cache onto OPFS ... for
WGSL cache the WGSL, since the browser consumes WGSL"). Browsers expose NO pipeline-binary
serialization to JS, so we cache **our CPU work** (the translated WGSL); the browser's own
shader/pipeline caches then handle repeats at ITS layer.

**Key** = a 128-bit content address (two differently seeded 64-bit FNV-1a streams,
used as an accidental-collision guard rather than a cryptographic hash) over: salt with
the exact shaderc v2025.4 and Tint/Dawn 36cf1fae pins + translation-policy suffix + format
version + shader name + per-stage GLSL (which already carries every `#define`) + optimize
flag + sampler_base + every sampler_mapping. Length-delimited so concatenations are
unambiguous. Every input that can change the emitted WGSL is either hashed directly or
represented by the pinned-tool/policy salt, so a source, define, resource, or toolchain
change flips the key and misses.

**File format**: `BWSC` magic + u32 format version + u64 salt-hash + bounded per-stage
lengths + u64 payload checksum + the WGSL blobs. `cache_lookup` validates the header,
length bounds, checksum, and every read; any failure is a miss (self-healing against torn
writes and accidental same-length payload corruption). Direct write (no rename
dependency); `compile_shader` is serial on the one WM worker.

**Inert where the mount is absent** (native gpu build, private browsing without OPFS):
`cache_available()` requires `access("/projects", W_OK)` and honours `BW_SHADER_CACHE=0`.
False => every entry point is a no-op and the full translation runs exactly as before.

## 3. Numbers - cold vs warm time-to-first-UI-present (zero input, gate 1600x900)

frame 1 = first real UI composite (`presentBackbuffer frame 1`, ungated printf). Persistent
Chromium profile so OPFS survives cold->warm. Cold = fresh profile (empty cache); warm =
same profile (cache populated by the cold boot).

| condition | frame 1 | compile block (f1-f0) | load | source |
|---|---|---|---|---|
| BASELINE (pre-cache binary) x3 | +20.55 / +20.37 / +21.13 s | ~16.9 s | ~12-13 | `base{1,2,3}-console.log` |
| cache-OFF control (BW_SHADER_CACHE=0, HTTP-warm) | +16.62 s | ~13.6 s | ~9 | `ctrl-cacheoff-result.json` |
| **COLD** (cache on, empty) x3 clean cycles | +15.79 / +16.50 / +16.50 s | ~13 s | ~8-11 | `cw*-summary.json` |
| COLD (landed final binary) | +16.15 s | ~13.4 s | ~9 | `landed2-summary.json` |
| **WARM** (cache hit) x6 clean | +2.88 / +3.12 / +3.00 / +3.02 / +3.06 / +2.94 s | ~2.1 s | ~8-11 | `cw*-summary.json` |
| WARM (landed final binary, load spike) | +3.48 / +3.55 s | ~2.4 s | ~17 | `landed2-summary.json` |

- **Warm vs cold: ~13.3 s faster (~82 % cut)** at matched load; compile block ~13 s -> ~2 s.
- **Honest delta under load**: at load ~17 warm still lands at +3.5 s (vs a cold that
  stretches to ~18-20 s under the same contention) - the win grows with load because it is
  the load-sensitive CPU translation that is removed.
- Cold-with-cache (+16.2 s) == cache-OFF control (+16.6 s): **empty-OPFS cold behaves as
  today**; the ~100 small cache writes add no measurable cold cost.
- The warm speedup is the shader cache, NOT browser wasm HTTP-caching: with `BW_SHADER_CACHE=0`
  on the SAME HTTP-warm profile the block returns to +16.6 s (control row).

## 4. Cache correctness proofs

- **Byte-identity (>=10 required; 101/101 done).** `BW_SHADER_CACHE_VERIFY` recomputed the
  fresh shaderc+Tint on every warm hit and byte-compared: **101 IDENTICAL / 0 MISMATCH**,
  with **101 cache hits / 0 miss** and **shaderc_us=0, tint_us=0** on the hit path (proves
  shaderc+Tint were fully skipped) - `warm-verify-result.json`, `warm-verify-console.log`.
- **Invalidation on a synthetic change.** Bumped the salt (`|INVALTEST`, a hashed key input
  standing in for a source/define/toolchain change - all feed the same 128-bit hash),
  rebuilt, booted the OLD-salt-populated profile: **+15.94 s = 100 % miss, full cold
  fallback** (`invaltest-saltbump-result.json`). Second boot (now repopulated under the new
  salt) = **+2.87 s hit** (`invaltest-saltbump-warm-result.json`). Salt then reverted +
  rebuilt.
- **Empty-OPFS cold == today.** Cold-with-cache (+16.2 s) ~= cache-OFF control (+16.6 s),
  section 3.
- **No collisions.** 101 distinct shaders -> 100 distinct cache files (one intra-boot
  duplicate `overlay_edit_particle_strand` correctly self-hits) -> warm boot 101/101 hits,
  0 false hits.

## 5. Parity + census (no behaviour change beyond timing)

- **Parity** workspace 1600x900 = **1.15 % over 0.016 (16583 px, mean 0.00277759)** via
  `sandbox/m4-fullscreen-parity/compare_fullscreen.sh` on `r51_parity_web_1600x900.png` -
  **byte-identical to r50's baseline** (16583 px, 1.15 %, mean 0.0028). The cache changes
  no pixels (WGSL byte-identity proven). The exit-1 is the standing web-vs-native baseline
  at Blender's strict 0.016/1 % threshold, not a regression.
- **Census** (wgpu_shader_compiler.cc + the new wgpu_shader_cache.cc are in the native
  build): `build-native-gpu` rebuilt (cache compiled in, inert since /projects absent),
  `run.sh --scope m3` = **149 PASS / 7 FAIL / 2 CRASH + static_shaders 956/973**; the only
  RED is the known-spurious I10 un-defer candidate (excepted). `native-census-m3.log`,
  `native-census-summary.txt`. No new regression.

## 6. Measured, not fixed - can the compile set shrink?

101 shaders compile on the first draw: a UI batch (~14: text/widget/polyline/image/node
socket), then the overlay engine's near-full cache (~70: armature, particle, volume,
lattice, curves, edit_mesh, outline, wireframe, motion-path, ...), workbench (~12), 3
`draw_*` compute, `OCIO_Display`. For the default factory scene (one cube, one camera, one
light) the overlay armature/particle/volume/lattice/curves/gpencil shaders are NEVER drawn
by the first frame - the overlay engine eagerly builds its whole `OVERLAY_shader_*` cache
at engine init (`WGPUShader::warm_cache` is a no-op, so this is the frontend requesting the
set, not a backend prewarm). **Deferring the unused overlay tail would cut the cold-boot
set substantially**, but faithfully requires the overlay engine (draw/engines/overlay) to
compile lazily per-object-type - a frontend change outside the webgpu fence and riskier
than the cache. Reported for a future lane; the cache already makes every post-first boot
pay only ~2 s regardless.

## 7. Falsified / not taken / DO-NOT-RE-RUN

- **Off-thread translation** (move shaderc+Tint to pthread workers to unblock COLD boots):
  the async ShaderCompiler is bypassed under `use_main_context_workaround` -
  `compilation_worker_` is null so `async_compilation` compiles inline synchronously
  (`gpu_shader.cc:1069`). Re-enabling it needs a GPUWorker/GPU context per thread (one Dawn
  device; ADR-007's per-thread JS-object table forbids offloading device work) AND edits to
  the shared `gpu_shader.cc` (out of fence). The cache wins warm boots without touching any
  of it. Off-thread translation remains the only lever for COLD boots - deferred/reported,
  do not attempt inside this fence.
- **GPU-binary cache: impossible.** Browsers expose NO pipeline/shader-binary serialization
  to JS. Do not re-attempt. We cache CPU-side WGSL; the browser caches its own binaries.
- **The cache does not help COLD boots** by design (empty cache = today's timing). It helps
  every boot AFTER the first. Do not measure "cold with cache" expecting a speedup.
- **The 25.2 s Phase-1 wall span is load-/instrumentation-inflated.** The finding is the
  RATIO (shaderc ~94 % of CPU, CPU ~86 % of wall), not the absolute seconds.
- Shell `?env=` hook + the `BW_SHADER_TIMING` / `BW_SHADER_CACHE_VERIFY` instrumentation
  were DIAGNOSTIC and are reverted; only the cache (with the `BW_SHADER_CACHE=0` ops gate)
  lands.

## 8. Evidence index (`sandbox/gpu-r51-shader-latency/`)

| file | what |
|---|---|
| `probe-shader-latency.mjs` + `p1-timing-{console.log,summary.json,timing.tsv}` | Phase-1 per-stage breakdown (BW_SHADER_TIMING) |
| `probe-cold-warm.mjs` + `cw{,-r2,-r3}-summary.json` + `*-console.log` | 3 clean cold/warm cycles |
| `base{1,2,3}-console.log` | pre-cache baseline x3 (load ~12) |
| `probe-one.mjs` + `cold-pop-`, `warm-verify-`, `ctrl-cacheoff-`, `invaltest-saltbump{,-warm}-` `*result.json`/`console.log` | populate / verify-101 / cache-off control / salt-bump invalidation |
| `landed{,2}-summary.json` | cold/warm on the final instrumentation-free binary |
| `parity-capture.mjs` + `r51_parity_web_1600x900.png` (+`.license`) | parity candidate (1.15 %) |
| `native-census-m3.log` / `native-census-summary.txt` | 149/7/2 + static_shaders 956/973 |
| `*.preimage` | pre-edit images for patch 0128 generation |
| `r50-baseline-shader-timing-console.log` | copy of r50's gpu.shader log |

## 9. Reproduce
```
# warm boot win (fresh profile: cold populates, warm hits):
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8134 &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/gpu-r51-shader-latency/probe-cold-warm.mjs 8134 repro   # cold ~16s, warm ~3s
```
