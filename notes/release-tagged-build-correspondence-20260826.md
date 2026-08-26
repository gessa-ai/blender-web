<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Tagged release build correspondence — 2026-08-26

## Outcome

Commit `2946f0e` adds the missing release boundary between a source tag and the
static artifact. `scripts/package-tagged-release.py` accepts only an annotated
semantic release tag at a completely clean `HEAD`, reuses the strict M8 APPLY
inventory and windowed-product preflight, requires the canonical pinned-upstream
source replay, independently replays full staged provenance, and requires the
public bundle's exact file set. It then emits a
normalized USTAR/gzip archive with fixed ownership, permissions, ordering, and
timestamps, plus a JSON sidecar binding the archive, source commit/tree, upstream
pin, accepted-profile identity, and every shipped file.

The receipt deliberately strips local profile and capture paths. It includes only
public artifact names and byte/hash identities. Existing output paths are never
overwritten, symlinks and extra files fail closed, and a partial archive is removed
if packaging fails before its receipt can be published.

The packager and its verifier are now explicit inputs to the two-root final source
freeze. The public README documents the reproducible invocation and the CAPTURE
prohibition.

## Evidence

- Fail-first stops at the absent packager:
  `ledger/buildlogs/20260826T212207-1269652.log`.
- The focused contract accepts an annotated tag and clean source tree, verifies
  the canonical pinned-upstream replay, produces two byte-identical normalized
  archives with an embedded receipt, and rejects eleven
  tag/source/tree/inventory/archive mutations plus the real current CAPTURE
  generation: `ledger/buildlogs/20260826T213247-1281587.log`.
- The canonical replay independently binds the pinned upstream worktree to the
  squashed source reconstruction: `ledger/buildlogs/20260826T213247-1281592.log`.
- The two-root technical-release freeze self-check remains green with both new
  required paths: `ledger/buildlogs/20260826T213247-1281589.log`.
- The canonical public assembler self-check remains green and continues to be the
  sole producer of hostable bundle files:
  `ledger/buildlogs/20260826T212546-1272218.log`.
- REUSE 6.2.0 is green:
  `ledger/buildlogs/20260826T213247-1281597.log`.
- Refreshed M8 returns to its existing 23 APPLY/browser/tier failures after the
  compliance receipt is regenerated:
  `ledger/buildlogs/20260826T212702-1273830.log`.

## Boundary

No tag, archive, APPLY build, public bundle, profile, hardware receipt, or milestone
result was created or promoted. The current build is intentionally rejected because
it is CAPTURE and its manifest marks it non-shipping. The driver-operated Apple rig
must still verify P0-E resize pixels and P0-G transient shadows and return accepted
profiles for `.wasm.orig` SHA-256 `5a9d09440073...`; only then may the build be
relinked to APPLY, tagged at clean `HEAD`, assembled, and packaged.
