<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E window resize recovery — 2026-08-26

## Outcome

Patch 0282 keeps the window default framebuffers coherent with the persistent WebGPU backbuffer
after a browser resize. The relinked shipping product now shrinks from 1280x720 to 1100x640 and
restores to 1280x720 with continued WM ticks and uncapped presentations, and with zero scissor,
encoding, submission, transaction, or device-loss rejection on the local fallback adapter.

This is implemented, not closed: software pixels bind no M4 receipt. The driver-operated Apple M4
Pro must still verify that semantic Blender pixels survive shrink, grow, and restoration. The
production entry point tested here is `platform_web/shell/windowed.html`, which is also the `/`
default served by `scripts/serve-web.sh`.

## Root cause

The original event-ordering hypothesis was false. A Python timer in the real product showed
`GHOST_kEventWindowSize` reaching `ghost_event_proc`, `bpy.context.window` changing, and Blender's
areas relayouting to the new geometry. The first post-resize sample briefly exposed the expected
old layout, then the next sample carried the new layout.

`WGPUContext::sync_backbuffer()` instead reused one `WGPUTexture` wrapper and called
`adopt_external()` when GHOST recreated the persistent offscreen texture. The wrapper's handle and
dimensions changed, but both default framebuffers still held the same pointer.
`FrameBuffer::attachment_set()` intentionally returns early for that identical pointer, leaving
`dirty_attachments_` false and `WGPUFrameBuffer::width_/height_` at 1280x720. Scissor planning used
that stale height while Dawn had a 1100x640 render attachment, producing the observed
`y=105 + height=594 > 640` rejection. Restoring the old extent stopped the rejection storm locally;
there was no queue submission, present transaction, or device-loss poison in this run.

Patch 0282 mirrors the established OpenGL window-context contract: immediately after external
texture adoption, publish the live width and height to both `back_left` and `front_left` through
`FrameBuffer::size_set()` on every activation.

## Evidence

- Fail-first source contract: `20260826T042644-314576`; fail-first live product:
  `20260826T042522-313703` (`64` invalid scissors and `64` rejected encodes).
- Locked shipping relink: `20260826T042718-314940`. Final live product:
  `20260826T042808-316107` (`resize=3`, `wm=2`, ticks `118/211/305`, uncapped presentations
  `2/6/10`, zero rejection/loss counters).
- Source/mutation contract and isolated reverse/forward patch identity:
  `20260826T043012-318304` and `20260826T043028-318482`.
- Canonical freeze/replay: `20260826T042907-316827` and `20260826T043012-318299`;
  20,258 entries reproduce byte-for-byte, canonical patch SHA-256
  `1db1b65e1fe3ad8224d99105d5de38031369f4fb78dac340a30967606bd13a6a`.
- REUSE: `20260826T043208-319397`. Required M4 remains honestly RED for its absent current hardware
  binding (`20260826T043059-318725`); full regression retains the existing split-product, receipt,
  and tier boundaries (`20260826T043107-318879`).

Implementation commit: `99edad1`.
