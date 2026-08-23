<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST callback serialization R8 — 2026-08-23

## Outcome

Implementation commit `5652eff` closes the arbitrary-thread half of the GHOST callback-lifecycle
contract. Every completion that reaches the shared context now owns one reentrant serialized
delivery slot, so two `AllowSpontaneous` callbacks cannot concurrently mutate GHOST state.

## Diagnosis and implementation

The pinned WebGPU header explicitly permits `AllowSpontaneous` delivery on an arbitrary or
application thread (`build-dawn/dawn/third_party/webgpu-headers/src/webgpu.h:470`). The R8 lifetime
gate registered each delivery and made destruction wait, but released its mutex before invoking the
completion. Two valid callbacks could therefore overlap on non-atomic resize, pipeline, surface,
and present fields without either callback outliving its owner.

`OwnerCallbackLifetime` now holds a recursive delivery mutex across the complete owner callback.
Another thread waits before accessing or destroying that owner, while a nested callback and a
callback that destroys its own context can re-enter on the same thread. A separate state mutex
keeps `cancel()` non-waiting: terminal device loss rejects future deliveries without blocking one
already running.

## Evidence

- The fail-first concurrency contract holds the first delivery open and observes the unchanged gate
  admit a second delivery (`20260823T233315-3434873`).
- The final focused driver passes byte-identically on native and wasm32 with peak concurrent owner
  access exactly one, nested delivery, concurrent destruction, delayed-delivery rejection, imported
  loss, and the unsafe AddressSanitizer control (`20260823T233835-3440498`).
- The canonical integrated pipeline/GHOST driver remains byte-identical across native and wasm32:
  38 contracts, 4,813 bytes, SHA-256 `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`
  (`20260823T233422-3436161`).
- The real `blender_browser` target rebuilds and then reports exact locked Ninja no-work
  (`20260823T233519-3438043`, `20260823T233607-3438431`). OFF preflight binds the resulting
  657,928-byte JavaScript, 118,759,291-byte Wasm, and 167,143,248-byte data product
  (`20260823T233613-3438501`); canonical replay remains exact (`20260823T233627-3439451`).
- REUSE 6.2.0 is green before the documentation commit at 2,239/2,239
  (`20260823T233747-3440066`).
- Required M4 remains fail-closed at the unchanged browser-pixel binding
  (`20260823T233903-3441615`). Final container-backed regression restores M0 to 6/6 green while
  M1-M8 retain their existing strict-receipt, split-product, browser, run-label, hardware, and
  release boundaries (`20260823T233925-3442029`).

## Boundary

This is device-free callback concurrency, source-binding, native/wasm32, ASan, and product build
proof. It creates no accepted hardware adapter, browser surface/pixel receipt, profile, split
product, or milestone receipt. No result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or promise changed. dzn and the staged Windows path were not attempted, and WSL
was not restarted. Live pixels remain deferred by the named blocker: no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
