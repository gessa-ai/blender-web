<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web cursor main-thread bridge — 2026-08-25

## Outcome

Commit `0aa45be` makes Blender's browser cursor state real instead of reporting successful no-ops.
`GHOST_WindowWeb` runs on the `PROXY_TO_PTHREAD` WM worker, where its transferred
`OffscreenCanvas` has no DOM `style`. Standard cursor-shape and visibility requests now publish
constant-initialized atomic state plus a release generation in shared Wasm memory. Three
`EMSCRIPTEN_KEEPALIVE` getters expose that snapshot to the browser main thread, and the already-first
`diagnostics-bootstrap.js` script applies it to the original `#canvas` once per changed generation.

All 46 non-custom `GHOST_TStandardCursor` values have an explicit CSS mapping. The custom
bitmap/mask sentinel is excluded and now returns `GHOST_kFailure`; the port no longer claims a
cursor capability it did not implement. Startup, missing-canvas, missing-export, transient-export
failure, and module-teardown states retry without becoming boot-fatal.

## Contract coverage

The predecessor failed both fail-first seams: the C++ source contract found only inline hard-coded
successes, and the production shell installed no `__bwCursorBridge`. The final source verifier binds
the exact pinned enum order, support range, release/acquire publication, three runtime exports,
absence of worker-side `EM_ASM` DOM access, honest custom-cursor failure, and first-script poll. Its
five mutations remove shape publication, visibility publication, the unsupported result, one
runtime getter, or one enum value. The independent Node/VM behavior contract executes the real shell
script across every standard mapping, hide/show, unchanged/advanced generations, and recovery from
missing module, canvas, export, and throwing export.

## Evidence

- Focused source/behavior verification is green (`20260825T145424-1417279`): 46 mappings, five
  rejected source mutations, both visibility states, and all bounded recovery cases.
- Native/wasm32 integrated transaction output remains byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`; its expanded 33-file
  production-source binding is `c43efc062805` (`20260825T145141-1413152`).
- The real optimized `blender_browser` relinked through locked Ninja and then ended exact no-work
  (`20260825T144757-1410053`, `20260825T144845-1410484`). Strict OFF preflight is green
  (`20260825T144913-1410746`). The bound outputs are 659,480-byte JavaScript at SHA-256
  `5d36bcb4e2c4`, 119,016,766-byte Wasm at `d3108109742d`, and 167,143,248-byte data at
  `09e58a25849e`.
- The headed COOP/COEP fallback diagnostic against the intended `/windowed.html` product reaches
  `state=running`, settles its second WM tick, advances 74 idle ticks, turns trusted input into nine
  more ticks and one presentation, consumes a real shared cursor snapshot (`shape=0`, CSS
  `default`), and reports zero stage-1/import failures, destroyed-texture submission rejections,
  transaction rejections, or device loss (`20260825T145036-1412364`).
- REUSE 6.2.0 remains green (`20260825T145554-1418593`). Required M4 remains red only at the
  unchanged unsupported historical binding schema (`20260825T145311-1415818`). Final
  container-backed regression restores M0 6/6 green while M1-M8 retain their strict existing
  receipt, product, browser, hardware, and release boundaries (`20260825T145345-1416316`).

The local fallback run is diagnostic-nonreceipt evidence. It binds no adapter, profile, split
product, pixel receipt, result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or promise. The named blocker remains `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn and Windows were not attempted, and WSL was
not restarted.
