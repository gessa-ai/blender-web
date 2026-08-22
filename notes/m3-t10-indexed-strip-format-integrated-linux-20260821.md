<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T10 indexed-strip pipeline format - 2026-08-21

## Outcome

Patch 0155 closes a silent indexed-strip validation gap in both WebGPU batch draw paths. The
direct path previously selected `stripIndexFormat` only for indexed triangle-fan emulation, and
the indirect path always retained `Undefined`. Pinned Dawn's command-buffer validator rejects an
indexed line-strip or triangle-strip pipeline when that field is undefined, and separately
requires its value to match the bound index buffer. Blender has indexed line-strip producers for
grease pencil, curves, and particles, so this was a shipping draw omission rather than an unused
enum row.

The new pure mapping returns Uint16 or Uint32 only for line-strip, line-loop, and triangle-strip
pipelines and preserves Undefined for non-indexed or non-strip draws. Direct draws pass the real
index-buffer format, with the existing fan expansion retaining Uint32. Indirect draws now resolve
the indexed buffer before pipeline lookup and pass the same format, so the cache key and Dawn
descriptor agree with `SetIndexBuffer`.

## Experiment and evidence

The unchanged source failed the new contract at compile time because no strip-format mapping API
existed (`ledger/buildlogs/20260822T005155-804522.log`). The final checkout-relative driver runs
all 11 Blender primitive types against Undefined, Uint16, and Uint32 for 33 cases, including six
selected strip-format rows. Native and Node 22.16.0 emit the same 300 bytes at SHA-256
`95eca01f9746e162bfdd588ef7f815253a521d8d222eb397dc6d32c8a089d3ff`; the 13 canonical
pipeline/batch/enum/assert inputs are bound at SHA-256
`09e4482edb512e36c7e5efd864de59bcec766ad05332c9dea210ff2c1edbad77`, and the driver requires
exactly two shipping batch call sites (`ledger/buildlogs/20260822T005507-807145.log`, descendant
replay `ledger/buildlogs/20260822T005716-810317.log`). Both native and Wasm targets end at exact
locked-Ninja no-work.

The canonical freezer retains 257 paths and 20,258 manifest rows. Its 1,537,496-byte patch is
SHA-256 `29c199a2c796b0c3f8d19f03ce7b7d478073a9fd635dd3e833bb3a6bc9bf94ae`, and its live/replay
manifests are byte-identical at SHA-256
`abf74d3b822383af83655166a12cdc3d58da6f4e771adb96cc66cb0dfc6c7e1a`
(`ledger/buildlogs/20260822T005406-806382.log`). Canonical replay is green
(`ledger/buildlogs/20260822T005457-807027.log`). The real windowed product rebuilt through locked
Ninja and then ended at exact no-work (`ledger/buildlogs/20260822T005534-807922.log`,
`ledger/buildlogs/20260822T005614-809068.log`). Final REUSE 6.2.0 is 2,016/2,016 green.

## Boundary

This contract creates no WebGPU instance, adapter, device, render pipeline, draw, pixel artifact,
or receipt. Required M3 remains red for the absent fresh strict candidate
(`ledger/buildlogs/20260822T005743-810791.log`). Container-backed regression keeps M0 at 6/6 green
and M1-M8 red on their existing strict-receipt, APPLY/artifact, browser/run-label, and s7 hardware
boundaries (`ledger/buildlogs/20260822T005746-810857.log`). No result was promoted and no deferral,
tolerance, golden, blacklist, dependency decision, or promise changed.
