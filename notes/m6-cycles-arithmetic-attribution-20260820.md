<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Cycles-CPU arithmetic attribution - 2026-08-20

> **Later correction (2026-08-20):** the experiment below correctly falsified
> SIMD selection and relaxed FP flags, but the remaining divergence was not a
> product arithmetic defect. The Wasm suite registered Cycles after loading the
> old `.blend`, skipping `cycles.version_update.do_versions`; see
> `notes/m6-cycles-edge-attribution-20260820.md`. The repaired 27/27 receipt is
> recorded in `notes/m6-cycles-load-order-repair-20260820.md`; the historical
> measurements below remain valid for the misconfigured runner.

## Outcome

The two remaining Cycles-CPU exclusions are **not caused by Cycles selecting
its scalar source path on WebAssembly**, and they are **not caused by the three
relaxed floating-point flags that differ from blender-web's strict platform
posture**. Both hypotheses were tested with full product relinks and unchanged
scene/golden inputs:

| Variant | `principled_bsdf_default` | `principled_bsdf_emission_alpha` | Versus scalar r3 |
|---|---:|---:|---|
| receipt-bound scalar r3 | max 0.1098039, 20.8% over | max 0.6862745, 11.4% over | baseline |
| wasm SIMD128 / SSE4.2 | max 0.1098039, 20.8% over | max 0.6862745, 11.4% over | 1 and 13 changed pixels |
| strict scalar FP | max 0.1098039, 20.8% over | max 0.6862745, 11.4% over | pixel-exact for both |

The earlier `scalar-Wasm/native-SIMD numerical drift` label was therefore too
specific. At this experiment stage, the honest remaining symptom was a
reproducible wasm32-versus-native render divergence on two high-frequency
Principled edge cases. Both narrow blacklist rows remained measured and
stale-failing here; the later load-order repair made them stale and retired them.
No blacklist, tolerance, golden, result flag, or deferral was changed by this
historical experiment itself.

## SIMD experiment

The baseline configure failure is exact: Cycles probes `-msse4.2` without the
`-msimd128` flag required by Emscripten 6.0.5, so `CXX_HAS_SSE42` is false and
the regular kernel uses scalar `float3`/`float4` code. The sandbox probe proves
both sides of that contract:

- `run_probe.sh` rejects the missing-`-msimd128` control, then compiles and runs
  Cycles' real `util/math_float4.h` SSE path through Emscripten's
  architecture-neutral `<immintrin.h>` compatibility header. Exact runtime
  output passes (`ledger/buildlogs/20260820T164706-2173098.log`).
- `compile_kernel_probe.sh` recompiles the production Cycles CPU mega-TU from
  the locked Ninja command without touching Ninja's object. The 1,984,375-byte
  probe object contains 70,578 `v128`/`f32x4`/`i32x4` disassembly rows and has
  SHA-256 `8746301444d95b61f179ecc37f66af46911fbd23ccc9e370f20d0481a4df27dc`
  (`ledger/buildlogs/20260820T164616-2172809.log`).
- The disposable three-file preview makes the CMake detection Emscripten-aware,
  enables Cycles' regular SSE4.2-equivalent path for `__wasm_simd128__`, and
  uses `<immintrin.h>`. The first full build correctly exposed an OpenImageIO
  include-order failure (`ledger/buildlogs/20260820T164902-2174731.log`); a
  directory-wide forced include fixed it, and all 180 Cycles/relink edges then
  passed (`ledger/buildlogs/20260820T165000-2175495.log`).

The SIMD product's unchanged golden comparisons are recorded in
`ledger/buildlogs/20260820T165256-2178101.log` and
`ledger/buildlogs/20260820T165326-2178420.log`. Against the scalar r3 renders,
the default scene differs at one 8-bit pixel (maximum 1/255), while the emission
scene differs at 13 pixels (maximum 2/255):
`ledger/buildlogs/20260820T165317-2178334.log` and
`ledger/buildlogs/20260820T165336-2178644.log`. Those tiny changes do not move
either Blender comparator statistic.

## Strict floating-point experiment

The second disposable preview leaves the scalar source path intact and appends
`-fno-reciprocal-math -fsigned-zeros -ffp-contract=off` after Cycles' normal
math flags. The same 180-edge product rebuild passes
(`ledger/buildlogs/20260820T165642-2181180.log`). Both unchanged golden
comparisons retain the exact baseline failure statistics
(`ledger/buildlogs/20260820T165752-2182976.log` and
`ledger/buildlogs/20260820T165756-2182975.log`), and exact 0/0 comparisons to
the scalar r3 renders pass for both scenes
(`ledger/buildlogs/20260820T165818-2183333.log` and
`ledger/buildlogs/20260820T165818-2183334.log`).

The focused A/B used the hydrated Linux OpenImageIO 3.1.13.1 tool only as a
diagnostic comparator. Its golden statistics reproduce the immutable r3
receipt's pinned OpenImageIO 2.4.17.0 values exactly; this note does not replace
or promote that receipt.

## Restoration and next experiment

Both preview patches reverse-apply cleanly and are retained only as falsified,
reproducible experiments. The three touched upstream files returned to their
pre-experiment SHA-256 values:

- `intern/cycles/CMakeLists.txt`:
  `a70959aecfb3ebfb0c2b2b96b93f2bf147723a4210fefbca9f478456fcc2c59f`
- `intern/cycles/util/optimization.h`:
  `f93d17eadbfbecf2d6b4b37d5f36e1b9a6486b91418c3062efb4a5fc7a7bbf6e`
- `intern/cycles/util/simd.h`:
  `29a3b99af2656c5d25dd5a45d05e58c487b305784fecc5342243a741288052cb`

The final scalar restore relink is green
(`ledger/buildlogs/20260820T165834-2183443.log`), and the locked dry run is
exact no-work (`ledger/buildlogs/20260820T165956-2184564.log`). The restored
receipt-bound product is byte-identical: JavaScript
`f1028f32d1682a1f76d42efa21735dbc19ea195e0c770de7e55c8c440985ff19`
and Wasm
`de05586d625b67a0ab759f87b02c428a05b3dfc1d5562ea3db11d20c96a62fa0`.

The next CPU-only round should compare native and Wasm float render passes and
run a one-variable scene-reduction matrix (transparent film/alpha, sampling and
camera jitter, then shader/geometry features). It must keep the two inputs,
goldens, comparator thresholds, and stale-blacklist behavior unchanged.
