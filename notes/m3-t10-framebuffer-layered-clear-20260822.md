<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU framebuffer layered clear - 2026-08-22

## Outcome

Patch 0182 makes framebuffer clears exhaust each all-layer color or depth attachment independently.
A shorter sibling is omitted from later one-layer WebGPU passes instead of aborting the clear and
leaving the longer attachment's remaining layers stale. Invalid selections still fail closed.

## Diagnosis and implementation

`WGPUFrameBuffer::submit_clear` previously chose the maximum attachment layer count, then required
every attachment view to exist on every pass. With two all-layer color attachments of depth two and
one, pass zero cleared both but pass one returned on the missing one-layer sibling view before it
submitted the two-layer attachment's final clear.

The pinned native 5.2.0 oracle clears both layers of the longer attachment and the only layer of its
sibling. WebGPU render attachments remain one layer per pass, so the shared selector at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:298` classifies each attachment as active,
inactive, or invalid without changing its output on a non-active decision. The shipping color and
depth paths consume that classification at
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:235` and `:271`: exhausted all-layer
attachments are omitted, while invalid layer counts or fixed selections abort before the pass is
submitted. Existing fixed-layer participation is unchanged.

## Evidence

- The unchanged canonical source rejects the new selector/wiring contract before build or evidence
  allocation (`20260822T121911-1424874`).
- The pinned Linux native oracle clears the exact `{2,1}` all-layer attachment pair to blue and
  reads back both layers plus the sibling layer (`20260822T121534-1422618`).
- The exact isolated postimage passes the locked native/wasm32 graph
  (`20260822T123507-1440259`). Final root and descendant-CWD canonical runs pass 18 contracts,
  including 11 layered-clear decisions (6 active, 1 inactive, 4 invalid), with byte-identical
  1,702-byte evidence at SHA-256
  `6f7a53e96b638acc6f95fdeb595fc693106527c1761b194b571c541b497cc5d5` and source SHA-256
  `1bdf46f60aec7fd8d4e0b1de237ed085a9057f7e49b27ec535ba0ea83f38f0ca`
  (`20260822T123906-1445494`, `20260822T123526-1441061`).
- A wrong Dawn identity rejects before creating its requested evidence directory
  (`20260822T123437-1439966`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,588,016 bytes at
  SHA-256 `c5612129214143aeaef19b652001f4d926b84dfbc9f79599d0391e5d4812f649`;
  live/replay manifests are byte-identical at SHA-256
  `831ad76e490ac58ee47689e97a72275c53eed6ab37af2416d8ba80ae820ac117`
  (`20260822T123158-1436886`, `20260822T124505-1449677`).
- `blender_browser` recompiles the affected framebuffer and common-header dependents, links, and
  then reports exact locked-Ninja no-work (`20260822T123338-1438615`,
  `20260822T123420-1439823`). The OFF-mode product preflight is green
  (`20260822T123430-1439938`).
- REUSE 6.2.0 reports copyright and license information for all 2,075 files
  (`20260822T123652-1442999`).
- Required M3 remains red for the absent fresh strict candidate
  (`20260822T123714-1443148`). Container-backed regression keeps M0 at 6/6 green while M1-M8
  retain their existing strict-receipt, APPLY/product, browser, run-label, and hardware
  boundaries (`20260822T123723-1443256`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, framebuffer, clear command,
pixel, browser receipt, or result promotion. Live layered-clear proof remains owned by
`M3-LINUX-REPLAY`, still blocked by the named s7 software-adapter condition.
