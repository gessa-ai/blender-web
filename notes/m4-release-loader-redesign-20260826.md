<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Release loader redesign — 2026-08-26

## Outcome

Commit `1040ac7` replaces the marketing-heavy windowed boot overlay with the owner-specified
minimal release loader: a neutral `#17181b` background, one thin ring, one 2-pixel determinate
bar, a percent readout, and one small single-line legal footer. The footer links the public GPL
source at <https://github.com/gessa-ai/blender-web> and carries the standing Blender Foundation
non-affiliation and trademark disclaimer. The hidden `#bw-diag` contract, `?gate=` behavior, and
loader dismissal after first semantic pixels are unchanged.

The removed proof copy now lives in `README.md`; it is no longer painted over Blender during
startup. No external font request is introduced.

## Local font and public inventory

The loader uses a deterministic static subset of the repository-pinned Inter 4.001 source at
`upstream/release/datafiles/fonts/Inter.woff2`. `scripts/subset-loader-font.py` pins FontTools
4.59.2 and Python Brotli 1.1.0, instantiates optical size 14 / weight 400, retains the required
Latin repertoire, and renames the modified font to `BW Interface Sans` in accordance with the
OFL reserved-font-name condition.

The emitted `platform_web/shell/fonts/bw-interface-sans.woff2` is 9,500 bytes with SHA-256
`266290448afbfd4c6ce386bbad0b305b478ca2612f665d1b26e5efc4d17e8190`. Its deterministic
Brotli-q11 public transport is 9,504 bytes. The font and `LICENSES/OFL-1.1.txt` are wired through
the monolithic and staged assemblers, service-worker precache/inventory, MIME servers, manifest
identity/provenance consumers, exact-tree checks, third-party inventory, and REUSE metadata.

## Evidence

- The pre-change shell fails the new contract at the required neutral background:
  `ledger/buildlogs/20260826T194953-1192465.log`.
- Deterministic font regeneration is exact:
  `ledger/buildlogs/20260826T195844-1198415.log`.
- The final source and real-browser loader contracts pass:
  `ledger/buildlogs/20260826T200725-1206450.log` and
  `ledger/buildlogs/20260826T200725-1206451.log`. The browser proof checks computed layout,
  the locally loaded font, the exact source/disclaimer footer, hidden diagnostics, retired-copy
  absence, and zero external requests.
- Public disclaimer, deploy portability, staged provenance, technical receipt, and critical-wire
  self-checks pass in `ledger/buildlogs/20260826T200725-1206456.log`,
  `20260826T200725-1206464.log`, `20260826T200725-1206472.log`,
  `20260826T200725-1206492.log`, and `20260826T200725-1206510.log`.
- Staged and monolithic assembler self-checks pass in
  `ledger/buildlogs/20260826T200725-1206527.log` and
  `ledger/buildlogs/20260826T195844-1198428.log`.
- Full M8 technical compliance passes in
  `ledger/buildlogs/20260826T200506-1204886.log`; repository-wide REUSE 6.2.0 reports all
  2,684 files compliant in `ledger/buildlogs/20260826T200251-1202455.log`.
- The pinned-container regression restores M0 to 6/6 while preserving the existing M1-M8
  receipt/APPLY/product boundaries in `ledger/buildlogs/20260826T200445-1204020.log`.

## Actual-product boot correction and exact relink

The first layout-only browser proof routed `boot-windowed.js` to an empty response, so it did not
execute the redesigned loader's real startup path. The release relink pass found the resulting
failure before publication: the real page stayed at `state=loading module`, requested neither the
Wasm nor data payload, and reported `ReferenceError: setIndeterminate is not defined`. The redesign
had removed the indeterminate helper and CSS but left one startup call behind.

Commit `824686b` replaces that stale call with `setProgress(0)`, preserving the single truthful
determinate bar while the independent ring provides activity. The static loader contract now rejects
any surviving `setIndeterminate` call and requires the zero-percent startup reset. The P0-G browser
diagnostic also passes Playwright timeouts in the documented third argument, fails early on an
explicit shell error, and persists a bounded DOM/page-error/console tail on failure instead of
discarding it.

Evidence:

- fail-first actual-product evidence is preserved in
  `sandbox/p0-widget-shadow/artifacts/diagnostic-failure.json`: `state=loading`, one page error,
  and the exact missing-function exception;
- final loader source/browser, P0-G source, and JavaScript syntax contracts pass in
  `ledger/buildlogs/20260826T202911-1222808.log`, `20260826T202911-1222809.log`,
  `20260826T202911-1222813.log`, `20260826T202911-1222827.log`, and
  `20260826T202911-1222820.log`;
- public disclaimer, deployment portability, monolithic/staged assembly, minifier, technical
  receipt, performance producer, and exact stage-provenance checks pass in
  `ledger/buildlogs/20260826T203130-1225796.log`, `20260826T203130-1225797.log`,
  `20260826T203130-1225801.log`, `20260826T203130-1225810.log`,
  `20260826T203143-1226149.log`, `20260826T203143-1226153.log`,
  `20260826T203143-1226161.log`, and `20260826T203204-1226545.log`;
- the exact-commit clean CAPTURE relink and no-work replay pass in
  `ledger/buildlogs/20260826T203329-1228089.log` and `20260826T203435-1228650.log`;
- strict CAPTURE inventory passes in `ledger/buildlogs/20260826T203617-1230257.log`;
- the final same-artifact browser run reaches `WM_main` in 28 seconds with 261 ticks, 18 uncapped
  presentations, zero page errors, and one black-RGB widget-shadow WGSL publication in
  `ledger/buildlogs/20260826T203518-1229660.log`;
- pinned REUSE 6.2.0 passes in `ledger/buildlogs/20260826T203229-1227335.log`.

The clean CAPTURE identities are: JavaScript 707,146 bytes at SHA-256 `901fa6ac74f0`; instrumented
Wasm 120,496,022 bytes at `a5534014979c`; `.wasm.orig` 119,142,918 bytes at `5a9d09440073`;
data 167,143,248 bytes at `09e58a25849e`; and schema-1 manifest 13,219 bytes at
`fe3fb7c007c0`. A second clean regeneration reproduced all five identities exactly. The manifest's
`prior_receipt_invalidated_before_mutation=false` truthfully records that the clean relink began
without an old receipt beside the outputs.

## Boundary

The release-quality CAPTURE generation is now freshly relinked and served with the corrected loader,
resize, pointer-lock, and P0-G candidates. It remains non-shipping and has no deferred shard. No
Apple profile or receipt was consumed or promoted, APPLY was not authorized, and no result/promise/
tolerance/golden/blacklist/deferral changed. Required M4 remains red locally because this host cannot
bind hardware pixels. The driver-operated Apple rig must still verify P0-E idle shrink/restore and
P0-G transient-shadow pixels, then produce fresh success plus terminal-error profiles against exact
`.wasm.orig` SHA-256 `5a9d09440073...` before a hash-bound APPLY relink is legal.
