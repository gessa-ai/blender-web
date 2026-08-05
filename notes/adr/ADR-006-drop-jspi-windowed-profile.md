<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-006 — Drop `-sJSPI` from the windowed browser profile

**Status:** ACCEPTED 2026-08-05 (driver), ratifying the M4 T9 worker's evidence-backed
link-flag change (commit e48906b). Amends the GOAL.md "Emscripten posture" bullet and
supersedes the JSPI-specific residuals of M2.7/ADR-003 for this profile.

## Context

GOAL.md's standing posture was `-sJSPI` (Chrome 137 floor) for async boundaries, with
ADR-003 confining suspends to top-level async boundaries. The M4 T9 windowed boot
falsified this empirically **before `main()` ever ran**:

- `initRuntime` aborted with `SuspendError: trying to suspend without
  WebAssembly.promising`, stack `__wasm_call_ctors → _GLOBAL__I →
  std::ios_base::Init::Init()`. Emscripten wraps only `main`/pthread entries with
  `WebAssembly.promising`; static ctors run unwrapped, so ANY suspend reachable from a
  ctor aborts. With ~200 archives of linked C++, proving the ctor graph suspend-free
  forever is not maintainable.
- Under `-sPROXY_TO_PTHREAD` (mandatory for us), `main()` lives on a worker where
  blocking `Atomics.wait` is legal: the WebGPU device await
  (`GHOST_ContextWGPUWeb::initializeDrawingContext` WaitAny) and texture readbacks
  block correctly without suspension. JSPI buys nothing on this thread topology.
  (The in-tab harness independently confirmed the inverse: synchronous WaitAny on the
  browser MAIN thread cannot work — fix_plan M3.F9-D — which is a reason to keep main
  off the main thread, not a reason for JSPI.)

## Decision

The windowed browser profile links **without `-sJSPI`** (patches/platform_wasm.cmake,
e48906b). All async boundaries use worker-blocking waits on the proxied main thread.
JS-EH stays (ADR-001/ADR-003 unchanged on exceptions); ADR-003's suspend-topology
invariant becomes vacuous here (no suspends exist).

## Consequences

- Browser floor is no longer JSPI-gated; COOP/COEP + SharedArrayBuffer (pthreads)
  remains the floor. Update LAUNCH.md wording at the M4 boundary.
- M2.7's "true-JSPI runtime validation at M4" residual is superseded for this profile.
- Reintroducing JSPI (e.g. for a future main-thread-blocking need) requires a new ADR
  plus a proof that no static ctor can suspend.

## Rejected

- Keeping JSPI and auditing/wrapping ctor suspends: fragile against every future link
  closure change, zero benefit under PROXY_TO_PTHREAD.
- Asyncify: ~50% size tax, rejected in GOAL from the start.
