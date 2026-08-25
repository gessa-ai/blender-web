<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Canonical WebGPU render-pipeline mapping parity smoke

This device-free M3.T10 reconciliation compiles Blender's canonical in-tree
`wgpu_pipeline` postimage directly for native and wasm32 against Blender's real
primitive, index-format, component, and fetch enums. The shared test also covers
the two-case transient uniform-buffer allocation transaction shared by
multi-viewport emulation and cross-format color blits,
the three-case mapped dummy-vertex-buffer creation transaction,
the fail-first/retry transactions shared by sampler/render-pipeline caches and the
per-shader compute-pipeline variant cache,
the atomic transient-handle publication shared by compute, direct/indirect batch, and
immediate bind-group builders plus the ordered bind-group gates used before command scopes,
16 direct-draw decisions, 28 multi-viewport/scissor decisions, 32 bottom-origin
window-backbuffer decisions, 21 ordinary offscreen viewport/scissor decisions, and
19 exact indirect-draw span decisions. Direct draws
resolve Blender's four signed backend parameters before WebGPU work, reject negative
first values and non-positive normalized counts, and preserve the full positive `int`
domain. Indirect draws cover signed input rejection, four-byte alignment,
16-byte array commands, 20-byte indexed commands, tightly-packed zero stride,
overlapping-but-aligned explicit stride, allocation bounds, and arithmetic overflow.
Multi-viewport draws preserve the signed raster transform while intersecting the
unsigned WebGPU scissor with the framebuffer. Legal zero and fully clipped rectangles
produce a contained zero scissor so pending load actions can still be consumed; negative
extents and device-invalid boundaries remain atomically rejected in both the direct and
indirect EEVEE-shadow paths. Their shared 16-byte `{layer,
viewport}` uniform allocation must publish a handle only on success; both paths
must return before queue or pass work when creation fails.
The color-blit fallback additionally rejects a missing shader module before pipeline creation,
the missing uniform before `WriteBuffer`, a missing bind group before command-encoder/pass
work, and failed compute encoder/pass/command-buffer creation before dependent work or submission
work. The source-order checks bind all three guards to the shipping method while the shared
native/Wasm allocation contract proves failure leaves the caller's buffer handle unchanged.
The indexed triangle-fan expansion likewise rejects a missing shader module before compute-
pipeline creation and uses the same tested encoder/pass/finish transaction, so any failed command
handle stops before expansion work or queue submission. Exact source-order checks bind both guards
to the shipping fan method.
Framebuffer full clears likewise use that tested render-pass transaction for both multi-attachment
clears and single-color-attachment clears. A failed encoder or pass now stops the layer loop before
dependent work, while a failed finished command buffer stops before submission; exact method-body
checks reject any retained unchecked command operation.
An all-layer explicit load clear additionally commits its pending load action only after every
selected layer's checked clear transaction succeeds. A failed layer remains pending so the next
draw retries instead of loading uncleared attachment contents; the device-free contract proves the
fail-first/retry state transition and exact shipping-source binding.
Ordinary single-subresource load clears use the enclosing draw submission as their commit boundary.
The first pass reserves each clear without consuming it, later same-epoch passes encode loads behind
that reservation, and a late attachment-view, bind-group, command-buffer, or submission failure
releases the complete set for a clean next-epoch retry. Generation-bound reservations prevent an
old callback from consuming a newer load-store bind. The six-case native/wasm32 contract covers both
late failures, same-epoch behavior, successful retry, and replacement isolation, while exact caller
census checks bind every direct, indirect, multi-viewport, and immediate draw completion.
Framebuffer blits likewise use the checked copy transaction for both the two-step stencil buffer
bridge and the raw texture-to-texture path. Encoder failure stops before either copy, and finished-
command-buffer failure stops before queue submission; exact method-body checks bind all three copy
operations to those two transactions.
Layered depth/stencil and renderable-color texture clears use one abortable encoder transaction.
Failure at the encoder, any per-layer view/pass, or the finished command buffer discards the whole
clear before submission, while the successful path retains one command buffer for every layer.
Native synchronous texture readback uses the same checked copy transaction before mapping its
staging buffer, so encoder or finished-buffer failure cannot reach mapping or queue submission.
Root texture copies retain their per-mip compatibility skips inside one checked command
transaction, so a failed encoder or finished buffer cannot be dereferenced or submitted.
Shader modules and render/compute pipelines use the scoped cache rather than null-only
publication. A shader retains its final WGSL while the complete required module set is pending;
a non-null error module rejects the set atomically, and draw/dispatch lookup recreates it before
pipeline creation. Every context, framebuffer, per-shader specialization, and context-owned
pipeline cache likewise publishes only after validation, out-of-memory, and internal scopes
settle. The one-shot mipmap module/pipeline pair instead reserves an ordered transient gate before
dependent command work. Rejected keys retry without disturbing accepted entries.
Async shader compilation additionally reads one locked instance/device/queue tuple from the latest
live context. Republishing one owner is atomic, destroying an older context cannot clear a newer
tuple, and destroying the newest overlapping context restores the previous live owner instead of
leaving the compiler handle-less. Seven native/wasm32 cases cover both teardown orders, coherent
replacement, restoration, last-owner cleanup, and duplicate cleanup.
Sampler cache misses additionally remain pending while validation, out-of-memory, and
internal scopes settle. A second lookup deduplicates the pending key; a non-null error
object is discarded, and a clean retry is published without exposing a provisional handle.
The cache owns callback state independently of the context lifetime.
Short-lived batch and immediate buffers use a separate ordered resource gate. Their provisional
handles may be consumed only by CPU-side encoding queued behind that gate; no dependent queue work
can run until validation, out-of-memory, and internal scopes accept the candidate. A null candidate
or non-null error object poisons only the current frame epoch, cancels every dependent submit, and
leaves a later epoch free to recreate the resource and retry.
The shared dummy vertex buffer uses the same scoped cache with one fixed key. Its
`{0,0,0,1}` payload is installed through `mappedAtCreation` before the creation scope is
popped, so no initialization write can overtake browser validation and no provisional buffer
can reach a draw. Creation and mapped-range failures both remain retryable.
The same rule applies to each specialization-keyed compute pipeline: a transient null
creation result must not become a retained variant that suppresses every later retry.
Every bind group created before its enclosing command scope now reserves the same ordered resource
gate, so a non-null error object cancels the dependent same-epoch command and a later frame can
retry. Direct and indirect compute share that pre-command gate and require zero uncaptured creation
errors before an accepted retry can publish its dispatch. Bind groups created inside an
already-scoped draw command remain covered by that complete command scope. Literal null guards
still preserve caller state. Exact source-order checks bind the pre-command gate to both compute
dispatches, all three context render helpers, both scissored-clear paths, and the indexed-fan
expansion, while the existing scoped command checks cover both compute dispatches, all
four direct/indirect ordinary/multi-viewport batch paths, mip generation, and immediate draws.
Before any of those compute, batch, or immediate encoders is allocated, the unique assembled
group-0 binding IDs must also equal the shader's exact surviving final-WGSL set. This keeps a
genuinely empty layout distinct from missing or partial resources and includes the injected
push-constant and multi-viewport uniforms. The six-case native/wasm32 contract covers empty,
complete, required-but-empty, partial, extra, and duplicate-assembled sets.
Framebuffer load-pass construction uses that same atomic publication rule before applying its
ordinary viewport or scissor. Callers therefore receive either a valid initialized pass or a
null result, without a failed `BeginRenderPass` handle being used inside the factory first.
Window-backbuffer rectangles preserve that same raster transform while converting
Blender's bottom-origin viewport and optional independent scissor with widened
arithmetic. Both rectangles must validate before a render pass is allocated; a legal
empty state remains encodable while the explicit scissor is clipped without narrowing
its signed frontend geometry.
Ordinary offscreen passes convert the same bottom-origin rectangles to WebGPU's top origin,
preserve signed viewport transforms, and clip an enabled scissor independently. Clip-space and
readback flips preserve orientation and row order but cannot relocate a partial rectangle.
The oracle's 6x5 viewport and viewport/scissor intersection are included verbatim.
It additionally covers 15 direct compute-dispatch decisions and 13 indirect
compute-dispatch ranges. Direct counts reject negative axes, non-positive published
limits, and values above those per-axis limits while preserving zero-count no-ops;
indirect commands require four-byte alignment and one complete 12-byte `[x,y,z]`
record without overflow. It covers all 11 primitive rows, all 33
primitive/index-format combinations, and all 96
combinations of eight vertex component types, four valid component lengths, and
three fetch modes. It also covers every one of the 32 shader input types in the
dummy-attribute plan and requires a zero-stride, vertex-stepped binding that remains
constant for arbitrary vertex and instance ranges. Before direct/indirect batch or immediate
command encoding, the complete vertex plan must resolve into an ordered non-null handle list;
failure preserves the caller-owned list, while an empty plan remains valid for procedural draws.
The matching index-buffer transaction distinguishes a required indexed draw from a valid
non-indexed draw before pipeline or command work. A failed frontend index upload therefore rejects
direct and indirect batches instead of silently omitting `DrawIndexed` or reinterpreting a
20-byte indexed indirect command as a 16-byte non-indexed command; triangle-fan batch and immediate
paths bind the same resolved transient handle. Failure preserves the caller-owned handle and the
non-indexed case publishes an explicit empty handle.
The browser compositor additionally treats handle truthiness as only a provisional result:
backbuffer and present-pipeline candidates remain unpublished until validation/OOM/internal scopes
complete cleanly. Per-frame presentation is stricter about time: a complete command buffer reaches
`Queue::Submit` synchronously in the same event-loop turn as surface-texture acquisition, before
either encoding or submission scopes can settle. Both scope groups then join before first-pixel/
keepalive publication. The contract covers literal null failures, non-null error objects, pending-
state publication, same-turn submission, both callback orders, scope failure, and one clean commit.
Resize requests remain separate from the last configured surface extent: a current validated
candidate configures and publishes the surface/backbuffer state atomically, stale candidates retry
the newest request, rejected candidates retry from the next present without another resize event,
and presentation requires exact authoritative, backbuffer, and acquired-surface extents. The pinned-
Dawn software control exercises the same shipping helpers against real non-null error objects but
remains explicitly non-receipt evidence.
The browser cursor follows the same realm boundary deliberately. Standard shape and visibility
requests publish shared atomic state from the WM worker, while the first main-thread shell script
maps all 46 supported `GHOST_TStandardCursor` values onto the DOM canvas. Arbitrary bitmap/mask
cursors fail honestly instead of reporting a no-op success. The pinned source contract rejects
enum drift, missing release publication, direct worker DOM access, and missing runtime exports;
the Node behavior contract covers every mapping, hide/show, generation ordering, and recovery from
temporarily missing module, canvas, or export state.
Continuous cursor grabs use the browser Pointer Lock API rather than claiming a worker-local no-op
success. Wrap and Hide modes accumulate `movementX/Y` into saturated virtual GHOST coordinates;
Wrap retains a visible Blender software cursor while Hide remains invisible. Disable cancels both
active and deferred lock requests, Normal preserves visible-pointer SDL semantics, and absolute
cursor warp remains honestly unadvertised. The source contract rejects 13 ordering, motion,
visibility, and capability mutations; the real worker-topology harness covers lock entry, relative
motion, and release, while the product diagnostic drives Blender's actual middle-drag navigation.
The synchronous GHOST window constructor additionally consumes only a complete pre-main browser
presentation bundle. Its worker-side transaction validates the initial backbuffer before main
starts, then puts non-fallback and unknown-status adapters through scoped canvas configuration,
surface clear submission, and queue-work completion. An exact browser-reported fallback adapter
uses a separately labeled diagnostic compatibility path because Chromium invalidates that
adapter's external Instance when a WebGPU promise follows canvas configuration; this path binds no
receipt. Fourteen pinned-Node cases cover device, canvas, surface, error-object/null backbuffer,
synchronous/delayed/omitted configuration telemetry, strict work completion, exact fallback
selection, cleanup, loss, and successful publication. The native/wasm32 decision table
independently rejects every partial status before the existing window-publication transaction can
run.
Surface acquisition is a separate per-frame transaction. The status contract accepts a texture
only for optimal or suboptimal success, retries a timeout without poisoning the configured state,
reconfigures outdated/error or malformed-success results, and recreates a lost surface. The
synchronous GHOST swap result reports whether this frame actually reached the asynchronous
validation transaction instead of manufacturing success for an acquisition that never started.
Device loss is stronger than that surface result. The pre-main worker now owns the imported
browser device's `lost` promise in its creation realm and publishes a generation-bound terminal
record before the device; a stale promise cannot overwrite a replacement record. The callback-owned
state samples that exact record before every queued configuration, publication, submission, and
present completion as well as each public swap boundary, then clears the context handles on the
first owner-side terminal propagation. The fallback C++ acquisition path installs a descriptor
callback that captures only the same shared state. Eleven pinned-Node
cases cover pending, pre-entry, post-entry unknown/destroyed, and stale loss order; a 13-case
native/wasm32 contract covers generation binding, sticky state, apparently successful surface
status override, and callback lifetime. Pinned Dawn's software control additionally forces a real
loss and proves a non-null post-loss error texture is blocked, without creating a receipt.
Every completion that can outlive the non-reference-counted GHOST context also registers with one
synchronized owner gate. Destruction stops new delivery, waits for concurrent delivery on other
threads, and remains reentrant when the active callback destroys its own context; no completion
retains a raw `this` pointer.
The Blender GPU backend now applies that completed-scope rule to every short-lived command and
direct queue write. A FIFO scheduler reserves queue chronology before browser error scopes can
yield, so a delayed submission cannot move behind a later `WriteBuffer` or `WriteTexture` call.
An encoding or submission failure cancels all later queue mutations from the same frame epoch;
`begin_frame()` opens a retry epoch. The six-case compute and buffer models cover null encoder,
pass, and command handles, non-null encoding and submission error objects, clean submission,
same-epoch cancellation, and next-epoch retry. Shipping-source checks require the sole direct
`Submit`, `WriteBuffer`, and `WriteTexture` calls to remain inside those scoped helpers.
Synchronous completion and cancellation drain through one iterative owner rather than recursively:
a failed head cancels 100,000 already-resolved followers with bounded stack use. Exact queued-epoch
reference counts retain a failed epoch only while it is current or still names queued work; a
second 100,000-failure sequence proves completed epochs do not accumulate and a clean epoch still
executes afterward on both native and wasm32.
The strip contract requires
`Uint16`/`Uint32` only for indexed
line-strip, line-loop, and triangle-strip pipelines and keeps every non-strip
topology at `Undefined`, matching pinned Dawn validation. This also includes the
resolved normalized signed-I10 mapping to `Snorm8x4`. A cache-key contract builds
two real vertex formats whose distinct two-alias lists concatenate to the same raw
bytes and requires length-framed hashing to keep their shader-location layouts
separate.

Run only through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/wgpu-pipeline-integrated-smoke/build.sh
```

To diagnose the pre-main WM-worker transaction against an already served windowed product, run:

```sh
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  harness/buildwrap.sh node sandbox/wgpu-pipeline-integrated-smoke/live_preinit_boot.mjs 8123
```

Pass `/` as the optional second argument to bind the same live diagnostic to the
canonical local-server root instead of the explicit `/windowed.html` path.

This headed check forces Chromium's SwiftShader adapter under its GPU-test initialization, then
requires the adapter to report fallback status. After `WM_main`, it bounds first-tick settlement,
requires a positive tick delta across two further samples, sends trusted mouse input, and requires
both another WM tick and a new presentation with no device loss, rejected present submission, or
rejected present transaction. It also requires the real product's 46-shape cursor bridge to consume
one shared-memory snapshot and apply the matching CSS cursor to `#canvas`. Its explicit
`diagnostic-nonreceipt` result never binds a GPU receipt or satisfies the live-pixel gate.

The triangle-fan row deliberately exercises the backend's fail-visible fallback:
both executions must emit the exact canonical `BLI_assert_unreachable` diagnostic
before returning `TriangleList`. Native and Wasm stdout and stderr must be
byte-identical.

The driver checksum-binds Dawn `36cf1fae` (including its stride-zero pipeline,
16/20-byte indirect draw-range, viewport/scissor, and direct/indirect compute validation), emcc 6.0.5,
Node 22.16.0, matching native/Wasm fmt headers, Blender's canonical clean-pin replay,
and 33 exact pipeline/batch/framebuffer/texture/vertex-format/enum/assert/presentation/cursor source inputs before
evidence allocation. It also
requires both shipping direct and indirect batch paths to call the tested strip-format
mapping. Both targets build only through `scripts/ninja-locked.sh` and finish
with exact no-work checks.

No WebGPU instance, adapter, device, render/compute pipeline, render/compute pass, draw, dispatch,
or pixel evidence is created. Live descriptor, dispatch, and pixel validation remain owned by
`M3-LINUX-REPLAY` and require an accepted hardware adapter.
