<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 CAPTURE-profile Linux portability

## Outcome

The strict Binaryen CAPTURE-profile producer is now checkout- and CWD-independent and fails
closed before evidence allocation. It derives the repository and immutable profile root from its
own source, resolves only repository-local or explicitly selected module roots, requires Node
22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and the bundled Chromium 149.0.7827.55, and selects the
Linux WebGPU launch arguments without the macOS-only Metal argument.

Before creating a run directory, the headed capture requests a high-performance WebGPU adapter
and records its browser-exposed vendor, architecture, device, description, and fallback flag.
Absent, masked, fallback, llvmpipe, lavapipe, softpipe, SwiftShader, WARP, CPU, and software
rasterizer identities are rejected. The profile union and APPLY finalizer independently recompute
that classification and reject missing, stale, internally inconsistent, old-schema, wrong-tool,
wrong-platform, or software-adapter capture receipts.

## Failure and repair

The pre-change experiment rejected `--selfcheck` before it could examine the producer
(`ledger/buildlogs/20260820T224822-2608911.log`). The old executable path then fell back to the
retired macOS module tree, accepted the ambient Node, launched without Linux's WebGPU argument,
allowed an arbitrary `--out-root`, and could emit a PASS profile receipt without any adapter
identity. That contradicted the s7 rule that a software adapter binds no profile.

The repaired browser-free producer check covers the parser, exact dependency loader, safe path
boundary, Darwin/Linux argument split, accepted hardware fixtures, and 22 negative cases; root and
descendant-CWD live checks select `.m4-node/node_modules` and launch zero browsers
(`ledger/buildlogs/20260820T230030-2620321.log`,
`ledger/buildlogs/20260820T230209-2622058.log`). Both Python receipt consumers accept four
Darwin/Linux hardware controls and reject 28 adversarial mutations
(`ledger/buildlogs/20260820T230030-2620356.log`). The source-integrity verifier binds the producer,
both consumers, and the adversarial test (`ledger/buildlogs/20260820T230030-2620365.log`).

The installed Playwright browser independently reports the pinned Chromium version
(`ledger/buildlogs/20260820T230030-2620374.log`). A no-evidence local browser control reports the
software Google/SwiftShader adapter and is classified inside the rejected token set
(`ledger/buildlogs/20260820T230059-2620559.log`). Wrong Node and the current non-CAPTURE product
both fail before the profile root exists (`ledger/buildlogs/20260820T225521-2613528.log`,
`ledger/buildlogs/20260820T225521-2613562.log`).

All Python and JavaScript split-contract tests plus the full two-phase source verifier pass
(`ledger/buildlogs/20260820T230109-2620713.log`). The existing windowed OFF development product
remains exact locked-Ninja no-work and passes its OFF preflight
(`ledger/buildlogs/20260820T230125-2621802.log`).

REUSE 6.2.0 is green (`ledger/buildlogs/20260820T230246-2623133.log`). The required M4 scope
remains honestly RED because no current hardware-bound APPLY receipt exists
(`ledger/buildlogs/20260820T230359-2623662.log`). Final container-backed regression restores M0
to 6/6 GREEN and leaves M1-M8 RED only on the existing strict-manifest, artifact, split/APPLY,
hardware, run-label, and pre-record compliance boundaries
(`ledger/buildlogs/20260820T230632-2626325.log`).

## Boundary

No CAPTURE profile, profile union, APPLY shard, browser/GPU receipt, result flag, deferral,
tolerance, golden, product/upstream source, or milestone promise was created or changed. The live
two-scenario producer remains stopped at s7: ornith-lab still exposes only software adapters, so
the accepted-hardware check deliberately allocates no profile evidence. Once the RTX-backed
adapter exists, the unchanged next action is the exact success plus terminal-error CAPTURE pair,
then union and APPLY.

## Audit correction

The subsequent 25-commit audit found that the intended non-fallback rule still accepted an
unreported `isFallbackAdapter` value. Commit `deac4ec` requires literal `false` in the producer,
profile union, and APPLY finalizer. Fresh browser-free evidence is 13/23 for the producer and
4/29 across both consumers (`ledger/buildlogs/20260820T232116-2638257.log`). No historical
profile or result changed because no Linux CAPTURE receipt exists.
