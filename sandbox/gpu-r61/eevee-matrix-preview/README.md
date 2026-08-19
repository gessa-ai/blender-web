<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# EEVEE physical-F12 matrix screen

`run_eevee_matrix.mjs` screens all 30 `engine=eevee` rows in
`sandbox/m6-prep/manifest.tsv`. It does not edit the canonical one-row driver.
Instead, it creates one temporary driver copy per row and binds that copy to the
row's blend, golden, hashes, audited effective-sample expectation, threshold,
fail percent, OPFS name, output directory, and output label. The checked-in
`eevee-input-contract.tsv` binds all 30 upstream inputs to their exact SHA-256,
single-scene/object-mode preconditions, sample counts, view transforms, and probe-setup flags.
The audited sample distribution is 27 rows at 64, `raycast_bump` at 128, and
the two transparency rows at 800.

The harness validates the manifest thresholds against the pinned upstream
`eevee_render_tests.py` before generating a row. Browser rows are deliberately
synchronous (`maximumGpuConcurrency: 1`) and hold an exclusive cross-process
GPU lock shared with the native fixture batch. A run label is single-use; the
harness refuses to overwrite an existing run tree.

For a diagnostic or post-fix rerun, `BW_EEVEE_MATRIX_KEYS` accepts a
comma-separated list of exact manifest keys such as
`principled_bsdf/principled_bsdf_specular`. Unknown, empty, or duplicate keys
fail closed. Omitting it preserves the authoritative full 30-row run. Subset
provenance records the full manifest size, selected count, and requested order;
a subset is not a replacement for the final full matrix.

```sh
node sandbox/gpu-r61/eevee-matrix-preview/run_eevee_matrix.mjs --selfcheck

BW_EEVEE_MATRIX_PORT=8151 \
  BW_EEVEE_MATRIX_CANONICAL_PROBES=1 \
  BW_EEVEE_MATRIX_KEYS=principled_bsdf/principled_bsdf_specular \
  NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/gpu-r61/eevee-matrix-preview/run_eevee_matrix.mjs specular-r1
```

Remove `BW_EEVEE_MATRIX_KEYS` from the command above for the full matrix. The
canonical probe route uses the canonical driver's modal browser probe bake for
all 29 probe-dependent rows. `raycast/raycast_visibility` is the only pinned input
with `EEVEE_skip_probes_setup=true`; it deliberately bypasses probe setup.
Probe setup must reach its terminal state before the trusted physical-F12 click.
Product classification is marker-independent: success is bound to the F12
invocation, render completion, saved-image evidence, and comparator receipt,
not a diagnostic marker.

Each run writes `results.tsv`, `results.json`, `provenance.json`, per-row logs,
and the physical-F12 driver's evidence under
`sandbox/gpu-r61/eevee-matrix-preview/runs/<label>/`. Consolidated files are
updated after every completed row so an interrupted run still has an exact
prefix receipt. Temporary driver sources are removed on exit; their hashes and
complete substitution records remain in provenance.

Guarded native-prebaked fixtures can be selected instead with
`BW_EEVEE_MATRIX_PREBAKED_MAP`. The TSV has four columns and must cover exactly
all 29 probe-dependent rows:

```text
# dir  test  fixture_blend  expected_sha256
principled_bsdf	principled_bsdf_default	sandbox/path/to/prebaked.blend	0123...
```

Every fixture hash is mandatory. The map must have an adjacent
`fixture-map.receipt.json` with PASS status that binds the exact 30-row manifest,
pinned setup source, fixture generator, worker, input contract, official Blender
binary, serial native execution, verified skip-row exclusion, and every fixture
and row-receipt hash. Partial maps and unreceipted fixtures are refused.

One complete setup route is required: either
`BW_EEVEE_MATRIX_CANONICAL_PROBES=1` or the guarded 29-row prebaked map above.
The matrix refuses an uncovered default route. Ad-hoc
`BW_EEVEE_MATRIX_SAMPLE_MAP` and `BW_EEVEE_MATRIX_DEFAULT_SAMPLES` overrides are
also refused; sample expectations come only from the pinned input contract.

Product mode is always forced and diagnostic/sample-override environment
variables are stripped before each row.

## Guarded native-prebaked fixture batch

`generate_eevee_prebaked_fixtures.mjs` prepares the guarded map above by
running the pinned official Blender 5.2 LTS build and the unmodified pinned
`eevee_render_tests.py::setup` recipe. It selects 29 rows and excludes only
`raycast/raycast_visibility`; an official-Blender worker first verifies that
the excluded file has `EEVEE_skip_probes_setup=true` without baking it.

Before setup, the worker verifies the audited input hash, one-scene/object-mode
state, exact effective samples, skip flag, and absence of a preexisting
`Volume_Probe_Baked`. The native workers are synchronous
(`maximumNativeConcurrency: 1`) under the shared exclusive GPU lock. The batch
refuses to reuse its run root or overwrite any fixture, receipt, or log. Every
fixture receipt binds the input contract, setup source, worker, official
Blender binary, output hash, newly created sphere and volume properties, and
the exact `Volume_Probe_Baked` recognition identity.

```sh
node sandbox/gpu-r61/eevee-matrix-preview/generate_eevee_prebaked_fixtures.mjs \
  --selfcheck

# Intentionally expensive: performs 29 native probe bakes, serially.
node sandbox/gpu-r61/eevee-matrix-preview/generate_eevee_prebaked_fixtures.mjs \
  eevee-prebaked-r1
```

The batch output is under `fixture-runs/<label>/`. Its `fixture-map.tsv` can be
passed directly as `BW_EEVEE_MATRIX_PREBAKED_MAP`; the adjacent
`fixture-map.receipt.json` records the complete plan, exclusion verification,
source identities, per-row receipts, and incremental progress. Self-check mode
launches neither Blender nor a browser and performs no bake.

If `.eevee-gpu.lock` exists, both entry points fail closed rather than assuming
it is stale. Verify the recorded owner process is no longer running before
removing that exact lock directory and retrying.
