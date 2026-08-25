<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 depth-cache readback primitive — 2026-08-25

## Outcome

Full-viewport View3D depth-cache creation now has an owned asynchronous readback primitive.
Patch 0264 adds `ViewportDepthCacheSession`, which retains the producing region identity and
dimensions, `viewinv` and `winmat`, and one exact `GPU_texture_read_async` ticket. Settlement
validates the byte count before allocating or transferring a `ViewDepths`; the transferred cache
keeps Blender's exact `[0, 1]` depth range. Cancellation and destruction retire a pending ticket.

The native synchronous `view3d_depths_create` entry point is deliberately unchanged. This patch is
an enabler for bounded paint, annotation, placement, and particle-edit continuations, not a caller
conversion or live WebGPU receipt. Depth cache therefore remains a partial synchronous family, and
WM window capture remains the other open family.

## Behavior and source evidence

- The 0263 predecessor rejects the new API before evidence allocation
  (`20260824T233851-586293`). Final focused Linux receipt `20260825T000145-605723` passes six
  contracts and 14 cases byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 386-byte
  output is `sha256:cd97664f57af2c085e9ed4281f12ba755fc9bbb328a15126e8070d8b1587982d`;
  the five-source postimage is
  `sha256:b453112f7cb43a550d2f9e8cbda606975812c940412b846a3cd6b00940c7da82`.
- The source checker rejects nine signature, ownership, geometry, validation, transfer, and
  cancellation mutations. Numbered patch 0264 reverses and forwards its exact postimages at
  `sha256:0d2a6f9cc54a062a949a69ba441d68cd9ae76af2c997de55242d0e9159a93c5d`.
- The reconstructed `view3d_draw.cc` compiles with the exact native and windowed-Wasm product graph
  commands. Unsigned-short cache dimensions, signed indexing bounds, `size_t` allocation
  arithmetic, exact byte count, and producing-view drift are checked before ownership transfer.
- Aggregate receipt `20260824T235745-601686` passes the canonical owned-readback contract on native
  and wasm32 at 627 bytes,
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`.
  Its 37 mutation controls fail closed, report zero evidence allocation on rejection, and retain
  exactly `depth_cache` plus `window_capture` as synchronous families.

## Integration evidence

- Clean-pin freezer receipt `20260824T235246-597600` composes 285 paths and reproduces 20,258
  manifest entries byte-for-byte. `PREVIEW_SNAPSHOT.patch` is 2,083,818 bytes at
  `sha256:366bb8d824079789aaba8de81d226f3cd8ce26a14f3fbae1a37fe0fc8bd2b5d6`; both manifests are
  `sha256:d82bcdcdd0a60f330000d6fd77ff8439a680dbef0db5a42553f38803d9fb1266`.
- The immutable-upstream windowed graph was reconciled once and then locked no-work
  (`20260824T235910-602614`/`20260825T000109-605443`). OFF preflight
  `20260825T000723-611824` binds the existing 657,928-byte JavaScript, 118,955,345-byte Wasm, and
  167,143,248-byte data artifacts.
- Repository-wide REUSE 6.2.0 is GREEN for 2,422/2,422 files
  (`20260825T000343-607592`). Required M5 remains honestly RED only at the absent
  `blender_browser.deferred.wasm` boundary (`20260825T000418-607865`). Container-backed regression
  `20260825T000429-608785` restores M0 6/6 GREEN while M1–M8 retain their existing strict-receipt,
  browser, split-product, hardware, run-label, and release boundaries.

Live C1/M5 acceptance remains separately deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). No adapter, browser profile,
split product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist,
or milestone promise changed. dzn and Windows were not attempted, and WSL was not restarted.
