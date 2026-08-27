<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize draw-plan diagnostic — 2026-08-27

## Outcome

The current CAPTURE product now reports one bounded `WGPUWeb-resize-trace` line for every
successful presentation inside a coherent-resize recovery episode. Each line binds that present to
the surface/configured/requested/backbuffer extents and to cumulative WebGPU draw-plan state. The
trace retains the latest draw plus dedicated `overlay_background` and `OCIO_Display` records, each
with its target extent, resolved viewport, explicit-scissor state, and whether it targeted the
window backbuffer.

This is diagnostic progress, not a P0-E fix. The driver measured both `8f604ab` and `d137387` at
0/10 Apple hardware shrinks with the same stable grey-overdraw pixels. The new generation exists to
distinguish the two remaining mechanisms before another behavior patch: unchanged background or
display sequences across presents prove retained-content reuse; advancing sequences with a stable
wrong target prove a stale geometry source; advancing correct plans point at submission/composition
order. P0-E remains open until the exact Apple test passes 10/10 with full idle grid, Cube, and gizmo
pixels after shrink and zero input.

## Bounded trace contract

`GHOST_WebDisplayState.hh` starts one single-writer trace snapshot only when a coherent replacement
drawable publishes a new redraw episode. The WebGPU framebuffer records plans after `Draw` or
`DrawIndexed` is placed into the pass. Native builds and multi-viewport emulation remain no-ops, and
steady-state browser draws pay only the inactive atomic check. Capture stops at the existing
180-tick recovery ceiling, after 24 successful presents in one episode, or after 64 lines for the
process, whichever comes first.

The record suffix is:

```text
<sequence>/<window-target>/<target-width>x<target-height>/
vp<x>,<y>,<width>x<height>/sc<enabled>,<x>,<y>,<width>x<height>
```

Sequences and draw counts reset at the coherent resize commit. The logger snapshots them at the
presentation call and emits only after that presentation transaction validates. Existing uncapped
presentation counters and semantic pixels remain the liveness/acceptance signals; the capped trace
is not a receipt.

## Verification

- Fail-first native compile rejected the absent trace API:
  `ledger/buildlogs/20260827T060133-1685867.log`.
- The focused seven-source/15-mutation trace contract is green:
  `ledger/buildlogs/20260827T060627-1689733.log`.
- The final integrated native/Wasm redraw and pipeline matrix, including 26 trace/recovery behavior
  cases, is green: `ledger/buildlogs/20260827T061847-1703423.log`.
- Canonical source replay is green after patch 0286 and the four-source snapshot refresh:
  `ledger/buildlogs/20260827T061831-1703234.log`.
- Pinned REUSE 6.2.0 is green: `ledger/buildlogs/20260827T061358-1699182.log`.
- Exact-product fallback shrink/restore is green at ticks `246/496/747`, presents `17/35/54`,
  episodes `0/1/2`, redraw presents `18/19`, and 37 parsed bounded trace rows, with coherent extent
  fields and zero scissor/encode/submit/transaction/device-loss failures:
  `ledger/buildlogs/20260827T062044-1706137.log`. This is diagnostic-nonreceipt evidence.
- The strict M4 scope remains RED at its exact-generation hardware binding boundary
  (`ledger/buildlogs/20260827T061422-1699333.log`); pinned-container regression restores M0 6/6
  while retaining the existing M1-M8 receipt/APPLY/product boundaries
  (`ledger/buildlogs/20260827T061445-1699777.log`).

## Relinked CAPTURE generation

RELINKED windowed-opt @ `140f50b` (`ledger/buildlogs/20260827T061915-1704817.log`):

| file | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,565 | `9541470a7ee08e9963276fa2e73b6ddf73a65c5bd3efddc23a4ea67a3c1c33ca` |
| `blender_browser.wasm` | 120,501,389 | `c9a392f623e6136c8aafb878758133405654579f1b25e1d975bb00058c8440fb` |
| `blender_browser.wasm.orig` | 119,148,234 | `6730a8ad7b2050ca8873f6a73187556a74f4034e33e75e797248fe1d5ddb2f09` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `48d307ec01593212110851b22a1d88967868111bb32d11c73b825b634740f06b` |

CAPTURE preflight, the producer self-check, and locked no-work replay are green at
`20260827T062033-1706025`, `20260827T062033-1706026`, and `20260827T062033-1706030`.
The relink invalidates earlier hash-bound profiles. No APPLY/public bundle, hardware receipt, result
promotion, tolerance, golden, blacklist, deferral, tag, or launch claim changed.
