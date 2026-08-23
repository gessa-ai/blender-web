<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU framebuffer load-action transaction contract — 2026-08-23

## Outcome

Commit `4a1821b` closes audit R6's ordinary framebuffer load-action finding. Color and depth
`CLEAR` actions are now provisional reservations shared by every command targeting a framebuffer.
The matching clear is consumed only after the complete draw command, including later attachment
views, bind groups, command encoding, and submission validation, succeeds. A rejected command
releases its reservation for retry, same-epoch followers observe `LOAD`, and generation matching
prevents a stale callback from consuming a newer frontend load/store bind.

## Implementation

- `FramebufferLoadActionTracker` owns the logical clear mask, per-attachment generations, and
  pending reservations independently of framebuffer lifetime. Descriptor assembly stages color
  and depth actions without mutating frontend state.
- Direct, indirect, multi-viewport, and immediate draw paths carry one transaction through their
  checked submission callback. Successful completion commits only matching generations; every
  late failure and abandoned transaction releases its reservations.
- The six-case device-free contract covers a late later-attachment-view failure, two-attachment
  retry, same-epoch `LOAD`, late bind failure, clean commit, and replacement-generation isolation.
  Source-order guards bind the contract to all shipping command paths.

## Evidence

- The unchanged source fails the new source-bound contract before evidence allocation because it
  has no load-action tracker (`20260823T143653-2921838`). Numbered patch 0239 is SHA-256
  `b8c02b9dfa29` and passes isolated reverse/forward exact-byte round trip
  (`20260823T145644-2956257`).
- Final root and descendant-CWD native/wasm32 runs pass 30 byte-identical contracts at 3,444 bytes,
  SHA-256 `5855de690c30`, with exact shipping inputs SHA-256 `708d6d172fc8`
  (`20260823T145606-2953629`, `20260823T145623-2955243`). The wrong Node 22.22.1 control fails
  before allocating evidence (`20260823T145025-2947348`).
- The source freezer retains 257 paths and 20,258 entries. Its 1,732,845-byte canonical patch is
  SHA-256 `dff11e4bc854`; live and replay manifests are byte-identical at 3,477,334 bytes, SHA-256
  `88055b9a4671` (`20260823T145415-2952298`). Canonical-only reconstruction independently passes
  against the exact postimage (`20260823T144908-2944770`).
- The real windowed `blender_browser` rebuild and locked no-work verification are green
  (`20260823T145119-2949261`, `20260823T145202-2949644`). OFF product preflight is green with
  167,143,248 data bytes and primary Wasm SHA-256 `6d631fa709f6`
  (`20260823T145238-2950030`). REUSE 6.2.0 is green for all 2,215 tracked files
  (`20260823T150057-2959412`).
- Required M3 remains red only for the absent fresh strict candidate. Container-backed regression
  at `2026-08-23T14:53:41Z` keeps M0 6/6 green while M1-M8 retain their existing strict-receipt,
  split-product, browser, run-label, hardware, and release boundaries.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted adapter, device,
pass, draw, pixel, browser receipt, result promotion, or milestone promise. Live hardware proof
remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn). This iteration did not retry dzn or the staged post-reboot
Windows path.
