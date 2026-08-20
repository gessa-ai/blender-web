<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 native USD receipt portability - 2026-08-20

## Outcome

The strict native USD capability producer is now checkout- and CWD-independent on Linux. It
derives the repository, build, producer, and immutable-output paths from its own source; requires
an explicit source-freeze receipt; confines output to a direct repository child; and validates
all build, freeze, and locked-no-work inputs before allocating an evidence directory.

This is producer readiness only. `build-native-gpu` is absent on ornith-lab, so no native USD
capability receipt was produced. No browser, adapter, split-product, M7 result, deferral, or
milestone promise was promoted. The M7 browser matrix remains blocked by the s7 hardware adapter
condition and the missing APPLY product.

## Reproduced defect

The old producer fixed its checkout and source-freeze inputs at `/Users/paws`, while its
self-check exercised only Ninja parsing and selector exclusivity. Root and descendant self-checks
therefore both passed even though a real Linux invocation could not address the current checkout.
It also created the immutable output root and label before validating the native build.

## Repair

- Derive the checkout from `Path(__file__).resolve()` and retain the canonical
  `build-native-gpu` and repository-relative producer identities expected by the aggregate gate.
- Require `--source-freeze` or `BW_SOURCE_FREEZE`; resolve relative values against the checkout,
  not the caller's CWD, and retain the existing real-file/hash binding.
- Reject unsafe labels, indirect roots, the repository root itself, and roots outside the
  checkout. Reserve the label only after the build profile, archive members, source freeze,
  locked Ninja no-work state, and stable re-analysis pass.
- Expand the product-free self-check to cover root derivation, freeze resolution, output
  confinement, unsafe paths, missing freeze input, Ninja capability rules, and selector
  exclusivity.

## Evidence

- Python syntax: `ledger/buildlogs/20260820T195735-2438879.log`.
- Root and descendant-CWD self-checks, each 5 positive / 7 negative:
  `ledger/buildlogs/20260820T200106-2444535.log` and
  `ledger/buildlogs/20260820T200106-2444542.log`.
- Missing-freeze and missing-native-build invocations both fail before output allocation:
  `ledger/buildlogs/20260820T200031-2444319.log`.
- Required M7 scope remains honestly RED only on its existing 34 missing staged/files/APPLY
  diagnostics: `ledger/buildlogs/20260820T195840-2440129.log`.
- Container-backed regression restores M0 6/6 GREEN and remains RED for the existing M1-M7
  strict-manifest, artifact, hardware, and run-label gates:
  `ledger/buildlogs/20260820T195959-2443066.log`.
- REUSE 3.3 is GREEN for 1,923/1,923 files:
  `ledger/buildlogs/20260820T200138-2445111.log`.
