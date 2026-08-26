<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 staged payload packer reconciliation — 2026-08-26

## Outcome

Commit `cb459b9` makes the staged-data partition used by the provisional split measurement a
committed release input. The packer now rejects partial, duplicate, unsafe, overlapping, gapped,
out-of-range, or byte-count-incoherent preload manifests instead of warning and continuing. It
also accepts Emscripten's integral scientific-notation offsets without silently omitting entries.
The executable contract is part of staged provenance and the two-root release freeze.

The uncommitted partition was not landed verbatim. A Stage-0-only browser experiment exposed an
empty-placeholder registration failure for the newly enabled Cycles add-on; the final partition
keeps all ten Cycles Python files. Source tracing also showed that factory solid shading selects
an external `.sl` preset by name. The final classifier therefore keeps the five tiny `.sl` files
and defers only lazy world/matcap images, preventing a zero-length selected preset from shading the
first frame black. Blender's datatoc CMake edges prove that `preview*.blend` and `splash.png` are
compiled into the executable, while `toolbar.blend` is a build-time icon-generator input; their
duplicate preload copies remain deferred with NumPy's test corpus and OpenUSD operator resources.

## Exact partition and wire measurement

Against the unchanged 167,143,248-byte CAPTURE data payload:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 2,554 | 28,741,042 |
| Stage 1 defer | 887 | 136,614,483 |
| drop | 1 | 1,787,723 |

The committed preimage produced 45,598,813 raw / 15,994,738 Brotli-q11 Stage-0 bytes. The final
partition produces 28,741,042 raw / 5,615,715 q11 bytes, saving 16,857,771 raw and 10,379,023 q11
bytes. Using the same Node 22 Brotli encoder for every critical component, the unchanged
provisional primary is 12,418,419 bytes and rewritten glue is 86,662 bytes. Critical wire is thus
**18,120,796 bytes**, still **3,120,796 bytes over** LAUNCH.md's 15 MB bar. This is a large staged
data improvement, not a launch-budget pass.

## Evidence and boundaries

- The 24-classification, five-positive, ten-negative packing contract passes, including exact
  KEEP/DEFER/DROP slicing and placeholder offsets
  (`ledger/buildlogs/20260826T095236-651142.log`).
- Staged provenance re-derives all four outputs, rejects eight mutations, and now runs the packer
  contract; assembly self-check and release-freeze self-check are green
  (`ledger/buildlogs/20260826T095236-651143.log`, `20260826T095236-651147.log`, and
  `20260826T095236-651155.log`).
- Exact product partition counts are in `ledger/buildlogs/20260826T094841-647368.log`; consistent
  q11 inputs, savings, and critical total are in
  `ledger/buildlogs/20260826T095445-653758.log`.
- A Stage-0-only CAPTURE probe and the monolith control each reach 254 uncapped WM ticks and 14
  presentations on fallback SwiftShader, with zero relevant console or page errors. Both decoded
  screenshots are the same uniform RGB 24 WSL fallback result, so this is liveness/error A/B
  evidence only, not pixel acceptance (`ledger/buildlogs/20260826T095652-655235.log`).
- REUSE 6.2.0 is green (`ledger/buildlogs/20260826T095337-653263.log`). The pre-commit M8 replay
  remained red at its 23 existing APPLY/browser/product boundaries plus the expected transient
  stale-compliance receipt (`ledger/buildlogs/20260826T095255-652121.log`).

No build-tree file, Wasm, JavaScript runtime, profile, APPLY artifact, hardware receipt, result
promotion, tolerance, golden, blacklist, dependency, deferral, or promise changed. The exact
CAPTURE `.wasm.orig` remains SHA-256 `c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.
Accepted success and terminal-error Apple profiles are still required before APPLY, and the real
staged product must still prove semantic Stage-0 pixels on conformant hardware.
