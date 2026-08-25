<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 IME terminal recovery — 2026-08-25

## Outcome

Commit `5daef5f` closes R11 MAJOR-2's queue-lifecycle defect. A browser composition can no longer
remain active because disposable updates filled the queue or owned-text allocation failed.
`ime-dead-keys` remains partial for its separate trusted physical-input receipt.

The fail-first real worker run filled all 64 pointer slots, rejected 1,985 later updates, and left
`composing=true` with no End (`20260825T204451-1773497`). The replacement queue stores messages in
fixed slots and reserves occupancy 62 for disposable Start/Update, 63 for Commit, and 64 for End
(`platform_web/ghost/GHOST_IMEQueueWeb.hh:63-131`). End/cancel carries no text and performs no
allocation. Browser allocation or saturation rejection invokes `_bw_shell_ime_cancel`, marks the
composition terminal, and ignores later updates; completed begin and explicit end use that same
path (`platform_web/ghost/GHOST_SystemWeb.cc:449-594`).

## Evidence

- The focused native/wasm32 contract is byte-identical at 110 bytes,
  SHA-256 `fb09ca9ccfd9a977ea73ec7d7586564aefae003bfffe3f100b0fd5ad1291ce36`. It covers normal
  ordering, exact 62/63/64 saturation boundaries, injected text-allocation failure followed by
  allocation-free cancel, and 128 reuse rounds (`20260825T205648-1786402`).
- The real PROXY_TO_PTHREAD worker harness covers the ordinary Unicode Commit/End path, synchronous
  update saturation to recovered End, converged producer/consumer/drop counters, and explicit
  cancel/focus restoration (`20260825T205127-1778536`). Fullscreen, Pointer Lock, clipboard,
  focus-reset, disposal/replacement, and custom-cursor browser regressions remain green
  (`20260825T205459-1781507`, `20260825T205511-1781894` through `1781911`).
- The 29-mutation source and baked-runtime contract is green (`20260825T205823-1788913`). The
  integrated native/wasm32 matrix remains byte-identical at 5,139 bytes,
  SHA-256 `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`
  (`20260825T205516-1783655`).
- The optimized product relinks and then ends exact no-work (`20260825T205147-1778830` and
  `20260825T205234-1779285`). OFF preflight binds 679,421-byte JavaScript, 119,030,301-byte Wasm,
  and 167,143,248-byte data (`20260825T205823-1788915`). The relink used the preserved dirty
  integration tree; its unrelated pre-existing first-pixel-settle and device-limit edits are not
  part of `5daef5f`.
- In headed Chromium under Xvfb, the same baked product completes a synthetic Unicode object rename
  through DOM → GHOST → Blender, advances three presentations, and reports zero rejected present
  submissions/transactions or device loss (`20260825T205422-1780996`). This forced
  fallback-software run is diagnostic-nonreceipt evidence. A preceding headless run stopped at the
  established second-presentation posture before reaching IME and is not accepted evidence
  (`20260825T205315-1779947`).
- Canonical replay and its 18-mutation freshness self-check are green
  (`20260825T205823-1788914`/`1788920`). REUSE 6.2.0 covers 2,580/2,580 files
  (`20260825T205823-1788930`).

Required M4 remains red only at the unchanged unsupported hardware binding. Container-backed
regression restores M0 6/6 green while M1–M8 retain their existing strict receipt, artifact,
hardware, run-label, and release boundaries (`20260825T205719-1786885`). No adapter, device,
profile, split product, hardware receipt, result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or promise changed. Mesa dzn and Windows were not attempted, WSL was
not restarted, and s7 remains blocked by `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)`.
