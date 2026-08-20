<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 canvas-smoke producer portability - 2026-08-20

## Outcome

The current trusted-keyboard canvas-smoke producer is source-portable to ornith-lab. It derives
all checkout paths from its own module, resolves the pinned Linux Playwright package through
documented module roots, and confines each immutable evidence run to a repository-local child.
Its self-check exercises those contracts without inspecting a product or opening a browser.

This is producer readiness only. The s7 preflight still exposes software llvmpipe and the
development windowed product is not the required APPLY primary/deferred pair. No browser was
launched, no canvas receipt was created, and no M5 result was promoted.

## Pre-patch discriminator

The driver already derived `REPO` from `import.meta.url` and its nine trace/state self-checks
passed from both the checkout root and a descendant directory. Three portability gaps remained:

- Playwright fell through to `/Users/paws/plushly/game-platform/node_modules`;
- a platform-delimited `NODE_PATH` was treated as one path and Playwright's version was not
  checked;
- `--out-root` could escape the repository even though receipt paths are repository-relative.

The pre-patch syntax and root/descendant self-checks passed at
`20260820T190008-2392010`, `20260820T190008-2392012`, and
`20260820T190013-2392080`; they did not exercise those three boundaries.

## Implementation

`sandbox/m5-canvas-smoke/drive-canvas-smoke.mjs` now:

- searches `BW_NODE_MODULES`, each platform-delimited `NODE_PATH` entry,
  `.m4-node/node_modules`, and repository-local `node_modules`, in that order;
- rejects missing/malformed exports and any Playwright version other than 1.61.1;
- validates a safe run label and permits evidence only in one child of a repository-local output
  root;
- extends `--selfcheck` with root derivation, absolute/deduplicated module roots, path-escape
  rejection, synthetic fallback, and optional live-loader checks;
- records the selected Playwright version in a real receipt without changing receipt schema v1.

The trusted key sequence, read-only bpy monitor, native/Wasm trace comparison, DPR/canvas checks,
request policy, and final M5 verifier are unchanged. The README and migration table now document
the Linux invocation and the unchanged s7 plus APPLY prerequisites. Class 8 in
`notes/porting-patterns.md` already records this producer-portability pattern.

## Evidence and remaining boundary

- Node syntax: `20260820T190929-2400349`.
- Browser/product-free root self-check: 17/17, zero browser launches,
  `20260820T190929-2400350`.
- Live loader: 18/18, Playwright 1.61.1, zero browser launches,
  `20260820T190220-2393516`.
- Descendant-cwd repeat with two distinct and one duplicate `NODE_PATH` entries: 18/18, both
  entries retained once, Playwright 1.61.1, zero browser launches,
  `20260820T190929-2400355`.
- REUSE 3.3 compliance: 1,919/1,919 files, zero missing/bad/unused licenses,
  `20260820T190953-2400659`.
- Required `--scope m5`: honestly RED only because the CAPTURE development product lacks
  `blender_browser.deferred.wasm`, `20260820T190324-2393956`.
- Container-backed `--regress`: M0 is 6/6 GREEN; M1-M6 remain RED on the existing strict
  manifest, binding/split-product, hardware, and run-label gates,
  `20260820T190801-2398420`.

The ROI-latency producer is the next independent portability unit, after its repo-local `sharp`
host dependency is pinned and recorded. Its greyscale/resize detector remains measurement
semantics and was not touched here.
