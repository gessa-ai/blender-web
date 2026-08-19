<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 trusted-canvas browser smoke

This additive evidence harness closes the browser-level portion of the M5
contract without changing Blender, the shipping shell, the event-simulate rig,
the native oracle, or any threshold/pass flag.

The existing tier-(c) rig uses Playwright for page orchestration but injects the
actual Blender inputs with `Window.event_simulate`. This harness exercises the
other seam: Playwright dismisses the shipping startup splash with trusted
`Escape`, then sends trusted `Tab`, `Alt+A`, and `A` keyboard events to the
shipping `platform_web/shell/windowed.html` canvas. A read-only
`bpy.app.timer` reports state transitions from the WM worker. The operator log
must contain, in order, the edit-toggle and select-all action sequence derived
at runtime from the unchanged native trace goldens.

It intentionally avoids click-picking. Click-picking remains the separate GPU
readback caller-conversion blocker and must not be hidden by browser-level smoke.

## Run

Serve the shipping shell and the intended binary in one terminal:

```sh
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
  /Users/paws/blender-web/scripts/serve-web.sh 8127
```

Then run the pure selfcheck and one evidence run:

```sh
node /Users/paws/blender-web/sandbox/m5-canvas-smoke/drive-canvas-smoke.mjs --selfcheck
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
  node /Users/paws/blender-web/sandbox/m5-canvas-smoke/drive-canvas-smoke.mjs \
    --port 8127 --run m5-canvas-smoke-r1
```

Run labels are immutable: the driver refuses to overwrite an existing evidence
directory. A successful directory contains the receipt, its SHA-256 companion,
the sanitized operator trace, WM-worker state markers, trusted DOM key records,
the request ledger, and a final screenshot.

The receipt binds exactly JS, primary Wasm, deferred Wasm, and data, plus the
non-shipping split manifest as provenance. Unexpected or missing shipping roles
in that manifest fail before the browser is launched.
