<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M5 L-A: production GPU readback primitive (r53)

Implements lane **L-A** of the M5 sync-readback contract adopted in
`notes/m5-sync-readback-contract-design.md` (r49): promote the twice-proven
`AllowSpontaneous` tick-pumped readback (patches 0117/0125) from a `BW_DIAG`-only
diagnostic to a production primitive at **both** backend seams, and fix the
callback-lifetime hazard (`M5.readback-callback-lifetime`). Patch **0133**.

Scope was L-A only: the backend mechanics. The public `GPU_*_read_async` API is **L-B**;
caller conversion + `wait_for_gpu_idle()` is **L-C**. Neither is in this patch.

## What landed

New file pair `source/blender/gpu/webgpu/wgpu_readback.{cc,hh}` (the "clearly-owned readback
helper" the design anticipated), plus the two seams rewired and a `~WGPUTexture` forget-hook.

### The contract (kick / latch / settle), exactly as the design prescribes

- **KICK** - on a `read()` the seam submits the copy (`CopyTextureToBuffer` /
  `CopyBufferToBuffer`) into a fresh MapRead staging buffer, calls
  `MapAsync(CallbackMode::AllowSpontaneous, cb)`, and returns. A **heap-owned** `Pending`
  record (in one static registry for the port's single-device profile) owns the staging
  buffer; the callback captures
  **only a plain `uint64_t` ticket**, never a caller-stack reference.
- **LATCH** - when the map resolves on a later WM-loop tick (`AllowSpontaneous` needs no
  `ProcessEvents`; it fires between `emscripten_set_main_loop` ticks once the C++ stack has
  returned to the browser loop), the callback strips the 256-byte row padding to a tight
  pitch and stores the device bytes in a `Settled` record keyed by source.
- **CONSUME on settle** - a later `read()` of the **same** source returns the latched bytes
  (`take_settled`). On the first read of a source (unsettled) the seam returns the
  **conservative interim**: deterministic zeros (texture) / empty (buffer), i.e. today's
  behaviour, now with the byte-capture side effect. This is the design's "return the latched
  bytes when settled; on first-call-unsettled the conservative interim" (section 3.1,
  option (a)/(b) "kick-now, fill-one-tick-late"). Documented staleness: a settled source
  serves up to one-frame-stale bytes and is re-kicked each read to refresh (acceptable per
  the design for C3 depth and the pick path; deliberate consumers get exact freshness
  through the ticket/settle-barrier path in L-B/L-C).

### The callback-lifetime fix (M5.readback-callback-lifetime)

The old path at both seams was `MapAsync(WaitAnyOnly, [&]{ ok = ... })` +
`WaitAny(f, UINT64_MAX)`. On the windowed profile `WaitAny` returns immediately unfulfilled
(ADR-006/007), `read()` returns, its stack frame (and `ok`) dies, and a later spontaneous
resolution of the `mapAsync` promise fires the callback through a **reused wasm
function-table slot** - the `table index is out of bounds` crash after back-to-back snapshot
ops (design section 4). The fix: on wasm the entire `WaitAnyOnly` + `WaitAny` block is
`#ifdef __EMSCRIPTEN__`-compiled **out**; the seam routes to the heap-owned kick instead, so
the dangling-stack callback **does not exist in the wasm binary**. Verified: 24 back-to-back
`render.opengl` + `screen.screenshot` ops, zero table-OOB, WM loop alive after.

### Native path preserved EXACTLY

Everything of substance in `wgpu_readback.cc` is `#ifdef __EMSCRIPTEN__`; on native it
compiles to a 336-byte stub. Both seams keep their verbatim blocking-`WaitAny` path under
`#else` - native Dawn has a working blocking `WaitAny`, so `read()` still returns real bytes
synchronously in the same call. Census held **149 PASS / 7 FAIL / 2 CRASH / 158** +
`static_shaders` 956/973 (the sole RED is the mission-excepted known-spurious I10
un-defer-candidate - a *deferred* test now passing, unrelated to readback). The readback
seams (`texture_read`, `storage_buffer_create_update_read`, `storage_buffer_clear`,
`framebuffer_clear_color_single_attachment`) all PASS directly.

### Registry safety

- **Bounded.** `kMaxInFlight = 64` caps concurrent kicks (a full kick beyond the cap is
  skipped, caller sees the interim) - this bounds live staging buffers **without** ever
  evicting an in-flight pending record (which would destroy a staging buffer a map still
  references). Duplicate kicks for the exact same source key (including buffer offset and
  size) return the existing ticket instead of consuming another slot. `kMaxSettled = 128`
  caps latched results (host bytes only; always safe to evict oldest).
- **No stale-key hits.** Texture records key on the `WGPUTexture*` wrapper and are purged by
  exact `(SourceKind::Texture, wrapper)` identity both in `~WGPUTexture` and before
  `adopt_external` replaces a surface acquisition. An in-flight kick for a dying or
  re-adopted source is marked `orphaned`, so its completion discards instead of latching for
  a dead/changed key. Kind-aware forgetting cannot erase an unrelated buffer whose raw
  handle happens to equal a texture-wrapper address. Buffer records key on the raw
  `wgpu::Buffer` handle and **pin** a ref-counted copy in the record, so the source address
  cannot be reused while a result for it is live.

### Diagnostic bridge intact (VERIFY #3)

`wgpu_diag_readback.{cc,hh}` is untouched and `diag::on_texture_read(this)` still runs at the
top of `WGPUTexture::read`, so the 0117/0125 `BW_DIAG` bridge still writes
`/tmp/bw_readback_<seq>.bin` for M6 rescore. Confirmed: one scene through
`sandbox/gpu-r46/bridge_boot.mjs` landed 2/2 captures (gpuErrors 0). The production primitive
coexists (both kick under `BW_DIAG`; only the diag half writes the M6 file). The production
primitive's own optional file sink is off unless `BW_READBACK_CAPTURE` is set (a diagnostic
knob, distinct from `BW_DIAG`, used by nothing in production).

## Seams the next lanes need (handoff)

- **L-B (public API, `gpu/intern`, upstream-shared).** Build `GPU_texture_read_async` /
  `GPU_storagebuf_read_async` / `GPU_framebuffer_read_color_async` +
  `GPU_readback_poll`/`_is_ready` on top of the ticket API already exported:
  `readback::kick_texture` / `kick_buffer` return a `Ticket`; `is_ready(ticket)`,
  `consume_ticket(ticket, dst, len)`, and the key-addressed `take_settled(key, dst, len)`
  consume it. On native these route to the synchronous blocking read (ticket completes
  immediately); the L-B facade should branch `__EMSCRIPTEN__` accordingly.
- **L-C (caller conversion + settle barrier).** `readback::pending_count()` and
  `readback::pump()` are the settle-barrier hooks: a `wait_for_gpu_idle()` in the WM main
  loop should advance ticks (returning to the loop each iteration so `AllowSpontaneous` can
  fire) until `pending_count() == 0` or a bounded frame budget. **Needed context seam
  (report, not edited - `wgpu_context.cc` is r52's right now):** a per-tick call to
  `webgpu::readback::pump()` in `WGPUContext::activate()` (next to the existing
  `diag::poll_and_pump`) is a clean place to drive eviction, but it is **optional**:
  spontaneous completions latch on their own; `pump()` only trims stale settled records.
  The registry lives static in `wgpu_readback.cc` (an accepted L-A shape), so L-C needs no
  context-struct member.

## Residue

- Fill-late serves one-frame-stale bytes to unconverted sync callers of a *stable* source
  (transient render/offscreen textures are freed per-call, always first-call → interim → the
  caller PNG stays zero until L-C converts it). This is the design's accepted interim; the
  exactness guarantee comes from L-C's settle barrier.
- `consume_ticket` retains a bounded ticket→exact-payload map (`kMaxSettled`); a
  failed/orphaned kick never records a result, so a settle barrier must bound itself by
  frame budget, not by waiting on such a ticket forever (documented in the header). Each
  completed ticket holds the exact immutable payload produced by its own kick; a later
  refresh of the same source cannot change what an older ticket consumes.
- The static registry is single-device (the port's profile). A future multi-device native
  build would need per-device registries; native never populates it today.

## Evidence

`sandbox/gpu-r53-readback/`: `probe_readback_fill_late.mjs` (final rebuilt binary:
`read0`=0, then `read1`,`read2`=real, known-colour match 51/153/229/255),
`probe_lifetime_stress.mjs` (24 iterations, no OOB, 8 post-barrage heartbeats), and
`evidence/` (`.bin` dumps + `.png` + logs). Fresh final 0117/0125 bridge proof is under
`evidence/bridge_final/`: 2 kicks / 2 completions at 128x128, zero GPU errors, plus the
headed compositor PNG and CC0 sidecar.
