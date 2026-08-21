<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Canonical source replay audit - 2026-08-20

## Outcome

The exact migration reconstruction path is green and is now explicit in
`patches/canonical`. Starting from Blender `fbe6228777e7`, its single SHA-256-bound squashed
patch applies cleanly and reproduces every final modified or untracked upstream file
byte-for-byte, including file modes and symlink targets. The historical
`PREVIEW_SNAPSHOT.patch` filename is retained because the final-source freezer independently
regenerated `canonical-source.patch` with the same 1,530,148 bytes and SHA-256. The bounded
replayer reports 257 concrete paths; the runbook's older 210 count was the compact `git status`
view in which an untracked directory is one entry.

The numbered `patches/series` history is not clean-replayable and is explicitly retained only
as development audit history. Its first failure is active entry 15,
`0016-gpu-webgpu-texture-format-conversion.patch`, at the GPU CMake source list. This is a
historical overlapping-hunk dependency, not source loss and not a Linux compiler delta.

## Diagnosis

- The series places `0016` before `0019`, but `0016`'s CMake preimage already contains the
  storage, uniform, vertex, and state-table lines introduced by later shared-lane patches.
- Moving `0016` after `0019` cannot resolve the dependency: `0019`'s own CMake preimage
  already contains the texture-format and data-conversion lines introduced by `0016`.
  The two recorded patch preimages are mutually dependent.
- The next shared-lane pair has the same shape: `0016b` expects shader/batch lines from
  `0022`, while `0022` expects the texture line from `0016b`.
- A scratch-only normalization experiment advanced through those pairs and then stopped at
  `0027-ghost-cmake-web.patch` on another stale shared CMake preimage. All experimental
  edits to historical patch payloads were restored byte-for-byte.

The active manifest currently names 125 numbered patches and intentionally retires two
diagnostic-only artifacts (`0117`, `0125`). Those patches mention 116 final path names;
the exact canonical patch contains another 141 paths that were never split into numbered patches.
This matches the migration note's explicit contract: numbered patches are useful history,
while the squashed patch named by `patches/canonical` is the integration-tree authority.

## Evidence and disposition

The stronger `sandbox/final-source-freeze/freeze.py` proof checks the exact pin, pristine real
index, repository state, initialized submodules, complete 20,258-entry live/replay manifests,
patch regeneration, and a final live resnapshot. It passed at
`ledger/buildlogs/20260820T155621-2091828.log`; the normalized receipt is retained at
`sandbox/series-replay/canonical-freeze-receipt.json`. Both manifests are 3,477,328 bytes with
SHA-256 `0d8fcd67732563bee9ed60d6329480408c5654524ba71cbb8c08c6dabec1849a`.

`sandbox/series-replay/verify.py` now treats canonical replay as its default green contract: it
checks the source pin, canonical manifest and digest, source/patch path-set equality, clean
application, modes, symlinks, and final fingerprints. `--numbered-history` remains a diagnostic
mode and still fails honestly at the first stale historical preimage. The two-attempt stop rule
therefore remains binding on piecemeal history repair, while exact source reconstruction is no
longer blocked on it.

## 2026-08-21 integration follow-up

Verified native-platform correction 0149 is now composed into the canonical snapshot. The
source freezer again proves exact clean-pin application, byte-identical 20,258-entry live/replay
manifests, byte-identical patch regeneration, and a stable final resnapshot. The authority remains
the same 257-path squashed patch but is now 1,530,642 bytes with SHA-256
`e03f140fe3f3c6448c9bc7bd52bfa572ea0f774fe5354cd98053341ef8d717b2`; the normalized current
receipt replaces the generic receipt path above. The old hash remains valid only for the dated
2026-08-20 evidence and migration save point.
