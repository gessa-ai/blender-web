<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 WM-worker early canvas registration — 2026-08-25

## Outcome

Commit `1fc5986` replaces the provisional direct `cmd:2` payload lookup from `645e2da` with
Emscripten's own `PThread.receiveOffscreenCanvases(d)` contract before presentation preflight.
The original `cmd:2` handler still runs after preflight and repeats the same registration
idempotently. The stage-1 missing-surface failure remains fail-closed.

This is the driver-validated late-registration repair: the transferred 1280x720
`OffscreenCanvas` was already present in the intercepted message, but the wrapper inspected
`GL.offscreenCanvases` before Emscripten's deferred handler populated it. No adapter capability,
canvas transfer, or relaxed presentation check was involved.

## Contract coverage

The pinned worker model now implements the Emscripten 6.0.5 helper semantics from
`tools/emsdk/upstream/emscripten/src/lib/libpthread.js:255` and reenacts both registrations. It
requires the first call before `getContext("webgpu")`, the second call in the forwarded handler,
exactly one forwarded entry, and the same registered canvas after both calls. A bounded injected
first-call exception must be diagnosed, leave stage 1 unpublished, and still allow the original
handler to run. Removing the early call is one of four rejected source mutations.

## Evidence

- Focused 20-case source contract plus four mutations is green
  (`20260825T140418-1369141`); shell syntax is green (`20260825T140418-1369142`).
- Exact committed worker source passes the complete 20-case contract
  (`20260825T140927-1375498`).
- Native/wasm32 integrated transaction parity remains byte-identical at 5,139 bytes,
  SHA-256 `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, preserving the
  same-turn surface-submission contract (`20260825T140601-1371078`).
- The real `blender_browser` relinks through locked Ninja, contains the early helper call and no
  retired `transferredCanvas` workaround, then ends exact no-work. OFF preflight is green
  (`20260825T140438-1369350`, `20260825T140535-1370853`, `20260825T140541-1370910`,
  `20260825T140552-1370986`). The bound artifacts are 659,927-byte JavaScript at SHA-256
  `07225a31a35b`, 119,016,606-byte Wasm at `8a78eb4d1054`, and 167,143,248-byte data at
  `09e58a25849e`.
- The headed COOP/COEP fallback diagnostic against `/` reaches `state=running`, settles a second
  WM tick, advances 74 idle ticks, turns trusted input into nine more ticks and one presentation,
  and reports zero stage-1/import failures, destroyed-texture submission rejections, transaction
  rejections, or device loss (`20260825T140645-1372714`).
- REUSE 6.2.0 remains green (`20260825T141208-1378470`). Required M4 remains red only at its
  unchanged unsupported hardware binding (`20260825T140937-1375823`); canonical container-backed
  regression restores M0 6/6 green while M1-M8 retain their existing strict receipt, product,
  browser, run-label, hardware, and release boundaries (`20260825T141007-1376291`).

The local fallback run is diagnostic-nonreceipt evidence. It binds no adapter, profile, split
product, pixel receipt, result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or promise. `/` and `/windowed.html` both select the intended windowed product under
the current `scripts/serve-web.sh` default. The hardware-only blocker remains
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn
and Windows were not attempted, and WSL was not restarted.
