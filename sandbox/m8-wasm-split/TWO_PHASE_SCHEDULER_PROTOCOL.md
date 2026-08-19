<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Two-phase Web scheduler and split-module protocol

Status: design for review. This document does not authorize a browser run or
an APPLY relink. The existing `preview0-final-single-flight-runtime-r6` receipt
remains the immutable failure showing that the present hot profile cannot boot
with `--threads 1`.

## Invariant

The deferred module may be requested only after semantic first pixels and the
first trusted semantic interaction. No pthread may execute a deferred
placeholder before its local deferred instance exists. The transition from the
bootstrap scheduler to the production scheduler therefore has a real WM park
barrier; timing delays and worker-count subsets are not valid substitutes.

Worker entry also has a cross-realm shared-memory visibility barrier. Before
reading a newly allocated pthread record or performing its mailbox Atomics, the
generated glue validates the aligned pointer and required end, refreshes normal
views, and—when the local view is still short—uses bounded
`wasmMemory.grow(0)` synchronization followed by forced view refresh. Stack
metadata is accepted only with nonzero size, `high >= size`, nonnegative low,
and a locally covered high address. Failure occurs before stack restoration,
Atomics, or entry invocation. CAPTURE and APPLY receipts bind this identical
generated transform; identity/byte-length-only refresh is not sufficient.

The web build starts with Blender `--threads 1`, at least eight precreated
Emscripten pthread workers, and a constant-initialized `split_ready=false`.
The proxied WM main keeps `STACK_SIZE=33554432` because shaderc/Tint compilation
runs in that realm and needs the larger stack. Ordinary pthread creation uses
the independent `DEFAULT_PTHREAD_STACK_SIZE=8388608`; this avoids reserving
32 MiB for every precreated/TBB worker while leaving the shader path unchanged.
Both effective link settings are parsed and bound by the split receipt.
The native scheduler's `split_ready` is one-way: it can become true only after
the same-generation PARK acknowledgement, the initial exact all-current-worker
deferred-module ACK, and a verified TBB active value of eight. This native bit
is not the product's final cold-ready signal: late workers created by APPLY must
also stabilize in the page protocol before RESUME.

## State machine

All fields are shared-memory atomics. Writers publish payload before generation
with release ordering; readers consume generation then payload with acquire
ordering. `g` is one positive transition-attempt generation. It must strictly
increase between complete attempts, while the three phase-specific requests
PARK, APPLY, and RESUME intentionally reuse that same `g` exactly once each and
in that order, with the PREPARED and PAGE_READY validation handshakes between
them. Each phase has its own request/ack generation field. A repeated
phase request, a phase carrying a different `g`, an out-of-order phase, a stale
attempt generation, or a wrong target transitions to a fail-closed error state.

1. `BOOTSTRAP_NOT_READY`: scheduler count/override is one. Background pools use
   the existing `TASK_POOL_NO_THREADS` path. Normal WM ticks run.
2. Page calls `bw_web_scheduler_request_park(g)` only after the trusted hot
   interaction. The next WM callback entry rejects if a WM job is running by
   publishing a same-generation terminal error ACK (never by timing out), or
   verifies/publishes bootstrap OpenEXR zero and OIIO one, publishes
   `parked_generation=g`, and returns before events, handlers, notifiers, or
   draw. Every later parked tick remains control-only.
3. Only after observing the exact PARK ACK, the page calls
   `Module.bwPrepareSplitSecondary()`. It snapshots a stable set of all loaded
   and current workers (baseline at least eight), installs one page instance
   and exactly one instance per worker, and requires zero pending, duplicate,
   rejected, or protocol-error ACKs. It then calls
   `BW_web_split_request_prepared(g, workers, acknowledgements, instances,
   local_instances, pending, protocol_errors, stabilization_epoch)`. The epoch
   is non-zero and is assigned only after two identical consecutive worker-set
   scans. Native code validates the exact
   payload, publishes `prepared_generation=g` on a control-only tick, and will
   reject APPLY until that ACK is acquired.
4. Page calls `BW_web_split_request_apply(g, 8)` only after PREPARED ACK. A
   parked WM tick calls the
   purpose-built `BLI_task_scheduler_reconfigure(8)`: construct control(8) while
   control(1) still lives, swap pointers, delete control(1), verify
   `tbb::global_control::active_value(max_allowed_parallelism)==8`, then update
   scheduler count and the Blender override. Raw scheduler exit/init is banned.
   If active-value verification fails, construct rollback control(1), swap it
   in, delete control(8), restore/verify count and override one, retain PARK,
   and publish a same-generation terminal error. A failed rollback or impossible
   one-way-ready transition publishes `reload_required=1`; the shell must discard
   the process. No failure path publishes applied or resume ACK.
5. That same control tick restores and observes the image-library thread
   policies. Success requires OpenEXR global count eight, a successful OIIO
   attribute setter, and observed OIIO threads eight. It finishes and verifies
   every TBB/IMB payload and phase field, publishes the observed EXR/OIIO counts,
   sets the one-way native ready flag,
   and release-stores `applied_generation=g` **last**. No success field may be
   written after that ACK. On any image mismatch it restores OpenEXR zero/OIIO
   one, transactionally rolls TBB back to verified control/count/override one,
   publishes a same-generation terminal error, stays parked, and never writes
   native ready or applied generation. Every worker created by TBB or OpenEXR
   receives a distinct deferred-install message synchronously after Emscripten's
   cmd1 and before the loader returns, so the browser's per-worker FIFO is
   cmd1, install, cmd2. The worker installs/ACKs it while draining that queue and
   before application/thread entry; no worker body can run first.
6. The page rechecks split status until a stable all-loaded/current-worker set
   has pending=0, one local instance, exactly one worker instance and ACK per ID,
   zero duplicate/rejected/protocol/timeout counts, and a reconciled late-worker
   generation. A worker first observed after PREPARED is accepted only when its
   persisted ACK says `delivery=initial-before-start`, the generation is `g`,
   and its instance count is one. That ACK is emitted after the secondary is
   installed from the FIFO initial-install message after cmd1 and before queued
   cmd2 or application/thread entry. (`delivery=initial-before-start` is the
   persisted protocol discriminator.) PAGE_READY never sends an install,
   probe, or liveness message to an already-running worker; a long-lived C/C++
   entry is not required to return to the worker JavaScript event loop. The page
   records the exact PREPARED IDs, late IDs, initial-ACK IDs, and late-initial-ACK
   IDs, then calls `BW_web_split_request_page_ready(g, workers,
   acknowledgements, instances, local_instances, pending, protocol_errors,
   late_workers, stabilization_epoch)`. The post-APPLY epoch must be strictly
   greater than the PREPARED epoch. Native code validates that distinct payload and publishes
   `page_ready_generation=g` on a control-only tick; native `split_ready` or
   APPLY ACK alone never releases cold work. The payload must satisfy
   `workers>=prepared_workers` and
   `late_workers==workers-prepared_workers`; an unchanged stale PREPARED
   snapshot cannot earn PAGE_READY even when its counters remain valid. After
   the native PAGE_READY ACK the page rechecks the exact IDs and persisted ACK
   payload, then performs the final synchronous status comparison and RESUME
   publication in one page task.
7. Page calls `BW_web_split_request_resume(g)` only after acquiring the exact
   PAGE_READY ACK.
   A parked control tick publishes `resumed_generation=g` and returns without
   ordinary work. The following tick may resume ordinary processing. The shell
   keeps input blocked until it observes the exact RESUME ACK, then replays its
   queued input for that following tick. EEVEE, Cycles, and file I/O remain
   forbidden before RESUME ACK.

## Source boundaries

- `source/blender/blenlib/BLI_task.h` and
  `source/blender/blenlib/intern/task_scheduler.cc`: add the one-way bootstrap
  state API and `BLI_task_scheduler_reconfigure(int)`. Native defaults remain
  ready and existing initialization behavior remains unchanged.
- `source/blender/blenlib/intern/task_pool.cc`: before computing `use_threads`,
  normalize both `TASK_POOL_BACKGROUND` and `TASK_POOL_BACKGROUND_SERIAL` to
  `TASK_POOL_NO_THREADS` only for Emscripten while bootstrap is not ready. Do
  not mutate already-created pools during transition.
- `source/blender/windowmanager/intern/wm.cc`: own the exported request/status
  atomics and consume PARK, PREPARED, APPLY, PAGE_READY, and RESUME only at the top of the Emscripten
  WM main-loop callback. PARK and every control transition return before all
  four ordinary WM phases.
- `source/blender/imbuf/IMB_imbuf.hh` and `source/blender/imbuf/intern/module.cc`:
  expose one public aggregate web transition API returning the observed
  OpenEXR and OIIO counts. WM must use this seam and must not include private
  file-format implementation headers.
- `source/blender/imbuf/intern/openexr/openexr_api.cpp`: OpenEXR global worker
  count is zero during bootstrap, then eight after APPLY; a private setter and
  getter bind `Imf::setGlobalThreadCount`/`Imf::globalThreadCount`. Its present
  count of one creates a persistent worker and is not safe.
- `source/blender/imbuf/intern/oiio/openimageio_api.cpp`: bootstrap policy is
  one (caller-only per OIIO's documented policy), then eight after APPLY;
  private helpers return the setter success and observed `threads` attribute.

The page exports return only integers/immutable status snapshots. Proposed
status fields are `phase`, `request_generation`,
`park_request_generation`, `parked_generation`, `prepared_request_generation`,
`prepared_generation`, `apply_request_generation`, `applied_generation`,
`page_ready_request_generation`, `page_ready_generation`,
`resume_request_generation`, `resumed_generation`,
`target_threads`, `active_threads`, `error_generation`, `error_code`, and the
observed `openexr_threads`, observed `oiio_threads`, `reload_required`, and the
one-way native `split_ready`, plus the exact PREPARED and PAGE_READY worker,
acknowledgement, instance, local-instance, pending, protocol-error, and
late-worker payloads. (`request_generation` is the current transition
attempt; phase-specific fields disambiguate the intentional reuse of `g`.) The
production shell separately binds the final page-ready worker-set status,
including exact prepared/late/initial-ACK/late-initial-ACK ID arrays and each
late worker's delivery, generation, and instance count. It
owns visible loading/error state and the cold-input queue; it must not
direct-evaluate preload, infer readiness from native APPLY, or bypass an error.
For wrong-generation requests during an active transaction, the terminal
`error_generation` acknowledges the active transaction `g` so its waiter cannot
time out; `offending_generation` separately records the rejected argument.

## Direct-thread audit

The background-pool constructor policy covers both variants and all current
call sites relevant to this build:

- edit-mesh undo compression (`editmesh_undo.cc`): exercised by the trusted
  Tab/extrude/Tab path; inline execution preserves its existing synchronous
  fallback and removes the bootstrap pthread race;
- sculpt undo compression (`sculpt_undo.cc`): cold user action, still covered;
- file-preview cache (`filelist.cc`): absent in the default Layout boot, covered
  if a file view opens before release;
- OpenGL result writing (`render_opengl.cc`): OpenGL is disabled in the web
  preset, but the serial variant is covered by the same constructor rule.

Other direct sources are not assumed safe:

- WebGPU does not create a `GPUWorker`: `wgpu_context.cc` sets
  `GCaps.use_main_context_workaround=true` under Emscripten, and
  `ShaderCompiler` therefore stays on the context thread. This is a static
  invariant and must not be re-enabled after APPLY because emdawn WebGPU object
  handles are per-thread.
- OpenEXR creates its own global pool during `IMB_init` and must be held at zero.
- OIIO is held at one (its documented caller-only policy) and restored to eight
  only after APPLY. The r6 pre-WM base-slot failure is consistent with dependency
  initialization rather than the statically absent WebGPU compiler worker.
- `WM_jobs_start` uses `BLI_threadpool` directly. PARK must reject if
  `WM_jobs_has_running(wm)` is true; the shell cannot start cold jobs while
  input is queued. The final browser proof must show no bootstrap WM job.
- sequencer prefetch, write compression, sound delayed close, soft-body pools,
  and Cycles workers are cold paths and remain input-gated until final ready.

## Focused tests before browser work

1. Host scheduler test: reconfigure 1 to 8, prove construct/swap/delete ordering
   via an injected factory, active value eight, count/override eight, and stale,
   duplicate, wrong-generation, and wrong-target rejection. Native default-ready
   behavior must remain unchanged.
2. Emscripten pthread harness: bootstrap false makes BACKGROUND and
   BACKGROUND_SERIAL callbacks finish before `push` returns on the caller
   pthread, with no worker/pthread-create delta; nested push/wait, cancel,
   work-and-wait, and free cannot hang. After the one-way ready transition,
   freshly created pools use worker semantics and join cleanly.
3. WM state-machine unit: PARK ACK is emitted at callback entry, running jobs
   produce a terminal same-generation error, ordinary phase counters remain
   unchanged while parked, release/acquire generations match, PREPARED cannot
   precede PARK, APPLY cannot precede PREPARED, PAGE_READY cannot precede APPLY,
   failed active-value verification rolls transactionally back to
   control/count/override one, image-policy mismatch restores EXR zero/OIIO one,
   native ready precedes applied generation, applied generation is the final
   success write, RESUME cannot precede PAGE_READY ACK, RESUME ACK is
   control-only, and ordinary counters change only on its following tick.
4. Static preset audit: the Emscripten WebGPU main-context workaround remains
   true and no GPU compiler worker exists; OpenEXR count is zero then eight;
   OIIO is caller-only one then eight; and every direct pthread source is either
   covered or cold-gated.
5. Only after these pass, CAPTURE on the exact modified product with
   `--threads 1`: semantic pixels, trusted orbit plus Tab/extrude/Tab, PARK,
   prepare/all probe ACK, APPLY-to-eight, then non-messaging PAGE_READY from two
   stable exact worker-set scans. Existing PREPARED IDs remain trusted by their
   PREPARED probe; every late ID must have a persisted successful page-main
   loader promise completed before worker entry. CAPTURE records and requires
   zero post-APPLY worker messages, then synchronously rechecks and publishes
   RESUME. Union this
   format-valid shared-memory profile with the existing launch profile and APPLY
   to the same `.wasm.orig` identity.
6. Final product proof: no shard request before the trusted interaction; one
   exact fetch/compile; all-current ACKs; active value eight; final page-ready;
   exact RESUME ACK; rapid queued input replay; late-worker reconciliation;
   physical EEVEE F12 with settled nonzero pixels;
   two Cycles renders; and two `.blend`/USD/OBJ/glTF round-trips. An Emscripten
   rapid-input/late-worker harness remains required in addition to browser proof.
