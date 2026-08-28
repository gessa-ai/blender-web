<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-J cumulative input: initial web-window activation

## Finding

The post-navigation workspace failure was an input-order defect, not a redraw-episode gap. Browser
capture showed the expected DOM clicks, but Blender sometimes received a button press at a later
queued click's position. One representative sequence was DOM/GHOST move `288 -> 352`, followed by
a Layout press reported at `352`; later batched presses all collapsed to the last queued position.
That could enter a tooltip, rename, or other modal handler and make later pointer and keyboard input
appear frozen.

Two mechanisms combined:

1. `registerCanvasCallbacks()` sampled an already-focused shell canvas into
   `browser_focus_active_` but intentionally emitted no initial `GHOST_kEventWindowActivate`.
   Registration occurs before `createWindow()` admits the new window to `GHOST_WindowManager`, and
   no later focus callback arrives when the canvas was already focused. Blender therefore kept
   `wmWindow::active == 0` for the entire session.
2. Every inactive button-down takes `wm_window.cc`'s defensive refresh path and queries GHOST's
   global cursor. With several proxied events queued on the WM worker, that global position can
   already belong to a later click. `on_mouse_button()` also re-cached delayed button-event
   coordinates, making the global source less trustworthy.

Translating button `clientX/clientY` was tested and rejected: the whole worker-delayed
`EmscriptenMouseEvent` can reflect a later buffered event. It is not an independent source of the
current click.

## Fix

`createWindow()` now publishes the seeded initial focus through `ghost_web_bridge::on_focus()` only
after the window manager has admitted and activated the window. This delivers the missing GHOST
activation and makes Blender process subsequent queued cursor/button events in order.

Cursor position is now owned only by the ordered mouse-move stream. Button callbacks still update
modifier and physical-button state and publish button events, but cannot overwrite the cursor with
a delayed event struct.

The focus-domain source contract requires the initial post-admission activation. A new
`verify_button_cursor.py` mutation contract requires move-owned cursor publication and is wired into
the integrated WebGPU/GHOST smoke driver.

## Diagnostic correction

The original `0/8` workspace observation was amplified by the automation clicking the already
active Layout tab, waiting on that intentional no-op, and leaving Blender's “Active workspace…”
tooltip open. Each later slow test click could then dismiss a tooltip rather than switch a
workspace. The corrected diagnostic:

- measures only nine state-changing workspace transitions;
- moves into the canvas and presses Escape between measured tab clicks;
- permits fallback-adapter workspace construction to finish before issuing another click; and
- compares every DOM click x-coordinate with the corresponding Blender/GHOST press coordinate.

This is a test-method correction, not a product relaxation: all nine native workspace states are
required and any coordinate mismatch fails closed.

## Verification

- Fail-first initial-focus contract: `20260828T013104-2648361`.
- Final focus/button source contracts: `20260828T013118-2648443` and
  `20260828T013118-2648444`.
- Real proxy-to-worker IME focus and drag/release regressions: `20260828T013141-2648668` and
  `20260828T013141-2648669`.
- Locked CAPTURE relink: `20260828T013151-2649391`.
- Exact fallback product, 10 orbit + 10 Shift-pan + 10 zoom, nine workspace transitions, settled
  Frame Selected, and final orbit: `20260828T014029-2653939`; fail-closed analyzer:
  `20260828T015004-2661153` (self-check `20260828T015004-2661152`).
- Integrated WebGPU/GHOST smoke: `20260828T014411-2656583`; post-commit locked no-work relink:
  `20260828T015059-2661591`.

The final product stayed running through 2,760 WM ticks and 137 presentations. Workspace state was
`Modeling -> Sculpting -> UV Editing -> Texture Paint -> Shading -> Animation -> Rendering ->
Compositing -> Layout`; DOM and GHOST x-coordinates were byte-for-byte equal at
`[352,421,494,577,657,727,805,891,288]`. There were zero hard bind-group warnings, page errors, or
browser lifecycle errors. The three- and six-second settle hashes match, while the final orbit hash
differs.

Relinked CAPTURE identities:

- `blender_browser.js`: `763dba372ec3` (707,729 bytes)
- `blender_browser.wasm`: `9023e97150f7` (120,324,908 bytes)
- `blender_browser.wasm.orig`: `a87d0c5cc09b` (118,976,413 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `587cdca663c7` (13,294 bytes)

## Remaining boundary

This host uses a software fallback adapter and binds no pixel or hardware-input receipt. P0-J stays
pending hardware until the driver repeats the original Apple M4 Pro total-freeze sequence and the
trusted 30-navigation/workspace battery, confirms native actions and scene/text pixels remain live,
and keeps P0-D/E/F plus the broader P0-I artifact regression green. No APPLY/public bundle, profile,
receipt, tag, or launch claim is promoted by this candidate.

## Ordinary-input recovery hardening

The initial activation/cursor-order defect above was the direct cause of the reproduced workspace
misrouting, but the driver's separate recovery observation exposed a real resilience gap: after
the 180-tick asynchronous-draw recovery budget finished, accepted mouse, wheel, and keyboard input
did not publish a new retry generation. A first-use browser resource could therefore drop the frame
triggered by an otherwise correctly delivered interaction and leave a retained region stale until a
later resource-readiness callback or resize happened to re-arm recovery.

Commit `8f2e09b` routes accepted mouse move, supported button, nonzero wheel, and key events through
`GHOST_SystemWeb::requestInputRedrawRetry()`. The helper deliberately calls the existing
`request_redraw_retry()` generation rather than `request_redraw_episode()`: ordinary input does not
own a replacement drawable and must never enter the resize-only frame barrier. Multiple callbacks
before one WM poll collapse into one `readiness_published` decision. A request during an active
burst gets an immediate update but does not reset its hard ceiling; the first later input after a
completed burst starts one fresh bounded retry. Unsupported buttons and zero-delta wheel callbacks
publish nothing.

The new source contract failed first (`20260828T015608-2665325`) and passes with 9 mutation controls
(`20260828T015657-2665599`, `20260828T015717-2665740`). The native/Wasm recovery model is identical
across 68 cases and now includes three coalesced input publications inside an active budget
(`20260828T015815-2666657`). The exact fallback product passes the corrected cumulative battery—10
orbit, 10 pan, 10 zoom, nine native workspace transitions, matched DOM/GHOST button coordinates,
stable settle, pixel-changing final orbit, and zero hard warnings/page errors
(`20260828T020045-2669114`, `20260828T020305-2671122`). The modal extrude/move/rotate/scale rerun
also reaches every surface phase and passes its analyzer (`20260828T020411-2672491`,
`20260828T020441-2672925`). One immediately preceding Chromium process exited during that modal
probe with no page error (`20260828T020309-2671162`); the clean fresh-context rerun is recorded, not
silently substituted.

The adjacent resize regression was reconciled with semantic first-frame admission without relaxing
its bar: its source contract now binds both viewport-content and ordinary resize completeness, and
its live probe uses diagnostic-only 16 ms idle polling and counts the two resize barriers after the
settled boot barrier. The exact relink passes shrink and restore with two WM relayouts, episodes
1/2/3, two successful resize-only barriers, current contained plans, and zero rejection
(`20260828T021218-2678642`, `20260828T021233-2678727`). Hardware producer/consumer self-checks remain
42/17 and 2/13; neither binds hardware pixels (`20260828T020545-2673439`,
`20260828T020545-2673440`).

Relinked CAPTURE identities for the pending Apple candidate:

- `blender_browser.js`: `763dba372ec3` (707,729 bytes)
- `blender_browser.wasm`: `e444e925238d` (120,324,987 bytes)
- `blender_browser.wasm.orig`: `00aa3c159b63` (118,976,482 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `cfd620f63744` (13,294 bytes)

P0-J remains open. Closure still requires repeated trusted Apple runs of both original freeze
sequences plus the navigation/modal/resize batteries, intact scene and text pixels, and an empty
all-shader incomplete-bind-group census.

## Exact interaction hardware producer

Commit `f63dc77` turns the corrected cumulative diagnostic into an Apple-only evidence lane without
weakening its default SwiftShader control. Hardware mode pins Node 22.16.0, Playwright 1.61.1,
PNGJS 7.0.0, and Chromium 149.0.7827.55; prefers the spec-current
`GPUAdapterInfo.isFallbackAdapter`; rejects absent, fallback, unclassified, and software-token
adapters; hash-binds all five CAPTURE product files; and requires the local and served split
manifests to identify the requested `wasm.orig`. It creates the immutable evidence directory only
after those checks pass. The Linux negative control allocates no evidence.

The pixel contract no longer treats PNG byte size or Blender-native Cube presence as sufficient.
It records a same-run front-view/Frame-Selected reference, restores the exact native pose after the
10-orbit/10-pan/10-zoom plus 9-workspace battery and again after a final orbit, then compares the
actual pixels. VIEW_3D has a 1% hard changed-pixel ceiling; the viewport header, left toolbar,
Outliner `Collection`/`Camera` rows, and workspace labels have a 0.2% ceiling. A real post-stress
`G X 2 Enter` must move the native Cube from x=0 to x=2 and `Control+Z` must restore x=0. The
consumer also retains zero page/lifecycle errors and a backend-wide zero incomplete-bind-group
census.

The exact fallback product run is green (`20260828T024302-2697427`, consumer
`20260828T024532-2698952`): 1,423 WM ticks, 133 presents, 136 native input events, 9/9 workspace
transitions with identical DOM/GHOST x coordinates, successful move/undo, and zero hard warnings,
page errors, or lifecycle events. The post-stress VIEW_3D and all four detail regions are
byte-identical to the reference. After the final orbit, VIEW_3D and all detail regions are again
byte-identical; the only full-canvas delta is the legitimate Outliner selected-row focus highlight
(0.4131%, below the 1% whole-canvas ceiling and explicitly outside the stable text crop). Producer
and consumer mutation checks, syntax, and the existing typed-geometry source check are green
(`20260828T025005-2701124`, `20260828T025005-2701125`,
`20260828T025005-2701129`, `20260828T025005-2701137`).

This is a device-free control and an Apple-ready producer, not Apple evidence. P0-I/J remain open
until the driver runs `--hardware` against exact `wasm.orig` `00aa3c159b63`, obtains both clean
same-pose canaries with the transform/undo and all-shader census green, and retains the modal plus
P0-E resize regressions.
