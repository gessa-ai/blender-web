# M8 public query-hook hardening source contract

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Commit `8867ebb` closes the committed-source security gap for the public shell.
The development shell retains its exact `?pyexpr=`, `?args=`, `?gate=`, and
keepalive controls for local capture rigs, while public assembly deterministically
changes one literal capability seam to false. Public Python and argv injection,
including their `window.__BW_*` equivalents, then return no value before boot argv
assembly. Public gate and keepalive query diagnostics also return production defaults.

The assembler and its independent provenance consumer now call the same byte-exact
transformer, which rejects an absent, duplicate, already-public, or mixed seam. The
focused executable contract evaluates the real boot-shell prefix in Node and rejects
six behavioral mutations: public re-enable, forged status, and removal of each of the
Python, argv, gate, and keepalive guards. Both new files are mandatory inputs to the
composite release freeze.

## Evidence

- Transformer self-check: positive 2 / negative 4
  (`ledger/buildlogs/20260826T054338-389708.log`).
- Real-source execution contract: positive 3 / negative 6, with Python, argv, and
  query controls all off in the public copy
  (`ledger/buildlogs/20260826T054338-389709.log`).
- Staged assembler source/confinement self-check: seven derived sources, zero APPLY
  manifest reads, zero writes (`ledger/buildlogs/20260826T054338-389710.log`).
- Independent staged provenance: four canonical derivations / eight negative cases
  (`ledger/buildlogs/20260826T054338-389715.log`).
- Staged producer self-check: 10 positive / 10 negative, exact Node 22.16.0,
  Playwright 1.61.1, and PNGJS 7.0.0, with zero browser launches
  (`ledger/buildlogs/20260826T054338-389727.log`).
- M8 consumer, composite release-freeze, and final M0-M6 hermetic self-checks are
  green (`ledger/buildlogs/20260826T054338-389735.log`,
  `ledger/buildlogs/20260826T054338-389753.log`, and
  `ledger/buildlogs/20260826T054338-389762.log`).
- REUSE 6.2.0 is green after the record update
  (`ledger/buildlogs/20260826T054603-394304.log`).
- Required M8 remains honestly red at 25 existing technical boundaries, headed by
  the missing APPLY inventory and staged/browser/product/soak receipts
  (`ledger/buildlogs/20260826T054432-391781.log`). Container-backed regression keeps
  M0 at 6/6 green and M1-M8 at their existing receipt/product boundaries
  (`ledger/buildlogs/20260826T054439-391854.log`).

## Remaining boundary

No public bundle was assembled and no browser, adapter, profile, receipt, result, or
promise was created. The current artifact is CAPTURE mode and has no deferred shard;
the driver-operated Apple rig must return the two exact hash-bound profiles before the
APPLY relink and real public-bundle attack run can occur. The security seam is now part
of committed source, but unrelated pre-existing worktree residue in the shell/GHOST
files still prevents the broader claim that committed state equals every byte used by
the current local build.
