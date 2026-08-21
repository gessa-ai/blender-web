<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 monolithic deploy diagnostic Linux portability - 2026-08-21

## Outcome

The retained monolithic M8 deployment diagnostic now runs from the ornith-lab
checkout root or a descendant working directory. Its assembler derives the
repository from its own source, copies the current shell set, emits
platform-independent UTC metadata, and confines destructive replacement to its
named `bundle`/`bundle-*` generated namespace. The boot checker derives its
output and module roots, requires Node 22.16.0 and Playwright 1.61.1, and selects
Linux WebGPU arguments without the Darwin Metal override.

This is a developer diagnostic for an OFF-mode monolith, not the shipping
APPLY/staged bundle. No browser was launched, no adapter was accepted, and no
profile, split product, M8 receipt, result promotion, deferral, or promise was
created. The s7 hardware-Vulkan stop remains binding.

## Reproduced defects

Before `75b4902`, assembly on Linux failed before input validation because it
opened `/Users/paws/blender-web/platform_web/shell` (`20260821T002938-2702444`).
The boot check likewise tried to resolve Playwright through the retired
game-platform path and failed before it could offer a browser-free check
(`20260821T002938-2702445`). The assembler also used BSD-only `stat -f`, allowed
an unconstrained `rm -rf` target, and omitted the current
`diagnostics-bootstrap.js` and `file-bridge.js` sources fetched by
`windowed.html`.

## Repair

- `make_bundle.sh` derives `SELF_DIR`, `REPO`, and shell paths from
  `BASH_SOURCE[0]`; resolves caller-relative input/output paths; and rejects any
  replacement outside `sandbox/m8-deploy/bundle` or `bundle-*`.
- The bundle contains the five current shell sources plus `_headers` and the
  three monolithic binary artifacts. File sizes and UTC mtimes come from
  Python's portable `os.stat`; `awk` replaces the undeclared `bc` dependency.
- `verify_boot.mjs` uses explicit/environment/repository-local module roots,
  exact Node and Playwright versions, confined output, bounded arguments, and
  platform-specific browser arguments. Its self-check exercises resolution and
  parser rejection without launching Chromium.
- `test_portability.py` creates a complete temporary fake Git checkout outside
  the real repository, exercises copy and symlink assemblies from root and
  descendant CWDs, and proves output confinement plus missing-input
  preservation. Generated `bundle-*` runs are ignored beside the pre-existing
  `bundle/` and `artifacts/` rules.

## Evidence

- Shell/Node syntax: `20260821T003716-2708351` and
  `20260821T003716-2708353`.
- Five browser/product-free portability cases, two real fixture assemblies, and
  zero launches: `20260821T003921-2709740`.
- The same test and REUSE ran concurrently after fixtures moved outside the
  checkout: `20260821T003922-2709976` and `20260821T003922-2709977`; REUSE is
  1,939/1,939 with zero read errors.
- Live local Playwright resolution, Linux arguments, zero launches:
  `20260821T003627-2706924`.
- The real ornith-lab OFF product assembled successfully as a symlink-backed
  272.6 MiB diagnostic with the full current shell inventory:
  `20260821T003627-2706931`. Its generated output was removed after inspection.
- Final source-inclusive REUSE is 1,940/1,940 and the locked windowed product is
  exact no-work (`20260821T004428-2715417/2715419`).
- Required M8 remains honestly RED (`20260821T004032-2711520`) on the missing
  staged/APPLY/browser receipts. Regression remains RED
  (`20260821T004033-2711572`) on the recorded M1-M8 boundaries. A container-backed
  retry (`20260821T004052-2711922`) could not restore M0 in this inherited agent
  process because its kernel supplementary-group list predates the already
  recorded `pc` docker-group enrollment; no permission bypass was attempted.
