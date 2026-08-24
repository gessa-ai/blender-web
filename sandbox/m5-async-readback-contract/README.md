<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 owned-readback and framebuffer continuation contract

This device-free reconciliation binds the current shipping L-B owned-result API
and the C1 Select-Next object-pick continuation to Blender's real
`gpu_readback.cc` and `gpu_select_next.cc` on native and wasm32. The shared
contract covers ready/failed ownership, undersized consume, cancellation,
Pending-to-Ready conversion, all three Select-Next modes, exact-key replay,
immutable ID-map transfer, repeated replay, terminal failure, null requests,
and overlapping-request rejection.

The same contract now exercises the production owned-transform request used by
asynchronous framebuffer region reads. The public color/depth entry points keep
native backends immediately ready while WebGPU owns one exact subresource ticket,
then applies the existing crop, row-order, channel-extension, and format
conversion only after that ticket settles. This is the shared primitive used by
the later legacy-selection continuations and the first converted depth-pick
consumer; it does not claim the remaining callers are converted.

The draw-selection layer now has its own owned raw-buffer request on top of that
framebuffer primitive. Native and wasm32 contracts cover pending and immediate
completion, exact byte-size rejection, out-of-viewport empty results, viewport
clamp/stride realignment, backend failure, and cancellation. Edit-mesh click
selection now replays sample/nearest queries through that request while restoring
the exact element-range context that produced each raw ID. The contract covers
pending output preservation, exact sample and nearest results, Manhattan distance,
multi-stage replay, context restoration, query-drift rejection, and cancellation.
Edit-mesh box, lasso, and circle selection now share a separate owned bitmap session.
It retains each raw request plus the inclusive rectangle, polygon mask, strict circle
radius, and producing element-range context until a bounded operator continuation
replays it. Pre-deselect and all later mesh mutation remain behind settlement. Circle
input events queue in order behind the active request, while the exact producing
selection operation, center, and radius are restored before each replay.

Cursor placement, Center View to Mouse, the depth eyedropper, ordinary navigation, and direct
dolly now share the exact owned progressive 0/2/4-pixel depth request across browser event-loop
ticks. Their separate contracts bind native immediate completion, exact event/orientation or
smooth-view replay, stock no-hit fallbacks, supersession, timeout/cancellation, and producing-state
drift rejection. Painting, zoom-border, and NDOF consumers remain synchronous, so the family census
remains open.

`verify_source.py` separately binds the public texture/storage/framebuffer APIs,
the owned draw-selection request and exact query session, exact WebGPU tickets,
temporary select-engine ownership transfer, and the bounded object/edit-mesh
selection continuations. All three non-viewport eyedroppers share one owned
window snapshot while browser mapping is pending and preserve native immediate
completion.
It also requires the three still-partial/synchronous caller families (depth pick,
depth cache, and WM window capture) to stay visible. The synchronous selection-buffer API remains
as the native/direct-execution fallback, but its edit-mesh gesture consumers no longer
use it during an active browser continuation. The screenshot operator has its own
owned-capture continuation contract; the ledger row remains `partial` for these three
families.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-async-readback-contract/run.sh
harness/buildwrap.sh bash sandbox/m5-async-readback-contract/selfcheck.sh
```

Both compilations use `scripts/ninja-locked.sh`. The driver requires the
canonical clean-pin replay, Linux x86_64, clang++ 17, emcc 6.0.5, pinned Node
22.16.0, and byte-identical native/Wasm fmt headers before accepting evidence.
No WebGPU instance, adapter, device, browser profile, split product, or milestone
receipt is created; live object-pick proof remains part of the s7-blocked M5
browser receipt.
