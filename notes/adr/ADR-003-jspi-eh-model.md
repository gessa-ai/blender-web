<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-003: EH model for the suspending (M4+) stack — JS-EH with confined suspend topology; Wasm-EH as declared fallback

Date: 2026-08-03. Status: ACCEPTED (driver), provisional-by-design with a hard M4 gate.
Evidence: M2.7/M2.7b/M2.7c probe series under real JSPI (tools-local Node v24.19.0),
commits 7c1722f, 26025bd, cb4258c; full matrices in notes/python-emcc605-probe.md.

## The measured facts

1. Real JSPI cannot suspend across JS frames. Under JS-EH (`-fexceptions`,
   `SUPPORT_LONGJMP=emscripten`), two constructs create JS `invoke_*` frames:
   - **setjmp**: poisons its entire containing function (suspend fails even lexically
     before the setjmp) — per-function blast radius;
   - **C++ try/catch**: breaks suspension only while a try is ACTIVE on the stack (F1,
     F3), no matter how many plain frames sit between it and the suspend; dormant or
     merely-containing try does not (F2) — per-active-scope blast radius.
2. Wasm-EH (`-fwasm-exceptions` + `-sSUPPORT_LONGJMP=wasm`) emits ZERO invoke_* imports;
   every probed shape suspends cleanly (F4 control, E).
3. **Census (the decisive input):** `libpython3.13.a` = 0 setjmp/longjmp-runtime refs;
   the full linked Python image (incl. mpdec/expat/Hacl) = 0; libjpeg-turbo's archive = 0
   (its setjmp pattern lives in the EMBEDDING app's error handler, active only during the
   synchronous decode window). CPython's real setjmp home is `_ctypes`/libffi — not built.

## Decision

Keep **JS-EH across the whole stack** (unchanged from ADR-001's appendix; zero rebuilds),
and make M4+ suspend topology a **hard architectural invariant**:

> **JSPI suspend points may exist ONLY at top-level async boundaries — main-loop tick,
> event-handler entry, and the OPFS/async shims — and NEVER while (a) any C++ `try` is
> active on the stack or (b) the imbuf/jpeg `setjmp` error scope is live.**

Practically: our own new code (webgpu backend waits, GHOST-web main loop, platform shims)
is where suspends live, and it is all code we author — the invariant is enforceable at
review time plus one runtime gate:

- **M4 gate (mandatory):** a Chrome ≥137 topology smoke that exercises the shipped suspend
  surface (GPU waits, loop yields, file IO) under the real UI boot and asserts zero
  `SuspendError` — plus a debug assertion hook where cheap (suspend-entry check).
- **Residual risk, named:** EH-heavy C++ deps (OIIO/OCIO/OpenEXR) run operations under
  active try blocks; the invariant means image/color operations must never contain a
  suspend point. Today they don't (decode is synchronous, IO is worker-side sync-handle,
  not main-thread JSPI); the smoke pins it.

**Declared fallback:** stack-wide Wasm-EH migration — proven viable end-to-end (libpython
builds/runs Wasm-EH; all suspend shapes pass; no emcc flag refusals). Cost: rebuild 29 deps
+ libpython (idempotent scripts exist — a scheduled machine-day) + a size/perf pass.
Trigger: the M4 smoke failing repeatedly, or the suspend surface proving unconfineable.
This fallback is now a clean engineering tradeoff fully decoupled from JSPI feasibility.

## Rejected

- **Immediate Wasm-EH migration:** pays the full-stack rebuild now to remove a constraint
  the census shows we don't currently violate anywhere; keeps open the option instead.
- **Asyncify instead of JSPI:** ~50% size tax (GOAL's stated reason) and our own probes
  show Asyncify masks real JSPI semantics (it false-positived the B-shape) — it would hide
  exactly the class of bug this ADR exists to prevent.
