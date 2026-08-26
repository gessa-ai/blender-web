<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 complete critical-wire accounting — 2026-08-26

## Outcome

Commit `b1474cd` closes a launch-accounting omission in the 15 MB gate. The prior
14,963,658-byte projection counted only the profile-split primary Wasm, rewritten Emscripten
glue, and Stage-0 data. It omitted seven responses that the public page requests before the
first semantic interaction: `index.html`, diagnostics bootstrap, file bridge, boot shell,
Stage-1 loader, service-worker registration, and the generated service worker.

The receipt and strict M8 consumer now share one complete critical-path inventory. The
performance producer observes browser-context requests and responses, including worker-owned
traffic, requires every critical request before semantic interaction, and requires Brotli on
the complete set. The public assembler emits deterministic Node 22.16.0 Brotli-q11/lgwin-24
siblings for all seven shell/control assets; provenance, exact-tree, and bundle-identity checks
bind them.

## Size correction

Exact compression of the current source templates shows at least 29,493 previously omitted
Brotli bytes. A contract-shaped generated-control fixture with the exact production paths and
digest lengths measures 31,044 shell/control bytes. Applied to the unchanged provisional
three-file projection, the complete provisional wire is approximately **14,994,702 bytes**,
only **5,298 bytes below** the 15,000,000-byte bar. This is deliberately described as a
projection: accepted Apple profiles, the hash-bound APPLY relink, the generated public bundle,
and its exact receipt do not yet exist, and final content hashes can move the compressed control
bytes slightly.

The size result therefore remains red as release evidence even though the current shape projects
under the numerical ceiling. The last exact staged browser receipt is still the older oversized,
slow generation, and no current product has passed the <=8 second interaction limit.

## Evidence

- The focused contract fails first because `verify_m8` has no complete critical-path authority
  (`ledger/buildlogs/20260826T150646-931848.log`).
- The final Python and JavaScript critical-path contracts, performance producer self-check,
  assembler self-check, deterministic codec, provenance, transport, update-transition, M8
  verifier, source-freeze, final-composition, and REUSE checks are green
  (`ledger/buildlogs/20260826T151245-937819.log`,
  `20260826T151245-937813.log`, `20260826T151245-937828.log`,
  `20260826T150848-933903.log`, `20260826T150908-934043.log`,
  `20260826T150833-933663.log`, `20260826T150833-933711.log`,
  `20260826T151209-936320.log`, `20260826T150908-934022.log`,
  `20260826T151209-936307.log`, `20260826T151209-936308.log`, and
  `20260826T151245-937846.log`).
- The complete contract-shaped projection is recorded in
  `ledger/buildlogs/20260826T151118-935899.log`.
- Technical compliance is current and green (`ledger/buildlogs/20260826T151645-941888.log`).
  Required M8 remains red at its 23 APPLY/browser/product/tier boundaries
  (`ledger/buildlogs/20260826T151653-942003.log`). Container-backed regression keeps M0 6/6
  green and M1-M8 strict (`ledger/buildlogs/20260826T151701-942078.log`); its expected M8
  compliance-staleness row is caused by earlier regression scopes updating tracked results, so
  the post-regression direct M8 scope is the current count.

## Boundary

No Wasm/data/glue artifact, CAPTURE profile, APPLY product, public bundle, browser receipt,
hardware receipt, result promotion, tolerance, golden, blacklist, dependency, deferral status,
or milestone promise changed. P0-E idle resize pixels and both P0-F capture scenarios remain on
the driver-operated Apple rig; their accepted profiles are still mandatory before APPLY.
