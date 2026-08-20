<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 files-browser Linux portability

## Outcome

The current M7 trusted-drop, File System Access, fallback upload/download, and OPFS-reload
producer is now checkout- and CWD-independent on ornith-lab. It derives the repository from
`import.meta.url`, resolves exact Playwright 1.61.1 from explicit and repository-local module
roots, requires Node 22.16.0, confines its gate receipt to the existing
`sandbox/m7-product-gate/verify_files.json`, and selects Linux WebGPU arguments without the
macOS-only Metal ANGLE argument. The v2 receipt schema and all eleven runtime acceptance facts
are unchanged.

The product preflight now runs before Chromium launch. It accepts only an uncredentialed
loopback HTTP origin, repository-local canonical inputs, a non-escaping and duplicate-free M8
bundle allowlist, exact split-manifest hashes, and canonical bundle artifact files. The
`--selfcheck` path exercises those contracts without reading a browser product, resolving a
live dependency unless explicitly supplied, writing a receipt, or launching a browser.

## Failure and repair

The pre-patch `--selfcheck` experiment stopped while importing Playwright from the retired
macOS module tree, before it could parse the option
(`ledger/buildlogs/20260820T222832-2588863.log`). The production script also fixed its checkout,
blend fixture, split manifest, public bundle, identity, and output to the old macOS root.

The repaired base self-check passes 17 checks from the repository root with zero launches
(`ledger/buildlogs/20260820T223824-2597651.log`). The live-loader check passes 18 checks from a
descendant CWD, resolves Playwright 1.61.1 from `.m4-node/node_modules`, selects only
`--enable-unsafe-webgpu` on Linux, and launches zero browsers
(`ledger/buildlogs/20260820T223824-2597687.log`). JavaScript syntax is green
(`ledger/buildlogs/20260820T223824-2597636.log`).

Node 25.1.0 is rejected with the exact version diagnosis
(`ledger/buildlogs/20260820T223831-2597778.log`). A production-shaped invocation with the pinned
Node and Playwright tree but no APPLY identity fails before receipt allocation and leaves
`verify_files.json` absent (`ledger/buildlogs/20260820T223832-2597810.log`). The existing M7
aggregate and fallback-producer adversarial self-checks remain green
(`ledger/buildlogs/20260820T223832-2597831.log`,
`ledger/buildlogs/20260820T223420-2593297.log`).

## Boundaries

No browser, GPU, CAPTURE/APPLY, bundle, files PASS receipt, product/upstream source, file-bridge
behavior, receipt schema, result flag, deferral, tolerance, golden, or promise changed. The
required M7 scope remains honestly RED on the same 34 staged/files/APPLY diagnostics. The s7
software-adapter stop condition still forbids the live producer and receipt.
