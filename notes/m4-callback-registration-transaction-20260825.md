<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 callback registration transaction — 2026-08-25

## Outcome

Commit `ef25bfa` closes the R11 callback-registration transaction residual. The twelve Emscripten
HTML5 listener setters now run as one ordered transaction. The first non-success result stops the
sequence, removes the exact successful prefix in reverse order, and leaves callback userdata,
active epoch, owner token, and registered state unpublished. A fully successful set publishes all
four together. Initial or replacement window creation now deletes the candidate and returns null
when its listener transaction cannot complete.

The durable epoch record introduced by `5ac001e` is retained before registration so even a queued
callback from a failed prefix can safely reject for the process lifetime. The ordinary full-set
unregister path uses the same reverse-order remover, preventing registration and retirement lists
from drifting.

## Evidence

- The predecessor fails before accepted evidence at the missing transactional declaration
  (`20260825T212927-1818560`). The final focused source/live contract rejects 32 mutations,
  including wrong set size, skipped prefix rollback, early owner publication, ignored window
  failure, and weakened replacement assertions (`20260825T213203-1820303`).
- Native and wasm32 execute 15 byte-identical transaction cases: every one of twelve failure
  positions, full success, failed replacement, and clean retry. Integrated output is 5,305 bytes,
  SHA-256 `98f9c1ca84af`, with the exact shipping helper compiled into both targets
  (`20260825T213408-1825858`).
- The real WasmFS + `PROXY_TO_PTHREAD` GHOST harness rebuilds cleanly
  (`20260825T213429-1827195`). Its browser lifecycle test passes disposal, fresh input, bounded hit
  testing, two delayed stale generations, and repeated replacement (`20260825T214140-1834863`).
  Focus, Pointer Lock, IME, clipboard, and custom-cursor browser regressions also pass
  (`20260825T213540-1828731` through `20260825T213540-1828744`).
- The optimized product relinks and then ends exact no-work
  (`20260825T213555-1829417`/`20260825T213645-1829794`). OFF preflight binds 679,421-byte JS,
  119,032,641-byte Wasm, and 167,143,248-byte data (`20260825T213705-1830090`), with SHA-256
  prefixes `3543d05636de`/`0e7e8df9dbf4`/`09e58a25849e`.
- The same product reaches Blender 5.2 LTS on the forced fallback adapter, advances 75 idle ticks,
  completes trusted input to a new presentation in 32 ms, and reports zero stage-1, import,
  submission, transaction, or device-loss failures (`20260825T214159-1835187`). This is explicitly
  diagnostic-nonreceipt evidence.
- Canonical replay retains 303 paths and 257 active patches at SHA-256 prefix `347d4aec2a1c`; its
  18-mutation freshness check passes (`20260825T213908-1831984`/`20260825T213908-1831983`).
- REUSE 6.2.0 covers all 2,583 files (`20260825T214344-1836881`).

Required M4 remains red only at its unchanged unsupported hardware binding; container-backed
regression restores M0 6/6 green at `2026-08-25T21:39:39Z` while M1–M8 retain their existing strict
receipt, product, browser, hardware, run-label, and release boundaries. The relink used the
preserved dirty integration tree; its unrelated first-pixel-settle and device-limit edits are not
part of `ef25bfa`. No adapter, device, profile, split product, live receipt, result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or promise changed. Mesa dzn and
Windows were not attempted, WSL was not restarted, and s7 remains blocked by `no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
