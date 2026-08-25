<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 callback registration epoch — 2026-08-25

## Outcome

Commit `5ac001e` closes R11 MAJOR-3. HTML5 callback userdata now identifies one listener
registration rather than the reusable `GHOST_SystemWeb` address. Each registration publishes a
unique epoch-bearing record, retirement clears its atomic admission token before removing the
twelve exact listeners, and records remain readable for the process lifetime so an already queued
browser callback can reject safely after window or system destruction.

The browser discriminator retains two Emscripten key-listener closures from successive windows,
performs two dispose/recreate cycles, and invokes both only after a third registration is current.
The predecessor delivered `KeyQ` and `KeyW` into the newest window
(`20260825T210619-1795624`); the replacement rejects both stale generations and still accepts fresh
input (`20260825T211850-1809457`).

## Evidence

- Exact-commit replay rejects 25 source/live-test mutations and binds both delayed generations
  (`20260825T211950-1810838`). The post-commit integrated native/wasm32 matrix remains
  byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`
  (`20260825T211834-1808176`).
- The real WasmFS + `PROXY_TO_PTHREAD` harness rebuilds cleanly
  (`20260825T210948-1797689`). Focus, IME, clipboard, custom-cursor, and Pointer Lock browser
  regressions pass in `20260825T211034-1800097`; the headed fullscreen case passes separately in
  `20260825T211100-1800939`.
- The optimized product relinks and then ends exact no-work
  (`20260825T211134-1801448`/`20260825T211222-1801895`). OFF preflight binds 679,421-byte
  JavaScript (`3543d05636de`), 119,031,405-byte Wasm (`e56ee5585a62`), and 167,143,248-byte data
  (`09e58a25849e`) (`20260825T211307-1803057`). The relink used the preserved dirty integration
  tree; its unrelated first-pixel-settle and device-limit edits are not part of `5ac001e`.
- The same baked product reaches Blender 5.2 LTS in headed Chromium on the forced fallback adapter,
  settles in 13.8 seconds, advances 77 idle ticks and one presentation 23 ms after trusted input,
  and reports zero stage-1/import/submission/transaction/device-loss errors
  (`20260825T211318-1803126`). This is explicitly diagnostic-nonreceipt evidence.
- Canonical replay retains 303 paths and 257 active patches at SHA-256 prefix `347d4aec2a1c`; its
  18-mutation freshness self-check passes (`20260825T212102-1811317` and
  `20260825T211912-1809765`). REUSE 6.2.0 covers 2,582/2,582 files
  (`20260825T212102-1811314`).

Required M4 remains red only at its unchanged unsupported hardware binding
(`20260825T211540-1805234`). Container-backed regression restores M0 6/6 green while M1–M8 retain
their existing strict receipt, product, browser, hardware, run-label, and release boundaries
(`20260825T211558-1805425`). No adapter, device, profile, split product, live receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or promise changed. Mesa
dzn and Windows were not attempted, WSL was not restarted, and s7 remains blocked by `no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
