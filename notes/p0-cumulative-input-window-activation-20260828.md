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

## Exact original-freeze replay and live recovery evidence

Commit `c8ef725` upgrades the producer to schema v2 and puts the driver's tighter isolation before
the cumulative battery: Numpad 1/3/7/0/4, Select All, Deselect All, MMB orbit, trusted Cube click,
`G X 2 Enter`, undo, and a second MMB orbit. View records use the settled native state paired with
their screenshots; the intermediate `PERSP` state emitted while entering camera view cannot be
misattributed to the following Numpad4 no-op. Both orbits require changed native view rotation,
changed pixels, and an increased production redraw-retry generation within 12 seconds.

`GHOST_ContextWGPUWeb.cc` now exposes that retry generation read-only as
`_bw_redraw_retry_count`. It is distinct from resize's drawable episode, so an interaction receipt
cannot pass merely because source contains the callback or because a resize happened earlier. The
source mutation contract binds the export back to `ghost_web::redraw_retry_generation()`.

The exact SwiftShader control found and removed two test-only ambiguities without weakening Apple:

- a failed software GPU pick leaves `VIEW3D_OT_select` asynchronous and can consume an immediate
  fallback key; the diagnostic cancels that pick before using Select All as a liveness check;
- Select All legitimately selects Camera, Cube, and Light, so a real Outliner click restores Cube
  alone before Frame Selected establishes the visual reference. DOM top-left `(1150,106)` and
  GHOST bottom-left `(1150,613)` coordinates must both match. Hardware may take neither fallback:
  its trusted viewport click must select exactly Cube.

The final unchanged fallback product run and consumer are green
(`20260828T043125-2767382`, `20260828T043422-2768934`): 41 screenshots, 88 native-state samples,
1,800 WM ticks, 171 presents, retry generation 2,273, 9/9 workspace transitions, two successful
move/undo canaries, two byte-identical restored-pose comparisons, and zero hard completeness
warnings, page errors, or lifecycle errors. The isolated orbits repainted after 484 ms and 74 ms
while their retry generations advanced `576 -> 587` and `856 -> 867`.

Source/analyzer mutation checks and syntax are green (`20260828T043121-2767317`,
`20260828T042629-2764067`, `20260828T043121-2767316`). The integrated native/Wasm pipeline and
GHOST suite is green at identical 5,751-byte output (`20260828T043640-2771241`); that run also
corrects the stale resize consumer vocabulary from absolute counters to the post-boot delta
variables introduced with `8f2e09b` (`20260828T043636-2771192`). REUSE 6.2.0 covers 2,767/2,767
files (`20260828T043540-2770152`). Direct M4 remains hardware-binding red
(`20260828T043655-2772604`), while container-backed regression restores M0 6/6 and keeps every later
strict receipt/APPLY/product boundary red (`20260828T043734-2773083`).

The committed-state locked relink is no-work (`20260828T043806-2774653`). Exact CAPTURE identities:

- `blender_browser.js`: `08bbe627c1c5` (707,845 bytes)
- `blender_browser.wasm`: `58d37a9786a6` (120,325,036 bytes)
- `blender_browser.wasm.orig`: `a1520b30a4a7` (118,976,522 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `93c530fc5e7c` (13,325 bytes)

Apple handoff uses `--hardware --expected-wasm-orig-sha256
a1520b30a4a707ad689403d0d91ec91028be02df805faa5867ea5eec8ec75e55` and a fresh immutable run
label. This host's pass remains diagnostic-only. P0-I/J stay open until repeated Apple runs of the
exact original-freeze and cumulative batteries retain scene/text pixels, trusted selection,
modal artifacts, P0-E resize recovery, and `incompleteBindGroups=[]`.

## Full trailing recovery after the last accepted input

The first input-recovery candidate shared the asynchronous resource-readiness generation. That
made its active-burst ceiling correct for lazy GPU publications but left one precise interaction
gap: input accepted at heartbeat 179 of 180 consumed the old burst's final update instead of
owning a new trailing budget. A draw dropped by that final orbit or click could therefore remain
stale until another input or resource publication arrived.

Commit `fe7bbf3` adds a distinct coalescible input-tail generation. Accepted move, supported
button, nonzero wheel, and key callbacks advance both that owner and the existing aggregate retry
counter exposed to the browser. One WM poll acknowledges the latest values, resets a complete
180-tick tail even when an older readiness burst is active, and still keeps ordinary input out of
resize's drawable episode and completed-frame barrier. Shader/resource readiness and repeated
hard draw drops retain their existing active-burst ceiling, so only ongoing real interaction can
extend the input tail; after input stops, it remains bounded.

The exact tick-179 behavior fixture failed first because the input owner did not exist
(`20260828T063444-2865242`). The final input source self-check, 70-mutation recovery contract, and
68-case byte-identical native/Wasm integration are green
(`20260828T064109-2875712`, `20260828T064109-2875738`). The loader semantic-content and resize
source adjacencies remain green (`20260828T064143-2877568`, `20260828T064151-2877651`).

The locked relink and committed-state no-work proof are green
(`20260828T064200-2877695`, `20260828T065021-2883506`). Against that exact product, the unchanged
41-step original-freeze/cumulative control and fail-closed analyzer pass with native state, same-pose
pixels, final-orbit recovery, nine workspace transitions, and an empty all-shader hard-warning
census (`20260828T064340-2878410`, `20260828T064650-2880737`). The first modal browser context
closed without a page/backend signature (`20260828T064654-2880787`); one recorded unchanged
fresh-context retry and its analyzer pass all four operators with clean settles
(`20260828T064721-2881291`, `20260828T064756-2881710`). The exact shrink/restore recovery probe and
REUSE 6.2.0 are green (`20260828T064806-2881778`, `20260828T064916-2883123`).

Exact CAPTURE identities:

- `blender_browser.js`: `4de9b95b0e7d`
- `blender_browser.wasm`: `5b4933d440bf`
- `blender_browser.wasm.orig`: `dbfad903a2be` (118,978,050 bytes)
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `0a551f2c8e81`

This is a new device-free hardware candidate, not closure. The driver must run `--hardware` with
`--expected-wasm-orig-sha256 dbfad903a2bee28d4fcfbb37e8912b42c8213ac408bcdf4c17c3121910dd24c8`
and repeat the original-freeze/cumulative, modal, P0-E resize, and P0-D/F regressions with intact
scene/text pixels and `incompleteBindGroups=[]`.

The required direct M4 scope remains honestly RED at `browser_pixels`, and the initial host-oracle
regression reproduced the known M0 3/6 environment boundary
(`20260828T065119-2884454`, `20260828T065119-2884498`). The authoritative pinned-container rerun
restores M0 6/6 while M1-M8 retain their named strict-receipt, browser-pixel, APPLY, and release
boundaries (`20260828T065152-2884930`; suite timestamp 2026-08-28T06:51:55Z).

## Repeated hardware evidence series

Commit `3d1d799` makes the filed "repeated clean hardware verification" bar machine-checkable.
`analyze_diagnostic.py --hardware-series` requires at least two distinct evidence paths and reruns
the complete P0-I/J single-receipt contract for every document. It additionally requires unique run
labels and valid unique UTC capture timestamps, then holds the producer, pinned browser stack,
accepted Apple adapter, local/served split generation, and all five product files byte-identical
across the series. A fallback receipt, one passing run, duplicated evidence, or mixed candidate can
no longer satisfy the closure wording.

The original multi-path invocation failed first (`20260828T070003-2890932`). Final self-checks pass
3 positive cases and reject 49 mutations, including 11 series-specific cases
(`20260828T070234-2892188`, committed-state `20260828T070504-2894510`). The unchanged single-run
diagnostic remains compatible (`20260828T070234-2892189`), while a repeated path fails before
evidence parsing (`20260828T070234-2892192`). Producer/source self-checks and pinned REUSE 6.2.0 are
green (`20260828T070326-2893141`, `20260828T070326-2893145`,
`20260828T070352-2893323`).

No runtime source or product byte changed: the CAPTURE identities remain JS `4de9b95b0e7d`, Wasm
`5b4933d440bf`, `.wasm.orig` `dbfad903a2be`, data `095d0ba748c3`, and split manifest
`0a551f2c8e81`. Direct M4 remains honestly RED at `browser_pixels`; the authoritative
container-backed regression restores M0 6/6 and preserves every later named boundary at suite
timestamp 2026-08-28T07:03:56Z. This contract does not hardware-close P0-I/J; the driver must still
produce at least two clean Apple diagnostics against this exact generation and run the modal and
resize regressions.

## Present the newest frame suppressed during validation

The strengthened camera canary exposed a separate loss after every previously instrumented input
and draw-recovery boundary. Before commit `868bd86`, two fresh fallback loads reached native
`CAMERA` state but captured the older top/perspective pixels; the following cancelled `Numpad4`
no-op caused the camera image to appear. Bounded trace counters then proved all four synthetic
WindowUpdates were queued, consumed by WM, and executed as full draws. The draw-drop generation
stayed fixed, the resize barrier did not advance, and only the surface presentation count lagged.
This falsified another resource-binding or WM-invalidation candidate.

`GHOST_ContextWGPUWeb::presentBackbuffer()` used a boolean pending guard around its asynchronously
validated surface transaction. Any later `swapBufferRelease()` returned failure without retaining
the request. The in-flight present command had already sampled the earlier persistent backbuffer;
later full-frame commands updated that backbuffer, but successful scope settlement only cleared the
guard. With no subsequent present, the canvas could remain permanently stale until unrelated input.

Commit `868bd86` replaces that lossy boolean with `PresentSettlementLatch`. The first suppressed
swap sets one coalesced retry bit; any number of later swaps preserve the same bit. Completion clears
the pending transaction and, from that callback's fresh browser turn, calls `presentBackbuffer()`
once to acquire a new swapchain texture and synchronously submit a blit of the retained latest
backbuffer. If that direct start cannot proceed, it publishes the existing bounded redraw edge.
Terminal device loss resets both states. This is deliberately not patch 0288's rejected deferred
GHOST callback: surface acquire/encode/submit remain contiguous in one browser turn.

The fail-first native compile rejected the missing latch
(`ledger/buildlogs/20260828T101433-3015016.log`). Final native/Wasm behavior and exact source-order
contracts are green (`ledger/buildlogs/20260828T105049-3042362.log`). A first redraw-only settlement
variant still failed the camera/no-op oracle (`ledger/buildlogs/20260828T103753-3032316.log`) and
was replaced rather than promoted. Two consecutive direct-retry camera runs then retained identical
camera pixels across the cancelled no-op, and both complete cleaned-product batteries pass:

- `ledger/buildlogs/20260828T104438-3038959.log` / `20260828T104754-3040605.log`;
- `ledger/buildlogs/20260828T105159-3045167.log` / `20260828T105527-3046830.log`.

The final run covers 41 steps, 98 native-state samples, 292 validated presentations, 9/9 workspace
transitions, two byte-identical known-pose comparisons across viewport/text/UI detail regions, and
native move/undo, with zero hard completeness warnings or page errors. The unchanged modal family
passes 80 constraint submissions across extrusion/move/rotate/scale and 12 modal presents
(`ledger/buildlogs/20260828T110032-3050686.log`, `20260828T110116-3051290.log`). Shrink/restore
retains two coherent resize barriers and no rejection
(`ledger/buildlogs/20260828T110127-3051370.log`). The final relink and committed-state no-work proof
are `ledger/buildlogs/20260828T104933-3041807.log` and
`ledger/buildlogs/20260828T105754-3048339.log`.

Exact CAPTURE identities:

- `blender_browser.js`: `c8e0c4a3ce3a` (708,076 bytes)
- `blender_browser.wasm`: `03f17d6862a2` (120,332,263 bytes)
- `blender_browser.wasm.orig`: `96cb55a62707` (118,983,629 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `497deb8505be` (13,325 bytes)

This is the exact next Apple candidate, not hardware closure. The driver must provide at least two
clean `--hardware-series` original-freeze/cumulative diagnostics for this generation, plus modal
artifact and P0-D/E/F/resize regressions with intact scene/text pixels and
`incompleteBindGroups=[]`.

The direct M4 verifier therefore remains honestly red at the unsupported hardware receipt binding
(`ledger/buildlogs/20260828T110357-3053068.log`). The authoritative pinned-container regression
keeps M0 green at 6/6 and preserves every named M1-M8 strict/APPLY/hardware/product boundary
(`ledger/buildlogs/20260828T110808-3055769.log`; suite timestamp 2026-08-28T11:08:12Z).

## Bind the suppressed-present seam in the Apple producer

Commit `56bd212` strengthens the existing P0-I/J capture without changing runtime source or product
bytes. After establishing the same-run front/Frame-Selected reference, it drives two immediate
`Numpad3 -> Numpad7 -> Numpad0 -> Numpad1` cycles. Each trusted key must reach its learned
Blender-native perspective/rotation, but the producer deliberately does not wait for intermediate
pixel settlement. It then requires the final retained frame to settle within the existing bounded
12-second window, remain byte-identical for another three seconds, advance both the uncapped
validated-present counter and the input-retry generation, and match a third same-pose full/detail
region diff. This directly exercises the coalescing behavior introduced by `868bd86` on the next
driver-operated Apple series instead of relying only on isolated transitions.

The analyzer failed first before the producer and fixture carried the burst
(`ledger/buildlogs/20260828T112009-3064291.log`). Its final synthetic contract, actual captured
document, producer/source/recovery seams, and pinned REUSE 6.2.0 are green
(`ledger/buildlogs/20260828T112931-3069739.log`,
`ledger/buildlogs/20260828T112931-3069748.log`,
`ledger/buildlogs/20260828T112931-3069757.log`,
`ledger/buildlogs/20260828T112931-3069766.log`,
`ledger/buildlogs/20260828T112931-3069775.log`, and
`ledger/buildlogs/20260828T112935-3069789.log`). The real fallback run is
`ledger/buildlogs/20260828T112218-3065518.log`: 43 screenshots, 123 native states, 297 validated
presents, eight ordered DOM/native burst transitions, presents 83 -> 108, retries 883 -> 899,
5,037 ms final settlement, three zero-difference known-pose canaries, and zero hard warnings or page
errors. This software result binds the contract only.

The CAPTURE inventory remains byte-identical: JS `c8e0c4a3ce3a`, Wasm `03f17d6862a2`,
`.wasm.orig` `96cb55a62707` (118,983,629 bytes), data `095d0ba748c3`, and manifest
`497deb8505be`. Direct M4 therefore remains honestly hardware-pixel RED
(`ledger/buildlogs/20260828T113140-3072157.log`). The authoritative container-backed regression
restores M0 6/6 and preserves the named M1-M8 boundaries
(`ledger/buildlogs/20260828T113046-3071062.log`; suite timestamp 2026-08-28T11:30:50Z). P0-I/J
still require at least two clean Apple runs of this exact generation plus modal, P0-D/E/F, and
resize pixels before closure.

## Keep suppressed-present replay inside the WM boundary

The rapid canary originally proved only aggregate presentation and input-retry progress. This
iteration added exact suppression and replay counters, then reproduced the camera/no-op stale-frame
oracle twice on the relinked direct-replay generation. In the failing run, top -> camera advanced
suppressed swaps `44 -> 58` and callback replays `10 -> 13`, while the first camera screenshot
still omitted its dashed frame. The following cancelled Numpad4 added no suppression or replay yet
produced the correct camera pixels. Blender-native camera state was byte-identical throughout.

Numbered patch 0302 adds a browser-only 12-stage witness for
`gpu_shader_3D_line_dashed_uniform_color`. The failing camera transition recorded 18 attempts,
four pipeline deferrals, 14 encodes, 13 accepted validations, and zero module/geometry/binding/load/
pass/rejection failures. The no-op then recorded 30 already-ready accepted draws. This rules out
bind-group completeness and command rejection: the retained stale image was below admitted draw
encoding, at the callback-side surface replay boundary.

The candidate keeps `PresentSettlementLatch` coalescing but replaces callback-side
`presentBackbuffer()` with `request_present_replay()`. That distinct release/acquire generation is
not part of the generic 180-tick recovery budget. `GHOST_SystemWeb::processEvents()` carries it
until a normal `GHOST_kEventWindowUpdate` is admitted through any resize barrier, consumes it only
after queuing that event, and therefore keeps surface acquire/encode/submit inside WM's synchronous
swap boundary. The earlier generic-redraw experiment could be lost at the heartbeat ceiling; this
request cannot.

Fail-first rejected the absent WM replay API (`20260828T122229-3110275`). Exact native/Wasm
behavior and 75-mutation source ordering pass (`20260828T122504-3117369`). The locked relink is
`20260828T122522-3118916`. Two independent unchanged 43-step fallback runs and consumers pass:

- `20260828T122630-3119475` / `20260828T123002-3121911`;
- `20260828T123017-3122002` / `20260828T123355-3123889`.

Both runs captured the correct camera image before Numpad4 and the identical SHA-256
`b2b6ac378aa78b6d5794e9d10fc13bc202aa6c33b2e99a2931ee9249c7d75929` afterward. Run two's rapid
burst advanced presents `83 -> 104`, suppressions `107 -> 145`, WM replays `27 -> 35`, and retries
`883 -> 899`, then held the exact known pose. Both retain zero hard completeness warnings and page
errors. Shrink/restore remains green (`20260828T123557-3125848`). Two modal-probe adjacency attempts
both reached `armed-probe-8` then lost their Chromium context without a backend/page signature
(`20260828T123514-3125016`, `20260828T123534-3125437`); the two-attempt rule leaves that separate
probe blocked rather than silently substituting a pass.

These are SwiftShader diagnostics, not closure. P0-I/J still require at least two clean Apple
hardware-series receipts for this exact generation plus the modal and P0-D/E/F/resize pixel
gauntlets.

## Do not suppress newer WM presents behind validation callbacks

The WM-owned replay candidate still had an intermittent loss window. Extending the exact producer
through the filed modal sequence exposed it on the ordinary camera canary before the modal battery:
Blender-native state had already reached camera view, presents advanced `11 -> 15`, suppressed swaps
advanced `35 -> 48`, and replay generation advanced `6 -> 7`, but the screenshot still showed the
previous perspective. A cancelled Numpad4 then changed neither native state nor the suppressed
counter and finally exposed the correct camera frame
(`ledger/buildlogs/20260828T130608-3146124.log`, consumer
`ledger/buildlogs/20260828T130951-3149040.log`). This was a real stale frame, not a camera-state or
shader-completeness ambiguity.

The remaining inversion was inside `presentBackbuffer()`. `PopErrorScope` removes its scope from
the WebGPU device synchronously, but its result callback may lag several complete WM frames. The
settlement latch treated that callback latency as if the whole present transaction were still
using the device stack and returned before every overlapping surface copy. One eventual replay was
therefore responsible for publishing an arbitrarily long run of newer backbuffer contents.

The candidate keeps exactly one scoped transaction as the validation owner. While its callbacks
are pending, every later WM frame still acquires the current surface texture, encodes the
persistent-backbuffer copy, and submits it in that same browser turn; those overlapping copies do
not push nested diagnostic scopes. They mark the existing coalesced latch, and settlement requests
one final scoped WM replay. Surface acquisition never moves into an asynchronous callback and the
P0-H-safe WM boundary remains intact. The fail-first source contract rejects the old early return
(`ledger/buildlogs/20260828T131421-3150996.log`); the final integrated native/Wasm presentation
suite is green (`ledger/buildlogs/20260828T133515-3169576.log`).

The final exact fallback capture and consumer pass 53 screenshot steps, 150 native-state samples,
764 validated presents, 9/9 workspace transitions, all three known-pose canaries, the post-stress
move/undo, and the complete modal battery with zero hard completeness warnings or page/lifecycle
errors (`ledger/buildlogs/20260828T132522-3163291.log`, final consumer
`ledger/buildlogs/20260828T133959-3175215.log`). Camera and cancelled-no-op pixels are now exactly
the same SHA-256 `b2b6ac378aa7`; the final run records 433 overlaps and 129 scoped replays without a
retained stale frame. This is diagnostic software evidence only.

The locked CAPTURE relink and immediate no-work proof are
`ledger/buildlogs/20260828T133327-3168646.log` and
`ledger/buildlogs/20260828T133432-3169160.log`. Exact identities are JS
`5915a76607af` (708,496 bytes), instrumented Wasm `d83b37c3f5f` (120,334,304 bytes),
`.wasm.orig` `5fea52ef8bc9` (118,985,639 bytes), data `095d0ba748c3` (168,637,598 bytes),
and manifest `a0fc17c7d4d5` (13,436 bytes). CAPTURE preflight and split-identity self-check are green
(`ledger/buildlogs/20260828T133440-3169223.log`,
`ledger/buildlogs/20260828T133440-3169224.log`). Direct M4 remains honestly hardware-pixel RED and
container-backed regression restores M0 6/6 while preserving the named M1-M8 strict/APPLY/product
boundaries (`ledger/buildlogs/20260828T133532-3171007.log`,
`ledger/buildlogs/20260828T133543-3171817.log`). P0-I/J remain open until at least two clean Apple
hardware-series runs also pass modal, P0-D/E/F, and resize pixels.

## Compose interaction and resize hardware evidence without generation drift

The repeated P0-I/J consumer and the ten-attempt P0-E consumer were individually strict, but their
handoff remained prose: two clean interaction runs could be cited alongside a resize receipt from a
different CAPTURE generation, browser stack, or adapter. The interaction consumer also trusted the
step hashes recorded in `diagnostic.json` without independently re-hashing the retained PNG files.

`verify_hardware_gauntlet.py` closes that composition gap. It reruns the complete interaction
series consumer, requires every interaction producer hash to match the current checkout, re-hashes
every named PNG and rejects any missing, extra, or symlinked evidence entry, and invokes the
independent P0-E receipt consumer under pinned Node. Only then does it require both evidence
families to share all five product byte identities, the explicit expected `.wasm.orig`, identical
local and served CAPTURE generations, the pinned Node/Playwright/PNGJS/Chromium stack, and the
complete accepted Apple adapter record. Separate run labels remain mandatory.

The 3-positive/23-negative contract is green
(`ledger/buildlogs/20260828T135911-3188734.log`), as are the unchanged complete interaction
consumer/source checks and independent P0-E consumer
(`ledger/buildlogs/20260828T135641-3186138.log`,
`ledger/buildlogs/20260828T135641-3186143.log`, and
`ledger/buildlogs/20260828T135641-3186150.log`). Exact CAPTURE preflight and locked Ninja dry-run
remain green without relinking (`ledger/buildlogs/20260828T135641-3186190.log` and
`ledger/buildlogs/20260828T135641-3186178.log`), and REUSE 6.2.0 remains green
(`ledger/buildlogs/20260828T135641-3186168.log`).

This is evidence plumbing, not hardware evidence. Exact `.wasm.orig` remains `5fea52ef8bc9`
(118,985,639 bytes), direct M4 remains RED at the Apple pixel boundary
(`ledger/buildlogs/20260828T135714-3187051.log`), and aggregate regression retains the existing
missing APPLY/release receipts (`ledger/buildlogs/20260828T135719-3187103.log`). P0-I/J close only
after at least two clean driver-operated interaction/modal runs and one 10/10 resize receipt from
this same generation produce `P0IJ_HARDWARE_GAUNTLET_PASS`.

## Separate rapid input backlog from permanent freeze

The later Apple handoff supplied five screenshot series at 350 ms per action for the exact
`5fea52ef8bc9` generation. In each series the first post-deselect orbit painted, while the following
click, opposite orbit, and move samples retained that orbit image. Those pixels establish a real
same-cadence observation, but they do not by themselves show whether the WM worker eventually
drained the queued actions: none of the retained evidence records a later counter-backed settle or
an extended final sample.

Commit `32692ee` adds a focused discriminator without changing product code. It repeats the exact
Numpad 1/3/7/0/4, Select All, Deselect All, orbit, click, opposite-orbit, and move sequence with the
same 350 ms snapshots. It then waits at most 12 seconds for one post-orbit result that simultaneously
changes canvas pixels and advances the WM tick, validated-present, and aggregate input-redraw
counters. A separate recovery orbit must meet the same four-part predicate. Immediate retained
frames remain reported but are not promoted to a liveness verdict. Page or browser lifecycle errors
always fail.

Hardware mode is Apple-only and independently rejects an absent adapter, fallback status other
than exactly false, incomplete adapter info, or a software identity token. On timeout the producer
retains all rapid samples, the last counter snapshot, pointer-lock diagnostics, and the last 80
native `ghost_event_proc` lines in its failure document, so the next hardware run can distinguish
DOM/GHOST delivery, WM progress, presentation progress, and pixel retention without another relink.

The mutation self-check and source contract pass at
`ledger/buildlogs/20260828T232030-3513437.log` and
`ledger/buildlogs/20260828T232030-3513438.log`. A first shared-WSLg attempt lost its X connection
with no page/backend error (`20260828T231723-3510906`) and binds no result. The isolated-X fallback
control passes (`20260828T232034-3513513`): the rapid action series itself drains, and the independent
recovery orbit advances ticks `143 -> 145`, validated presents `45 -> 47`, and retries `458 -> 728`
after 6,555 ms. That result proves only that 350 ms samples can be shorter than a real recovery
latency; software pixels bind no Apple verdict. The integrated WebGPU/GHOST suite is green at
`20260828T232115-3514661`, and REUSE 6.2.0 is green at
`20260828T232231-3517380`.

No relink or runtime byte changed. Direct M4 remains honestly RED at the Apple pixel boundary
(`20260828T232153-3516272`), while the pinned-container regression restores M0 6/6 and retains the
named M1-M8 strict/APPLY/product boundaries (`20260828T232156-3516324`). P0-I/J remain open until
the driver runs this discriminator on the conformant Apple adapter and the existing composed
same-generation gauntlet passes.

## Bind the verdict to the terminal GHOST input edges

The five supplied Apple series establish less elapsed time than the accompanying permanent-freeze
description implied. In every series `h-deselect-all.png` differs from `i-orbit-before-click.png`,
so the first orbit was accepted and painted. The five identical files from
`i-orbit-before-click.png` through `m-g-confirmed.png` span only 1.396 seconds by their retained
timestamps (09:49:00.789 through 09:49:02.185). They prove a same-cadence retained frame, but contain
no terminal worker-delivery or later settle observation.

The first focused producer had a corresponding false-acceptance gap: any intermediate changed
sample after the first orbit could satisfy `action-drain`, even while the later opposite orbit and
G/confirm events remained queued. A pass-through Blender modal probe also cannot close that gap by
itself because an active `VIEW3D_OT_rotate` consumes its matching release before a later modal
handler can observe it.

Commit `5cad54c` moves the discriminator to the correct boundary. Transition-only counters now
advance after proxied button callbacks update `GHOST_SystemWeb` state; key callbacks publish their
own press/release totals, and an atomic held-button mask exposes a terminal press whose release has
not reached the WM worker. The producer snapshots the trusted DOM tail and requires the complete
post-deselect sequence (two MMB press/release pairs, two left press/release pairs, and the G
press/release), a zero left/middle held mask, a drained Blender modal stack, changed pixels, and
advancing WM tick/present/input-retry counters. The independent recovery orbit must add another
balanced MMB pair and satisfy the same drain predicate. Apple retains the 12-second bound;
SwiftShader gets 30 seconds only in the explicitly non-receipt fallback lane.

The 81-case native/Wasm display-state contract and the complete integrated GHOST/WebGPU source
suite pass (`ledger/buildlogs/20260828T234415-3535343.log`). The locked relink and committed-state
no-work proof are `ledger/buildlogs/20260828T234517-3537308.log` and
`ledger/buildlogs/20260828T234911-3540705.log`. Most importantly, the committed-state exact fallback
replay reproduces all five identical rapid action frames and then proves they were backlog, not a
terminal freeze (`ledger/buildlogs/20260828T234941-3540978.log`): action drain completes after
5,725 ms with left `2/2`, middle `2/2`, key `10/10`, held mask zero, ticks 158, presents 64,
retries 713, and only the diagnostic modal remaining. A fresh recovery orbit completes after
1,744 ms with middle `3/3`, changed native rotation and pixels, ticks 163, presents 68, retries 727,
and zero page/lifecycle errors. These are software-adapter diagnostics and bind no Apple pixel
verdict.

The relinked CAPTURE generation is JS `cae158a06338` (709,160 bytes), Wasm `8d6928a6545d`
(120,334,720 bytes), `.wasm.orig` `b326a3be5331` (118,986,006 bytes), data `095d0ba748c3`
(168,637,598 bytes), and manifest `ddf56d15022d` (13,612 bytes). P0-I/J remain open: the driver must
run this terminal-edge discriminator on Apple and the existing same-generation hardware gauntlet
must still pass. A hardware timeout will now say whether the loss is before GHOST delivery, in a
stuck modal, or below a fully drained WM/present path instead of inviting another speculative
runtime change.

## Bind rapid drain to Blender-native action state

The terminal GHOST-edge discriminator still had one false-pass path: after every queued callback
arrived, any unrelated pixel change could satisfy the canvas predicate even if Blender ignored the
Cube click and `G` transform. The previous SwiftShader control demonstrated the gap directly: the
second orbit eventually changed the view, but GPU picking selected nothing and Cube stayed at the
origin while the old predicate reported drain.

Commit `f27df7e` keeps the worker-edge, modal-stack, WM-tick, present, retry, and pixel conditions,
then adds a hardware-only semantic boundary. Apple action drain now requires one selected active
Cube, a view rotation different from the first-orbit baseline, and a Cube location different from
that baseline. The independent recovery orbit must advance native state and rotation again while
retaining the confirmed Cube location. Thus neither a tooltip redraw nor a delivered-but-ignored
input tail can produce a hardware PASS. SwiftShader remains explicitly diagnostic because its
asynchronous GPU pick can fail; its output records `nativeStateContract.enforced=false` rather than
claiming the hardware predicate.

The contract failed first on the absent semantic boundary
(`ledger/buildlogs/20260828T235921-3550739.log`) and passes 33 mutations, including four delivery
mutations (`ledger/buildlogs/20260828T235953-3550986.log`). Node syntax and the focused source
contract pass (`ledger/buildlogs/20260829T000005-3551068.log`,
`ledger/buildlogs/20260829T000005-3551069.log`), as does the integrated native/Wasm suite
(`ledger/buildlogs/20260829T000149-3552840.log`). The exact fallback product again retains all five
rapid samples, drains after 5,845 ms, and repaints the independent orbit after 2,384 ms with zero
page/lifecycle errors (`ledger/buildlogs/20260829T000031-3551393.log`). That run correctly records
both hardware-only semantic checks false and unenforced; it binds no Apple verdict.

REUSE 6.2.0 is green (`ledger/buildlogs/20260829T000351-3556722.log`). Direct M4 remains RED at the
unsupported Apple-pixel binding (`ledger/buildlogs/20260829T000236-3554459.log`), while the
authoritative container regression restores M0 6/6 and preserves the named M1-M8 strict/APPLY/
product boundaries (`ledger/buildlogs/20260829T000332-3555249.log`). No runtime source or artifact
changed and no relink occurred: the current CAPTURE generation remains JS `cae158a06338`, Wasm
`8d6928a6545d`, `.wasm.orig` `b326a3be5331` (118,986,006 bytes), data `095d0ba748c3`, and manifest
`ddf56d15022d`. P0-I/J remain open for this strengthened Apple run and the same-generation composed
hardware gauntlet.

## Bind terminal input publication to WM redraw admission

The driver's next hypothesis asked whether ordinary orbit/click/key completion ever calls the
resize episode. Source tracing first established the required distinction: `request_redraw_episode()`
is owned only by initial/replacement drawable publication, while accepted ordinary input already
publishes a separate `request_input_redraw_retry()` generation. Routing input through the resize
episode would incorrectly attach it to the replacement-drawable barrier and risk regressing P0-E.
What was missing was evidence that the distinct input generation actually crossed that barrier as
a WM `GHOST_kEventWindowUpdate` rather than being acknowledged and lost beforehand.

Commit `8177420` adds that discriminator without changing redraw policy. Every completed button,
key, or wheel callback records its exact terminal input generation and logs the retry and resize
episode before/after publication. `GHOST_SystemWeb::processEvents()` publishes a separate admitted
generation only after `filter_redraw_present_barrier_update()` accepts the synthetic WindowUpdate;
one bounded line records admission, while a separately bounded line records a terminal generation
withheld by an active barrier. Browser exports expose published, terminal, admitted, and episode
generations. The focused producer now requires its last terminal generation to be admitted and the
resize episode to remain unchanged before either action drain can pass.

The contract failed first at the absent terminal/admission predicate
(`ledger/buildlogs/20260829T001518-3565923.log`). Final rapid-input and ordinary-input mutation
contracts, the real GHOST harness, and the integrated native/Wasm WebGPU/GHOST suite are green
(`20260829T001658-3566974`, `20260829T001800-3568158`,
`20260829T001707-3567083`, `20260829T001859-3570697`). REUSE 6.2.0 is green
(`20260829T002058-3573279`).

The committed CAPTURE relink and locked no-work proof are
`20260829T002121-3573518` and `20260829T002415-3576246`. Exact identities are:

- `blender_browser.js`: `116d74fdfda8` (709,604 bytes)
- `blender_browser.wasm`: `2e7a762e37ac` (120,335,819 bytes)
- `blender_browser.wasm.orig`: `1caec08e9582` (118,987,074 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `10946183fc74` (13,729 bytes)

The exact isolated-X fallback replay is green
(`ledger/buildlogs/20260829T002319-3575639.log`). It deliberately reproduces five identical rapid
action samples, then drains after 5,814 ms with terminal/admitted `50/50`, ticks 143, presents 57,
retries 713, balanced left `2/2` and middle `2/2` edges, and held mask zero. Its independent orbit
repaints after 327 ms with terminal/admitted `63/63`, ticks 145, presents 60, and episode still 1.
Every logged terminal has `episode_changed=0`; there are no withheld lines, page errors, or lifecycle
errors. This proves on the fallback path that ordinary input does not request a resize episode but
does rearm and cross its own WM retry boundary. It does not determine the Apple failure.

CAPTURE inventory, profile/capture, and same-generation hardware-gauntlet self-checks are green
(`20260829T002442-3577176`, `20260829T002707-3580238`,
`20260829T002714-3580334`, `20260829T002707-3580239`). Direct M4 remains honestly RED at the Apple
pixel binding (`20260829T002624-3578397`); pinned-container regression restores M0 6/6 while later
tiers retain their named strict/APPLY/product boundaries (`20260829T002652-3579215`).

The adjacent resize source and trace contracts remain green, but the live fallback probe is
retained as RED rather than hidden: two fresh runs completed exactly two coherent resize barriers,
current/contained plans, and zero encode/submit/transaction rejection or device loss, yet exceeded
its legacy at-most-three-total-presents heuristic with shrink/restore deltas `5/2` and `5/4`
(`20260829T002442-3577191`, `20260829T002529-3577774`). This diagnostic-only change does not claim
P0-E regression green. The driver must run the exact Apple discriminator and P0-E/P0-I gauntlet. If
Apple terminal exceeds admitted, the loss is at barrier admission; if they match while native state
or pixels remain frozen, the re-arm-gap hypothesis is falsified and the defect is downstream.

## Bind admitted terminal input to clean surface presentation

Commit `ebb602a` adds the next downstream discriminator without changing redraw or presentation
policy. `presentBackbuffer()` snapshots the latest admitted ordinary-input generation before
encoding its surface transaction and publishes that generation only after the transaction's
validation scopes complete cleanly. The atomic publication is monotonic: an older scoped callback
that settles after a newer unscoped frame cannot move the counter backward. One bounded console
line records each terminal generation that crosses this boundary, and the browser export
`bw_input_redraw_presented_count()` makes the same fact machine-readable.

The rapid producer now requires `presented >= terminal` alongside terminal GHOST delivery, WM
admission, advancing ticks/presents/retries, changed pixels, a drained modal stack, and—in Apple
mode—the Blender-native selection/rotation/location transitions. Its fail-first source contract
rejects the absent counter (`ledger/buildlogs/20260829T003222-3584150.log`). The final mutation
contract, real GHOST harness, and integrated native/wasm32 suite are green
(`20260829T003529-3587662`, `20260829T003359-3584756`, and
`20260829T003600-3589134`). The behavior suite now covers 85 cases, including newer, duplicate,
and out-of-order presentation callbacks.

The relinked exact fallback product passes the filed sequence
(`ledger/buildlogs/20260829T003810-3592128.log`). Action drain takes 6,294 ms and reaches
terminal/admitted/presented `51/51/51`; the independent recovery orbit takes 2,486 ms and reaches
`64/65/65`. The resize-only episode remains 1, retained rapid samples are deliberately observed
before the backlog drains, and page/lifecycle errors are empty. This is software-adapter diagnostic
evidence only.

The CAPTURE product is JS `6da5ca692add`, Wasm `e68f67650b7a`, `.wasm.orig`
`f396b0ea7950` (118,987,372 bytes), data `095d0ba748c3`, and manifest `8bde9ab660d1`.
Relink and committed-state locked no-work are green
(`ledger/buildlogs/20260829T003635-3591210.log` and
`20260829T004013-3594597.log`); CAPTURE preflight is green
(`20260829T003759-3592021.log`). REUSE and the profile/capture/gauntlet self-checks are green
(`20260829T003856-3593310`, `20260829T003920-3593499`,
`20260829T003856-3593311`, and `20260829T003856-3593316`). Direct M4 remains honestly RED at the
unsupported Apple-pixel binding (`20260829T003924-3593540`); pinned-container regression restores
M0 6/6 and preserves the named later strict/APPLY/product boundaries
(`20260829T003932-3593638`).

P0-I/J remain open. On the exact Apple repro, terminal greater than admitted locates the loss at
barrier admission; admitted greater than presented locates it between admitted WindowUpdate and a
clean surface transaction; matching terminal/admitted/presented with stale native state or pixels
locates it downstream. No hardware receipt, profile, result, promise, tolerance, golden, blacklist,
deferral, APPLY/public bundle, tag, or launch claim changed.

## Bind queue admission to completed Blender WM dispatch

The driver-provided `b326a3be` screenshots are real retained pixels, but their filesystem times
also establish that every sample was taken only 344-408 ms after the previous one. The labeled
Numpad4 frame is byte-identical to the preceding Camera frame even though later selection frames
advance. That evidence proves a substantial worker/render backlog at the filed cadence; the rapid
producer's existing 12-second terminal/native-state decision remains the authority for separating
backlog from a permanent freeze.

Source tracing found one remaining false-localization seam in that producer. The admitted counter
advanced when `GHOST_SystemWeb::processEvents()` pushed a synthetic `GHOST_kEventWindowUpdate` into
GHOST's queue. It did not prove `ghost_event_proc()` consumed the event. Presentation then sampled
the latest admitted atomic directly, so an unrelated later surface transaction could publish that
generation even if the intended WindowUpdate had not crossed Blender's consumer.

Commit `9942dd9` carries the exact input generation in a web-owned WindowUpdate event and installs a
small GHOST consumer on the first `processEvents()` call. Blender registers its WM consumer before
that call, and `GHOST_EventManager` dispatches consumers in registration order, so the new monotonic
dispatched edge advances only after Blender's WM callback has returned. `presentBackbuffer()` now
snapshots dispatched rather than admitted state. The browser exposes the new counter, bounded logs
record it, and the rapid producer requires terminal, admitted, dispatched, and cleanly presented
generations all to cross the terminal edge. Redraw policy, the resize-only episode/barrier, receipt
criteria, and hardware adapter rules are unchanged.

The contract failed first on the absent dispatched predicate
(`ledger/buildlogs/20260829T004747-3599335.log`). Final mutation/source checks, real Wasm GHOST
objects, and the integrated native/wasm32 WebGPU/GHOST suite are green
(`20260829T005213-3604552`, `20260829T005740-3608240`, and
`20260829T005740-3608241`). The exact fallback preserves all five immediate retained frames, then
drains after 6,579 ms with terminal/admitted/dispatched/presented `49/49/49/49`; its independent
orbit repaints after 1,412 ms at `62/62/62/62`. Button/key edges are balanced, the held mask is zero,
the resize episode remains 1, and page/lifecycle errors are empty
(`ledger/buildlogs/20260829T005411-3605481.log`). This is software-adapter diagnostic evidence only.

CAPTURE preflight, the hardware-gauntlet and pinned capture-profile self-checks, and REUSE 6.2.0 are
green (`20260829T005630-3607651`, `20260829T005630-3607643`,
`20260829T005644-3607836`, and `20260829T005656-3607959`). Exact product identities are:

- `blender_browser.js`: `06505f5705bf` (709,920 bytes)
- `blender_browser.wasm`: `64151db95d30` (120,336,944 bytes)
- `blender_browser.wasm.orig`: `31c7a6bab76a` (118,988,169 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `e49feeebb96c` (13,812 bytes)

The CAPTURE relink and committed-state locked no-work proof are
`ledger/buildlogs/20260829T005241-3604751.log` and
`ledger/buildlogs/20260829T005835-3609942.log`. Direct M4 remains honestly RED at the unsupported
Apple-pixel binding (`20260829T005500-3606111`); the pinned-container regression restores M0 6/6
while every later tier retains its named strict/APPLY/product boundary
(`20260829T005537-3606633`).

P0-I/J remain open. The exact Apple discriminator now localizes terminal greater than admitted to
the resize barrier, admitted greater than dispatched to GHOST/WM dispatch, dispatched greater than
presented to surface validation/presentation, and matching generations with stale Blender state or
pixels downstream of all three. No hardware receipt, profile, result, promise, tolerance, golden,
blacklist, deferral, APPLY/public bundle, tag, or launch claim changed.

## Bound nonterminal input redraw bursts

The driver's latest `b326a3be` evidence retains five action images, but their filesystem times are
only 344-408 ms apart. The exact pre-change fallback discriminator likewise needed 8,951 ms to
drain (`ledger/buildlogs/20260829T010610-3614749.log`). Source tracing found that every mouse-motion,
button, and key callback advanced both the input-specific and aggregate retry generations. The
recovery helper treated each paired increment as fresh asynchronous readiness, requested another
full-screen `WindowUpdate`, and reset the full 180-tick input tail on every motion sample. Blender's
native cursor/button/key event already owns the immediate interaction redraw, so this synthetic work
could accumulate behind the action it was intended to recover.

Commit `5721ba7` keeps one input generation per accepted callback and one terminal generation per
completed button/key/wheel action. `redraw_recovery_tick()` now subtracts the paired per-tick input
delta from the aggregate retry delta. An unmatched aggregate edge remains real resource/resize
readiness and retries immediately. A first nonterminal input after an exhausted burst opens a new
bounded burst, but further motion inside it neither injects a synthetic update nor resets the hard
ceiling. The terminal edge still restarts one complete coalesced tail. This does not route ordinary
input through the resize-only episode or barrier.

The source contract failed first against the all-input full-tail policy
(`ledger/buildlogs/20260829T010825-3616459.log`). Final input/rapid mutation contracts and the
87-case native/wasm32 integrated state model are green
(`20260829T011803-3625326`, `20260829T011803-3625327`, and
`20260829T011819-3626120`). Two fresh isolated-X executions of the driver's exact cadence both
drain and repaint: action drain is 5,545/5,566 ms, recovery orbit is 2,513/1,551 ms, and terminal,
admitted, dispatched, and presented generations converge with zero page/lifecycle errors
(`20260829T012005-3628557` and `20260829T012041-3629691`). The complete fallback fidelity battery
also passes 53 steps, 172 states, 767 presentations, 9/9 workspace transitions, the modal settle,
three same-pose checks, and an empty hard-warning/page-error census
(`20260829T012150-3630371`, consumer `20260829T012556-3632964`). These are software-adapter
diagnostics, not pixel closure.

The final CAPTURE relink is `ledger/buildlogs/20260829T011849-3627966.log`; committed-state locked
no-work is `20260829T012913-3636244`. Exact product identities are:

- `blender_browser.js`: `06505f5705bf` (709,920 bytes)
- `blender_browser.wasm`: `8751f1615ad1` (120,337,101 bytes)
- `blender_browser.wasm.orig`: `aa374938f2b8` (118,988,326 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `b74035aa5b00` (13,812 bytes)

Resize source and trace contracts remain green (`20260829T012613-3633091/3633093`). The fallback
live probe still reports its already-filed legacy present-churn failure `5/2` despite two coherent
barriers and no rejection/loss (`20260829T012618-3633116`), so no P0-E regression is claimed.
Capture/gauntlet self-checks and pinned Node 22.16.0 profile self-check are green
(`20260829T012950-3637110/3637111`, `20260829T012957-3637177`), as is REUSE 6.2.0
(`20260829T012832-3635921`). Direct M4 remains Apple-pixel RED
(`20260829T012652-3633666`); pinned-container regression restores M0 6/6 while later tiers retain
their named strict/APPLY/product boundaries (`20260829T012726-3634160`). P0-I/J remain open for the
exact Apple discriminator and same-generation composed gauntlet.

## Bind terminal presentation evidence to its originating WM frame

The dispatched-to-presented discriminator still had one late-sampling ambiguity. A browser surface
transaction copied the persistent backbuffer only after Blender had finished drawing, and a resize
barrier could delay that copy behind a newer WM frame. Sampling the process-global dispatched input
generation inside `presentBackbuffer()` could therefore label old backbuffer content with an input
generation dispatched after that content's frame began. A matching terminal/admitted/dispatched/
presented tuple would then be weaker than it appeared on the exact Apple freeze.

Commit `430c8f5` snapshots the latest fully dispatched input generation in
`swapBufferAcquire()`, immediately before Blender's `GPU_context_begin_frame()`. The resize trace
snapshot carries the same generation with the completed frame, and a delayed resize barrier takes
that immutable value instead of the current context member. A clean surface transaction now
publishes only this frame-bound generation. The bounded compatibility line retains its established
prefix and adds `frame-bound=1`. This is diagnostic provenance only: no input callback, recovery
tail, redraw episode, resize barrier, surface scheduling, receipt rule, or adapter policy changed.

The new contract failed first on the absent provenance class
(`ledger/buildlogs/20260829T014122-3644112.log`). Final source/mutation checks, the actual Wasm
GHOST object, and the 90-case native/wasm32 integrated model are green
(`20260829T015426-3655163`, `20260829T015454-3656637`, and
`20260829T015426-3655164`). The model proves that a later dispatch cannot relabel an already-begun
frame, a delayed resize barrier retains its completed frame generation, and the next frame adopts
the newer dispatch. REUSE 6.2.0 is green (`20260829T015426-3655165`).

The exact committed fallback replay retains the filed rapid samples, then drains in 5,810 ms at
terminal/admitted/dispatched/presented `49/49/49/49` and repaints an independent orbit in 2,046 ms
at `62/62/62/62`. Its bounded console evidence carries `frame-bound=1`, GHOST button/key edges are
balanced, the held mask is zero, and page/lifecycle errors are empty
(`ledger/buildlogs/20260829T015907-3660655.log`). SwiftShader remains diagnostic software and the
hardware-only native selection/transform predicate is deliberately not promoted.

The same exact product also passes the complete fallback fidelity battery: 53 steps, 160 native
states, 803 validated presentations, 9/9 workspace transitions, eight rapid-burst transitions,
three same-pose comparisons, move/undo, matched DOM/GHOST button coordinates, and zero hard
warnings or page errors (`ledger/buildlogs/20260829T020143-3662703.log`, consumer
`20260829T020618-3666228`). This remains software-adapter coverage, not hardware pixel closure.

The final CAPTURE relink and committed-state locked no-work proof are
`ledger/buildlogs/20260829T015729-3659214.log` and
`ledger/buildlogs/20260829T020047-3661574.log`. CAPTURE preflight is green
(`20260829T015907-3660654`). Exact product identities are:

- `blender_browser.js`: `06505f5705bf` (709,920 bytes)
- `blender_browser.wasm`: `fe50fe1a5bed` (120,337,716 bytes)
- `blender_browser.wasm.orig`: `025682159147` (118,988,932 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `6d8de4bc40ed` (13,812 bytes)

Resize source/trace contracts remain green (`20260829T015259-3653578/3653580`). The fallback live
probe retains only its already-filed legacy `5/3` present-churn failure despite coherent resize
state (`20260829T015304-3653624`), so no P0-E pixel claim is made. Direct M4 remains RED at the
unsupported Apple-pixel binding (`20260829T015502-3656683`); authoritative container-backed
regression restores M0 6/6 while M1-M8 retain their named strict/APPLY/hardware/product boundaries
(`20260829T015653-3658192`). P0-I/J remain open for the exact Apple deterministic-freeze run and
same-generation composed gauntlet. Final-tree REUSE 6.2.0 is green
(`20260829T020734-3666676`).

## Bind terminal presentation evidence to encoded VIEW_3D content

Frame provenance removed one false label, but a validated frame-bound surface copy still did not
prove that its persistent backbuffer contained the 3D region affected by input. A WM frame can
present chrome or retained backbuffer bytes without successfully encoding the viewport background,
grid, and final display composite. On the deterministic Apple failure, matching terminal,
admitted, dispatched, and presented generations would therefore still leave two materially
different explanations: a complete input frame was presented but pixels stayed stale, or the
present was valid while the intended VIEW_3D content never entered that frame.

Commit `d90aee1` adds a separate, bounded content trace. `WGPUContext::begin_frame()` opens it only
when a fully dispatched terminal input generation has not yet acquired a strict content receipt.
`WGPUFrameBuffer::debug_note_draw()` records the same successfully encoded draw plans already used
by the resize and loader contracts without sharing or resetting their state. A trace is complete
only when the exact input generation contains offscreen overlay-background and stock-grid draws,
then a direct-window OCIO display composite, with the frame ending on a window target. The browser
surface validation callback publishes a monotonic `contentPresented` generation only for that
snapshot. Input callbacks, bounded recovery, resize episodes/barriers, surface ordering, and
adapter policy are unchanged.

The producer contract failed first on the absent content predicate
(`ledger/buildlogs/20260829T021836-3674711.log`). The final 57-mutation/22-delivery source model,
96-case native/wasm32 behavior model, integrated WebGPU/GHOST suite, canonical freeze/replay, and
the real windowed Wasm objects are green (`20260829T022932-3686147`,
`20260829T023055-3689060`, `20260829T022932-3686155`, and
`20260829T023133-3691534`). Patch 0303 applies exactly over the preceding frozen source and the
updated canonical snapshot remains byte-bound.

The CAPTURE relink and committed-state locked no-work proof are
`ledger/buildlogs/20260829T023337-3694050.log` and
`20260829T023444-3695190.log`. Exact product identities are:

- `blender_browser.js`: `b80ccc954b75` (710,108 bytes)
- `blender_browser.wasm`: `34c7d4b16992` (120,339,472 bytes)
- `blender_browser.wasm.orig`: `f6a096b53f13` (118,990,678 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `0bd8d5884659` (13,861 bytes)

The first fallback attempt was invalidated by an external WSLg Xwayland abort at the exact browser
close timestamp; its retained product evidence had zero page errors and valid content receipts up
to that point (`ledger/buildlogs/20260829T023520-3695431.log`). A fresh isolated-X run under pinned
Node 22.16.0 is green: action drain reaches terminal/admitted/dispatched/presented/content-presented
`51/51/51/51/51`, with 85 recorded draws (69 offscreen, 16 window), and the independent recovery
orbit reaches `64/65/65/64/64`, with 78 draws (63 offscreen, 15 window). Button/key edges are
balanced, the held mask is zero, the resize episode remains 1, and page/lifecycle errors are empty
(`ledger/buildlogs/20260829T023652-3696942.log`). REUSE 6.2.0 is green
(`20260829T023832-3698228`).

P0-I/J remain open. Direct M4 is still RED because this host cannot bind the required Apple pixel
receipt, and aggregate regression retains the named strict/APPLY/product boundaries. The driver
must run the exact deterministic freeze against `.wasm.orig` `f6a096b53f13`: if ordinary
`presented` advances but `contentPresented` does not, the loss is now localized to complete
VIEW_3D frame production; if both advance while native state or pixels stay stale, it is below
that content-bearing surface transaction. Only the repeated same-generation Apple interaction
series plus the composed 10/10 resize gauntlet can close P0-I/J.

## Retire an input tail after exact VIEW_3D content presentation

The strict content edge made one remaining source of self-inflicted queue pressure measurable.
Every terminal input restarted the full 180-tick recovery budget, and the helper continued issuing
periodic full-screen `WindowUpdate` events after that exact input generation had already encoded
and presented overlay background, stock grid, and the final OCIO display composite. The preceding
fallback battery needed 803 validated presentations for 53 steps. Those redundant retries can sit
ahead of the next sparse user action even though native input has already produced its successful
frame.

Commit `b4c04d1` gives the shared recovery helper one explicit input-tail target. A terminal input
sets the target; validation of a strict content-bearing surface transaction for that generation
retires the synthetic tail immediately. The optimization is deliberately fail-closed outside that
case: a replacement-drawable episode, newly accepted lazy resource, or any dropped draw clears
input ownership and leaves the original 180-tick generic recovery intact. Resize still owns its
completed-frame barrier, ordinary input still does not enter that barrier, and no adapter, receipt,
pixel tolerance, or completeness predicate changed. A later terminal input starts a fresh tail.

The contract failed first on the absent per-window tail state
(`ledger/buildlogs/20260829T031018-3716984.log`). The final 101-case native/wasm32 behavior model,
79-mutation recovery source contract, resize-trace terminal-path mutations, and integrated
WebGPU/GHOST matrix are green (`ledger/buildlogs/20260829T031653-3728774.log`). REUSE 6.2.0 is green
(`ledger/buildlogs/20260829T031746-3730559.log`).

The CAPTURE relink and committed-state locked no-work proof are
`ledger/buildlogs/20260829T031808-3730798.log` and
`ledger/buildlogs/20260829T032142-3733980.log`. CAPTURE preflight is green
(`ledger/buildlogs/20260829T032734-3737899.log`). Exact product identities are:

- `blender_browser.js`: `0ce224a7fc73`
- `blender_browser.wasm`: `0c73f8a1f21a`
- `blender_browser.wasm.orig`: `e61df1b64f7b` (118,991,717 bytes)
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `8f266d4cf283`

One first fallback browser was externally closed by WSLg during settle with zero product page
errors (`ledger/buildlogs/20260829T031943-3732136.log`); it binds no verdict. The fresh exact replay
passes: action drain reaches terminal/admitted/dispatched/presented/content-presented
`49/49/49/49/49` in 5,624 ms, and the independent recovery orbit reaches `62/62/62/62/62` in
748 ms, with balanced input and zero page/lifecycle errors
(`ledger/buildlogs/20260829T032029-3732691.log`). The full fallback battery and independent consumer
pass 53 steps, 181 native states, 724 validated presentations, 9/9 workspace transitions, three
same-pose comparisons, move/undo, and zero hard completeness warnings or page errors
(`ledger/buildlogs/20260829T032154-3734050.log`,
`ledger/buildlogs/20260829T032614-3736593.log`). Rapid-source and same-generation hardware-gauntlet
self-checks remain green (`ledger/buildlogs/20260829T032749-3737999.log`,
`ledger/buildlogs/20260829T032749-3738000.log`). All local pixels are software-adapter diagnostics.

Direct M4 remains honestly RED at the Apple pixel boundary, while container-backed regression
restores M0 6/6 and retains every later named strict/APPLY/product boundary (results
`2026-08-29T03:27:17Z` through `03:27:18Z`). P0-I/J close only after the driver runs this exact
`e61df1b64f7b` generation through the deterministic freeze 10/10 and the composed P0-D/E/F/I
hardware gauntlet.
