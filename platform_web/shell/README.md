<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# blender-web — M4.pre browser boot shell (local link)

Runs the wasm Blender build in a real Chrome tab, headless
(`--background --factory-startup`). This is the browser equivalent of the node boot
in `notes/m2-python-boot.md`. Design + verification: `notes/m4-browser-shell.md`.

## 1. Build the browser binary (once)

```sh
cd <repo-root>
cmake build-wasm -DWITH_BLENDER_WEB_BROWSER=ON
scripts/ninja-locked.sh -C build-wasm blender_browser
```

Produces `build-wasm/bin/blender_browser.{js,wasm,data}` (~0.6 MB / 112 MB / 93 MB).
The `.data` file is the preloaded runtime payload (CPython stdlib + Blender scripts +
datafiles); it is fetched once at page load.

## 2. Serve it (COOP/COEP required)

```sh
scripts/serve-web.sh            # http://localhost:8000/
scripts/serve-web.sh 8123       # or pick a port
```

The server sets `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` on every response — mandatory, because
threads ⇒ SharedArrayBuffer ⇒ cross-origin isolation. Opening the files with a plain
static server (or `file://`) will **not** work.

## 3. Open in Chrome / Edge

Navigate to the printed URL (e.g. `http://localhost:8123/`) in **current Chrome or
Edge**, then click **Boot Blender**. stdout/stderr stream to both the on-page log box
and the devtools console (F12). The status bar shows state / exit code / wall time.

To change the arguments, edit the single `ARGV` array at the top of `boot.js` (the
`--python-expr` there prints `BPY_OK <version> <#objects>` once Python boots).

## Expected output (parity with the node build)

Today this build stops at the **same known pre-Python abort** the node build hits
(the in-flight DNA reconstruct fix is not yet in it). Reaching this line **in the
tab** is the M4.pre success criterion — it proves the entire browser layer works:

```
Blender 5.2.0 LTS
BLI_assert failed: source/blender/blenkernel/intern/layer_utils.cc:205,
  BKE_view_layer_object_bases_get(), at '(view_layer->flag & VIEW_LAYER_OUT_OF_SYNC) == 0'
  Object Bases out of sync, invoke BKE_view_layer_synced_ensure.
Aborted()
```

The page state pill turns **aborted** and `onAbort` is logged — that is the expected
result for now.

You will also see one benign line before the banner (an OpenImageIO wasm stub, not an
error): `... sysutil.cpp:214: physical_memory: Assertion ... failed.` The boot
continues past it.

### When the DNA fix lands

Rebuild `blender_browser` and reload. The banner is then followed by:

```
BPY_OK 5.2.0 3
```

(`3` = objects in the factory startup scene: cube, camera, light), the state pill
turns **exited (0)**, and the exit code is `0`. No shell change is needed — the
browser layer is already proven end-to-end.

## Notes / limits

- Dev-grade eager preload (one big `.data`). Staged/lazy loading + stdlib
  tree-shaking + OPFS project store are M7 (`LAUNCH.md`) — see
  `notes/m4-browser-shell.md`.
- Headless (`--background`). No WebGPU canvas yet (that is M3/M4 proper); this shell
  proves boot + Python parity, not pixels.
- `blender_browser` is `EXCLUDE_FROM_ALL` and gated on `-DWITH_BLENDER_WEB_BROWSER=ON`,
  so it never affects the node / gtest iteration builds.
