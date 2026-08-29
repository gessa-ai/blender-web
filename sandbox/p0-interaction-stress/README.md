<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# P0-I/J cumulative-interaction diagnostic and Apple acceptance producer

`capture_diagnostic.mjs` reproduces the filed 10-orbit, 10-pan, 10-zoom sequence against the real
windowed Wasm product. It couples screenshots to Blender-native workspace, region, scene, and Cube
projection state so an off-screen object is not mistaken for a dropped geometry draw. It also
censuses every hard bind-group completeness warning rather than naming one expected shader. The
post-stress header pass requires nine state-changing workspace clicks while proving that DOM click
and GHOST press coordinates are identical. Moving back into the canvas between transitions
prevents a tooltip from turning the automation's settle delay into a false input failure; the
fallback diagnostic also allows the real workspace layout time instead of queuing later clicks.

`rapid_freeze_repro.mjs` separately preserves the driver's 350 ms screenshot cadence around the
exact Numpad-view, Select All, Deselect All, orbit, click, second-orbit, and move sequence. Those
immediate frames are diagnostic samples, not a liveness verdict: a busy WM worker can leave several
queued actions behind an unchanged canvas. The producer therefore records trusted DOM events and
worker-side GHOST press/release counters, plus a held-button mask that must return to zero. Within
12 seconds on hardware, the complete terminal MMB/G/click edge sequence must reach GHOST, Blender's
modal stack must drain, pixels must change, and WM-tick, presentation, and input-retry counters must
advance. The input-tail evidence distinguishes queue admission, dispatch after Blender's WM event
consumer, and clean surface presentation; each boundary must reach the last terminal input
generation. The hardware verdict also requires native state proving that the click selected Cube,
the second orbit changed the view rotation, and the confirmed `G` changed Cube location. One
independent recovery orbit must then change rotation again without moving Cube. (The software-only fallback
allows 30 seconds because SwiftShader validation is substantially slower and does not bind the
hardware-only GPU-pick/state predicate.) It reports
whether the rapid action frames were identical without treating identity alone as failure. Page or
browser lifecycle errors always fail. The default lane is SwiftShader and binds no pixels; on the sanctioned
Apple diagnostic host set `BW_P0_RAPID_HARDWARE=1` to omit the software-adapter flags and record the
adapter info. Hardware mode rejects fallback, absent-status, incomplete-info, and software-token
adapters before the interaction sequence. A timeout preserves every rapid sample, the last live
counter snapshot, trusted DOM tail, terminal GHOST delivery/mask, Blender modal/state trace, and
pointer-lock diagnostics so failure can be localized without another relink. This focused
diagnostic does not replace the immutable hardware
receipt below.

Set `BW_P0_SPARSE=1` to run the complementary slow/sparse discriminator. It leaves 650 ms between
the view/select/deselect samples, sends exactly one middle-mouse orbit, and queues no later input
until that orbit either reaches balanced GHOST delivery, WM admission/dispatch, validated surface
presentation, strict VIEW_3D content presentation, a confirmed and retired `VIEW3D_OT_rotate`,
changed native view state, and changed pixels, or exhausts the same 12-second Apple bound. The
rotate invoke/confirm/terminal/active counters sit after GHOST-to-WM delivery, so a failure now
separates a retained modal operator from a normally retired operator whose frame went stale. Only
then does it send the filed Cube click. After one more real 650 ms pause it sends exactly one
navigation orbit without waiting for the asynchronous selection continuation to finish. When that
modal is still active, navigation events return bare `OPERATOR_PASS_THROUGH`, which leaves the
modal installed while allowing the viewport keymap to invoke and retire `VIEW3D_OT_rotate`
immediately; they never enter the continuation's retained-input FIFO. State-changing ordinary
input remains retained until the pick settles. The combined drain requires both input stages, a
retired selection continuation,
exactly Cube selected, a changed view rotation, strict content pixels, and an unchanged Cube
location. The click point is Blender's own projection of the Cube origin into the live `VIEW_3D`
window, converted from Blender's bottom-left window coordinates to the browser canvas; the producer
does not guess a stale screen coordinate after the first orbit. A bounded
per-poll timeline preserves every generation, pixel hash, held-button mask, native state, and modal
stack, so a hardware failure identifies the first stalled boundary instead of treating an
immediate identical screenshot as permanent freeze. This exact orbit -> click -> orbit order is
load-bearing: the click, not the already-retired first orbit, triggered the selection-readback
error popup in the diagnosed candidate. Every sample also carries the global draw-drop generation
and the browser selection-validation pending/failure counters, distinguishing a synchronous draw
deferral, a validation callback that never settles, and an asynchronously rejected selection draw
without changing selection or redraw policy. The continuation telemetry additionally binds GPU
session/attempt/result/replay/failure generations, the current GPU phase (`0` inactive, `1`
session, `2` validation pending, `3` retry pending, `4` retry ready, `5` readback pending, `6`
result ready, `7` failed), separate GPU/query/combined readback status, modal timer progress,
queued input, and replay/finish edges. These are read-only discriminators; they do not alter the
selection timeout, input ordering, redraw policy, or hardware acceptance bar.

The deterministic-freeze acceptance bar is ten independent slow/sparse Apple runs against one
exact CAPTURE generation. Hardware mode requires an immutable run label, the expected
`wasm.orig` SHA-256, and a new output path. It hashes all five local product files, matches the
local and served split manifests, pins the browser stack and accepted adapter, and creates the JSON
only after the run passes. Produce and validate the series with:

```sh
orig_sha=$(sha256sum build-wasm-windowed-opt/bin/blender_browser.wasm.orig | awk '{print $1}')
evidence=sandbox/p0-interaction-stress/sparse-hardware-evidence
mkdir -p "$evidence"
for attempt in 01 02 03 04 05 06 07 08 09 10; do
  run="mac-m4pro-p0j-sparse-${attempt}"
  BW_P0_RAPID_HARDWARE=1 BW_P0_SPARSE=1 \
    BW_P0_RUN="$run" \
    BW_P0_EXPECTED_WASM_ORIG_SHA256="$orig_sha" \
    BW_P0_OUTPUT="$evidence/${run}.json" \
    "$PWD/tools/emsdk/node/22.16.0_64bit/bin/node" \
    sandbox/p0-interaction-stress/rapid_freeze_repro.mjs 8123 || exit 1
done
.host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/analyze_sparse_hardware_series.py \
  "$evidence"/mac-m4pro-p0j-sparse-{01,02,03,04,05,06,07,08,09,10}.json
```

The series consumer reruns every per-document selection, navigation, native-state, pixel, timeout,
page/lifecycle, stack, adapter, and product assertion. It rejects fewer or more than ten runs,
duplicate labels/timestamps/paths, or any cross-run source, stack, adapter, or product drift. This
focused 10/10 discriminator complements rather than replaces the broader repeated interaction and
same-generation P0-E gauntlet below.

Before that broader battery, schema v2 replays the driver's tighter total-freeze isolation:
Numpad 1/3/7/0/4, Select All, Deselect All, MMB orbit, trusted Cube click, `G X 2` plus undo, and a
second MMB orbit. Each changing view is coupled to settled Blender-native perspective/rotation and
new pixels. Each orbit must advance the read-only `_bw_redraw_retry_count` generation and change
the canvas within the 12-second bounded recovery ceiling; the measured settle time is retained.
Hardware must select exactly Cube through the trusted viewport click. SwiftShader may cancel its
known asynchronous failed GPU pick, use Select All only as a liveness canary, then restore Cube-only
selection through a real, coordinate-checked Outliner click before visual comparison begins.

After the same-run front/Frame-Selected reference is established, the producer also drives two
back-to-back `Numpad3 -> Numpad7 -> Numpad0 -> Numpad1` cycles. It waits only for each Blender-native
view transition, never for intermediate pixels, then requires the final front pose to settle within
12 seconds and remain byte-identical for three more seconds. Ordered trusted DOM key receipts,
strictly increasing native state sequences, advancing present/input-retry counters, and a third
same-pose region diff bind the suppressed-present coalescing path without changing the product.
Every screenshot additionally samples a 12-stage witness for the stock dashed-line immediate
shader used by the camera frame and modal guides. The consumer requires monotonic attempt/accept
counters through camera entry, zero asynchronous validation rejection, and the same camera pixels
before and after the cancelled Numpad4 no-op. This separates a genuine draw-stage failure from a
surface replay that retained older pixels.

The default Linux run deliberately exercises the Apple-verified pointer-lock rejection fallback
and forces SwiftShader. It is diagnostic-only and binds no hardware or pixel receipt.

Serve an already-linked product and run the capture plus both contracts:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-interaction-stress/capture_diagnostic.mjs 8123
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/analyze_diagnostic.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_source.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_buffer_texture_pending.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_buffer_texture_readback_pending.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_auxiliary_cache_redraw.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_capture_contract.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_immediate_dashed_trace.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_rapid_input_drain.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_view3d_rotate_retirement.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_select_stream_continuation.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_select_draw_admission.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_select_draw_validation.py
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_select_readback_same_turn.py --self-check
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_select_wall_timeout.py --self-check
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/p0-interaction-stress/rapid_freeze_repro.mjs 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir BW_P0_SPARSE=1 \
  harness/buildwrap.sh node sandbox/p0-interaction-stress/rapid_freeze_repro.mjs 8123
```

The analyzer requires a running product, semantic pixels through the final orbit, Blender-native
Cube presence, stable three-to-six-second settle pixels, zero page/lifecycle errors, and zero hard
completeness warnings. It also requires all nine post-stress workspace transitions and the full
DOM-to-GHOST button-coordinate canary. An already-active tab is deliberately excluded because it
is not a workspace transition.

The strengthened P0-J path establishes a same-run front-view/Frame-Selected reference, returns to
that exact Blender-native pose after the rapid view burst, the cumulative battery, and the final
orbit, then compares actual pixels. The full VIEW_3D must stay within a 1% changed-pixel ceiling; narrower
viewport-header, toolbar-icon, Outliner-text, and workspace-label regions use a 0.2% ceiling. This
detects the filed missing Cube/grid, clipped leading text, missing icons, and retained grey bars
without relying on PNG byte size. A real `G X 2 Enter` followed by `Control+Z` must also change and
restore Blender's native Cube location after the stress sequence.

On the driver-operated Apple host, run the same producer in hardware mode against an already-served
CAPTURE generation:

```sh
node sandbox/p0-interaction-stress/capture_diagnostic.mjs \
  --hardware --port 8123 \
  --run mac-m4pro-p0ij-<label> \
  --bin-dir build-wasm-windowed-opt/bin \
  --expected-wasm-orig-sha256 <64-lowercase-hex>
.host-tools/bin/python3.13 sandbox/p0-interaction-stress/analyze_diagnostic.py \
  sandbox/p0-interaction-stress/hardware-evidence/mac-m4pro-p0ij-<label>/diagnostic.json
```

P0-I/J closure requires repeated clean hardware runs, not one lucky pass. After producing at least
two fresh immutable runs against the same candidate, validate them together:

```sh
.host-tools/bin/python3.13 sandbox/p0-interaction-stress/analyze_diagnostic.py \
  --hardware-series \
  sandbox/p0-interaction-stress/hardware-evidence/mac-m4pro-p0ij-<label-1>/diagnostic.json \
  sandbox/p0-interaction-stress/hardware-evidence/mac-m4pro-p0ij-<label-2>/diagnostic.json
```

The series check reruns every single-receipt assertion and rejects duplicate run labels or capture
timestamps, non-hardware evidence, and any change in producer, pinned browser stack, accepted Apple
adapter, local/served generation, or five-file product inventory between runs.

Before closing P0-I/J, compose that repeated interaction series with the independent ten-attempt
P0-E resize receipt from the same candidate:

```sh
.host-tools/bin/python3.13 sandbox/p0-interaction-stress/verify_hardware_gauntlet.py \
  --interaction sandbox/p0-interaction-stress/hardware-evidence/<interaction-run-1>/diagnostic.json \
  --interaction sandbox/p0-interaction-stress/hardware-evidence/<interaction-run-2>/diagnostic.json \
  --resize-evidence sandbox/m4-resize-recovery/hardware-evidence/<resize-run> \
  --bin-dir build-wasm-windowed-opt/bin \
  --expected-wasm-orig-sha256 <64-lowercase-hex>
```

The composer reruns the complete interaction consumer and the independent resize consumer. It then
rehashes every interaction screenshot and its exact evidence inventory, then requires both evidence
families to identify the current interaction producer, the same five exact product files, local and
served CAPTURE generation, pinned browser stack, and accepted Apple adapter. Thus a clean
interaction series cannot be combined with an older P0-E receipt, and a coherently edited
interaction identity cannot bypass the resize consumer's fresh product/image rehash. Its
device-free mutation contract is:

```sh
harness/buildwrap.sh .host-tools/bin/python3.13 \
  sandbox/p0-interaction-stress/verify_hardware_gauntlet.py --self-check
```

Hardware mode is Apple-only and pins Node 22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and Chromium
149.0.7827.55. It prefers `adapter.info.isFallbackAdapter`, rejects absent/fallback/software
adapters, verifies local and served split manifests against the requested `wasm.orig`, and creates
the immutable evidence directory only after those checks pass. Pointer lock may succeed or take the
single bounded rejection fallback; either path must leave zero page errors.

Hardware input receipts retain the five-second delivery bar. Only the explicitly non-receipt
SwiftShader lane permits a 15-second workspace-event window for synchronous Shading workspace
construction.

The source contract verifies that vertex and index buffers preserve SSBO binding intent while
first-use allocation is pending, and that numbered patch 0297 carries both changes. The original
diagnostic emitted six `gpu_shader_3D_polyline_flat_color` failures with surviving bindings
`[0,1,2,3]`, assembled bindings `[3]`, and missing bindings `[0,1,2]`. A device-free PASS proves the
specific retry contract and does not close P0-I's required Apple-hardware pixel verification.
The adjacent buffer-texture contract verifies that patch 0298 preserves the eventual correctly
shaped backing plus its separate pending allocation dependency. In particular, float1-3 sampler
buffers must wait for their expanded float4 backing rather than binding the smaller primary buffer.
Its device-free PASS likewise binds only that state transition, not pixels.
The readback-readiness sibling contract covers the next float1-3 transition: a valid primary VBO
whose browser `MapAsync` readback has not settled yet. The eventual expanded float4 binding remains
exactly Pending, and successful cache settlement publishes one bounded retry. A synchronous
non-pending absence stays hard Incomplete; failed/canceled callbacks, ordinary cache callers, and
exact ticket owners do not acquire a self-perpetuating redraw edge. The runtime also records each
distinct pending shader/set signature once (up to 128) so a hardware interaction pass retains the
full surviving/assembled/pending census without letting boot repetition consume the diagnostic.
The adjacent input-recovery contract also requires the production aggregate retry export and a
separate coalesced input-tail generation. Its tick-179 case proves the final accepted callback
starts one complete bounded tail instead of inheriting the last tick of an older readiness burst;
hardware evidence can therefore prove the callback path fired rather than accepting a source-only
hook.
The auxiliary-cache contract closes a separate first-use scheduling gap across the persistent
dummy-buffer, clear, blit, upload, empty-attachment, and triangle-fan caches. All 13 producers now
publish one coalescible redraw-readiness edge only when browser validation accepts a new handle;
pending work, rejection, null publication, and cache hits publish none. This prevents an accepted
first-use helper from remaining invisible after its original draw was dropped, but Apple pixels
remain the authority for P0-I/J closure.

The slow/sparse freeze discriminator retains two distinct input-delivery stages. `ghostInput`
counts the proxied HTML5 callbacks after they reach the WM worker; `wmInput` counts the matching
button, key, and cursor events from a GHOST consumer registered after Blender's own consumer. Each
isolated orbit must deliver middle-button press, motion, and release through both stages with both
held masks clear. A timeout can therefore distinguish a worker-callback success whose release or
motion never entered Blender's WM queue from a later modal, redraw, or presentation failure. These
are read-only diagnostics and bind no Apple pixel verdict by themselves.

The one-draw selection continuation contract in `verify_select_stream_continuation.py` binds the
temporary selection output to an ordered `GPU_USAGE_STREAM` resource. Browser validation,
clear/draw, and exact readback therefore remain in one queue epoch even though the temporary draw
engine is destroyed on return. While that owned readback is pending, state-changing ordinary input
is retained in a bounded FIFO and replayed in order, but navigation passes through immediately. The
slow/sparse producer isolates the exact triggering click, waits one real 650 ms user pause, then
sends one navigation orbit before requiring selection completion. If the continuation still owns
the modal stack, the evidence requires its replay counter to remain unchanged while the orbit
reaches the rotate-retirement, native-view, and pixel boundaries before Cube selection completes.
The rapid producer fails on any `WebGPU selection readback failed` report and
requires queued and recovery orbits to reach the exact rotate retirement boundary.
`BW_P0_STATE_ONLY=1` is a
software-adapter diagnostic only; Apple hardware mode rejects it, so it cannot satisfy the pixel
acceptance gate.

`verify_select_draw_retry.py` closes the adjacent semantic hole: a browser selection pass can own a
valid stream readback while one of that pass's first-use WebGPU draws was synchronously dropped.
The async select-next state snapshots the draw-drop generation, cancels that cleared result, and
waits for a later resource-readiness generation before executing the exact selection again. A
clean empty hit remains a valid miss; only an attempt proven to have dropped work is retried.
Shader-module and pipeline deferral now contribute to that generation just like an incomplete bind
group, rather than silently returning from batch/immediate drawing. Buffers first allocated by the
one-draw `G_FLAG_PICKSEL` context use its ordered transient resource gate, so a retry does not
recreate persistent allocations whose owner disappears before browser validation can publish them.

`verify_select_draw_validation.py` closes the next terminal-boundary gap. A browser batch that
encoded `Draw*` can still reject asynchronously after the synchronous admission guard disarms.
Each selection command now owns a balanced validation ticket; readback consumption waits for every
ticket, and a late rejection cancels the exact cleared result before retry. The failure generation
is selection-specific, so an unrelated UI draw drop cannot invalidate a genuine pick.

Browser selection failure teardown is deliberately non-modal. The continuation still replays every
retained input in order and emits one bounded console diagnostic, which this producer rejects, but
it does not populate the operator report list: Blender turns any such report into a popup that can
capture all later input and recreate the apparent total freeze. Native selection reports retain
their existing behavior.

`verify_select_readback_same_turn.py` binds the browser-only lifetime seam between queue submission
and mapping the selection staging buffer. The copy submit remains synchronous in the calling
JavaScript turn; `MapAsync` is registered immediately after that submit instead of waiting behind
asynchronous error-scope settlement. Mapped bytes remain private until both mapping and command
validation succeed, so the ordering fix cannot publish a rejected cleared selection result.

`verify_select_wall_timeout.py` binds the asynchronous viewport-selection fail-close to monotonic
elapsed time. The 10 ms modal timer is scheduler/coalescing dependent and its delivery count remains
telemetry only; a 30-second runtime ceiling prevents an abandoned callback from retaining the modal
operator indefinitely. Hardware evidence still uses the producer's stricter 12-second acceptance
bar, so this runtime correction does not relax the Apple gate.

`verify_select_readback_lifecycle.py` makes that seam observable without changing it. The exact
buffer path publishes monotonic generations for command submission, map registration, map callback,
validation callback, the two-leg join, and final ready-ticket publication. The slow/sparse producer
samples all six on every bounded poll and rejects a product missing any export. A hardware timeout
can therefore identify one stalled readback boundary instead of collapsing every case into the
same `Pending` ticket status; only Apple pixels can close the underlying freeze.

Each poll also records `selectionReadbackBoundary`, an automatic classification derived from the
counter deltas since the pre-action baseline. It preserves those raw deltas and labels the first
unfinished edge from selection admission through submit, mapping, command validation, join,
result consumption, and modal finish. Run the nine-case executable fixture with
`BW_P0_READBACK_CLASSIFIER_SELFCHECK=1`; this classifier is diagnostic and never converts a
software-adapter run into hardware evidence.
