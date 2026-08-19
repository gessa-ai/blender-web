<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 browser support and degraded modes

## Launch support

The launch target is current desktop Google Chrome and Microsoft Edge on hardware
with WebGPU enabled. Both must pass the same exact-artifact boot, first-pixels,
interaction, and zero-GPU-error smoke before the M8 technical receipt can turn green.
Chromium alone is useful development evidence but does not substitute for both branded
browser receipts.

The page must be served over HTTPS (localhost is allowed for development) with
`Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Embedder-Policy: require-corp`, and same-origin/CORP-eligible assets.
Without cross-origin isolation the pthread build cannot obtain SharedArrayBuffer and
must fail before boot with a clear capability error.

## Documented degraded modes

- File System Access API unavailable: open uses the ordinary file-input/drag-drop
  fallback and save uses a download. OPFS remains the local project store when the
  Storage API is available.
- Offline: only available after one complete stage-1 download and successful
  service-worker precache. The first visit requires a network. A cached reload must
  retain COOP/COEP isolation and reach the real WM_main.
- WebGPU unavailable, disabled, or adapter request denied: there is no WebGL renderer.
  Show an actionable unsupported-GPU/browser message; do not imply a working editor.
- Mobile/touch: not launch-supported. The product is desktop-first; touch, memory,
  viewport size, and mobile browser process limits are not covered by the launch gate.
- Firefox and Safari: not launch-supported until they separately pass the full
  WebGPU/pthreads/browser matrix. Do not infer support from standards availability.
- Scenes beyond the wasm32/Memory64 ceiling and declared subsystem deferrals remain
  visible in the conformance dashboard; a degraded browser must not silently corrupt
  or pretend to support them.

## Security boundary

Production static bundles must disable the development `?pyexpr=` and `?args=` query
hooks. They permit arbitrary Python/Blender argv execution and are valid only in local
verification shells. Capture-only `?gate=`, keepalive tuning, and `?stage1=manual`
are dev-only too, so shared public links cannot suppress rendering or deferred loading.
The shipped share route accepts exactly
`?scene=stress-mixed`: it maps through a closed JavaScript allowlist to one bundled
same-origin path, rejects redirects/unknown values without a request, and verifies the
581,494-byte payload's SHA-256 before opening it. It never treats query text as a URL,
path, argv, Python expression, or general operation name.
