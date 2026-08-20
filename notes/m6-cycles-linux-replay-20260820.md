<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Cycles-CPU Linux replay - 2026-08-20

> **Later correction (2026-08-20):** the two measured SKIPs below came from the
> suite registering the staged Cycles add-on after loading these old `.blend`
> files, which skipped Cycles' file-version handler. The immutable r3 receipt is
> valid for that runner, but its arithmetic attribution is superseded by
> `notes/m6-cycles-edge-attribution-20260820.md`. No exclusion is removed until a
> repaired full-suite receipt passes the stale-blacklist control.

## Outcome

The hardware-independent Cycles-CPU component is freshly verified on ornith-lab.
All 27 scenes rendered to completion from the dedicated Release Wasm product. The
unchanged pinned comparator reports 25 PASS and two measured, justified SKIPs:

| Test | Max error | Pixels over 0.016 | Disposition |
|---|---:|---:|---|
| `principled_bsdf_default` | 0.1098039 | 20.8% | wasm32/native edge divergence; exact operation unisolated |
| `principled_bsdf_emission_alpha` | 0.6862745 | 11.4% | wasm32/native edge divergence; exact operation unisolated |

There are zero render failures, unlisted comparator failures, stale exclusions,
blocked inputs, or mid-run artifact changes. This is a component result only. It
does not promote the aggregate M6 gate: the current Workbench/EEVEE product replay,
split APPLY artifact, and complete strict M0-M3 manifest remain blocked by the s7
hardware-Vulkan condition.

## Product and build evidence

- Blender source pin: `fbe6228777e7`.
- Configuration: Release, `WITH_CYCLES=ON`, `WITH_OPENSUBDIV=ON`,
  `WITH_PYTHON=ON`, `WITH_TBB=ON`, `WITH_CYCLES_EMBREE=OFF`, and
  `WITH_CYCLES_OSL=OFF`.
- Configure: `ledger/buildlogs/20260820T161231-2106101.log`.
- Locked build: `ledger/buildlogs/20260820T161328-2110696.log`.
- Final locked no-work proof: `ledger/buildlogs/20260820T163315-2162511.log`.
- JavaScript: 252,309 bytes,
  `f1028f32d1682a1f76d42efa21735dbc19ea195e0c770de7e55c8c440985ff19`.
- Wasm: 134,342,166 bytes,
  `de05586d625b67a0ab759f87b02c428a05b3dfc1d5562ea3db11d20c96a62fa0`.

## Final matrix and independent verification

- Immutable label: `m6-cycles-ornith-linux-20260820-r3`.
- Producer: `ledger/buildlogs/20260820T163026-2149534.log`.
- Independent live verifier: `ledger/buildlogs/20260820T163252-2158451.log`.
- Results SHA-256:
  `7fc9804e563f0c477d59b32354bac791f9ba038f56593fed42a14907e90c3d8f`.
- Manifest SHA-256:
  `272b80e1a4763931269ca6022b82a66e41b8f9a845a36b274b7de210212e12a2`.
- Blacklist SHA-256:
  `fe9c5a9f5c974f909a5102945a6a86fb1dbdccc26ce4836237552b41e37838a6`.
- Runner SHA-256:
  `161a97de6c8eb84caede1d1178f5863e073eac372889f6ede68d8cf179758e8f`.

The verifier re-hashes the exact JS/Wasm, runner, driver, addon tree, manifest,
blacklist, result table, all 27 inputs, goldens, renders, and comparator transcripts.
It then reruns all 27 comparisons with the network-disabled oracle image's pinned
`oiiotool` 2.4.17.0. The CPU-only entry point is explicit; the default verifier and
`harness/run.sh --scope m6` still require every GPU/browser component.

## Exclusion controls

The original OpenSubdiv note suspected BVH2 versus Embree. A fresh native control
rules that out. The pinned official Blender reports `_cycles.with_embree=True`, but
both scenes were explicitly rendered with `debug_bvh_layout='BVH2'`:

- Render controls: `ledger/buildlogs/20260820T162708-2145243.log` and
  `ledger/buildlogs/20260820T162718-2145595.log`.
- Golden comparisons: `ledger/buildlogs/20260820T162735-2145959.log` and
  `ledger/buildlogs/20260820T162735-2145960.log`.
- Native BVH2 maximum errors are 0.0117647 and 0.0156863, with zero pixels over
  0.016 for both scenes.

The Wasm failures are also independent of render thread count. Fresh two-thread
renders are recorded in `ledger/buildlogs/20260820T162754-2147117.log` and
`ledger/buildlogs/20260820T162754-2147118.log`; exact 0/0 pixel comparisons against
the one-thread renders pass in `ledger/buildlogs/20260820T162813-2147790.log` and
`ledger/buildlogs/20260820T162813-2147795.log`. PNG container hashes differ because
of metadata, so the claim is pixel identity, not byte identity.

The remaining named blocker is therefore a reproducible wasm32-versus-native
render divergence on two high-frequency Principled edge cases. A subsequent
full-product attribution round falsified both the scalar-versus-SIMD source path
and Cycles' relaxed reciprocal/signed-zero/contraction flags: see
`notes/m6-cycles-arithmetic-attribution-20260820.md`. Its exact scene, sampling,
or kernel operation is not yet isolated. The exclusions remain narrow and fail
stale if a future fix makes either comparator pass.

## Runner portability

The preserved immutable runner initially failed before rendering on a clean Linux
checkout because it created a unique label atomically without first creating the
ignored `cycles-runs/` parent. The parent is now initialized before the unchanged
atomic label creation. The independent verifier also exposes `--cycles-only` for
this CPU component; no harness scope, tolerance, golden, aggregate verifier default,
or result flag was weakened.

## Required repository checks

- Runner syntax and inventory self-checks:
  `ledger/buildlogs/20260820T163020-2148670.log` and
  `ledger/buildlogs/20260820T163020-2148671.log`.
- Aggregate-verifier self-check:
  `ledger/buildlogs/20260820T163020-2148690.log`.
- REUSE 3.3 compliance: `ledger/buildlogs/20260820T163518-2163231.log`.
- Required M6 scope: honestly RED only because the hardware-bound Workbench
  matrix is absent (`ledger/buildlogs/20260820T163527-2163350.log`).
- Required regression: M0 remains 6/6 GREEN; M1-M6 remain honestly RED on the
  existing strict-manifest, APPLY-artifact, hardware, and GPU-matrix blockers
  (`ledger/buildlogs/20260820T163538-2164251.log`).

No ledger result flag, comparator tolerance, golden, deferred entry, adapter
profile, split artifact, or milestone promise was promoted.

## Preserved M6 owner inputs

This commit also makes the previously preserved outer-worktree M6 input set
coherent in Git: the upstream-derived per-directory EEVEE thresholds, the full
77-row manifest, and the historical Workbench/EEVEE blacklist entries consumed
by the already-committed aggregate verifier. Those GPU rows retain their old
artifact labels and are historical only on ornith-lab. They were covered by the
verifier self-check, not relabeled as fresh Linux receipts; the missing current
Workbench matrix keeps the real M6 scope RED as shown above.
