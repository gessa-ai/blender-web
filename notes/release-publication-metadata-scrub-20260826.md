# Public source metadata scrub — 2026-08-26

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Commit `a920bfd` removes the three private-host metadata carriers identified by the live public
snapshot audit. `.gitignore` and `patches/series` now describe the source-transfer boundary without
naming the private migration host. `patches/OUTER_WORKTREE_REMAINDER.patch` is regenerated from its
exact `0577f7f46a4be0ec2e61f02230e9fc7bff15a7cd` anchor, and neither the patch bytes nor its
reconstructed 178-path postimage contains a macOS/Linux user path or the private host label.

The refreshed patch remains a Git recovery patch rather than a redacted text dump. Files whose
historical preimage would expose a path are represented as Git binary deltas, while executable
postimage examples derive the repository root or use `$PWD`. Its exact identity is:

```text
563dfe303d9e401c73938d733e118d3f0e21dbeec5e4216a3b43154031b8e4b1  OUTER_WORKTREE_REMAINDER.patch
```

## Contract and evidence

`sandbox/publication-readiness/verify_metadata_scrub.py` fails closed on a private path/host label,
checksum drift, an unsafe or empty diff, apply failure, a dirty reconstructed postimage, reverse
failure, or any touched-path difference after reversal. The predecessor failed first on the named
`.gitignore` host label. At exact implementation commit `a920bfd`:

- anchored scrub/apply/reverse contract: `ledger/buildlogs/20260826T205531-1246339.log`;
- REUSE 6.2.0: `ledger/buildlogs/20260826T205531-1246340.log`;
- pinned-container regression: `ledger/buildlogs/20260826T205553-1246550.log`, restoring M0 6/6
  while M1-M8 retain their existing strict boundaries;
- current technical compliance refresh: `ledger/buildlogs/20260826T205602-1247273.log`;
- M8 scope after refresh: `ledger/buildlogs/20260826T205604-1247369.log`, unchanged at 23 missing
  APPLY/browser/tier receipt boundaries and with no metadata-staleness failure.

## Boundary

This iteration changes source-preservation metadata only. It does not regenerate or push the public
snapshot, publish a bundle, relink Blender, accept hardware pixels, create an APPLY product, or
promote a milestone result. The driver can now refresh the public snapshot from the canonical tree.
P0-E/P0-G Apple pixels and the current CAPTURE generation's accepted profiles remain separate.
