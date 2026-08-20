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

The repository root is derived from the driver. Playwright resolves from
`BW_NODE_MODULES`, each `NODE_PATH` entry, `.m4-node/node_modules`, then the
repository's `node_modules`, and must be the pinned 1.61.1 package. Evidence is
confined to one immutable child of a repository-local output root. `--selfcheck`
validates those contracts without opening a browser or reading a build product.

## Run

Run the browser/product-free self-check first, then export the documented local
browser roots and serve the shipping shell in one terminal:

```sh
node sandbox/m5-canvas-smoke/drive-canvas-smoke.mjs --selfcheck

export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers"
export BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin"

bash scripts/serve-web.sh 8127
```

Then run one evidence capture:

```sh
node sandbox/m5-canvas-smoke/drive-canvas-smoke.mjs \
  --port 8127 --run m5-canvas-smoke-r1
```

Run labels are immutable: the driver refuses to overwrite an existing evidence
directory. A successful directory contains the receipt, its SHA-256 companion,
the sanitized operator trace, WM-worker state markers, trusted DOM key records,
the request ledger, and a final screenshot.

The receipt binds exactly JS, primary Wasm, deferred Wasm, and data, plus the
non-shipping split manifest as provenance. Unexpected or missing shipping roles
in that manifest fail before the browser is launched.

A real receipt requires the s7-accepted hardware WebGPU adapter and an APPLY
split product. The self-check is the only supported invocation before that
gate; a software adapter binds no M5 evidence.
