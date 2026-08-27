<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E ordered window presentation candidate — 2026-08-27

## Outcome

Patch 0288 queues the browser's persistent-backbuffer surface blit behind every draw/write already
reserved in the WebGPU backend FIFO. It is a hardware-pending candidate for the Apple resize pixel
failure, not closure: P0-E still requires 10/10 zero-input shrinks with the full grid, Cube, and
gizmo visible.

## Trace correction and root cause

The round-4 Apple trace was internally coherent. Its `overlay_background` target of 900x547 is the
live Blender `VIEW_3D` region after a 1280x720 -> 1100x640 window shrink, not a stale full-window
extent. A temporary read-only product probe printed Blender's actual screen/region layout:

- 1280x720 window: `VIEW_3D`/`WINDOW` = 1048x621.
- 1100x640 window after WM relayout: `VIEW_3D`/`WINDOW` = 900x547.
- restore to 1280x720: the region returns to 1048x621.

The same trace identifies `overlay_background` as an offscreen target (`window_target=0`) while
`OCIO_Display` and the latest direct draw target the 1100x640 window. Replacing 900x547 with
1100x640 would therefore corrupt a valid region pass.

The stronger ordering defect is at submission rather than encoding. Blender's WebGPU helpers
encode commands immediately, but their `queue.Submit` calls remain in `OrderedQueueScheduler`
until asynchronous browser error scopes settle. `GHOST_ContextWGPUWeb::swapBufferRelease()` used
to bypass that scheduler and synchronously submit its backbuffer-to-surface blit. It could therefore
present an intermediate backbuffer before the frame's content submissions reached the queue. A
later input creates another present after the pending content settles, matching the driver's
instant recovery under orbit.

The browser GPU context now installs a queue-enqueue callback on its GHOST context. At
`swapBufferRelease()`, the blit enters the same FIFO after all prior frame operations. Once it
reaches the head, surface acquire, encode, and submit remain synchronous within that callback's
browser turn, preserving the already-verified swapchain-texture lifetime fix. Teardown clears the
only callback capturing the backend scheduler. The standalone GHOST harness installs no callback
and keeps its immediate presentation path.

## Evidence

- Layout/trace falsification: `ledger/buildlogs/20260827T070424-1741637.log`.
- Fail-first source rejection: `ledger/buildlogs/20260827T072042-1752024.log`.
- Four-source, 14-check/14-mutation binding: `ledger/buildlogs/20260827T073232-1766593.log`.
- Native/Wasm integrated queue ordering, cancellation, and retry:
  `ledger/buildlogs/20260827T073014-1763223.log`.
- Canonical 20,258-entry replay: `ledger/buildlogs/20260827T072821-1760666.log`.
- Locked CAPTURE relink at implementation commit `2c887da`:
  `ledger/buildlogs/20260827T073632-1770105.log`; exact no-work replay:
  `ledger/buildlogs/20260827T073743-1770896.log`.
- CAPTURE inventory and producer self-check: `ledger/buildlogs/20260827T073029-1764707.log` and
  `ledger/buildlogs/20260827T073036-1764763.log`.
- Exact fallback product shrink/restore: ticks 270/595/903, presents 9/23/36, episodes 0/1/2,
  redraw presents 14/13, advancing/current/contained draw plans, and zero WebGPU rejection/loss at
  `ledger/buildlogs/20260827T073049-1764905.log`. This is diagnostic, not pixel evidence.

Relinked CAPTURE identities before the documentation commit:

| file | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,565 | `e5994b59f5c53c4131e4ed4cf8b8abd6b6fffc42c877007ce64141f440c71ac9` |
| `blender_browser.wasm` | 120,508,666 | `34a5df7c85e788417f20f9c8f17d9dd37dad765880e4a200e2c988e972094127` |
| `blender_browser.wasm.orig` | 119,155,301 | `e3d284c7da0e11f09beada6c9a4b788044b0c8f9715dcee42bc80839d70c8238` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `3f99713e406f9466ad839df015c4ee90b86432e7862df461076c604347d0ada8` |

No APPLY/public bundle, profile, hardware receipt, result, tolerance, golden, blacklist, deferral,
tag, or launch claim was promoted. The relink invalidates earlier hash-bound profiles; the driver
must run the exact `p0e_10x.mjs` Apple acceptance check against this `.wasm.orig` generation.
