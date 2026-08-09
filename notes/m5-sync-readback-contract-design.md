<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M5 sync-readback contract design (r49, design-only)

Decision-grade design for the caller-facing GPU readback contract that M5 (interactive
parity) needs. GOAL.md M5 requires event-simulate click-pick with operator-trace parity;
click-pick reads GPU select buffers back, and those readbacks return ZEROS in the windowed
browser build today. This note delivers the mechanism verdict, the caller census, the
recommended contract (with rejected alternatives), the table-OOB disposition, the M5
acceptance session spec, and an effort estimate plus lane structure.

Scope fence honoured: this lane authored only this note, `sandbox/m5-readback-design/*`,
and the ledger r49 line. No edit to `upstream/`, `gpu/webgpu`, `harness/`, `oracle/`, or
`tests/golden/`. Tree at authoring/probe time: `b7dd8f2` (branch `agent/m2.5-python-boot`),
no active relink, only `sandbox/m5-readback-design/` untracked.

---

## 0. TL;DR

- **Mechanism:** the sync path returns zeros because a same-thread blocking wait
  (`WaitAny(f, UINT64_MAX)`) halts the very WM-worker event loop that must run to deliver
  the WebGPU `mapAsync` completion. It is NOT "WaitAny works on the worker" (the F9-D
  prediction). Two proven facts compound: (a) the port's blocking `WaitAny` is
  ASYNCIFY-only and, under ADR-006 (no JSPI/asyncify), returns immediately unfulfilled;
  (b) even a hand-rolled `Atomics.wait` would deadlock, because the map callback is a
  microtask on this same worker's loop and the per-thread JS-object table (ADR-007) forbids
  offloading it. The decisive lever, proven twice (patches 0117, 0125), is
  `CallbackMode::AllowSpontaneous` + return-to-loop: the completion fires between
  `emscripten_set_main_loop` ticks with no `ProcessEvents` dependency.
- **Census:** two backend seams funnel every readback: texture reads through
  `WGPUTexture::read` (wgpu_texture.cc:1201, WaitAny at 1277) and buffer reads through
  `webgpu::Buffer::read` (wgpu_buffer.cc:132, WaitAny at 164). Seven M5-critical caller
  families sit above them; the critical few that MUST work for click-pick are the object
  pick (a StorageBuffer read) and the legacy element/box select (a framebuffer texture
  read).
- **Recommended contract:** kick-on-request, latch-on-tick, consume-on-settle. Promote the
  proven `AllowSpontaneous` primitive from diagnostic to production at both seams, add an
  async/poll GPU API, convert the pick + depth + colour-sample callers to
  request -> settle-barrier -> consume, and expose a `wait_for_gpu_idle()` barrier that the
  M5 harness (and the standalone player frame loop) drives. This is event-simulate
  compatible and operator-trace-faithful because the barrier is exactly the settle step the
  harness already needs for deterministic render comparison.
- **Rejected:** a synchronous busy-wait + `ProcessEvents` pump on the WM worker. Falsified
  by r31 (0 completions across 30 s of `ProcessEvents`) plus emscripten loop non-reentrancy
  plus `Atomics.wait` halting the delivering loop. No synchronous pump makes progress on
  this profile. JSPI/asyncify reversal is rejected by ADR-006.
- **Table-OOB:** same ROOT (an undeliverable sync map future) but a distinct, separately
  fixable manifestation (a `WaitAnyOnly` callback that captures the stack by reference and
  can fire after `read()` returns). The recommended kick-then-consume shape (heap-owned
  pending state) eliminates it as a side effect; track a small independent safety patch too.

---

## 1. Mechanism verdict (why the sync path returns zeros)

### 1.1 The measured fact (reconfirmed first-hand, dated 2026-08-09, tree b7dd8f2)

Booted `build-wasm-windowed-opt` in the windowed WM-worker profile with `BW_DIAG` UNSET
(the honest production path) and ran the two snapshot ops from a `bpy` timer:

| op | result | capture | oiiotool verdict |
|---|---|---|---|
| `render.opengl(write_still, view_context)` | `{'FINISHED'}` | `/tmp/vp0.png` 1920x1080x4 | **Constant: Yes, 0/255 all channels** |
| `screen.screenshot(filepath=...)` | `{'FINISHED'}` | `/tmp/win.png` 1280x720x3 | **Constant: Yes, 0/255** |
| CDP compositor control (same instant) | n/a | `probe_cdp_composite.png` | **Constant: No, avg 61.9/255** |

Both ops report success, yet write constant-zero pixels, while the CDP compositor capture
proves the window painted its UI on-canvas at the same moment. This is a first-hand
reconfirmation of `notes/gpu-r25-shim-boot-restored-viewport-isolated.md` section 2.
Evidence: `sandbox/m5-readback-design/evidence/probe_{vp0,win,cdp_composite}.png` +
`probe_result.json` + `probe_console.log`.

### 1.2 The code path (both seams are the identical WaitAny shape)

- Texture readback `WGPUTexture::read` (upstream `.../webgpu/wgpu_texture.cc:1201`):
  `CopyTextureToBuffer` -> `Submit` -> `staging.MapAsync(..., CallbackMode::WaitAnyOnly,
  cb)` -> `ctx->instance_get().WaitAny(f, UINT64_MAX)` at **line 1277**. If `ok` never
  latches, `read()` returns having written nothing, so the destination stays zero.
- Buffer readback `webgpu::Buffer::read` (`.../webgpu/wgpu_buffer.cc:132`): identical
  `CopyBufferToBuffer` -> `Submit` -> `MapAsync(WaitAnyOnly)` -> `WaitAny(f, UINT64_MAX)`
  at **line 164**. `WGPUStorageBuffer::read` (wgpu_storage_buffer.cc:107) delegates to it;
  `async_flush_to_host` is a documented no-op there (line 145).

The framebuffer readback path funnels into the texture seam: `WGPUFrameBuffer::read`
(wgpu_framebuffer.cc:242) calls `tex->read(0, format, ...)` at line 271. So the whole
census reduces to two WaitAny sites.

### 1.3 Reconciling the F9-D prediction with the r25/r31 measurement

fix_plan M3.F9 item (D) predicted the zeros would "VANISH in the real windowed binary
(PROXY_TO_PTHREAD: WM worker can Atomics.wait; device lives on WM worker)". The device
does live on the WM worker (ADR-007), and the worker CAN legally `Atomics.wait`. The
prediction still failed, for two compounding reasons, both now proven:

1. **The port's blocking WaitAny is asyncify-gated and inert here.** ADR-007 finding 2 and
   the M4.T11 port characterization: the emdawnwebgpu `futures`/`emwgpuWaitAny` blocking
   waits are `#if ASYNCIFY`-only; a `TimedWaitAny`-featured `CreateInstance` returns NULL
   without asyncify/JSPI, and `WaitAny(..., 0)` asyncify-free is an `abort(TODO)`. Under
   ADR-006 (JSPI dropped, asyncify rejected), there is no functioning blocking WaitAny.
   `webgpu::Buffer::read`'s `WaitAny` "still returns immediately unfulfilled"
   (ledger/deferred.json id=gpu-sync-readback-windowed). `read()` returns before the copy
   resolves; the buffer is never mapped; the destination is left zero.

2. **Even a working blocking wait would deadlock (the decisive structural fact).** The
   `mapAsync` completion is a JS microtask/task on the WM worker's OWN event loop
   (per-thread JS-object table, ADR-007 finding 1: the map/device are neither
   structured-cloneable nor transferable, so no other thread can drive the completion). A
   thread parked in `Atomics.wait` halts its own event loop (ADR-007 finding 2), i.e. the
   exact loop that would deliver the completion. This is why the port gates blocking waits
   behind asyncify in the first place: asyncify unwinds the C++ stack back to JS (and JSPI
   integrates with promises) so the loop keeps pumping while "waiting". ADR-006 forbids
   both, so a same-thread synchronous wait on a WebGPU promise is structurally impossible
   on this profile.

**Which named suspect is it?** All three named candidates are real and intertwined, but
the ROOT is (b) "the queue/map callback never pumps while the requesting thread blocks"
(event-loop starvation). (a) "WaitAny's TimedWaitAny feature absence" is a consequence of
the same asyncify posture and means we cannot even attempt a real blocking wait. The
per-thread JS-object table (ADR-007 territory) is why we cannot sidestep by delivering the
completion on another thread. It is not one bug; it is the single-threaded JS event-loop
model meeting a no-stack-unwind posture.

### 1.4 What DOES work (the proven lever, twice)

The r31 diagnostic (patch 0117) and the r35 render bridge (patch 0125) both prove the
alternative: `diag_kick_readback` (wgpu_texture.cc:1416) submits the same copy, then
`staging.MapAsync(..., CallbackMode::AllowSpontaneous, cb)` and RETURNS. The completion
fires on the WM worker's own loop between ticks and writes the true device bytes to a heap
`DiagPending`. The DECISIVE toolchain finding (r31 note, "DECISIVE toolchain finding"):

> `CallbackMode::AllowProcessEvents` + `instance.ProcessEvents()` does **NOT** deliver the
> map completion in the imported-device windowed profile (0 completions across a 30 s
> kicked run). `CallbackMode::AllowSpontaneous` **DOES**, with no ProcessEvents dependency.

This is load-bearing for the contract below: the only thing that advances a map completion
on this profile is returning the C++ call stack to the browser event loop. Any design that
tries to resolve a readback without returning to the loop is dead on arrival.

---

## 2. Caller census (M5 critical path)

Every readback funnels through one of two backend seams (see 1.2). The table lists the
upstream callers on or adjacent to the M5 critical path, the seam each reaches, and whether
it needs true synchronous semantics (the caller consumes the pixels/bytes in the same C++
statement flow) or can take an async/poll contract.

| # | caller (file:line) | reads | seam | consume shape | classify |
|---|---|---|---|---|---|
| C1 | **Object pick / click-select**: `draw/engines/select/select_instance.hh:271-272` `select_output_buf.async_flush_to_host(); .read()` (in `read_result()`) | StorageBuffer (`GPU_storagebuf_read`) | Buffer::read (wgpu_buffer.cc:164) | reads then iterates the buffer in the SAME statement flow (hh:279-327), returns hits via `gpu_select_next_set_result` | **SYNC-consumed; async-convertible via settle** |
| C2 | **Legacy element / box / lasso select**: `draw/intern/draw_select_buffer.cc:104` `GPU_framebuffer_read_color(select_id_fb, ... GPU_DATA_UINT ...)` | FB colour texture (R32UI id) | Texture::read (wgpu_texture.cc:1277) | fills `buf`, realigns, returns to `GPU_select_end` caller synchronously | **SYNC-consumed; async-convertible via settle** |
| C3 | **Depth pick / autodist / snap**: `editors/space_view3d/view3d_draw.cc:2426` `GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)` (in `view3d_depths_create`) and `:2348` `GPU_framebuffer_read_depth` | depth texture | Texture::read | fills `ViewDepths` cache, consumed by callers NOW | **SYNC-consumed; tolerates one-frame-stale + settle** |
| C4 | **Viewport colour sample** (in-3D eyedropper): `editors/space_view3d/view3d_draw.cc:2873` `GPU_texture_read(tex, GPU_DATA_HALF_FLOAT, 0)` (in `ViewportColorSampleSession`) | copied colour texture | Texture::read | fills a session buffer, `sample()` reads it | **SYNC-consumed; modal-pollable** |
| C5 | **Window eyedropper sample**: `windowmanager/intern/wm_draw.cc:1508` `GPU_offscreen_read_color_region(...)` (in `WM_window_pixels_read_sample_from_offscreen`) | offscreen colour | Texture::read (via FB) | fills `r_col`, returned to modal eyedropper | **ASYNC-tolerable (modal), pollable** |
| C6 | **Screenshot**: `editors/screen/screendump.cc:70` -> `WM_window_pixels_read` -> `wm_draw.cc:1466` `GPU_offscreen_read_color` | offscreen colour | Texture::read (via FB) | fills an ImBuf, writes a PNG | **ASYNC-tolerable (writes a file)** |
| C7 | **RenderResult display (F12)**: `draw/engines/eevee/eevee_film.cc:113,922` `GPU_texture_read`; `draw/engines/workbench/workbench_engine.cc:662,683` `GPU_framebuffer_read_color/_depth` | render pass textures | Texture::read | fills RenderResult passes | **ASYNC-tolerable (render is a job); bytes already extractable by patch 0125** |

Counts: **7 M5-relevant caller families** over **2 backend seams**. Sync-consumed in the
same statement flow: C1, C2, C3, C4 (4). Async-tolerable already: C5, C6, C7 (3). The
critical few for click-pick parity are **C1 (object pick, StorageBuffer)** and **C2 (legacy
element/box select, FB texture)**; C3 rides along because many pick/drag operators call
`ED_view3d_autodist` for depth.

Notes:
- C1 is the modern `gpu_select_next` engine; its whole render+readback+convert runs inside
  the `GPU_select_begin ... GPU_select_end` bracket (gpu_select.cc:135-184), driven
  synchronously by the editor select operator. `GPU_select_end()` returns the hit count NOW
  (gpu_select.cc:169-186). There is no async yield inside the bracket today.
- C2 is the legacy `GPU_select` path used for edit-mode vertex/edge/face and box/circle/
  lasso; same bracket, same synchronous return expectation.
- The pick path is the **sibling buffer readback** the deferral flagged as remaining work:
  it needs `Buffer::read`/`GPU_storagebuf_read` converted, not just the texture seam.

---

## 3. Contract options

### 3.1 Option (a) RECOMMENDED: kick-on-request, latch-on-tick, consume-on-settle

A poll-shaped readback fence at the two seams, consumed across main-loop ticks, with a
harness-visible settle barrier. Three layers:

**Layer 1 - backend primitive (owned by the gpu/webgpu lane, not this one).** Promote the
proven `wgpu_diag_readback` machinery from diagnostic to a production `webgpu::readback`
module. A request allocates a heap pending record (staging buffer + destination pointer +
done-flag + seq), submits the copy, calls `MapAsync(AllowSpontaneous, cb)`, and returns a
ticket. The callback (a later tick) strips row padding into the caller destination and flips
`done`. Add the sibling for `Buffer::read` (the C1 pick path). Keep a belt-and-suspenders
`ProcessEvents()` drain in `WGPUContext::activate` for the headless profile, but do not
depend on it (r31 proved it is inert here). `poll(ticket)` returns done/pending.

**Layer 2 - GPU module API.** Add `GPU_texture_read_async(tex, fmt, dst, &ticket)`,
`GPU_storagebuf_read_async(ssbo, dst, &ticket)`, `GPU_framebuffer_read_color_async(...)`,
and `GPU_readback_poll(ticket)` / `GPU_readback_is_ready(ticket)`. On native and
headless-node profiles these can complete synchronously (real WaitAny) and report ready
immediately, so those profiles are unchanged. On wasm-windowed they route to Layer 1. The
existing synchronous `GPU_texture_read` stays for unconverted callers; on wasm-windowed it
either logs a one-time "sync readback returns zero on this profile, convert to async" and
returns zeros (today's behaviour, now diagnosed), or, for read-caching callers like C3, is
internally re-expressed as "kick now, fill one tick late".

**Layer 3 - caller conversion + settle barrier (M5 scope).**
- Expose `GPU_backend_wait_for_readbacks()` / a WM-level `wait_for_gpu_idle()` that advances
  frames (returns to the emscripten loop) until all in-flight readback tickets are ready or
  a bounded frame budget is hit. This is the ONLY correctness-preserving "wait": it works
  because it returns to the loop each iteration, which is what lets AllowSpontaneous fire.
- **C1 object pick:** `GPU_select_end()` on wasm returns a "pending" sentinel; the editor
  select invocation resumes on a later tick. Two implementation shapes, pick per operator:
  (i) the select operator's `invoke` kicks and installs a modal handler that consumes on the
  next event after the readbacks are ready; or (ii) a narrower "the DRW select engine kicks
  the StorageBuffer read, then the WM main loop's settle barrier is pumped before
  `GPU_select_end` returns the count" - viable ONLY inside the harness/standalone frame loop
  that owns the tick cadence, not from an arbitrary nested operator call. Shape (i) is the
  general answer; shape (ii) is the fast path when the caller already owns the loop.
- **C2 legacy select:** same treatment at `draw_select_buffer.cc` (kick the FB read, consume
  after settle).
- **C3 depth:** `ViewDepths` is already a cache; convert to "kick on first request, serve
  one-frame-stale until ready". Navigation/snap tolerate a one-frame-stale depth; the M5
  harness settles before asserting.
- **C7 RenderResult / C6 screenshot:** render/screenshot are already deferred; complete the
  job on the settle tick. Patch 0125 already proves the bytes land; wire them into
  RenderResult/the PNG instead of the diag file.

Correctness risk: LOW for state (the final state is identical once settled), MEDIUM for
plumbing (touches select engine + editors + WM loop). The one real hazard is a caller that
truly cannot yield (a deeply nested synchronous operator that must return hits in the same
call). For those, the answer is shape (i) modal deferral, not a synchronous wait.

Event-simulate compatibility: HIGH. See section 3.4.

Blast radius (upstream patch terms): backend module promotion (~2-4 patches in gpu/webgpu,
owned lane); GPU public API additions (~1-2 patches); editor/select conversion (~3-5
patches across `gpu_select_next.cc`, `select_instance.hh`, `draw_select_buffer.cc`,
`view3d_draw.cc`, and a WM settle hook). All additive and `GPU_WEBGPU`/`__EMSCRIPTEN__`
guarded so native/headless is untouched.

### 3.2 Option (b) REJECTED: bounded busy-wait + ProcessEvents pump on the WM worker

The idea: inside `read()`, loop `instance.ProcessEvents()` (or spin the main loop) up to a
timeout until the map resolves, keeping the call synchronous. **Falsified on three
independent grounds:**

1. r31 measured `AllowProcessEvents` + `instance.ProcessEvents()` delivering **0
   completions across 30 s** in the imported-device windowed profile. ProcessEvents does not
   drive map futures here.
2. There is no re-entrant "spin the emscripten main loop from inside a tick": emscripten's
   loop is not re-entrant without asyncify's `simulate_infinite_loop`, which ADR-006
   forbids. A C++ busy-loop never returns the stack to JS, so neither the `mapAsync` promise
   nor AllowSpontaneous can fire.
3. `Atomics.wait` on a manual flag halts the WM worker's event loop, which is the loop that
   would deliver the completion (ADR-007 finding 2). Deadlock.

Is there "a pump that makes progress without returning to JS"? No. The 0125 bridge's
tick-pump works precisely BECAUSE the emscripten main loop returns to JS between ticks; the
progress happens in the gaps, not inside a call. This rejection is the single most important
constraint in the design: on this profile, a readback can only complete by returning to the
loop.

### 3.3 Option (c) HYBRID: sync fast-path when already resolved, async otherwise

Keep a synchronous return when the mapping is already resolved (e.g. a prior kick for the
same texture/buffer already completed and is cached), else return pending. Useful as an
optimization layer on top of (a): a caller that kicked last frame and settled can read
synchronously this frame. It does NOT remove the need for (a), because the first read of any
buffer is always pending. Recommended as a later refinement, not the M5 core. Correctness
risk: LOW (it is a cache hit check); value: reduces added latency on repeated picks of the
same region.

### 3.4 Event-simulate compatibility and operator-trace determinism

M5's harness sends synthetic events (a click at a pixel). The concern: does an async pick
break operator-trace parity against the oracle?

It does not, provided the resume is deterministic. The reasoning:
- The operator invocation is unchanged: the synthetic click still dispatches `view3d.select`
  with the same `mouse_x/mouse_y`. The operator trace records operator calls and arguments,
  not GPU-tick timing. So the trace line `view3d.select(mouse=(mx,my))` is identical to the
  oracle's.
- Only the INTERNAL timing of the readback differs: the oracle (native Blender) resolves the
  pick synchronously within the click event; the web resolves it a few ticks later. The
  final state (ACTIVE object = cube, cube selected) is identical.
- Determinism is preserved because the harness inserts a `wait_for_gpu_idle()` settle barrier
  between the synthetic click and the state assertion. The same DSL script, run against the
  oracle, has a matching settle/no-op. Both reach the same final state before the assert.

The one thing the harness MUST do: model "click, then settle-to-idle, then assert" in the
DSL, and drive the settle by advancing ticks (returning to the loop) rather than a wall-clock
sleep. This is the same barrier M5 already needs for deterministic render comparison, so it
is not new machinery specific to picking.

---

## 4. The table-OOB crash disposition

r25 section 3 measured: immediately after `render.opengl` + `screen.screenshot` back-to-back,
`Uncaught RuntimeError: table index is out of bounds` from the WM worker, and the loop HALTS.
My r49 probe ran the same two ops and did **not** reproduce it this run (loop survived to
`OPS_COMPLETE`, `crashed=false`). That non-determinism is itself the tell.

**Same knot or separate?** Same ROOT, separate manifestation, separately fixable.

- ROOT: the undeliverable sync map future under ADR-006/007 (section 1). It is the same
  constraint that produces the zeros.
- MANIFESTATION: a lifetime/table-slot bug specific to the `WaitAnyOnly` sync path. Both
  `WGPUTexture::read` (wgpu_texture.cc:1274) and `Buffer::read` (wgpu_buffer.cc:161) register
  a lambda that captures stack state BY REFERENCE (`[&]{ ok = ... }`). `WaitAny` returns
  without firing it, `read()` returns, and the owning stack frame (and its `ok`) is
  destroyed. If the browser's `mapAsync` promise later resolves spontaneously, it invokes the
  now-dangling callback and/or a wasm function-table slot that has since been reused: an
  indirect call through a stale slot = `table index is out of bounds`. Back-to-back ops make
  it likelier because the second op's staging/callback churn reuses table slots while the
  first op's deferred promise is still pending. Timing-dependent, hence not reproduced every
  run.
- WHY the diag path never crashes: `diag_kick_readback` heap-allocates `DiagPending`, keeps
  the staging buffer alive in it, uses `AllowSpontaneous`, and frees in the completion
  (`diag_complete`). No stack capture, no dangling reference. This is direct evidence that
  the crash is the stack-captured `WaitAnyOnly` callback, not a generic readback fault.

**Disposition:** the recommended contract (option a) removes the crash as a side effect,
because every converted caller uses the heap-owned kick-then-consume shape. Additionally,
track a SMALL independent safety patch (own lane, low risk) for the interim: make the sync
`read()`/`Buffer::read` path not leave a dangling deferred callback (heap-own the callback
state and detach/cancel the future when `WaitAny` returns unfulfilled, or drop the
WaitAnyOnly registration entirely on this profile since it cannot succeed anyway). Repro
pointer: `notes/gpu-r25-...md` section 3, and `sandbox/m5-readback-design/probe_result.json`
(the non-reproducing counter-run). Fix item name: **M5.readback-callback-lifetime**.

---

## 5. M5 acceptance session spec (event-simulate click-pick on the default cube)

**Preconditions.** Default startup scene (Cube, Camera, Light). The viewport must render the
cube (the M4 cube-visible blocker resolved) OR the select engine's offscreen id-pass must
render independently of the main viewport composite; note this dependency, since the select
engine is a separate offscreen engine and may function before the main composite does.

**Session steps (web, under the M5 harness).**
1. Boot `windowed.html` to the default scene; run to a stable WM loop.
2. Neutral synthetic mouse-move away from any widget (per the rig recipe), then a synthetic
   LEFT-click (down+up) at pixel `(mx, my)` centred on the cube.
3. The click dispatches `view3d.select` with `location=(mx, my)`.
4. On web, `view3d.select` kicks the GPU select render + StorageBuffer readback
   (AllowSpontaneous) and returns pending / installs its resume.
5. Harness advances ticks via `wait_for_gpu_idle()` (pump frames, returning to the loop each
   iteration, until the readback ticket is ready; bounded frame budget).
6. Consume: `select_output_buf` bytes land, `read_result()` (or its async successor) sets
   `BASACT`/active object to the cube and the cube's SELECT flag.

**Assertions (parity vs the oracle running the same DSL on native Blender).**
1. STATE PARITY: `context.view_layer.objects.active.name == "Cube"` and the cube is selected;
   matches the oracle's final state.
2. OPERATOR-TRACE PARITY: the trace contains exactly one `view3d.select` with
   `mouse_x==mx, mouse_y==my` (within the harness coord tolerance), identical to the oracle's
   trace line and count. No extra/dropped/reordered operator invocations from the async
   internals.
3. DETERMINISM: repeat the click; the trace and final state are byte-stable run to run.
4. NO-CRASH: repeated back-to-back click-picks do not trigger the table-OOB (directly
   stresses the r25 section 3 hazard); the loop survives.
5. (Optional) RENDER PARITY: the post-click viewport (selection outline around the cube)
   matches the golden within threshold.

**What the readback contract must deliver for this to pass.**
1. `GPU_storagebuf_read`-class readback returns the TRUE `select_output_buf` bytes (non-zero,
   containing the cube's select id) after the settle barrier; NOT zeros.
2. The result is available deterministically within a bounded number of ticks (settle
   converges; no unbounded wait, no wall-clock dependence).
3. No table-OOB across repeated picks (M5.readback-callback-lifetime resolved or subsumed).
4. The async internal timing adds/drops/reorders NO operator invocations, so the trace equals
   the oracle's.

---

## 6. Effort estimate and suggested lane structure

Rough sizing (patches are additive, `GPU_WEBGPU`/`__EMSCRIPTEN__`-guarded; native/headless
untouched):

| lane | scope | owns files | size |
|---|---|---|---|
| **L-A backend primitive** | promote `wgpu_diag_readback` -> production `webgpu::readback`; add the `Buffer::read` async sibling for the pick path; ticket + poll + heap-owned pending; fix M5.readback-callback-lifetime | `gpu/webgpu/*` (the fenced lane, NOT r49) | ~2-4 patches, MEDIUM |
| **L-B GPU module API** | `GPU_*_read_async` + `GPU_readback_poll`/`_is_ready`; route webgpu backend; keep native/headless synchronous | `gpu/intern/gpu_texture.cc`, `gpu_framebuffer.cc`, `gpu_storage_buffer.cc`, `GPU_*.hh` | ~1-2 patches, SMALL-MEDIUM |
| **L-C caller conversion + settle barrier** | convert C1 (object pick), C2 (legacy select), C3 (depth cache), C4 (colour sample); add `wait_for_gpu_idle()` to the WM main loop | `gpu_select_next.cc`, `select/select_instance.hh`, `draw_select_buffer.cc`, `space_view3d/view3d_draw.cc`, a WM loop hook | ~3-5 patches, MEDIUM-LARGE |
| **L-D M5 harness / event-simulate** | click-pick session driver, synthetic-event injection, `wait_for_gpu_idle` settle in the DSL, oracle parity + operator-trace capture | `harness/` (the M5 lane) | MEDIUM (separate from readback) |

Dependency order: L-A unblocks L-B unblocks L-C; L-D can proceed against L-C's settle
barrier once it exists. L-A + L-B together are the actual "readback contract" unblock; L-C is
caller adoption; L-D is verification. C6/C7 (screenshot, RenderResult) are follow-on wins
once L-A/L-B land, since patch 0125 already proves the bytes are extractable.

Suggested first slice for the smallest demonstrable M5 win: L-A (Buffer::read async +
lifetime fix) + a narrow L-C shape-(ii) fast path inside the harness-owned frame loop for C1,
so a scripted click-pick returns real hits under `wait_for_gpu_idle`. That proves the
contract end-to-end on the pick path before the broader operator-modal conversion.

---

## 7. Open risks

- **Nested-operator callers that cannot yield.** Any select caller that must return hits in a
  single synchronous call, invoked from a context where the frame loop is not the caller's to
  drive, needs shape-(i) modal deferral. Enumerate these during L-C; they are the real
  complexity, not the backend primitive.
- **Select engine vs main-viewport dependency.** The acceptance session assumes the select
  offscreen id-pass renders correctly. If it shares the workbench bind-completion defect that
  blocks the main viewport (r31/r35 BindGroup entry-count family), the pick may read a valid-
  but-empty id buffer. Verify the select engine renders the cube's id independently before
  asserting M5 pick parity; if not, the M4 cube-visible fix is a hard precondition.
- **One-frame-stale depth (C3).** Acceptable for navigation/snap under a settle barrier, but
  any operator that assumes pixel-exact current-frame depth in the same call needs review.
- **Settle-barrier frame budget.** Must be bounded and deterministic; a readback that never
  completes (device lost, e.g. the r35 open_mainfile device-loss) must fail closed with a
  diagnostic, not hang the harness.
- **Table-OOB non-determinism.** It did not reproduce in the r49 probe; do not treat "did not
  crash" as "fixed". The lifetime fix (M5.readback-callback-lifetime) should land regardless,
  and acceptance assertion #4 must run repeated picks to stress it.
