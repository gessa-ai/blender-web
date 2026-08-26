<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 Blender Python support staging — 2026-08-26

## Outcome

Commit `8ea65f3` keeps the active Blender keymap and live startup/UI sources in Stage 0 while
moving boot-cold help, translation-tooling, Freestyle, template, test, and inactive-preset
sources to Stage 1. This is staged loading, not a feature cut: the production loader restores
every source byte after first pixels.

The optimized CAPTURE Wasm is unchanged: `.wasm.orig` remains 119,142,918 bytes at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Measured closure

The pinned Blender 5.2 native oracle reports the active key configuration as `Blender` and
loads no module from the deferred support roots. The exact windowed CAPTURE product agrees.
Because Blender executes keymap presets indirectly, the partition does not infer safety from
`sys.modules`: it explicitly retains both active files:

- `/bw/scripts/presets/keyconfig/Blender.py`
- `/bw/scripts/presets/keyconfig/keymap_data/blender_default.py`

All other presets are selected on demand. The deferred support roots cover `bl_pkg` tests,
Freestyle scripts, `_bl_i18n_utils`, `_rna_manual_reference.py`, Python/OSL/TOML templates,
and inactive operator/data/keymap presets.

- Native oracle evidence: `ledger/buildlogs/20260826T121551-785513.log`.
- Fail-first packer classification: `ledger/buildlogs/20260826T121718-787050.log`.
- Final 73-classification contract: `ledger/buildlogs/20260826T123927-807474.log`.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 964 | 17,786,235 |
| Stage 1 defer | 2,477 | 147,569,290 |
| drop | 1 | 1,787,723 |

The new boundary removes 1,507,477 raw bytes from Stage 0. Pinned Node 22.16.0 Brotli-q11
reduces Stage-0 data from 3,699,553 to **3,521,872 bytes** and rewritten glue from 80,383 to
**78,953 bytes**. With the unchanged 12,418,419-byte provisional split primary, projected
critical wire falls from 16,198,355 to **16,019,244 bytes**, a **179,111-byte reduction**.
It remains honestly **1,019,244 bytes over** LAUNCH.md's 15,000,000-byte bar.

Canonical packing is recorded in `ledger/buildlogs/20260826T121820-788226.log`; the exact q11
measurement is `ledger/buildlogs/20260826T123459-801467.log`.

## Runtime and release evidence

- The real monolith/candidate browser A/B preserves version, enabled add-ons, editor areas,
  default objects, and the exact active keymap structure. Ten support representatives are
  nonempty in the monolith and zero-length in Stage 0; four active boot sources remain exact.
  Trusted viewport input advances the uncapped WM/presentation counters before Stage 1. The
  loader restores 2,477 files / 147,569,290 bytes, imports the manual and i18n-settings paths,
  compiles restored i18n/template sources, and reports zero serious/page errors
  (`ledger/buildlogs/20260826T123321-800422.log`).
- The preceding codec partition still restores all bytes and CP1252/Latin-1/Shift-JIS behavior
  against the same candidate (`ledger/buildlogs/20260826T122457-792678.log`).
- Canonical current-product provenance, provenance self-check, staged assembler/runtime
  self-checks, release-freeze self-check, M8 consumer self-check, compliance-tool self-check,
  and REUSE are green (`ledger/buildlogs/20260826T123642-804705.log`,
  `ledger/buildlogs/20260826T123630-804566.log`,
  `ledger/buildlogs/20260826T123605-803484.log`,
  `ledger/buildlogs/20260826T123605-803483.log`,
  `ledger/buildlogs/20260826T123605-803490.log`,
  `ledger/buildlogs/20260826T123630-804567.log`,
  `ledger/buildlogs/20260826T123605-803503.log`, and
  `ledger/buildlogs/20260826T123759-805236.log`).
- The locked optimized target is exact no-work (`ledger/buildlogs/20260826T123745-805084.log`).
  M8 returns to its existing 23 APPLY/browser/tier failures after authoritative compliance
  refresh (`ledger/buildlogs/20260826T123824-806311.log`); container regression restores M0
  6/6 and retains every strict M1-M8 boundary (`ledger/buildlogs/20260826T123831-806416.log`).

The browser A/B uses a fallback software adapter and binds no semantic-pixel or hardware
receipt. No build-tree artifact, accepted profile, APPLY product, public bundle, result
promotion, tolerance, golden, blacklist, dependency, deferral, or promise changed. Accepted
Apple profiles, the hash-bound APPLY relink, and semantic hardware pixels for the staged product
remain mandatory.
