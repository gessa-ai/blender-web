<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU cache publication transactions — 2026-08-22

## Outcome

Patch 0204 keeps every remaining sampler and render-pipeline cache entry absent until its
fallible WebGPU handle creation succeeds. A transient null result can therefore fail the current
operation without permanently poisoning that key; the next sampler lookup, ordinary draw,
immediate draw, color/depth blit, or depth upload can create and publish a valid handle.

## Diagnosis and implementation

The framebuffer audit had already established this failure class for its two scissored-clear
pipeline caches. A complete cache-publication census found the same create-then-publish order at
five still-live sites:

- `WGPUContext::get_sampler()`;
- the color-blit, depth-blit, and depth-upload pipeline maps in `WGPUContext`; and
- the process-wide `WGPUPipelinePool` used by batch and immediate draws.

Each path previously inserted its candidate before or independently of the null check. For the
pipeline pool and sampler cache, a later lookup returned the retained null handle without
attempting creation again. The context blit/upload maps had the same permanent retry loss.

`cache_handle_if_valid()` in
`upstream/source/blender/gpu/webgpu/wgpu_common.hh` is the single publication transaction. It
rejects null without touching the cache and copies a valid handle into the requested key while
preserving the caller's handle. All five sites now call that helper immediately after creation;
their existing callers already stop the current operation on a null return.

## Verification

- The unchanged source fails before evidence allocation because the atomic helper is absent
  (`20260822T221918-1989190`).
- Final native and wasm32 runs execute the exact fail-first/retry transaction byte-identically:
  the failed candidate leaves an existing entry untouched and the key absent, then a valid retry
  publishes exactly once. The complete 16-contract output is 1,496 bytes, SHA-256
  `7f196af57ffe7021eeea60980818a2f40fa63bd3ffc9119e6960720bed6a814c`; exact source inputs are
  SHA-256 `599e1063a15acd1d8379ba3b3616138a5c433cb0d56fb4da4d9a7f1c4efe4028`
  (`20260822T222233-1993605`). Source guards bind the helper to all five production sites and
  reject every former direct publication expression.
- The canonical freezer regenerates and independently replays a 1,652,050-byte patch spanning
  257 paths and 20,258 entries. Patch SHA-256 is
  `05eb9e8a5a35aa97a40850aa4ab08c7673368f8b90335c01b74a352ce92a53e6`; both manifests are
  SHA-256 `42ee0e3a279d49196efa06ff7c31f037e19486f820f6bc3185487ac124cf9d12`
  (`20260822T222135-1992121`). Patch 0204 also reverse-applies cleanly to the live postimage.
- The real `blender_browser` rebuild and exact locked no-work check are green
  (`20260822T222300-1994841`, `20260822T222342-1995310`). OFF preflight binds the resulting
  118,072,015-byte primary Wasm (`20260822T222346-1995384`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T222404-1995669`). Container-backed regression retains M0 green and the existing
  M1-M8 strict-receipt/product/browser/run-label/hardware boundaries
  (`20260822T222416-1995756`).

## Boundary

No WebGPU adapter, device, sampler, pipeline, pass, draw, pixel, or browser receipt is claimed.
Live retry and pixel proof remain owned by `M3-LINUX-REPLAY` and s7-blocked because ornith-lab's
only Vulkan adapter is software. No result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or milestone promise changed.
