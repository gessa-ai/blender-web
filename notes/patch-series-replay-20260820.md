<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Patch-series replay audit - 2026-08-20

## Outcome

The exact migration reconstruction path is green on ornith-lab. Starting from Blender
`fbe6228777e7`, the SHA-256-bound `patches/PREVIEW_SNAPSHOT.patch` applies cleanly and
reproduces every final modified or untracked upstream file byte-for-byte, including file
modes and symlink targets. The bounded verifier reports 257 concrete file paths; the
runbook's 210 count is the compact `git status` view in which an untracked directory is one
entry.

The numbered `patches/series` history is not clean-replayable and must not be promoted to
the current reconstruction authority. Its first failure is active entry 15,
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
the exact preview contains another 141 paths that were never split into numbered patches.
This matches the migration note's explicit contract: numbered patches are useful history,
while the preview snapshot is the integration-tree authority.

## Evidence and disposition

`sandbox/series-replay/verify.py --preview-only` checks the source pin, preview digest,
preview/status path-set equality, clean application, and final fingerprints. Receipt:
`ledger/buildlogs/20260820T155158-2088641.log` (`PREVIEW_REPLAY_PASS`, preview SHA-256
prefix `4e8233c5302d`, 257/257 paths).

Per the two-attempt stop rule, numbered-series repair is blocked rather than normalized
piecemeal in this iteration. A successor must either regenerate every overlapping
historical hunk against its true predecessor and prove all 125 sequentially, or introduce
an explicitly reviewed squashed canonical patch whose postimage equals the accepted preview.
Until then, reconstruction must continue to use the hash-pinned preview exactly as
`notes/migration-to-ornith-lab.md` requires.
