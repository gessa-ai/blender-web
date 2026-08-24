<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 screenshot async readback

## Outcome

Commit `55afed3` and numbered patch 0250 retire the stock screen-screenshot operator from the
synchronous browser-readback inventory. Screenshot invocation now starts one owned WM offscreen
capture before opening the file selector, so its captured window remains the pre-selector frame.
If direct execution or an early file-selector confirmation finds the exact request pending, the
operator retains ownership and resumes through a 10 ms timer bounded at 240 ticks. Failure,
timeout, and cancellation retire the GPU request before releasing its offscreen.

Native backends preserve immediate completion through the existing framebuffer read. The browser
path adds host-read usage, starts `GPU_texture_read_async`, validates the exact RGBA8 byte count,
and flips physical top-origin rows only after consuming the terminal owned result. The offscreen is
retained while pending and released once `GPUReadback::status()` has snapshotted terminal bytes.

The device-free native and wasm32 contract passes six ownership/continuation contracts and 12
cases with byte-identical 294-byte output at
`7a617b0c7f2bd5337a2b48132424034bf551b286ac63cb757737e93a585acca1`. Its five-file source receipt
is `PASS` at `782381c0cff069dfd319959aaf7c3351354bc9cdddd5faa17a1308a7167217d9`; eight independent source
mutations fail closed. The broader owned-readback contract remains byte-identical and now names
five synchronous families.

## Evidence

- Unchanged-source rejection before evidence allocation:
  `ledger/buildlogs/20260824T143004-140888.log`.
- Final native/wasm32 contract and source receipt:
  `ledger/buildlogs/20260824T143611-146139.log`.
- Broader owned-readback contract and five-family census:
  `ledger/buildlogs/20260824T143622-146564.log`.
- Canonical clean-pin freeze/replay at patch
  `237769d920e753b74ad346781ec342d80c9d3bc51ea6011939d5ce977c6b2bcb` and byte-identical
  20,258-entry manifest
  `56433c956cf708903bc04b17221056f555a6313dae607964dd64907309b55ef7`:
  `ledger/buildlogs/20260824T143504-144599.log`. Numbered patch 0250 also passed an isolated
  three-file reverse/forward byte-exact round trip.
- Native Release `bf_windowmanager` + `bf_editor_screen` rebuild/no-work:
  `ledger/buildlogs/20260824T144301-153467.log` and
  `ledger/buildlogs/20260824T144414-154885.log`.
- Final optimized `blender_browser` rebuild/no-work:
  `ledger/buildlogs/20260824T144418-154954.log` and
  `ledger/buildlogs/20260824T144735-159714.log`.
- OFF-mode product preflight binds JS 657,928 bytes at
  `d486fef13756d2c0fee6d0f94cd15b8baf7dbbaf3794fd275bcf9339fc3d1c7e`, Wasm 118,912,155
  bytes at `fd73d2ba5b529513637efb124de7b33ea88c30f43f71443fbc0c029789f0d2a2`, and data
  167,143,248 bytes at `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`:
  `ledger/buildlogs/20260824T144735-159715.log`.
- Final REUSE 6.2.0 covers 2,318/2,318 current files including this record:
  `ledger/buildlogs/20260824T145246-164407.log`.
- Required M5 remains honestly red only at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T144929-161435.log`.
- Pinned-container regression restores M0 6/6 green while M1-M8 retain their existing strict
  receipt, browser, split-product, run-label, and release boundaries:
  `ledger/buildlogs/20260824T144949-161670.log`.

## Remaining boundary

Five synchronous caller families remain under `gpu-sync-readback-windowed`: legacy selection
buffer, depth pick, depth cache, WM window capture, and WM window colour sampling. Patch 0250 does
not claim to convert any of them.

This work creates no WebGPU instance, adapter, device, browser profile, split product, or live M5
receipt. Live C1 and aggregate M5 acceptance remain separately deferred by the named blocker
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn,
Windows interop, or WSL restart path was attempted.
