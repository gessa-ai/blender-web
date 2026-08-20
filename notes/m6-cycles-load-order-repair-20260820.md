<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 Cycles staged-add-on load-order repair - 2026-08-20

## Outcome

The hardware-independent Cycles-CPU matrix is now **27/27 PASS with zero
exclusions** against the unchanged pinned goldens and the unchanged `0.016` / 1%
comparator. The two former Principled exclusions were suite-order artifacts, not
product arithmetic differences.

The repaired driver registers the staged Cycles add-on while factory startup is
still loaded, verifies that the exact add-on version handler is present, and only
then opens the test `.blend`. Each invocation records one version-handler event.
For files at or before 4.2.52 it additionally requires every scene to arrive with
the upstream-preserved `TABULATED_SOBOL` sampling pattern. The loaded scene is
then explicitly switched to Cycles, preserving the prior behavior for test files
whose stored engine is EEVEE.

## Behavior proof and stale-control proof

- The pinned Linux oracle proves that a persistent handler registered before
  `bpy.ops.wm.open_mainfile` runs exactly once, the Python driver continues, and
  `principled_bsdf_default.blend` loads as 2.78.4 with Tabulated Sobol:
  `ledger/buildlogs/20260820T175305-2306146.log`.
- Targeted repaired Wasm controls make both old blacklist rows pass the unchanged
  comparator and therefore trip the existing stale guard:
  `ledger/buildlogs/20260820T175555-2307923.log` and
  `ledger/buildlogs/20260820T175608-2308342.log`.
- The complete pre-removal matrix `m6-cycles-ornith-linux-20260820-r4b-stale-control`
  is 25 PASS / 2 STALE / 0 FAIL / 0 SKIP / 0 BLOCKED. The only stale rows are
  `principled_bsdf_default` (max 0.0117647, 0% over) and
  `principled_bsdf_emission_alpha` (max 0.0549020, 0.0061% over):
  `ledger/buildlogs/20260820T175853-2317214.log`.

Only those two Cycles blacklist entries were retired. Workbench's one and EEVEE's
seventeen measured exclusions are unchanged.

## Final immutable receipt

- Label: `m6-cycles-ornith-linux-20260820-r5`.
- Producer: `ledger/buildlogs/20260820T180250-2327982.log` (27 PASS, zero other
  verdicts, artifact stable).
- Independent live verifier: `ledger/buildlogs/20260820T180516-2336903.log`
  (`M6_CYCLES_CPU_PASS cycles=27pass/0skip`).
- Receipt SHA-256:
  `8ce1f67008f1e87934667c9a1e05dc126e002b710f5ad5c7bdc4aa43635273a7`.
- Result-table SHA-256:
  `9ee5d8035324cd37f7cebf50c73cfd228a0421daca633b43a5732522a7df6df4`.
- JavaScript SHA-256:
  `f1028f32d1682a1f76d42efa21735dbc19ea195e0c770de7e55c8c440985ff19`.
- Wasm SHA-256:
  `de05586d625b67a0ab759f87b02c428a05b3dfc1d5562ea3db11d20c96a62fa0`.

Receipt schema v3 hash-binds each row's render, comparator transcript, and node
log. The independent verifier re-hashes all three, reruns all 27 comparisons
with container-pinned OIIO 2.4.17.0, and requires exactly one
`addon-registered-before-load` plus one legacy-settings receipt per row. Nine
inputs exercise the Tabulated Sobol migration; eighteen newer inputs correctly
record the migration-specific assertion as not applicable while still proving
the pre-load handler event.

## Repository gates

Runner syntax, Python syntax, runner inventory, and aggregate-verifier self-checks
are green (`ledger/buildlogs/20260820T180239-2327872.log` through
`20260820T180239-2327890.log`). The post-edit independent verifier remains green
(`ledger/buildlogs/20260820T180917-2344493.log`), as does REUSE 6.2.0 compliance
(`ledger/buildlogs/20260820T180935-2348595.log`). The required M6 scope remains honestly RED only
because the current Workbench matrix is absent
(`ledger/buildlogs/20260820T180605-2341887.log`). Regression keeps M0 6/6 GREEN
and M1-M6 RED on the existing strict-manifest, hardware, split-product, and
current GPU-artifact gates (`ledger/buildlogs/20260820T180614-2342068.log`).

No product source, upstream file, golden, threshold, GPU receipt, result flag,
deferral, adapter profile, or milestone promise was changed.
