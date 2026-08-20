<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Cycles edge attribution - 2026-08-20

## Outcome

The two Cycles-CPU exclusions are **not product arithmetic divergences**. They are
caused by the diagnostic runner loading each old `.blend` before the staged
Cycles add-on is registered. That ordering skips Cycles' persistent file-version
handler, so the Wasm render uses current property defaults while the pinned
native oracle uses the migrated settings stored for the old file version.

Calling the exact upstream `cycles.version_update.do_versions(None)` after the
late registration changes the unchanged native/Wasm display comparison from
20.8% to 0% over 0.016 for `principled_bsdf_default`, and from 11.3% to 0.0061%
for `principled_bsdf_emission_alpha`. The same two corrected Wasm PNGs pass the
unchanged committed goldens with pinned OIIO 2.4.17.0 at 0% and 0.0061% over.
No product source, golden, threshold, blacklist, result flag, or deferral changed.

The existing immutable r3 receipt remains byte-valid historical evidence of what
that runner rendered. Its attribution of the two SKIPs to wasm32/native arithmetic
is superseded by this result. The exclusions must be removed only by a fresh
27-row receipt after repairing the runner's add-on/load order.

## Root-cause chain

1. `sandbox/m6-prep/run_wasm_cycles.sh:152` supplies the `.blend` before
   `--python render_test.py`, so Blender has already loaded and versioned the file
   before the diagnostic script runs.
2. `sandbox/m6-prep/wasm-first-render/render_test.py:26-43` registers the staged
   Cycles add-on only after that load. The immutable r3 logs confirm this path with
   `M6T_ENGINE_OK addon-registered` and `adaptive=True` for both excluded scenes.
3. The missed handler is the persistent
   `upstream/intern/cycles/blender/addon/version_update.py:66-105`. It preserves
   old-file behavior, including adaptive sampling and Tabulated Sobol at
   `:223-268`, older glossy/clamp defaults at `:177-188`, and world/material
   migrations at `:287-325`.
4. Without that handler, `AUTOMATIC` becomes full blue noise for background
   renders in `upstream/intern/cycles/blender/sync.cpp:435-471`. That changes the
   stochastic light samples before any suspected wasm arithmetic seam.

The effective baseline differences are:

| Input | Native after normal load | Wasm after late add-on registration |
|---|---|---|
| both files | Tabulated Sobol; adaptive off; light tree off | Automatic/blue noise; adaptive on; light tree on |
| `default` (file 2.78.4) | glossy blur 0; indirect clamp 0; world sampling NONE; material displacement 0 | glossy blur 1; indirect clamp 10; world sampling AUTOMATIC; displacement unset |
| `emission_alpha` (file 2.81.2) | no additional effective delta | no additional effective delta |

The sealed verifier checks equality of the scene, world, light, and material
effective settings after the handler runs. Explicit Tabulated Sobol alone makes
`default` pass at 0.153% but leaves `emission_alpha` at 1.43%; adding the legacy
light-tree setting reduces the latter to 0.0061%. The full handler is the honest
control because it also preserves every version-specific property for arbitrary
suite inputs.

## Float-pass boundary and reduction matrix

The 30-pair matrix writes 32-bit multilayer EXR plus display PNG for both runtimes.
At one sample, the primary geometry boundary is effectively identical while the
first stochastic passes are already different:

| Scene | Pass | Max error | Pixels over 0.016 |
|---|---|---:|---:|
| `default` | Object Index | 0 | 0 |
| `default` | Position | 0.0000158 | 0 |
| `default` | Diffuse Direct | 0.197 | 7,960 (48.6%) |
| `emission_alpha` | Object Index | 0 | 0 |
| `emission_alpha` | Position | 0.00000453 | 0 |
| `emission_alpha` | Diffuse Direct | 148.13 | 13,180 (80.4%) |

This places the first material divergence after the primary intersection, in the
sampling/light-transport configuration. Increasing both sides to 100 samples
converges the display failures to 2.64% and 0.574%; transparent film is a no-op,
forcing alpha does not clear the failures, and shader/geometry reductions only
remove the affected contributions. Those controls agree with the load-order root
and falsify film, output alpha, camera hits, subdivision, and Principled alone.

## Evidence

- Sealed label: `m6-edge-ornith-linux-20260820-r10` (30 native/Wasm pairs).
- Matrix/product/input hash check:
  `ledger/buildlogs/20260820T173718-2262051.log` (GREEN, 179 s).
- Independent pass/settings/golden verifier:
  `ledger/buildlogs/20260820T174027-2271099.log` (GREEN, 39 s).
- Score-table SHA-256:
  `20c639ed0b9d1b0a51496b38c74ef957cb6f7b86f8398f244fc0ab70c6181cc5`.
- Pinned corrected-golden comparator transcript SHA-256 values:
  `ec22a727f894390ac0eb41d89f11bcb585835870eebae184e128202592e0e6c6`
  (`default`) and
  `3c1e4a1b2acb4cd97c342c5c6fe0441c3ec2e3b3d17d1055d953d62cbbc95d32`
  (`emission_alpha`).
- Reproducer/verifier:
  `sandbox/m6-cycles-edge-attribution/{run_matrix.sh,render_variant.py,analyze_matrix.py,verify_attribution.py}`.
- REUSE 6.2.0: GREEN (`ledger/buildlogs/20260820T174506-2299103.log`).
- Required container-backed M6 scope: honestly RED on the unchanged aggregate
  run-label contract (`ledger/buildlogs/20260820T174538-2299510.log`).
- Required container-backed regression: M0 remains 6/6 GREEN; M1-M6 remain RED
  on their existing strict-manifest, hardware, split-product, interaction, and
  aggregate M6 label gates (`ledger/buildlogs/20260820T174538-2299614.log`).

Generated EXRs, PNGs, logs, and receipts live under the ignored sealed-label run
directory. The runner hash-binds itself, all three Python tools, both input blends,
both unchanged goldens, and the receipt-bound JS/Wasm pair, then rejects any
mid-run drift.

## Next unit

Repair the suite launch sequence so the staged add-on is registered before the
file load, or execute the exact upstream handler once after a deliberately late
registration. Then rerun all 27 Cycles rows and the independent verifier. The two
blacklist entries may be removed only after the unchanged pinned comparator is
27/27 green and the old entries trip the stale-blacklist control.
