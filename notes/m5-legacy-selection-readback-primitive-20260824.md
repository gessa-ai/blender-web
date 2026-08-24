<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 legacy-selection owned readback primitive

## Outcome

Commit `66fd3aa` and numbered patch 0253 add an owned, non-blocking raw readback request at the
legacy draw-selection boundary. The request retains both the requested rectangle and its exact
viewport clamp, owns the framebuffer `GPUReadback` across browser event-loop ticks, rejects an
unexpected terminal byte size, and applies Blender's existing stride realignment only after the
exact clamped bytes settle. Empty out-of-viewport and no-selectable-ID requests complete ready with
the synchronous null/zero-length result.

The stock synchronous `DRW_select_buffer_read` and its bitmap/sample/nearest callers remain
unchanged. This is deliberately the prerequisite for their later mesh and gesture operator
continuations, not a claim that the legacy-selection family is already browser-safe.

## Evidence

- The unchanged source rejects before evidence allocation because the owned selection API is
  absent: `ledger/buildlogs/20260824T162127-241508.log`.
- The final post-commit driver rejects 14 independent source mutations, reverse/forwards the exact
  two-file numbered patch, and compiles the actual `gpu_readback.cc` and `gpu_select_next.cc`
  sources natively and under wasm32. Five contracts, including six selection-request scenarios and
  a 12-pixel clamp/realign case, produce the same 383 bytes at SHA-256
  `a3c96d89adbb5a4790dcbfc6201706fe44230bf0480c08708cd4967aa17cd0af`:
  `ledger/buildlogs/20260824T163820-255433.log`.
- Patch 0253 is SHA-256
  `1d362c642cac5d428ce31db49ff24b0315de6801dcf476cc354488c6f9b3e3b2`. Canonical freeze/replay
  retains 20,258 byte-identical entries at patch SHA-256
  `00e429a23c1e41832d0b94fb8fc39eee060c53e3cdd2c766931c4a0ae67cddac` and manifest SHA-256
  `014efb3d3fb3afa5e412737271a52c5c2287a8de5836b4e98b7604302afa2d1a`:
  `ledger/buildlogs/20260824T163512-252822.log` and
  `ledger/buildlogs/20260824T163051-248021.log`.
- The actual native and wasm draw libraries compile, the real optimized `blender_browser` relinks
  and ends locked-Ninja no-work, and strict OFF preflight binds 657,928-byte JavaScript,
  118,918,379-byte Wasm, and 167,143,248-byte data:
  `ledger/buildlogs/20260824T162710-245361.log`,
  `ledger/buildlogs/20260824T162738-245692.log`,
  `ledger/buildlogs/20260824T163114-248416.log`,
  `ledger/buildlogs/20260824T163203-249575.log`, and
  `ledger/buildlogs/20260824T163219-249781.log`.
- Repository-local REUSE 6.2.0 covers 2,331/2,331 files:
  `ledger/buildlogs/20260824T163919-256650.log`. Container-backed regression restores M0 to 6/6
  green while retaining the existing strict receipt, split-product, browser, and release
  boundaries: `ledger/buildlogs/20260824T163331-250712.log`.

## Remaining boundary

`gpu-sync-readback-windowed` remains `partial` with four synchronous families: legacy
selection-buffer callers, depth pick, depth cache, and WM window capture. The raw legacy-selection
request is now available, but edit-mesh click and box/lasso/circle gesture owners still need
bounded kick/poll continuations before that family can close.

Required M5 remains honestly red only at the absent
`build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary. Live C1/M5
acceptance remains separately deferred by the named blocker: no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). No adapter, device, browser profile, split
product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist, or
promise changed; dzn and Windows were not attempted and WSL was not restarted.
