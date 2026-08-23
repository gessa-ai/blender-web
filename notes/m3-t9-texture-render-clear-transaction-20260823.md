<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 texture render-clear transaction - 2026-08-23

## Outcome

Patch 0221 (`e4f860d`) preserves one command buffer for every layer of direct depth/stencil and
renderable-color texture clears while making the transaction fail closed. The shared command
helper now treats a boolean encoder callback result as an atomic abort: a failed encoder,
per-layer view or render pass, or finished command buffer stops before queue submission. A failure
after earlier layers were encoded therefore discards the local encoder instead of publishing a
partial clear. Existing void callbacks retain their prior copy-command behavior.

## Evidence

- The unchanged canonical source fails the exact two-branch transaction guard before evidence
  allocation (`20260823T035259-2319030`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared command transaction's four cases prove encoder failure stops before work, a boolean
  callback failure discards already encoded work before finish/submission, finished-buffer failure
  stops before submission, and success submits exactly once. Exact method-body checks bind both
  shipping clear branches, including their per-layer view/pass guards. Final output is 1,918 bytes
  at SHA-256 `59d7376aa84833ab4adc4633960b068fcc44e65252515ba643408561d306aa78`,
  with 25 shipping inputs at SHA-256
  `03cbe22c851088ca654ecf118f24734ee87d051f9e1ca0a1a841224d6f5f038b`
  (`20260823T040033-2324515`, `20260823T040355-2329363`). Ambient Node 22.22.1 is rejected
  before its dedicated output path is created (`20260823T040240-2327289`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,658,698-byte patch
  is SHA-256 `f41e773adbe2f18d58a3228c39a99f97956fd70df3ab618c0ca8d0b6d52f7270`, and the
  live/replay manifests are byte-identical at SHA-256
  `46e5660a3617ef50362ce651456aea01a9573e6efe7da4252f84c9f3d6d51f35`
  (`20260823T035920-2322923`, `20260823T040019-2324404`). Numbered patch 0221 is 12,859
  bytes at SHA-256 `feeb5d72b09a057bf31325969e519b24cb3c811a3556848f3958b1aef2fce03a`
  and applies from its captured preimage and reverse-applies cleanly from the live postimage.
- The real `blender_browser` recompiles `wgpu_texture.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T040103-2325644`, `20260823T040147-2326025`). OFF preflight binds the
  resulting 118,075,593-byte primary Wasm (`20260823T040240-2327279`).
- Final REUSE 6.2.0 is green for 2,171/2,171 files (`20260823T040556-2331541`). Required M3 remains red only
  for the absent strict candidate (`20260823T040300-2327972`); final container-backed regression
  restores M0 6/6 green while M1-M8 retain their existing strict-receipt, split-product, browser,
  run-label, hardware, and independent M8 performance boundaries (`20260823T040339-2328489`).

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, accepted adapter, device,
render pass, submission, pixel, browser receipt, profile, or split product. Live proof remains
blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)**. No result promotion, dependency decision, deferral, tolerance, golden, blacklist, or
milestone promise changed.
