<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M6 — THE FIRST RENDERED IMAGE FROM BLENDER ON WEBASSEMBLY

**RENDERED.** Cycles-CPU path-traced the factory-startup default cube to PNG
under node from the `wasm32` Blender binary, and the image matches the native
pin oracle **within Blender's own idiff threshold (exit 0)** — 0 pixels over
`0.016`, effectively bit-near-identical (max error one LSB on one channel).
First pixels rendered by Blender's real render engine running as WebAssembly.

Artifact: `sandbox/m6-prep/wasm-first-render/wasm_out/cube_.png` (64x64 RGBA).

## Verdict line (the deliverable)

```
oiiotool <native> <wasm> --fail 0.016 --failpercent 1 --diff   ->  EXIT 0 (PASS)
  Mean error = 3.82966e-06   RMS = 0.000122549   Peak SNR = 78.2338 dB
  Max error  = 0.00392 @ (30,5,B)   (0.227451 vs 0.231373 — a single 1/255 step)
  13 pixels (0.317%) over 1e-06 ; 0 pixels (0%) over 0.016
RGB-only (alpha-normalized) diff: PASS
```

**Parity robustness (2nd data point):** re-ran at **128x128 @ 64 spp** (4x res,
4x samples — the m6-prep golden size, more path-tracer float-contraction
accumulation). Still `EXIT 0`: Mean error `2.3337e-06`, `0 pixels over 0.016`,
max error again a single `1/255` LSB. wasm render ~1.6 s at 2 threads. Parity
does not degrade with scale at this scene.
Evidence: `wasm_out2/cube_.png` vs `native_ref2/cube_.png`.

Thresholds are Cycles' verbatim upstream defaults (`0.016 / 1`,
`cycles_render_tests.py main`, transcribed in `sandbox/m6-prep/suite_plan.tsv`).
Comparison is **wasm-vs-native-oracle** on the identical scene+settings+script
(the default cube has no staged golden), per the brief's step-4 self-compare.

## Invocation (exact, reproducible)

Boot smoke (step 2 gate):
```
BLENDER_SYSTEM_RESOURCES=$PWD/upstream \
BLENDER_SYSTEM_PYTHON=$PWD/lib/wasm \
BLENDER_SYSTEM_DATAFILES=$PWD/upstream/release/datafiles \
M6_CYCLES_ADDON_PARENT=$PWD/sandbox/m6-prep/wasm-first-render/addon \
tools/emsdk/node/22.16.0_64bit/bin/node build-wasm-cycles/bin/blender.js \
  --background --factory-startup \
  --python sandbox/m6-prep/wasm-first-render/boot_smoke.py
# -> BPY_OK 5.2.0 LTS 3 / CYCLES_BUILTIN_OK True / CYCLES_ADDON_REGISTER_OK /
#    CYCLES_ENGINE_SET_OK CYCLES
```

The render (step 3) — same env, plus `M6_OUT`, `M6_SAMPLES=16`, `M6_RES=64`,
`M6_THREADS=2`, `--python render_cube.py`. Output `wasm_out/cube_.png`.

## Timings / thread count

| stage | result |
|---|---|
| link `bin/blender.js` (full core+Cycles, `-O2` Release) | BUILD OK, **599 s**, 14-core ninja `nice -19` |
| `blender.wasm` / `blender.js` sizes | **109 MB** / 236 KB (`--profiling-funcs`; +Cycles vs M2's 103 MB) |
| boot to `BPY_OK` | ~2 s wall |
| Cycles render (16 spp, 64x64, **2 threads**) | **~1.6 s** wall (`00:01.608 render Saved`) |
| native oracle same render (14 threads) | ~0.9 s |

**Threads:** ran at `--threads 2` (`render.threads_mode=FIXED`) on the first
attempt as a precaution against the probe's `-Wpthreads-mem-growth` TBB/pthread
wedge risk. It did **not** wedge — rendered clean first try; 2 threads was
conservative, not forced. Cycles-CPU is per-pixel deterministic (RNG seeded by
pixel+sample), so the low wasm thread count still matches the many-threaded
oracle — confirmed by the near-bit-exact diff.

## What made the binary render (the wiring, not a redesign)

The probe (`notes/m6-cycles-probe.md`) proved Cycles-CPU *compiles*; this closed
the remaining link + execution + parity gap. No upstream patches were needed —
**zero source changes; no patch 0113+ written.** The tree was already configured
`WITH_CYCLES=ON` (+ node profile from patch 0010); only three link/runtime
wirings mattered:

1. **Link:** `build-wasm-cycles/` had only the Cycles libs from the probe; the
   ~2400 core Blender TUs (blenkernel/gpu/nodes/draw/editors/python) had never
   been compiled in this tree. `ninja bin/blender.js` built them all + linked
   (Cycles libs pulled in via the pre-existing target deps). **No undefined
   symbols** — `_cycles` and `bf_intern_cycles` wired in clean.
2. **`_cycles` builtin:** present as a Python inittab entry under `WITH_CYCLES`
   (`bpy_interface.cc:370 {"_cycles", CCL_initPython}`) — `import _cycles`
   works with no extra plumbing.
3. **Engine registration:** the Cycles addon (`intern/cycles/blender/addon/`) is
   copied into the runtime `scripts/addons_core/cycles` only at *install* time,
   so the source-tree boot (`BLENDER_SYSTEM_RESOURCES=upstream`) lacks it. Staged
   a copy at `wasm-first-render/addon/cycles/` and registered it by hand
   (`import cycles; cycles.register()`) — `scene.render.engine='CYCLES'` then
   sets. (A later install step could place it in addons_core for auto-enable;
   the manual register is the minimal bring-up path and touches nothing upstream.)

## Method note (why default cube, not a staged manifest test)

The staged Cycles goldens (`sandbox/m6-prep/manifest.tsv`, 27 tests) are rendered
by `cycles_render_tests.py`, which spawns Blender **subprocesses** and uses
`multiprocessing` — neither available in the single-process wasm python (M2 debt).
Matching a staged golden also requires each test's *full* sample/resolution
settings (slow on the scalar kernel). The default cube via direct `bpy` — run
byte-identically on wasm and the native oracle — is the brief's sanctioned
step-4 path and gives a controlled, deterministic first-pixel comparison with no
test-runner dependency.

## Non-fatal noise (pre-existing, characterized elsewhere)

- `ModuleNotFoundError: No module named 'js'` at startup — `_bpy_internal/http/
  fetch` reaches for a Pyodide/browser module; boot continues to `BPY_OK`. M2/M4
  python-debt, not M6.
- OIIO `physical_memory` assert-print — pre-existing since M1.11
  (`notes/m2-python-boot.md` open items).

## What M6 needs next (from here to the M6 render-parity gate)

1. **Cycles-CPU small-scene subset** against the 27 staged goldens: needs a
   wasm-runnable render path at each test's real settings — either port
   `cycles_render_tests.py` off `multiprocessing`/subprocess (drive one blend
   per `node` invocation from the host runner) or add a bpy shim that loads the
   test blend + renders frame 1 directly. Then reuse the m6-prep comparator
   verbatim (exit-code gate) — no golden re-authoring.
2. **Workbench + EEVEE subsets** are the *GPU* half of M6 and block on the M4
   viewport composite (`notes/gpu-r21-cube-blocker.md`); Cycles-CPU was
   correctly taken first (pure CPU, no GPU dependency).
3. **Perf:** scalar kernel; fine for "small scenes" launch tier. wasm-SIMD
   (`-msimd128` + widen the SSE arch guard) is a later speed pass, not a
   correctness prerequisite (probe item 4).
4. Optional hardening: raise samples/resolution to confirm the sub-threshold
   match holds as path-tracer float-contraction accumulates (first look: 78 dB
   PSNR at 16 spp leaves large margin under 0.016).

## Evidence

- `sandbox/m6-prep/wasm-first-render/wasm_out/cube_.png` — THE wasm render.
- `sandbox/m6-prep/wasm-first-render/native_ref/cube_.png` — native oracle ref.
- `sandbox/m6-prep/wasm-first-render/render_cube.py` / `boot_smoke.py` — scripts.
- `sandbox/m6-prep/wasm-first-render/addon/cycles/` — staged Cycles addon copy.
- Build receipt: `ledger/buildlogs/20260806T201531.log` (BUILD OK 599 s).
