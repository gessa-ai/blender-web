<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 split-runtime Linux portability

## Outcome

The strict APPLY runtime proof is now host-portable and fail-closed before evidence allocation.
It derives the checkout and module roots from its own file, requires Node 22.16.0, Playwright
1.61.1, PNGJS 7.0.0, and Playwright Chromium 149.0.7827.55, and selects Linux WebGPU arguments
without the Darwin-only Metal ANGLE flag. The receipt records those identities and the shared
runtime-adapter contract source.

The producer probes the exact headed persistent context through the shared
`hardware-webgpu-adapter-v1` contract. An absent, masked, fallback, CPU, or named software
adapter fails before the immutable run directory is reserved. The accepted adapter is recorded
in the runtime receipt. The persistent browser profile is a validated self-cleaning temporary
directory, not evidence and not a reusable warm profile.

## Failure and repair

The browser-free saved-render test reproduced the retained macOS fallback: without
`BW_NODE_MODULES` or `NODE_PATH`, PNGJS resolution failed (`20260821T001115-2685683`). The
driver also created its output directory before browser launch and had no adapter assertion, so
a software-backed run could allocate and potentially write a split-runtime receipt.

The repair adds exact dependency resolution from environment or repository-local roots, strict
platform/argument/path checks, and one injectable adapter-then-reserve seam. Its fixtures prove
both sides: llvmpipe reaches zero allocations, while an identified RTX 4090-shaped adapter reaches
exactly one. The authoritative saved-render test now derives the pinned repository Node and local
PNGJS paths, so its no-environment replay is independent of the caller's working directory.

## Evidence

- Root and descendant-CWD self-checks: 9 positive / 15 negative, exact live dependencies, zero
  browser launches (`20260821T001851-2691425`, `20260821T001908-2691595`).
- Real Node 25.1.0 is rejected in favor of the pinned Node 22.16.0
  (`20260821T001954-2693002`).
- Missing APPLY product rejects with zero immutable output allocation
  (`20260821T002207-2695791`).
- Saved-render oracle, topology-state monitor, exact split-artifact preflight, and full two-phase
  source verifier are green (`20260821T001908-2691600`, `2691606`, `2691615`,
  `20260821T001851-2691431`).
- The locked windowed target remains exact no-work (`20260821T002153-2695703`). REUSE 6.2.0 is
  green for 1,938/1,938 tracked files (`20260821T002247-2696872`).

## Boundary

No browser, CAPTURE/APPLY product, runtime receipt, adapter profile, GPU/product source, golden,
tolerance, blacklist, result promotion, deferral, or milestone promise was created or changed.
The live producer remains blocked by s7: ornith-lab exposes only software Vulkan, which binds no
receipt. At the final container-backed regression, M0 is 6/6 GREEN and M1-M8 remain RED only on
their recorded strict-receipt, APPLY/artifact, hardware, and run-label prerequisites.
