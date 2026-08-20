<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 ROI-latency producer portability - 2026-08-20

## Outcome

The strict ROI-latency producer is source-portable to ornith-lab. It derives repository and
evidence paths from its own module, resolves exact repo-local Playwright and Sharp host tools,
binds their versions into new receipts, and rejects runtime, module, or output-path drift before
product inspection. The established screenshot greyscale/resize/MAD detector and the
100/150/33 ms budgets are unchanged.

This is producer readiness only. The s7 preflight still exposes software llvmpipe, and the current
development product has no APPLY deferred Wasm shard. No browser was launched, no latency receipt
was created, and no M5 result was promoted.

## Pre-patch discriminator

The retained producer still used `/Users/paws/plushly/game-platform/node_modules`, treated a
platform-delimited `NODE_PATH` as one path, accepted evidence outside the checkout, and recorded no
Node/Playwright/Sharp/libvips versions. Its three-check ROI/parser/budget self-check passed from the
checkout root and a descendant directory, while `.m4-node/node_modules/sharp` was absent. Those
controls are sealed by buildwrap logs `20260820T191359-2404730`, `-2404762`, `-2404777`, and
`-2404792`.

## Implementation

`sandbox/m5-latency/drive-trusted-latency-roi.mjs` now:

- searches `BW_NODE_MODULES`, each platform-delimited `NODE_PATH` entry,
  `.m4-node/node_modules`, and repository-local `node_modules`, with absolute-path deduplication;
- requires Node 22.16.0, Playwright 1.61.1, Sharp 0.35.3, and libvips 8.18.3;
- validates a safe immutable run label and confines evidence to one child of a repository-local
  output root before inspecting product artifacts;
- exercises loader fallback, version rejection, and a deterministic live Sharp transform in
  browser-free self-check mode;
- records the selected Node, Playwright, Sharp, and libvips versions in every new receipt.

The ignored `.m4-node` prefix was populated under native Node 22.16.0 without downloading a
browser (`20260820T191500-2405215`). `ledger/deps.json` records Sharp and its Linux x64 binary
closure as host-only, including package integrity and licenses. The runbook and latency README now
pin `sharp@0.35.3`. No Sharp code enters the Wasm or browser payload.

## Evidence and remaining boundary

- Node syntax: `20260820T192033-2408770`.
- Browser/product-free base self-check: 15/15, zero browser launches,
  `20260820T192033-2408802`.
- Repo-local live loader and transform: 17/17, exact Playwright/Sharp/libvips versions, transform
  SHA-256 `b03e4f437764f830b9807234b213357b2ce164c2e5cef2d874a476096c43054e`, zero browser
  launches, `20260820T192033-2408821`.
- Descendant-CWD repeat with split/duplicate `NODE_PATH`: the same 17/17 and transform SHA-256,
  zero browser launches, `20260820T192034-2408843`.
- Negative runtime control: global Node 25.1.0 is rejected against the 22.16.0 pin,
  `20260820T191952-2408559`.
- REUSE 3.3 compliance: 1,920/1,920 files with copyright and license information, zero errors,
  `20260820T192254-2412078`.
- Required `--scope m5`: honestly RED only because
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` is absent.
- Container-backed `--regress`: M0 is 6/6 GREEN; M1-M6 remain RED on their existing strict
  manifest, binding/APPLY, hardware, and run-label gates at `2026-08-20T19:21:53Z`.

The next browser receipt still begins with the strict CAPTURE -> accepted-hardware profiles ->
APPLY sequence. The llvmpipe adapter binds no profile or receipt.
