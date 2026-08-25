<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 WM-worker presentation preinit recovery — 2026-08-25

## Outcome

Commit `645e2da` fixes the shipping windowed boot failure introduced when presentation became a
mandatory pre-main transaction. `platform_web/shell/windowed.html` is the intended M4 windowed
native-app entry point for the `WITH_HEADLESS=OFF` browser product, so the driver's explicit
`/windowed.html` URL was correct. The `/` route in `scripts/serve-web.sh` still maps to the older
headless M4.pre `index.html`; it is not an equivalent windowed-product entry point.

The rebuilt product now advances to the `running`/`WM_main` state instead of rendering
`boot failed - see console`. This iteration does not claim first pixels or a hardware receipt.

## Root cause and fix

Emscripten includes the transferred canvas in the proxied-main `cmd:2` message, but publishes it
to `GL.offscreenCanvases` only inside its original message handler. The post-js wrapper intercepted
that same message and awaited presentation preflight before calling the original handler. Both
`GL.offscreenCanvases["canvas"]` and `specialHTMLTargets["#canvas"]` were therefore necessarily
empty at stage 1.

The worker now reads `d.offscreenCanvases[d.moduleCanvasId]` directly without prematurely mutating
Emscripten's registry. Its persistent backbuffer is completed under validation, out-of-memory, and
internal scopes before `OffscreenCanvas.configure()`. Surface configuration then requires an
initial texture, one uncaptured-error event-loop turn, and a still-active device before publishing
the complete status-5 bundle. This ordering also avoids Chromium's software adapter dropping its
raw external instance when an error-scope promise follows canvas configuration.

The first locked rebuild exposed a second defect: changing the string-valued `--post-js` source did
not dirty `blender_browser.js`. The CMake target now carries an explicit `LINK_DEPENDS` edge to the
worker source, so incremental product builds cannot silently ship stale preinit code.

## Evidence

- Fail-first real-order Node model: `20260825T065905-960524` rejects the predecessor because the
  canvas registries are empty before forwarding `cmd:2`.
- Final 11-case pinned worker contract: `20260825T072220-984670` passes canvas, surface,
  configuration, backbuffer, device-loss, cleanup, and single-entry cases.
- Exact implementation-commit worker source independently passes the same contract:
  `20260825T073121-993390`.
- Locked windowed relink: `20260825T072227-984702`; subsequent exact no-work check:
  `20260825T072440-988219`.
- Headed COOP/COEP product diagnostic: `20260825T072320-985189` reports
  `state=running device=1 presentation=1 stage1_failure=0 import_failure=0 ticks=1 device_lost=0`.
- Canonical native/Wasm integrated parity: `20260825T072340-985736`, 4,813 identical bytes,
  SHA-256 `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`.
- Final pinned REUSE 6.2.0: `20260825T072854-991636`, 2,495/2,495 files.
- Required M4 stays RED at the unchanged unsupported historical binding schema. Authoritative
  container-backed regression `20260825T072717-990292` restores M0 to 6/6 GREEN while M1-M8 keep
  their existing strict receipt, product, browser, run-label, hardware, and release boundaries.

The headed run used Chromium's software adapter only as a boot-regression diagnostic. It binds no
adapter, profile, split product, receipt, result promotion, or pixels. The named blocker remains
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn and
Windows Edge were not attempted, and WSL was not restarted.
