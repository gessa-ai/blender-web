<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize completed-frame present barrier — 2026-08-27

## Outcome

Commit `86d2ef6` and patch 0290 produce the first post-P0-H ordering candidate without moving the
actual browser surface swap out of GHOST. During a coherent resize episode, the WebGPU backend
appends a tail entry to its existing `OrderedQueueScheduler`. GHOST suppresses interim surface
copies until that entry proves every earlier scoped draw/write submission has drained, then admits
one ordinary `WindowUpdate` and calls `presentBackbuffer()` synchronously inside
`swapBufferRelease()`. Completing that same-turn submit releases later queue work and retires the
synthetic resize episode.

This differs from rejected patch 0288: 0288 deferred surface acquire/blit/submit into a later queue
callback and its generation hard-aborted on 10/10 Apple boots. Patch 0290 delays only permission to
present; surface acquire, encoding, queue submit, and the WM return value remain in the synchronous
GHOST swap call.

## Evidence

- The fail-first/native/Wasm recovery model now covers 44 cases, including scheduled, ready,
  single-update, synchronous-completion, superseded, canceled, and retryable-failure states.
  The seven-source contract rejects 44 mutations and the resize trace contract rejects 31.
- The source contract also binds the upstream window call graph on which the barrier depends:
  `wm_draw_window()` finishes all offscreen/onscreen encoding, calls the per-context
  `GPU_context_end_frame()`, and only then does `wm_draw_update()` call GHOST's synchronous
  `wm_window_swap_buffer_release()`. Three new mutations prove that a missing/misordered context
  tail or a pre-draw swap cannot escape. Fail-first/final evidence is
  `ledger/buildlogs/20260827T121845-2000991.log` and
  `ledger/buildlogs/20260827T121909-2001772.log`.
- Canonical pin replay is exact at 20,258 entries; the generated patch is 2,362,507 bytes at
  SHA-256 `ac4ccc43a0ef7b71858be62a3c5185b92d6e486380f978cece534ef1efc86e6f`.
- The integrated native/Wasm GPU suite is green at
  `ledger/buildlogs/20260827T112348-1954686.log`.
- Commit `0161808` extends that integration through both transient rejection boundaries. A failed
  prior-frame submission cancels the waiting resize barrier and drains work from the next epoch; a
  failed synchronous surface present releases the barrier entry and leaves the same resize episode
  retryable. All 15 success/rejection/retry cases pass byte-identically on native and wasm32 at
  `ledger/buildlogs/20260827T130130-2040448.log`. The focused source contract and pinned Apple
  producer self-check remain green at `ledger/buildlogs/20260827T130230-2042403.log` and
  `ledger/buildlogs/20260827T130230-2042407.log`; REUSE 6.2.0 is green at
  `ledger/buildlogs/20260827T130524-2045728.log`. This test-only change does not alter or relink the
  pending CAPTURE generation.
- The exact fallback-browser product boots, shrinks 1280x720 to 1100x640, and restores with ticks
  `246/353/460`, presents `16/17/18`, coherent episodes `0/1/2`, exactly one barrier present per
  resized extent, two complete/current/contained/VIEW_3D-bound trace rows, and zero scissor,
  encode, submit, transaction, or device-loss rejection:
  `ledger/buildlogs/20260827T112204-1953387.log`.
- Ten additional fresh-browser/fresh-X-server repetitions of that exact shrink/restore diagnostic
  all pass. Every run reports episodes `0/1/2`, exactly one barrier present at each resized extent,
  two complete/current/contained/VIEW_3D-bound plans, and zero rejection or device loss:
  `ledger/buildlogs/20260827T113859-1968370.log`. This is lifecycle stress on SwiftShader, not the
  conformant-hardware semantic-pixel acceptance run. Post-record REUSE 6.2.0 remains green at
  `ledger/buildlogs/20260827T114413-1974446.log`.
- The portable Apple acceptance producer remains fail closed at ten attempts and passes its
  31-positive/17-negative self-check; the profile producer remains 21-positive/23-negative:
  `ledger/buildlogs/20260827T112428-1956857.log` and
  `ledger/buildlogs/20260827T112428-1956858.log`.
- Post-audit, the resize trace and hardware producer self-checks remain green, the integrated
  native/Wasm GPU suite remains green, and REUSE 6.2.0 remains green:
  `ledger/buildlogs/20260827T122001-2002051.log`,
  `ledger/buildlogs/20260827T122001-2002052.log`,
  `ledger/buildlogs/20260827T122007-2002115.log`, and
  `ledger/buildlogs/20260827T122038-2003603.log`.
- Locked `blender_browser` remains a true no-op at
  `ledger/buildlogs/20260827T122212-2005765.log`; all five CAPTURE hashes below are unchanged.
  Direct M4 remains RED only at the unsupported hardware binding
  (`ledger/buildlogs/20260827T122101-2004365.log`), while authoritative pinned-container
  regression restores M0 6/6 and preserves every later named boundary
  (`ledger/buildlogs/20260827T122142-2004888.log`).
- The current original contains 136,771 defined functions; the deferral registry and generated
  public dashboard bind the new generation and explicitly retain 14,628,429 bytes only as a
  preceding-generation planning fixture: `ledger/buildlogs/20260827T112952-1961349.log` and
  `ledger/buildlogs/20260827T113156-1962707.log`.
- Locked Ninja is a committed-state no-op at
  `ledger/buildlogs/20260827T112723-1959693.log`. REUSE 6.2.0 covers 2,736/2,736 files at
  `ledger/buildlogs/20260827T112528-1958288.log`.

## Relinked CAPTURE generation

- `blender_browser.js`: 707,565 bytes,
  `5b6ed02286fda34d4483734d23e347f3439dad985150463faad82c5f449d5214`
- `blender_browser.wasm`: 120,506,081 bytes,
  `a8d75b880e2c3ddc6916d03a1ba3a5fd4c10eda9264a6ddb807d2238cb4cbf68`
- `blender_browser.wasm.orig`: 119,152,777 bytes,
  `2f45a8ed62ebeee3a9a80587ceca7e6918cb5c79c59f5a8fcd8219bb4934ffc6`
- `blender_browser.data`: 168,637,598 bytes,
  `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`
- `blender_browser.split-build.json`: 13,251 bytes,
  `4f0cbcbc21bb0a5cfb491860e8aa216188f3d263d3b54c7f4b259d6272c8d607`

## Boundary

The software adapter proves boot, queue progress, rejection handling, exact resize ordering, and
contract coherence; it binds no M4 pixel receipt. P0-E stays open until the driver-operated Apple
M4 Pro producer reports `BW_P0E_HARDWARE_RESIZE_PASS attempts=10/10` for this exact `.wasm.orig`
generation, with full idle grid, Cube, and gizmo pixels after every shrink. No APPLY build, public
bundle, profile promotion, tag, receipt, result, or launch claim is authorized by this candidate.
