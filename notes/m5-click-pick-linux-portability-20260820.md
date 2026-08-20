<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 click-pick producer portability - 2026-08-20

## Outcome

The first current M5 browser-receipt producer is source-portable to ornith-lab. It no longer
contains the macOS checkout or Node-module root, and its self-check can validate the production
path contract without a browser, a shipping product, or a GPU receipt.

This is producer readiness only. The s7 adapter preflight still exposes software llvmpipe, and the
development windowed product is not the required APPLY primary/deferred pair. No browser was
launched, no click-pick receipt was created, and no M5 result was promoted.

## Pre-patch discriminator

The existing driver had three distinct properties:

- `REPO` already derived correctly from `import.meta.url`;
- Playwright fell through to `/Users/paws/plushly/game-platform/node_modules` and did not split
  multi-entry `NODE_PATH` values;
- the driver had no browser-free self-check, while `--out-root` could point outside the repository
  even though every artifact receipt assumes a repository-relative path.

The pre-patch canvas/latency self-checks and click syntax check passed at
`20260820T184510-2379153`, `20260820T184510-2379168`, and `20260820T184510-2379199`. They did not
exercise click-pick portability. The repo-local `.m4-node` prefix contains neither Playwright nor
Sharp because s7 stopped before browser receipt setup; that absence was preserved rather than
hidden by an install during this producer-only task.

## Implementation

`sandbox/m5-click-pick/drive-click-pick.mjs` now:

- searches `BW_NODE_MODULES`, each platform-delimited `NODE_PATH` entry,
  `.m4-node/node_modules`, and repository-local `node_modules`, in that order;
- rejects missing or malformed Playwright exports with the attempted roots named;
- permits evidence only in one safe immutable child beneath a repository-local output root;
- validates port, timeout, and run-label inputs before product inspection;
- implements `--selfcheck` for root derivation, absolute/deduplicated module roots, path escape
  rejection, exact native click-cycle identity, ordered trace matching, Playwright fallback, and
  selection-monitor markers.

The README now gives checkout-relative Linux commands and states the unchanged accepted-hardware
plus APPLY prerequisites. `notes/porting-patterns.md` Class 8 already records this recurring
producer-portability pattern, so no duplicate pattern entry was added.

## Evidence and remaining boundary

- Node syntax: `20260820T185121-2382786`.
- Browser/product-free self-check: 11/11 from the checkout root,
  `20260820T185121-2382801`.
- Live module-loader self-check: 12/12, Linux Playwright 1.61.1 resolved from an existing
  host-local module tree, zero browser launches, `20260820T185121-2382832`.
- Descendant-cwd repeat: the same 12/12 root and loader contract,
  `20260820T185121-2382785`.
- REUSE 3.3 compliance: GREEN, `20260820T185210-2383954`.
- Required `--scope m5`: honestly RED because the OFF development product has no
  `blender_browser.deferred.wasm`.
- Container-backed `--regress` at `2026-08-20T18:55:37Z`: M0 is 6/6 GREEN; M1-M6
  remain RED on the existing strict-manifest, browser-artifact, split-product, hardware, and
  run-label boundaries.

The current canvas-smoke producer retains the same macOS fallback and is the next independent
portability unit. The ROI-latency producer additionally requires `sharp`; its exact host-tool
version and license must be recorded before the repo-local install is expanded. Its established
Sharp greyscale/resize detector is measurement semantics and must not be silently replaced.
