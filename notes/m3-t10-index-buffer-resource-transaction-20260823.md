<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 index-buffer resource transaction - 2026-08-23

## Outcome

Patch 0227 (`fb38385`) resolves the required index-buffer handle before pipeline or command work
in direct batch, indirect batch, and immediate draws. Failed indexed uploads now reject the draw
instead of omitting `DrawIndexed` or reinterpreting an indexed indirect command as non-indexed;
triangle-fan paths bind the same resolved transient handle.

## Evidence

- The unchanged shipping source fails before compilation or evidence allocation at the absent
  resolver (`20260823T055330-2434100`).
- Final root and descendant-CWD native/wasm32 runs pass 22 byte-identical integrated contracts at
  2,274 bytes, SHA-256 `9c2ce0713df1576aa277884b3eca996a3c4a9e6b1cad81d39bf83132eeb37ec7`.
  The 25 shipping inputs are SHA-256
  `8ffba8416f131e63c6ff1b5e961a6fc10d704397e2ca4ee79faf6b67e3144ab9`
  (`20260823T055805-2438666`, `20260823T060024-2441312`). Ambient Node 25.1.0 is
  rejected before its requested evidence directory exists (`20260823T060039-2442097`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,663,734-byte
  patch is SHA-256 `a17d61098b3308d80d339e2b1b1df0acfdea845acf931f1c3e5b927aebf3b24c`,
  and both manifests are SHA-256
  `922552d1417285085011c6be960eeb14f699814f5df8dd302f0d26ca5f08059c`
  (`20260823T055627-2436521`). Canonical-only replay is green
  (`20260823T055957-2440290`). Numbered patch 0227 is 10,022 bytes at SHA-256
  `504c61aa2ffb9bfb4ca69ad9e5d11b1f896c5b8545a89fbe404dcd17ac73c32e`;
  isolated forward and live reverse checks are green (`20260823T060527-2447635`).
- The real `blender_browser` recompiles both draw implementations and relinks, then reaches exact
  locked-Ninja no-work (`20260823T060051-2442695`, `20260823T060140-2443492`). OFF preflight
  binds the 118,079,461-byte primary Wasm at SHA-256
  `4815f7607b08bc5f3485dd742a42c9e5b1117262f76edda740464a95c33fbc55`
  (`20260823T060157-2443659`).
- Final REUSE 6.2.0 is green for all 2,183 files (`20260823T060750-2448462`).
- Required M3 remains red only for the absent fresh strict candidate. Container-backed regression
  at `2026-08-23T06:04:11Z` restores M0 6/6 green while M1-M8 retain their existing strict-receipt,
  split-product, browser, run-label, hardware, and independent M8 performance boundaries.

## Boundary

This is device-free index-resource proof. It creates no WebGPU instance, accepted adapter, device,
index buffer, encoder, pass, draw, submission, pixel, browser receipt, profile, or split product.
Live proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa
dzn rejected by Dawn)**. No result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or milestone promise changed.
