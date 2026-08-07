<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M6 — Cycles-CPU small-scene suite on WebAssembly (MEASURED)

The first wasm Cycles render (notes/m6-first-wasm-render.md) took the default cube
from one image to exit-0 parity. This takes the **27-test Cycles-CPU small-scene
subset** (m6-prep manifest) to the measured suite — the M6 gate's Cycles third —
via a host runner that drives ONE blend per `node` invocation (no `multiprocessing`,
no subprocess: the M2 debt named in the first-render notes is weaned off by
construction, one OS process per test = crash isolation for free).

## Verdict: 2/27 PASS as-is — and the failures collapse to ONE missing dependency

| bucket | n | meaning |
|---|---|---|
| **PARITY (PASS)** | **2** | wasm render matches the committed golden within Blender's own threshold |
| **OPENSUBDIV_OFF** | **22** | FAIL vs golden, but wasm render == native-oracle-with-Subsurf-disabled within threshold → the SOLE delta is disabled subdivision; the wasm Cycles engine is otherwise pixel-faithful |
| **OPENSUBDIV_OFF+RESIDUAL** | **3** | FAIL, and a secondary delta survives even after equalizing subdivision |

**Headline:** the wasm Cycles-CPU renderer is faithful. 24 of 27 tests would very
likely pass once **`WITH_OPENSUBDIV` is ON** (2 already green + 22 proven to differ
ONLY by subdivision); 3 need a further look. The suite is not blocked by a Cycles
bug — it is blocked by a **missing build dependency (OpenSubdiv)**.

All 27 rendered to completion (`node_exit=0` for every test) — no crash, no
threading wedge (2 threads, per-pixel-deterministic RNG), no missing addon module,
no OOM. Total wall **317 s** for 27 renders (mean 11.8 s, min 3.8 s
`raycast_hit`, max 28.3 s `principled_bsdf_metallic`), scalar kernel, 128×128 at
each blend's own native samples (1–128 spp).

Per-test receipts: `sandbox/m6-prep/results-wasm-cycles.tsv` (suite verdict +
max-err + render-time) and `results-wasm-cycles-attribution.tsv` (adds the
OpenSubdiv A/B column + bucket).

## The decisive experiment (why "OpenSubdiv, not a Cycles bug" is proven, not asserted)

`WITH_OPENSUBDIV=OFF` in the build (`build-wasm-cycles/CMakeCache.txt`) makes Blender
**silently disable every Subsurf/Multires modifier** at render time
(`WARNING ... Modifier: "Subsurf", Disabled, built without OpenSubdiv`). Introspection
(`diag_opensubdiv_ab.py` + a modifier census) shows **26 of 27 test scenes carry
Subsurf/Multires** — the stock Blender render-test rig is a subdivided shaderball/plane
— so on wasm nearly every scene renders faceted low-poly geometry vs the golden's
smooth subdivided surface. That is the large pixel drift (max err up to 1.0, 15–71 %
of pixels over threshold).

To attribute it rather than guess, I rendered every blend on the **native pin oracle
with Subsurf/Multires forced off** (`m.show_render=False`, mimicking the wasm build)
and diffed oracle-subdiv-disabled vs the wasm render at each test's own threshold:

- **22 of 25 failures → MATCH** (oracle-nosubdiv ≈ wasm within threshold; e.g.
  colorspace/acescg_blackbody max 0.0039, transparency_blended 0.0039,
  principled_bsdf_coat 0.0078, metallic 0.0039). Equalize subdivision and the wasm
  output is bit-near-identical to the oracle → **subdivision is the ONLY difference**,
  and color management (AgX / ACES 2.0 / Display-P3 / Rec.2020 all appear in these
  scenes), shading, sampling and ray tracing are all correct on wasm.
- **3 of 25 → DIFFER** even with subdivision equalized (below).

The native oracle re-renders (subdivision ON) all match the goldens — confirming the
goldens are valid at this pin (consistent with m6-prep's 27/27 oracle baseline). So
the wasm-vs-golden failures are wasm-vs-oracle deltas, not stale goldens.

## Colorspace was a red herring — both sides output P3-D65

The wasm renders are tagged `oiio:ColorSpace: srgb_p3d65_scene` while the goldens are
tagged `srgb_rec709_scene`; this looked like a display-device mismatch. It is not:
the blends themselves store `display_device='Display P3'` (acescg) / `'Rec.2020'`
(rec2020_lights), the **native oracle emits the identical `srgb_p3d65_scene` tag**,
oracle-vs-golden PASSES (oiiotool idiff compares raw pixels, ignoring the tag), and
both colorspace tests land in the OPENSUBDIV_OFF bucket (MATCH after subdiv-equalize).
Color management is correct on wasm.

## The 2 PASSes and the 3 residuals

**PASS (PARITY):** `raycast/raycast_direction_constant` (max 0.0078, 0 % over) and
`raycast/raycast_visibility` (max 0.22 but 0.006 % over, inside the 1 % failpercent) —
scenes whose subdivision does not materially change the rendered pixels.

**OPENSUBDIV_OFF+RESIDUAL (3)** — differ from oracle-subdiv-disabled too, so a second
cause stacks on OpenSubdiv:
- `principled_bsdf_default` — residual max **0.094**, 21.6 % over (spread, low
  amplitude): consistent with faceted-silhouette anti-aliasing / ray-precision on the
  now-hard edges.
- `principled_bsdf_emission_alpha` — residual max **0.678**, 11.2 % over: a
  high-frequency wavy emissive surface; sub-pixel sampling of its edges differs.
- `principled_bsdf_thin_subsurface` — residual max **1.0**, 20.1 % over: geometry-nodes
  (2 NODES modifiers) + subsurface random-walk + `film_transparent` — shading/geometry
  differs beyond subdivision.

Prime suspect for the residual is **`WITH_CYCLES_EMBREE=OFF`** (wasm uses Cycles' own
BVH2, the oracle uses Embree): BVH2≈Embree for the 22 MATCH scenes, but high-frequency
edges and SSS random-walk are exactly where the two traversals diverge most.
Unconfirmed — isolate on an OpenSubdiv-ON rebuild (where these three can be diffed
without the subdivision confound). Not OSL (`WITH_CYCLES_OSL=OFF`, but these are
non-OSL SVM tests), not OpenVDB (no volume tests), not denoising (off in the blends).

## What unblocks the M6 Cycles third (the nameable blocker)

**Build OpenSubdiv into `lib/wasm` and set `WITH_OPENSUBDIV=ON`.** OpenSubdiv is not a
GOAL forced-OFF dep (unlike OpenVDB/Mantaflow) and is a **launch-tier requirement for
modeling too** (the Subdivision Surface modifier) — it is simply not yet in the M2
harvested superbuild subset. This is a build-deps task (superbuild cross-compile +
`-DHARVEST_TARGET` + relink), not a deferral. Projected result on that rebuild: ~24/27
(the 2 + 22), then chase the 3 residuals (Embree-off hypothesis).

Secondary/optional: `WITH_CYCLES_EMBREE=ON` (needs Embree cross-compiled to wasm; may
be a launch deferral if Embree does not port cleanly — then the 3 residuals get a
justified blacklist entry per adapter, exactly as tier-c allows).

The per-test blacklist stays **committed empty**: these are engine-capability gaps to
be fixed by building the dependency, not adapter deltas to be adjudicated away.

## Deliverables

- `sandbox/m6-prep/run_wasm_cycles.sh` — host runner (one node invocation per test →
  render_test.py → verbatim upstream oiiotool idiff, exit-code-primary → results TSV;
  reads the m6-prep blacklist; `--filter`/`--limit`/`--threads`).
- `sandbox/m6-prep/wasm-first-render/render_test.py` — per-test wasm render driver
  (registers the staged Cycles addon, CYCLES/CPU, frame 1, blend's own settings; the
  first-render addon staging under `wasm-first-render/addon/cycles/` is reused).
- `sandbox/m6-prep/results-wasm-cycles.tsv` — 27 rows: verdict/max-err/render-time.
- `sandbox/m6-prep/results-wasm-cycles-attribution.tsv` — + OpenSubdiv A/B + bucket.
- `sandbox/m6-prep/diag_opensubdiv_ab.py` — the oracle subdiv-disabled A/B (reproduces
  the attribution).
- `sandbox/m6-prep/wasm-cycles-fails/` — 6 representative failure renders (the 3
  residual outliers + colorspace/principled/raycast OpenSubdiv examples); the full
  25-failure set is regenerable via the runner.

## LFS accounting

**Zero bytes pulled.** All 27 Cycles input blends were already materialized by the
m6-prep worker's 11.1 MB pull (real files, 97 KB–1.6 MB each; none are LFS pointers).
No new `git lfs pull` was needed.
